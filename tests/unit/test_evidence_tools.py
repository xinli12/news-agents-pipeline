from agents.evidence_tools import (
    quote_match_score,
    score_source_independence,
    summarize_evidence_completeness,
    summarize_side_evidence,
    validate_evidence_item,
)


def complete_evidence(**overrides: str) -> dict:
    evidence = {
        "source": "Local Daily",
        "title": "Residents question project cost",
        "url": "https://local.example/project-cost",
        "quote": "Residents questioned whether the published cost includes mitigation funding.",
    }
    return evidence | overrides


def test_quote_exact_match_scores_one() -> None:
    score = quote_match_score(
        "Officials said the policy would be reviewed after public comment.",
        "Officials said the policy would be reviewed after public comment.",
    )

    assert score == 1.0


def test_quote_partial_match_scores_between_none_and_exact() -> None:
    score = quote_match_score(
        "The mayor said the project costs could rise materially after the audit.",
        "Project costs could rise after an audit, according to city documents.",
    )

    assert 0.45 <= score < 1.0


def test_quote_not_found_scores_zero() -> None:
    score = quote_match_score(
        "Apple harvests improved after spring rainfall.",
        "The fiscal committee approved a budget amendment.",
    )

    assert score == 0.0


def test_validate_evidence_warns_for_missing_url() -> None:
    result = validate_evidence_item(
        complete_evidence(url=""),
        {
            "Local Daily": {
                "full_content_snippet": (
                    "Residents questioned whether the published cost includes "
                    "mitigation funding."
                )
            }
        },
    )

    assert result["status"] == "warning"
    assert result["missing_fields"] == ["url"]
    assert "missing url" in result["warnings"]
    assert result["quote_match_score"] == 1.0
    assert result["score"] == 0.75


def test_validate_evidence_rejects_missing_quote() -> None:
    result = validate_evidence_item(complete_evidence(quote=""))

    assert result["status"] == "invalid"
    assert result["score"] == 0.0
    assert result["quote_match_score"] == 0.0
    assert "missing quote" in result["warnings"]


def test_source_independence_warns_for_repeated_wire_service() -> None:
    result = score_source_independence(
        [
            complete_evidence(source="Outlet A", wire_service="Reuters"),
            complete_evidence(source="Outlet B", wire_service="Reuters"),
            complete_evidence(source="Outlet C", wire_service="Associated Press"),
        ]
    )

    assert result["distinct_sources"] == 3
    assert result["wire_service_counts"]["Reuters"] == 2
    assert any("wire_service 'Reuters'" in warning for warning in result["warnings"])


def test_source_independence_warns_for_duplicate_cluster() -> None:
    result = score_source_independence(
        [
            complete_evidence(source="Outlet A", duplicate_cluster="cluster-one"),
            complete_evidence(source="Outlet B", duplicate_cluster="cluster-one"),
            complete_evidence(source="Outlet C", duplicate_cluster="cluster-two"),
        ]
    )

    assert result["distinct_duplicate_clusters"] == 2
    assert result["duplicate_cluster_counts"]["cluster-one"] == 2
    assert any(
        "duplicate_cluster 'cluster-one'" in warning for warning in result["warnings"]
    )


def test_source_independence_uses_source_when_cluster_metadata_is_sparse() -> None:
    result = score_source_independence(
        [
            complete_evidence(source="Outlet A", duplicate_cluster="cluster-one"),
            complete_evidence(source="Outlet B"),
            complete_evidence(source="Outlet C"),
        ]
    )

    assert result["distinct_duplicate_clusters"] == 1
    assert result["distinct_sources"] == 3
    assert result["distinct_independence_keys"] == 3
    assert result["score"] == 1.0
    assert result["independence_label"] == "strong"


def test_source_independence_scores_shared_cluster_plus_independent_source() -> None:
    result = score_source_independence(
        [
            complete_evidence(source="Outlet A", duplicate_cluster="cluster-one"),
            complete_evidence(source="Outlet B", duplicate_cluster="cluster-one"),
            complete_evidence(source="Outlet C"),
        ]
    )

    assert result["distinct_independence_keys"] == 2
    assert result["score"] == 0.667
    assert result["independence_label"] == "partial"
    assert any(
        "duplicate_cluster 'cluster-one'" in warning for warning in result["warnings"]
    )


def test_source_independence_ignores_empty_independence_metadata() -> None:
    result = score_source_independence(
        [
            complete_evidence(source="", outlet_group="", duplicate_cluster=""),
            complete_evidence(source="Outlet B"),
        ]
    )

    assert result["distinct_sources"] == 1
    assert result["distinct_outlet_groups"] == 0
    assert result["distinct_duplicate_clusters"] == 0
    assert result["distinct_independence_keys"] == 1
    assert result["score"] == 0.5
    assert result["independence_label"] == "weak"


def test_summarize_side_evidence_balanced_vs_one_sided() -> None:
    balanced = summarize_side_evidence(
        [complete_evidence(source="Outlet A")],
        [complete_evidence(source="Outlet B")],
    )
    one_sided = summarize_side_evidence([complete_evidence()], [])

    assert balanced["side_a_count"] == 1
    assert balanced["side_b_count"] == 1
    assert balanced["balance_label"] == "balanced"
    assert balanced["warnings"] == []
    assert one_sided["balance_label"] == "one_sided"
    assert any("side_b has no evidence" in warning for warning in one_sided["warnings"])


def test_empty_evidence_list_returns_none_summaries() -> None:
    completeness = summarize_evidence_completeness([])
    independence = score_source_independence([])
    side_summary = summarize_side_evidence([], [])

    assert completeness == {
        "total_items": 0,
        "with_source": 0,
        "with_url": 0,
        "with_quote": 0,
        "complete_items": 0,
        "completeness_label": "none",
    }
    assert independence["total_items"] == 0
    assert independence["score"] == 0.0
    assert independence["independence_label"] == "none"
    assert side_summary["balance_label"] == "no_evidence"
