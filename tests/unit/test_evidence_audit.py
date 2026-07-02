from agents.evidence_audit import (
    audit_dispute_evidence,
    audit_perspective_evidence,
    build_article_lookup,
    run_deterministic_evidence_audit,
)


def complete_evidence(**overrides: str) -> dict:
    evidence = {
        "source": "Local Daily",
        "title": "Residents question project cost",
        "url": "https://local.example/project-cost",
        "quote": "Residents questioned whether the published cost includes mitigation funding.",
    }
    return evidence | overrides


def matching_articles() -> dict:
    return {
        "articles": [
            {
                "source": "Local Daily",
                "title": "Residents question project cost",
                "url": "https://local.example/project-cost",
                "summary": (
                    "Residents questioned whether the published cost includes "
                    "mitigation funding."
                ),
                "full_content_snippet": (
                    "Residents questioned whether the published cost includes "
                    "mitigation funding."
                ),
            }
        ]
    }


def test_build_article_lookup_indexes_article_identity_and_snippets() -> None:
    lookup = build_article_lookup(matching_articles())

    assert "https://local.example/project-cost" in lookup
    assert "Residents question project cost" in lookup
    assert "Local Daily" in lookup
    assert lookup["https://local.example/project-cost"]["summary"].startswith(
        "Residents questioned"
    )


def test_complete_fact_and_perspective_evidence_passes_with_strong_summary() -> None:
    facts_data = {
        "consensus_facts": [
            {
                "claim": "The project cost was questioned by residents.",
                "evidence": [complete_evidence()],
            }
        ],
        "timeline": [
            {
                "date": "2026-07-01",
                "event": "Residents questioned the project cost.",
                "evidence": [complete_evidence()],
            }
        ],
        "disputed_claims": [],
    }
    narratives = {
        "profiles": [
            {
                "perspective_group": "Residents",
                "support_status": "reported perspective from sources",
                "evidence": [complete_evidence()],
            }
        ]
    }

    result = run_deterministic_evidence_audit(
        facts_data, narratives, matching_articles()
    )

    assert result["status"] == "passed"
    assert result["warnings"] == []
    assert result["summary"]["total_evidence_items_checked"] == 3
    assert result["summary"]["completeness_label"] == "strong"
    assert result["fact_evidence"]["summary"]["completeness_label"] == "strong"


def test_missing_url_and_quote_create_warnings() -> None:
    facts_data = {
        "consensus_facts": [
            {
                "claim": "The project cost was questioned by residents.",
                "evidence": [complete_evidence(url="", quote="")],
            }
        ],
        "timeline": [],
        "disputed_claims": [],
    }

    result = run_deterministic_evidence_audit(facts_data, {}, matching_articles())

    assert result["status"] == "warnings"
    assert result["summary"]["missing_url_count"] == 1
    assert result["summary"]["missing_quote_count"] == 1
    assert any("missing url" in warning for warning in result["warnings"])
    assert any("missing quote" in warning for warning in result["warnings"])


def test_quote_not_found_in_article_snippets_creates_quote_warning() -> None:
    facts_data = {
        "consensus_facts": [
            {
                "claim": "A crop harvest improved.",
                "evidence": [
                    complete_evidence(
                        quote="Apple harvests improved after spring rainfall."
                    )
                ],
            }
        ],
        "timeline": [],
        "disputed_claims": [],
    }

    result = run_deterministic_evidence_audit(facts_data, {}, matching_articles())

    assert result["status"] == "warnings"
    assert result["summary"]["quote_match_warning_count"] == 1
    assert any("quote not found in article snippets" in w for w in result["warnings"])


def test_one_sided_dispute_evidence_creates_warning() -> None:
    facts_data = {
        "consensus_facts": [],
        "timeline": [],
        "disputed_claims": [
            {
                "claim": "Whether the timeline is realistic",
                "side_a_assertion": "Officials say the timeline is realistic.",
                "side_a_evidence": [complete_evidence(source="City Journal")],
                "side_b_assertion": "Residents say the timeline is too short.",
                "side_b_evidence": [],
            }
        ],
    }

    result = audit_dispute_evidence(facts_data, {})

    assert result["status"] == "warnings"
    assert result["summary"]["one_sided_dispute_count"] == 1
    assert any("side_b has no evidence" in warning for warning in result["warnings"])


def test_repeated_wire_service_and_duplicate_cluster_create_warnings() -> None:
    facts_data = {
        "disputed_claims": [
            {
                "claim": "Whether the timeline is realistic",
                "side_a_assertion": "Officials say the timeline is realistic.",
                "side_a_evidence": [
                    complete_evidence(
                        source="Outlet A",
                        wire_service="Reuters",
                        duplicate_cluster="cluster-one",
                    ),
                    complete_evidence(
                        source="Outlet B",
                        wire_service="Reuters",
                        duplicate_cluster="cluster-one",
                    ),
                ],
                "side_b_assertion": "Residents say the timeline is too short.",
                "side_b_evidence": [complete_evidence(source="Outlet C")],
            }
        ]
    }

    result = audit_dispute_evidence(facts_data, {})

    assert result["status"] == "warnings"
    assert result["summary"]["wire_duplicate_warning_count"] == 2
    assert any("wire_service 'Reuters'" in warning for warning in result["warnings"])
    assert any(
        "duplicate_cluster 'cluster-one'" in warning
        for warning in result["warnings"]
    )


def test_reported_perspective_without_evidence_creates_warning() -> None:
    narratives = {
        "profiles": [
            {
                "perspective_group": "Residents",
                "support_status": "reported perspective from sources",
                "evidence": [],
            }
        ]
    }

    result = audit_perspective_evidence(narratives, {})

    assert result["status"] == "warnings"
    assert result["summary"]["reported_perspective_without_evidence_count"] == 1
    assert any("reported perspective" in warning for warning in result["warnings"])


def test_empty_inputs_return_not_available_without_crashing() -> None:
    result = run_deterministic_evidence_audit({}, {}, {})

    assert result["status"] == "not_available"
    assert result["warnings"] == []
    assert result["summary"]["total_evidence_items_checked"] == 0
    assert result["summary"]["missing_url_count"] == 0
    assert result["summary"]["missing_quote_count"] == 0
    assert result["summary"]["quote_match_warning_count"] == 0
