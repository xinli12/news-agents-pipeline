"""Shared network-access tool functions used by multiple agents.

Scraping and web search were each reimplemented ad hoc wherever an agent
needed them. This module is the single home for those primitives so agents
share one implementation instead of drifting apart.
"""

import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from ddgs import DDGS
from google.genai import errors as genai_errors

from agents.evidence_verifier import register_article_full_text

_SCRAPE_ERROR_PREFIXES = ("HTTP Error", "URL Error", "Scraping error", "Invalid URL")


def is_transient_error(error: Exception) -> bool:
    """True for API/network hiccups worth a blind backoff-and-retry.

    Everything else (schema/validation failures, parsing errors, etc.) is
    likely to reproduce under the exact same prompt, so those are better
    retried immediately with the failure fed back into the prompt/fallback
    logic instead of waiting on a fixed backoff that won't change the outcome.
    """
    if isinstance(error, genai_errors.ServerError):
        return True
    if isinstance(error, genai_errors.ClientError):
        return getattr(error, "code", None) == 429
    return isinstance(error, (TimeoutError, ConnectionError, OSError))


def extract_retry_delay_seconds(error: Exception) -> float | None:
    """Read Google's suggested wait time out of a 429 error's RetryInfo detail.

    Per-minute quota errors (e.g. low-tier models like Gemma) report exactly
    how long until the quota window resets. A blind exponential backoff is
    usually much shorter than that window, so retries just burn through
    max_retries without ever landing after the reset; honoring the server's
    own delay makes the retry actually useful.
    """
    details = getattr(error, "details", None)
    if not isinstance(details, dict):
        return None
    error_details = details.get("error", {}).get("details", [])
    if not isinstance(error_details, list):
        return None
    for item in error_details:
        if not isinstance(item, dict):
            continue
        if str(item.get("@type", "")).endswith("RetryInfo"):
            retry_delay = item.get("retryDelay")
            if isinstance(retry_delay, str) and retry_delay.endswith("s"):
                try:
                    return float(retry_delay[:-1])
                except ValueError:
                    return None
    return None


def scrape_article_text(url: str, timeout: int = 10) -> str:
    """Fetches the HTML of the URL and extracts clean paragraph text.

    Args:
        url: The web page URL to scrape.
        timeout: Request timeout in seconds.

    Returns:
        A string of extracted text, capped at 6000 characters, or an error/empty message.
    """
    if not url or not url.startswith("http"):
        return "Invalid URL."

    # Try Jina Reader first for robust scraping and bypass blocks
    try:
        jina_url = f"https://r.jina.ai/{url}"
        jina_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        }
        req = urllib.request.Request(jina_url, headers=jina_headers)
        with urllib.request.urlopen(req, timeout=3) as response:
            content = response.read().decode("utf-8")
            if content and len(content.strip()) > 200:
                return content[:6000]
    except Exception:
        # Fall back to local BS4 scraper on failure or rate-limit
        pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            html = response.read()

            # Parse using BeautifulSoup and lxml parser
            soup = BeautifulSoup(html, "lxml")

            # Decompose unwanted elements
            for element in soup(
                [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "aside",
                    "form",
                    "iframe",
                ]
            ):
                element.decompose()

            # Extract paragraphs
            paragraphs = soup.find_all("p")
            paragraph_text = " ".join([p.get_text() for p in paragraphs])

            # Clean up whitespace
            cleaned_text = " ".join(paragraph_text.split())

            # If text is too short, try fallback on body text
            if len(cleaned_text) < 200:
                body_text = soup.get_text()
                cleaned_text = " ".join(body_text.split())

            # Cap the response to prevent context window bloat (6000 characters is ~1000-1500 words)
            return cleaned_text[:6000]

    except urllib.error.HTTPError as e:
        return f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"URL Error: {e.reason}"
    except Exception as e:
        return f"Scraping error: {e!s}"


def scrape_articles_parallel(urls: list[str], max_workers: int = 15) -> dict[str, str]:
    """Scrapes a list of article URLs in parallel using a ThreadPoolExecutor.

    Args:
        urls: List of URLs to fetch.
        max_workers: Number of threads to run in parallel.

    Returns:
        A dictionary mapping each URL to its extracted text content.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_url = {executor.submit(scrape_article_text, url): url for url in urls}

        # Collect results
        for future in future_to_url:
            url = future_to_url[future]
            try:
                content = future.result()
                results[url] = content
                if content and not content.startswith(_SCRAPE_ERROR_PREFIXES):
                    # Make the full text available to the evidence verifier so quotes
                    # can be checked against more than the short snippet.
                    register_article_full_text(url, content)
            except Exception as e:
                results[url] = f"Error in threading execution: {e!s}"

    return results


def search_authoritative_data(query: str) -> str:
    """Searches the web for authoritative academic papers, official regulatory standards, economic data, or industry guidelines.

    Args:
        query: The search query, e.g., 'CPI inflation rate US 2024' or 'FDA pharmaceutical trial regulations'.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return f"No authoritative sources found for query: {query}"
            output = []
            for r in results:
                title = r.get("title", "N/A")
                url = r.get("href", "") or r.get("url", "")
                body = r.get("body", "N/A")
                output.append(f"Title: {title}\nURL: {url}\nSnippet: {body}\n---")
            return "\n".join(output)
    except Exception as e:
        return f"Error executing DuckDuckGo search: {e!s}"
