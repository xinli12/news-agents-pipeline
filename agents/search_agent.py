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


def classify_search_results(
    topic: str, articles: list[dict], max_retries: int = 1
) -> dict:
    """Classifies topic type/complexity and every article's political bias in one Gemini call.

    This used to be two sequential API calls (topic characteristics, then a
    separate per-article bias batch) even though both read the same article
    data and don't depend on each other's output, so they're combined here
    into a single round trip. Transient API/network errors get one retry;
    anything else falls back to a neutral default immediately since retrying
    with an unchanged prompt is unlikely to fix it.
    """
    if not articles:
        return {"is_viewpoint_oriented": False, "complexity": "Simple", "article_bias": {}}

    import os
    import sys
    import time

    from google import genai

    from agents.web_tools import is_transient_error

    model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    articles_to_classify = [
        {
            "id": idx,
            "title": art.get("title", "N/A"),
            "source": art.get("source", "N/A"),
            "snippet": art.get("body", "N/A"),
        }
        for idx, art in enumerate(articles)
    ]

    prompt = (
        f"Analyze the search topic '{topic}' and the following news search results.\n\n"
        "Return a JSON object with exactly these keys:\n"
        "1. 'is_viewpoint_oriented' (boolean): true if the topic/articles cover political, public policy, "
        "legal, economic, or other topics with multiple conflicting or diverse viewpoints/interpretations; "
        "false if the topic is non-political or primarily factual (e.g., sports, science, weather, "
        "technology, or a single straightforward news event with little disagreement or analysis).\n"
        "2. 'complexity' (string, one of 'Simple', 'Moderate', 'High'):\n"
        "   - 'Simple': The search results primarily describe a single event with little disagreement or analysis.\n"
        "   - 'Moderate': The search results cover multiple aspects of the topic, such as different stakeholders, analyses, or developments.\n"
        "   - 'High': The search results reveal a complex, evolving, or controversial topic with multiple independent viewpoints.\n"
        "3. 'article_bias' (object): a flat dictionary mapping each article's 'id' (as a string) to its "
        "political/ideological bias classification, one of 'LEFT', 'RIGHT', 'CENTER', 'OTHER/NON-POLITICAL'.\n"
        "   - 'LEFT': The article primarily frames issues from a progressive perspective, emphasizing themes such as social justice, government intervention, labor rights, environmental protection, or critiques of corporate power.\n"
        "   - 'RIGHT': The article primarily frames issues from a conservative perspective, emphasizing themes such as free markets, limited government, or traditional values.\n"
        "   - 'CENTER': The article reports facts in a balanced, descriptive, and neutral manner without clearly advocating a particular political perspective.\n"
        "   - 'OTHER/NON-POLITICAL': The article is non-political (e.g., science, technology, sports, or entertainment), has no obvious political perspective, or presents a viewpoint that does not fit the other categories.\n\n"
        "Do not include any formatting or explanation outside the JSON.\n\n"
        f"Articles:\n{json.dumps(articles_to_classify, indent=2)}"
    )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            client = genai.Client()
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            result = json.loads(response.text)

            is_viewpoint = bool(result.get("is_viewpoint_oriented", False))
            complexity = str(result.get("complexity", "Moderate"))
            if complexity not in ("Simple", "Moderate", "High"):
                complexity = "Moderate"

            url_bias_map = {}
            for key, value in (result.get("article_bias") or {}).items():
                try:
                    idx = int(key)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(articles):
                    url = articles[idx].get("url")
                    if url:
                        url_bias_map[url] = str(value).upper()

            return {
                "is_viewpoint_oriented": is_viewpoint,
                "complexity": complexity,
                "article_bias": url_bias_map,
            }
        except Exception as e:
            last_error = e
            if attempt > max_retries or not is_transient_error(e):
                break
            backoff = 2**attempt
            print(
                f"Warning: Search result classification hit a transient error "
                f"(attempt {attempt}/{max_retries + 1}): {e!s}. Retrying in {backoff}s...",
                file=sys.stderr,
            )
            time.sleep(backoff)

    print(
        f"Warning: Search result classification failed ({last_error!s}). "
        "Falling back to default classification.",
        file=sys.stderr,
    )
    return {"is_viewpoint_oriented": False, "complexity": "Moderate", "article_bias": {}}


def get_live_news_articles(topic: str) -> str:
    """Searches the web for live news articles on a given topic and scrapes full texts in parallel.

    Args:
        topic: The news topic or search query, e.g. 'Federal Reserve interest rate hike'.
    """
    import sys

    RAW_FETCH_TARGET = 55
    THIN_PAGE_THRESHOLD = 20

    try:
        with DDGS() as ddgs:
            results: list[dict] = []

            # Fetch page 1 of news results. A second page is only pulled if page 1
            # came back thin, since dedupe_candidate_pool collapses wire/reprint
            # clusters below and a small raw pool often can't survive that intact.
            try:
                news_results = list(ddgs.news(topic, max_results=RAW_FETCH_TARGET))
            except Exception as news_err:
                print(
                    f"Warning: ddgs.news search failed ({news_err!s}).",
                    file=sys.stderr,
                )
                news_results = []
            results.extend(news_results)

            if len(news_results) < THIN_PAGE_THRESHOLD:
                try:
                    results.extend(
                        ddgs.news(topic, max_results=RAW_FETCH_TARGET, page=2)
                    )
                except Exception as news_err2:
                    print(
                        f"Warning: ddgs.news page 2 search failed ({news_err2!s}).",
                        file=sys.stderr,
                    )

            # Always widen with general text search too, instead of only falling
            # back to it when ddgs.news raises -- a news call that succeeds but
            # returns few results previously never got supplemented.
            try:
                text_results = list(ddgs.text(topic, max_results=RAW_FETCH_TARGET))
            except Exception as text_err:
                print(
                    f"Warning: ddgs.text search failed ({text_err!s}).",
                    file=sys.stderr,
                )
                text_results = []

            for r in text_results:
                url = r.get("href", "") or r.get("url", "")
                domain = get_domain(url)
                # Extract a simple source name from domain (e.g. cnn.com -> Cnn)
                source_name = (
                    domain.split(".")[0].capitalize() if domain else "Web Search"
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

            # Classify topic type/complexity and every article's bias in one call
            classification = classify_search_results(topic, results)
            is_viewpoint = classification["is_viewpoint_oriented"]
            complexity = classification["complexity"]
            articles_bias_map = classification["article_bias"]

            # Determine maximum articles to scrape based on complexity
            if complexity == "Simple":
                max_to_scrape = 8
            elif complexity == "Moderate":
                max_to_scrape = 15
            else:
                max_to_scrape = 24

            # Categorize the search results by their article-level bias dynamically
            lefts = []
            rights = []
            centers = []
            others = []

            for r in results:
                url = r.get("url", "")
                bias = articles_bias_map.get(url, "OTHER/NON-POLITICAL")

                if bias == "LEFT":
                    lefts.append(r)
                elif bias == "RIGHT":
                    rights.append(r)
                elif bias == "CENTER":
                    centers.append(r)
                else:
                    others.append(r)

            # Select candidates based on selection logic
            selected_results = []
            if is_viewpoint:
                # Use round-robin balanced selection
                bucket_counts = {
                    "LEFT": len(lefts),
                    "RIGHT": len(rights),
                    "CENTER": len(centers),
                    "OTHER/NON-POLITICAL": len(others),
                }
                queues = [lefts, rights, centers, others]

                while len(selected_results) < max_to_scrape:
                    added = False
                    for q in queues:
                        if q:
                            selected_results.append(q.pop(0))
                            added = True
                            if len(selected_results) >= max_to_scrape:
                                break
                    if not added:
                        break
            else:
                # Prioritize relevance and source quality (bubble wire services first, keeping search relevance rank)
                sorted_by_quality = sorted(
                    enumerate(results),
                    key=lambda x: (0 if x[1].get("wire_service") else 1, x[0])
                )
                selected_results = [r for _, r in sorted_by_quality[:max_to_scrape]]
                bucket_counts = {
                    "LEFT": sum(1 for r in selected_results if articles_bias_map.get(r.get("url", ""), "") == "LEFT"),
                    "RIGHT": sum(1 for r in selected_results if articles_bias_map.get(r.get("url", ""), "") == "RIGHT"),
                    "CENTER": sum(1 for r in selected_results if articles_bias_map.get(r.get("url", ""), "") == "CENTER"),
                    "OTHER/NON-POLITICAL": sum(1 for r in selected_results if articles_bias_map.get(r.get("url", ""), "") not in ["LEFT", "RIGHT", "CENTER"]),
                }

            # Scrape all selected articles in parallel
            urls = [r.get("url") for r in selected_results if r.get("url")]
            scraped_contents = {}
            if urls:
                from agents.web_tools import scrape_articles_parallel

                scraped_contents = scrape_articles_parallel(urls)

            status_str = "Moderate" if len(results) < 6 else "Good"
            output = [
                f"SEARCH_STATUS: {status_str}",
                f"QUERY: {topic}",
                f"RAW_CANDIDATES: {raw_count}",
                f"UNIQUE_CANDIDATES_AFTER_DEDUP: {len(results)}",
                f"SELECTED_ARTICLES: {len(selected_results)}",
                f"SOURCE_BALANCE: "
                f"LEFT={bucket_counts['LEFT']}, RIGHT={bucket_counts['RIGHT']}, "
                f"CENTER={bucket_counts['CENTER']}, OTHER/NON-POLITICAL={bucket_counts['OTHER/NON-POLITICAL']}",
                f"TOPIC_COMPLEXITY: {complexity}",
                f"TOPIC_TYPE: {'viewpoint-oriented' if is_viewpoint else 'factual-oriented'}",
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
                    f"Prior Bias Signal: {articles_bias_map.get(url, 'UNKNOWN')}\n"
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
            f"CRITICAL: Do not flag search results as fictional, hypothetical, or speculative solely because they describe events that occurred after your training data cutoff. If multiple credible, independent sources report an event as real news, treat it as authentic rather than as a hypothetical scenario.\n"
            f"CRITICAL: The number of articles you select and include in the 'articles' list MUST depend on the diversity and complexity of the search results "
            f"(or as many as possible if search results are limited), based on the 'TOPIC_COMPLEXITY' returned by the tool:\n"
            f"- 'Simple' (primarily describes a single event with little disagreement or analysis): Select 4 to 7 articles.\n"
            f"- 'Moderate' (covers multiple aspects of the topic, such as different stakeholders, analyses, or developments): Select 8 to 12 articles.\n"
            f"- 'High' (reveals a complex, evolving, or controversial topic with multiple independent viewpoints): Select 12 to 18 articles.\n"
            f"If the tool returns fewer unique articles than the target range, select as many available articles as possible.\n"
            f"CRITICAL: You must follow the selection logic and method based on 'TOPIC_TYPE' returned by the tool:\n"
            f"- If the TOPIC_TYPE is 'viewpoint-oriented' (covering political, public policy, legal, economic, or other topics with multiple viewpoints): "
            f"Use the round-robin balanced selection provided in the search results for a balanced representation of Left, Right, and Center perspectives when such perspectives are available.\n"
            f"- If the TOPIC_TYPE is 'factual-oriented' (covering topics that are non-political or primarily factual, e.g., sports, science, weather, or a single news event): "
            f"Prioritize relevance and source quality over viewpoint balance (i.e. select the articles in the order of relevance and source quality as returned by the tool).\n"
            f"CRITICAL: You MUST search articles only from reliable news sources, such as mainstream wires (e.g., Reuters, AP, AFP), "
            f"large mainstream outlets (e.g., BBC, NYT, WSJ News, CNN, Fox News), or reputable niche/partisan/independent outlets (e.g., Reason, Democracy Now, ProPublica). "
            f"You MUST exclude unreliable sources, such as hyper-partisan blogs, anonymous publishers, conspiracy-focused sites, etc.\n"
            f"Do not treat the same wire-service story or likely reprint cluster as independent corroboration. "
            f"Preserve duplicate_cluster and selection_rationale for each article when available.\n"
            f"For each article, you MUST determine:\n"
            f"- bias_category: Each article comes with a 'Prior Bias Signal' computed from its title/source/search "
            f"snippet before you saw the full scraped text. Treat it as a strong prior and use it as your answer "
            f"by default. Only override it if the full scraped Content Snippet clearly contradicts it (you have "
            f"more information than that prior signal did) -- do not silently re-derive a different answer from "
            f"scratch without a concrete reason from the article text. Classify based on the article's actual tone, "
            f"framing, and content, NOT by publisher name alone. "
            f"Use 'Left' if the article primarily frames issues from a progressive perspective, emphasizing themes such as social justice, government intervention, labor rights, environmental protection, or critiques of corporate power; "
            f"'Right' if the article primarily frames issues from a conservative perspective, emphasizing themes such as free markets, limited government, or traditional values; "
            f"'Center' if the article reports facts in a balanced, descriptive, and neutral manner without clearly advocating a particular political perspective; "
            f"or 'Other/Non-Political' if the article is non-political (e.g., science, technology, sports, or entertainment), has no obvious political perspective, or presents a viewpoint that does not fit the other categories.\n"
            f"- neutrality: Classify the neutral/factual tone of the whole article into one of the following three classes:\n"
            f"  * HIGH_NEUTRALITY: Calm, descriptive, specific, and fact-based. Avoids emotional wording, blame-heavy framing, opinionated claims, and dramatic emphasis.\n"
            f"  * MEDIUM_NEUTRALITY: Mostly factual but contains mild interpretation, emphasis, or framing. May highlight conflict, consequences, winners or losers, or criticism, but avoids strongly emotional or sensational language.\n"
            f"  * LOW_NEUTRALITY: Clearly opinionated, promotional, accusatory, sensational, alarmist, mocking, or emotionally charged. Pushes a conclusion more than it reports facts.\n"
            f"  Do not classify an article as less neutral simply because the topic is political, controversial, or negative.\n"
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
