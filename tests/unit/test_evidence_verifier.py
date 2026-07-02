from agents.evidence_verifier import (
    register_article_full_text,
    verify_analysis_evidence,
)


def _articles_data() -> dict:
    return {
        "articles": [
            {
                "title": "Agency announces new policy review",
                "url": "https://example.com/policy-review",
                "source": "Example News",
                "published_date": "2026-06-21",
                "bias_category": "Center",
                "summary": "The agency announced a new policy review after public comment.",
                "full_content_snippet": (
                    "The agency announced a new policy review after public comment "
                    "and said implementation would depend on the consultation record."
                ),
                "outlet_group": "example.com",
            },
            {
                "title": "Lawmakers respond to policy review",
                "url": "https://second.example.org/lawmakers-policy",
                "source": "Second Wire",
                "published_date": "2026-06-22",
                "bias_category": "Right",
                "summary": "Lawmakers said the policy review would remain open through July.",
                "full_content_snippet": (
                    "Lawmakers said the policy review would remain open through July "
                    "while agencies collected comments from affected companies."
                ),
                "outlet_group": "second.example.org",
            },
        ]
    }


def test_evidence_verifier_accepts_valid_fact_and_timeline() -> None:
    facts = {
        "consensus_facts": [
            {
                "claim": "The policy is under public review.",
                "supporting_sources": ["Example News", "Second Wire"],
                "explanation": "Multiple independent sources corroborated the policy review announcement.",
                "evidence": [
                    {
                        "source": "Example News",
                        "title": "Agency announces new policy review",
                        "url": "https://example.com/policy-review",
                        "published_date": "2026-06-21",
                        "bias_category": "Center",
                        "quote": "announced a new policy review after public comment and said implementation would depend",
                    },
                    {
                        "source": "Second Wire",
                        "title": "Lawmakers respond to policy review",
                        "url": "https://second.example.org/lawmakers-policy",
                        "published_date": "2026-06-22",
                        "bias_category": "Right",
                        "quote": "policy review would remain open through July while agencies collected comments",
                    },
                ],
            }
        ],
        "timeline": [
            {
                "date": "2026-06-21",
                "event": "The agency announced the review.",
                "evidence": [
                    {
                        "source": "Example News",
                        "title": "Agency announces new policy review",
                        "url": "https://example.com/policy-review",
                        "published_date": "2026-06-21",
                        "bias_category": "Center",
                        "quote": "The agency announced a new policy review after public comment",
                    }
                ],
            }
        ],
    }

    report = verify_analysis_evidence(_articles_data(), facts_data=facts)

    assert report["passed"] is True
    assert report["error_count"] == 0


def test_evidence_verifier_rejects_unknown_url_and_bad_quote() -> None:
    facts = {
        "consensus_facts": [
            {
                "claim": "Unsupported claim.",
                "supporting_sources": ["Example News"],
                "explanation": "Test explanation",
                "evidence": [
                    {
                        "source": "Example News",
                        "title": "Agency announces new policy review",
                        "url": "https://not-in-search.example/bad",
                        "published_date": "2026-06-21",
                        "bias_category": "Center",
                        "quote": "This sentence never appeared in the searched article set.",
                    },
                    {
                        "source": "Second Wire",
                        "title": "Lawmakers respond to policy review",
                        "url": "https://second.example.org/lawmakers-policy",
                        "published_date": "2026-06-22",
                        "bias_category": "Right",
                        "quote": "This sentence also does not match the source article content.",
                    },
                ],
            }
        ]
    }

    report = verify_analysis_evidence(_articles_data(), facts_data=facts)

    assert report["passed"] is False
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert "not present in the searched article set" in messages
    assert "does not match the cited article snippet" in messages


def test_quote_verifies_against_registered_full_text() -> None:
    register_article_full_text(
        "https://example.com/policy-review",
        "Deep inside the article the agency chair said the timeline for adoption "
        "remains flexible and subject to further consultation with stakeholders.",
    )
    facts = {
        "consensus_facts": [
            {
                "claim": "The adoption timeline is flexible.",
                "supporting_sources": ["Example News", "Second Wire"],
                "explanation": "Test explanation",
                "evidence": [
                    {
                        "source": "Example News",
                        "url": "https://example.com/policy-review",
                        "published_date": "2026-06-21",
                        "bias_category": "Center",
                        "quote": "the timeline for adoption remains flexible and subject to further consultation",
                    },
                    {
                        "source": "Second Wire",
                        "url": "https://second.example.org/lawmakers-policy",
                        "published_date": "2026-06-22",
                        "bias_category": "Right",
                        "quote": "policy review would remain open through July while agencies collected comments",
                    },
                ],
            }
        ]
    }

    report = verify_analysis_evidence(_articles_data(), facts_data=facts)

    assert report["passed"] is True





def test_public_report_takeaways_require_verifiable_evidence() -> None:
    report_data = {
        "title": "Policy review briefing",
        "key_takeaways": [
            {"point": "The review is open.", "evidence": []},
            {
                "point": "Comments continue through July.",
                "evidence": [
                    {
                        "source": "Second Wire",
                        "url": "https://second.example.org/lawmakers-policy",
                        "quote": "policy review would remain open through July while agencies collected comments",
                    }
                ],
            },
        ],
    }

    report = verify_analysis_evidence(_articles_data(), report_data=report_data)

    assert report["passed"] is False
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert "Key takeaway has no evidence trail" in messages


def test_expert_citations_checked_for_hyperlinks() -> None:
    experts = {
        "expert_opinions": [
            {
                "expert_name": "Macroeconomic Policy Analyst",
                "cited_references": ["Completely fabricated statute 99-Z"],
                "recommended_reading_or_context": ["[Valid Reading](https://example.com/report)"],
                "supporting_evidence": [
                    {
                        "source": "Example News",
                        "url": "https://example.com/policy-review",
                        "quote": "announced a new policy review after public comment and said implementation would depend",
                    }
                ],
            }
        ]
    }

    report = verify_analysis_evidence(
        _articles_data(),
        experts_data=experts,
    )

    warnings = [issue for issue in report["issues"] if issue["severity"] == "warning"]
    assert any(
        "cited_references[0]" in issue["path"] and "is not formatted as a markdown link or URL" in issue["message"]
        for issue in warnings
    )
    assert not any(
        "recommended_reading_or_context" in issue["path"]
        for issue in warnings
    )


def test_outlook_requires_structured_most_likely_scenario() -> None:
    outlook = {
        "most_likely_scenario": None,
        "alternative_scenarios": [],
        "time_horizon": "next 30-90 days",
    }

    report = verify_analysis_evidence(_articles_data(), outlook_data=outlook)

    assert report["passed"] is False
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert "Most-likely scenario is missing" in messages
