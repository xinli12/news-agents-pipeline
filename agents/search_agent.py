import json
import re
import urllib.parse

from ddgs import DDGS
from google.adk.agents import Agent
from google.genai import types

from agents.schemas import ArticleList

WIRE_SOURCE_NAMES = {
    "reuters": "Reuters",
    "ap": "Associated Press",
    "associated press": "Associated Press",
    "apnews": "Associated Press",
    "afp": "AFP",
    "agence france-presse": "AFP",
}


def get_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            return netloc[4:]
        return netloc
    except Exception:
        return ""


def normalize_title(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    words = [word for word in normalized.split() if len(word) > 2]
    return " ".join(words[:16])


def detect_wire_service(article: dict) -> str | None:
    source = str(article.get("source", "")).lower()
    title = str(article.get("title", "")).lower()
    body = str(article.get("body", "")).lower()
    combined = f"{source} {title} {body}"
    for marker, label in WIRE_SOURCE_NAMES.items():
        if marker in combined:
            return label
    return None


def dedupe_candidate_pool(results: list[dict]) -> tuple[list[dict], list[str]]:
    """Remove exact duplicates and collapse likely wire/reprint clusters."""
    selected = []
    seen_urls = set()
    seen_story_keys = set()
    wire_groups = []

    for result in results:
        url = result.get("url") or result.get("href") or ""
        if not url or url in seen_urls:
            continue

        title_key = normalize_title(result.get("title", ""))
        domain = get_domain(url)
        wire_service = detect_wire_service(result)
        story_key = f"{wire_service or domain}:{title_key}"

        if story_key in seen_story_keys:
            continue

        seen_urls.add(url)
        seen_story_keys.add(story_key)

        enriched = dict(result)
        enriched["domain"] = domain
        enriched["wire_service"] = wire_service
        enriched["duplicate_cluster"] = story_key
        selected.append(enriched)

        if wire_service:
            wire_groups.append(f"{wire_service}: {title_key[:90]}")

    return selected, sorted(set(wire_groups))


def classify_articles_bias_batch(articles: list[dict]) -> dict[str, str]:
    """Classifies the political bias of each article based on its title, source, and snippet using a batch Gemini call."""
    if not articles:
        return {}
    try:
        import os

        from google import genai

        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
        client = genai.Client()

        # Prepare the list of articles for classification
        articles_to_classify = []
        for idx, art in enumerate(articles):
            articles_to_classify.append(
                {
                    "id": idx,
                    "title": art.get("title", "N/A"),
                    "source": art.get("source", "N/A"),
                    "snippet": art.get("body", "N/A"),
                }
            )

        prompt = (
            "Analyze the following list of news articles (including their title, source, and search snippet) "
            "and classify the political/ideological bias of each article as 'LEFT', 'RIGHT', 'CENTER', or 'OTHER'.\n"
            "Classification guidelines:\n"
            "- 'LEFT': Left-leaning framing, focusing heavily on progressive arguments, social justice, government regulation/safety nets, or critiques of corporate power.\n"
            "- 'RIGHT': Right-leaning framing, focusing heavily on conservative arguments, market-driven solutions, tax cuts, individual liberties, critiques of government regulation/spending, or national security.\n"
            "- 'CENTER': Factual, objective reporting with balanced arguments, descriptive tone, and no obvious ideological bias (e.g. wire reports like Reuters/AP, straightforward informative coverage).\n"
            "- 'OTHER': Use for articles that are non-political (e.g. sports, technology, science, lifestyle, recipes, entertainment) or cannot be classified.\n\n"
            "Respond strictly in JSON format as a flat dictionary mapping each article's 'id' (as a string) to its bias category.\n"
            "Do not include any formatting or explanation outside the JSON.\n\n"
            f"Articles:\n{json.dumps(articles_to_classify, indent=2)}"
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
            },
        )

        result = json.loads(response.text)

        # Map back from ID to URL
        url_bias_map = {}
        for k, v in result.items():
            try:
                idx = int(k)
                if 0 <= idx < len(articles):
                    url = articles[idx].get("url")
                    if url:
                        url_bias_map[url] = v.upper()
            except ValueError:
                continue
        return url_bias_map
    except Exception as e:
        import sys

        print(
            f"Warning: Batch article classification failed: {e!s}. Falling back to default center/other classification.",
            file=sys.stderr,
        )
        return {}


def get_live_news_articles(topic: str) -> str:
    """Searches the web for live news articles on a given topic and scrapes full texts in parallel.

    Args:
        topic: The news topic or search query, e.g. 'Federal Reserve interest rate hike'.
    """
    try:
        with DDGS() as ddgs:
            # Fetch up to 40 articles to ensure we have a diverse pool to choose from
            try:
                results = list(ddgs.news(topic, max_results=40))
            except Exception as news_err:
                # Fallback to general text search if news search is rate-limited/blocked
                import sys

                print(
                    f"Warning: ddgs.news search failed ({news_err!s}). Falling back to ddgs.text search...",
                    file=sys.stderr,
                )
                try:
                    text_results = list(ddgs.text(topic, max_results=40))
                    results = []
                    for r in text_results:
                        url = r.get("href", "")
                        domain = get_domain(url)
                        # Extract a simple source name from domain (e.g. cnn.com -> Cnn)
                        source_name = (
                            domain.split(".")[0].capitalize()
                            if domain
                            else "Web Search"
                        )
                        results.append(
                            {
                                "title": r.get("title", "N/A"),
                                "url": url,
                                "source": source_name,
                                "date": "N/A",
                                "body": r.get("body", "N/A"),
                            }
                        )
                except Exception as text_err:
                    return (
                        f"Error executing DuckDuckGo news and text search: {text_err!s}"
                    )

            if not results:
                return (
                    "SEARCH_STATUS: no_results\n"
                    f"QUERY: {topic}\n"
                    "No credible news articles were found for this query."
                )

            raw_count = len(results)
            results, wire_groups = dedupe_candidate_pool(results)

            if len(results) < 3:
                return (
                    "SEARCH_STATUS: Low\n"
                    f"QUERY: {topic}\n"
                    f"RAW_CANDIDATES: {raw_count}\n"
                    f"UNIQUE_CANDIDATES: {len(results)}\n"
                    "The search produced too few distinct news sources to support a multi-source analysis."
                )

            # Categorize the search results by their article-level bias dynamically
            lefts = []
            rights = []
            centers = []
            others = []

            # Classify all articles in batch based on their content (title, source, snippet)
            articles_bias_map = classify_articles_bias_batch(results)

            for r in results:
                url = r.get("url", "")
                bias = articles_bias_map.get(url, "OTHER")

                if bias == "LEFT":
                    lefts.append(r)
                elif bias == "RIGHT":
                    rights.append(r)
                elif bias == "CENTER":
                    centers.append(r)
                else:
                    others.append(r)

            # Select up to 20 articles in a balanced round-robin way
            selected_results = []
            max_articles = 20
            bucket_counts = {
                "LEFT": len(lefts),
                "RIGHT": len(rights),
                "CENTER": len(centers),
                "OTHER": len(others),
            }
            queues = [lefts, rights, centers, others]

            while len(selected_results) < max_articles:
                added = False
                for q in queues:
                    if q:
                        selected_results.append(q.pop(0))
                        added = True
                        if len(selected_results) >= max_articles:
                            break
                if not added:
                    break

            # Scrape all selected articles in parallel
            urls = [r.get("url") for r in selected_results if r.get("url")]
            scraped_contents = {}
            if urls:
                from agents.scraper import scrape_articles_parallel

                scraped_contents = scrape_articles_parallel(urls)

            status_str = "Moderate" if len(results) < 6 else "Good"
            output = [
                f"SEARCH_STATUS: {status_str}",
                f"QUERY: {topic}",
                f"RAW_CANDIDATES: {raw_count}",
                f"UNIQUE_CANDIDATES_AFTER_DEDUP: {len(results)}",
                f"SELECTED_ARTICLES: {len(selected_results)}",
                "SOURCE_BALANCE: "
                f"LEFT={bucket_counts['LEFT']}, RIGHT={bucket_counts['RIGHT']}, "
                f"CENTER={bucket_counts['CENTER']}, OTHER={bucket_counts['OTHER']}",
                "WIRE_GROUPS: "
                + ("; ".join(wire_groups[:8]) if wire_groups else "None detected"),
                "---",
            ]
            for idx, r in enumerate(selected_results, start=1):
                url = r.get("url", "N/A")
                # If we successfully scraped the full content, use it. Otherwise, fallback to the search snippet.
                scraped_text = scraped_contents.get(url, "")
                if scraped_text and not scraped_text.startswith(
                    ("HTTP Error", "URL Error", "Scraping error", "Invalid URL")
                ):
                    snippet = scraped_text
                else:
                    snippet = r.get("body", "N/A")

                output.append(
                    f"Article #{idx}\n"
                    f"Title: {r.get('title', 'N/A')}\n"
                    f"Source: {r.get('source', 'N/A')}\n"
                    f"URL: {url}\n"
                    f"Date: {r.get('date', 'N/A')}\n"
                    f"Outlet Group: {r.get('domain', '')}\n"
                    f"Wire Service: {r.get('wire_service') or 'None'}\n"
                    f"Duplicate Cluster: {r.get('duplicate_cluster', '')}\n"
                    f"Content Snippet: {snippet}\n"
                    "---"
                )
            return "\n".join(output)
    except Exception as e:
        return f"Error executing DuckDuckGo search: {e!s}"


def get_search_agent(model_name: str | None = None) -> Agent:
    if model_name is None:
        import os

        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    tools = [get_live_news_articles]
    tool_name = "get_live_news_articles"

    return Agent(
        name="search_agent",
        model=model_name,
        instruction=(
            f"You are a News Categorizer Agent. Your job is to take a news topic, search for articles "
            f"using your '{tool_name}' tool, and categorize the articles according to the ArticleList schema.\n"
            f"First, perform an initial authenticity screen from the search output. If the tool returns "
            f"SEARCH_STATUS no_results or Low, set search_status accordingly, explain "
            f"the issue in verification_summary, keep articles empty, and do not invent sources. If the tool "
            f"returns Moderate or Good, set search_status to the corresponding returned "
            f"value. If the query "
            f"appears to contain an obvious name/date/event error but results strongly indicate a correction, "
            f"set corrected_query and explain the correction in warnings. "
            f"CRITICAL: Search engine date metadata (the 'Date' field) can sometimes be incorrect or represent early drafts/previews. "
            f"Always verify dates, timelines, and match/event results from the actual article text and content snippets, "
            f"and cross-reference multiple sources if dates differ.\n"
            f"CRITICAL: You MUST process and include at least 12 to 15 articles in the 'articles' list in your response. "
            f"Do NOT limit your output to only a few (2-4) articles. Process as many articles from the search results as possible (at least 12, up to 18), "
            f"ensuring a balanced representation across different viewpoints (Left, Right, Center, and Independent).\n"
            f"CRITICAL: You MUST select articles only from reliable news sources, such as mainstream wires (e.g., Reuters, AP, AFP), "
            f"large mainstream outlets (e.g., BBC, NYT, WSJ News, CNN, Fox News), or reputable niche/partisan/independent outlets (e.g., Reason, Democracy Now, ProPublica). "
            f"You MUST exclude unreliable sources, such as hyper-partisan blogs, anonymous publishers, conspiracy-focused sites, etc.\n"
            f"Do not treat the same wire-service story or likely reprint cluster as independent corroboration. "
            f"Preserve duplicate_cluster and selection_rationale for each article when available.\n"
            f"For each article, you MUST determine:\n"
            f"- bias_category: Classify based on the article's actual tone, framing, and content — NOT by publisher name alone. "
            f"Use 'Left' if the article emphasizes progressive arguments, social justice, or government intervention; "
            f"'Right' if it emphasizes conservative arguments, free-market solutions, or critiques of regulation; "
            f"'Center' if the reporting is factual, balanced, and uses a neutral descriptive tone; "
            f"'Independent' if it presents a non-mainstream or contrarian viewpoint (e.g., libertarian, grassroots, or investigative); "
            f"or 'Other/Non-Political' if the article is about science, technology, sports, lifestyle, or has no obvious political/ideological bias.\n"
            f"- objectivity_score: Analyze the neutral/factual tone of the title and snippet (0.0 to 1.0):\n"
            f"  * Calm, descriptive, direct (no loaded words) = 0.85 to 0.95.\n"
            f"  * Slightly framed or opinion-edged = 0.60 to 0.80.\n"
            f"  * Sensationalized, emotional, or alarmist (words like 'stifling', 'choking', 'regulatory overreach', 'threatens democracy') = 0.30 to 0.50.\n"
            f"- full_content_snippet: Extract the most informative, fact-dense section or paragraph of the article "
            f"describing key arguments, statistics, or events. Keep this snippet between 250 and 400 characters to save output tokens.\n"
            f"Finally, write a brief 2-3 sentence summary of the article's core claim.\n"
            f"You must use the '{tool_name}' tool to get the articles first."
        ),
        tools=tools,
        output_schema=ArticleList,
        output_key="articles_data",
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1,
        ),
    )
