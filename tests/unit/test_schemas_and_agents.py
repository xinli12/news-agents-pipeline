# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
def test_public_reporter_agent() -> None:
    from agents.public_reporter_agent import get_public_reporter_agent
    from agents.schemas import PublicReport

    agent = get_public_reporter_agent()
    assert agent.name == "public_reporter_agent"
    assert agent.output_schema == PublicReport
    assert agent.output_key == "public_report_data"


def test_fact_schema_supports_traceable_evidence() -> None:
    from agents.schemas import DisputeItem, EvidenceItem, FactItem, TimelineEvent

    evidence = EvidenceItem(
        source="Reuters",
        title="Example title",
        url="https://www.reuters.com/example",
        published_date="2026-06-27",
        bias_category="Center",
        quote="Officials said the policy would be reviewed after public comment.",
    )

    fact = FactItem(
        claim="The policy is under public review.",
        supporting_sources=["Reuters"],
        evidence=[evidence],
        cross_verification_score=0.8,
    )
    dispute = DisputeItem(
        claim="Whether the policy will raise costs.",
        side_a_assertion="Supporters say costs will be limited.",
        side_a_sources=["Reuters"],
        side_a_evidence=[evidence],
        side_b_assertion="Opponents say costs will rise materially.",
        side_b_sources=["AP"],
    )

    assert fact.evidence[0].url == "https://www.reuters.com/example"
    assert dispute.side_a_evidence[0].bias_category == "Center"
    assert dispute.side_b_evidence == []

    timeline_event = TimelineEvent(
        date="2026-06-27",
        event="The policy entered public review.",
        evidence=[evidence],
    )
    assert timeline_event.evidence[0].quote.startswith("Officials said")


def test_input_review_schema_supports_query_repair_options() -> None:
    from agents.schemas import TopicReviewResult

    review = TopicReviewResult(
        is_safe=True,
        is_news_relevant=True,
        suggested_query_formulation="Keir Starmer recent news",
        input_issue_type="fragment",
        suggested_options=["Recent developments", "Full political timeline"],
        auto_modified=True,
        needs_user_confirmation=True,
        confidence=0.72,
    )

    assert review.auto_modified is True
    assert review.suggested_options[0] == "Recent developments"


def test_article_list_schema_supports_search_verification_metadata() -> None:
    from agents.schemas import ArticleList

    article_list = ArticleList(
        topic="Example topic",
        query_used="Example topic latest news",
        search_status="insufficient_corroboration",
        verification_summary="Only one distinct source was found.",
        warnings=["Do not continue without more sources."],
        articles=[],
    )

    assert article_list.search_status == "insufficient_corroboration"
    assert article_list.warnings == ["Do not continue without more sources."]


def test_search_candidate_pool_deduplicates_wire_clusters() -> None:
    from agents.search_agent import dedupe_candidate_pool

    raw_results = [
        {
            "title": "Reuters: Cabinet announces new fiscal plan",
            "url": "https://example.com/one",
            "source": "Reuters",
            "body": "The cabinet announced a new fiscal plan.",
        },
        {
            "title": "Reuters: Cabinet announces new fiscal plan",
            "url": "https://mirror.example.com/one",
            "source": "Yahoo News",
            "body": "Reporting by Reuters.",
        },
        {
            "title": "Local officials react to fiscal plan",
            "url": "https://local.example.com/two",
            "source": "Local Daily",
            "body": "Officials in the region reacted to the plan.",
        },
    ]

    candidates, wire_groups = dedupe_candidate_pool(raw_results)

    assert len(candidates) == 2
    assert candidates[0]["wire_service"] == "Reuters"
    assert wire_groups
