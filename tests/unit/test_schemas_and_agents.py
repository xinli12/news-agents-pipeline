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


def test_dispute_agent_contract_is_preserved() -> None:
    from agents.dispute_agent import get_dispute_agent
    from agents.schemas import DisputeList

    agent = get_dispute_agent()

    assert agent.name == "dispute_agent"
    assert agent.output_schema == DisputeList
    assert agent.output_key == "disputes_data"
    assert "under-supported" in agent.instruction
    assert "wire-service" in agent.instruction


def test_bias_agent_contract_is_preserved_for_perspective_agent() -> None:
    from agents.bias_agent import get_bias_agent
    from agents.schemas import PerspectiveProfile

    agent = get_bias_agent()

    assert agent.name == "bias_agent"
    assert agent.output_schema == PerspectiveProfile
    assert agent.output_key == "bias_data"
    assert "Perspective Agent" in agent.instruction
    assert "classification axis" in agent.instruction


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
        explanation="Both Reuters and other independent sources corroborated the policy review announcement.",
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


def test_dispute_schema_supports_evidence_strength_metadata() -> None:
    from agents.schemas import DisputeItem, EvidenceItem

    evidence = EvidenceItem(
        source="Local Daily",
        title="Residents question project cost",
        url="https://local.example/project-cost",
        published_date="2026-06-28",
        bias_category="Local",
        quote="Residents questioned whether the published cost estimate includes mitigation funding.",
    )

    dispute = DisputeItem(
        claim="Whether the project cost estimate includes mitigation funding.",
        dispute_question="Does the cost estimate include mitigation funding?",
        side_a_assertion="Officials say mitigation funding is included.",
        side_a_sources=["City Office"],
        side_a_support_level="single-source",
        side_b_assertion="Residents say the available documents do not show it.",
        side_b_sources=["Local Daily"],
        side_b_evidence=[evidence],
        side_b_support_level="source-supported",
        evidence_warning="Side A is under-supported by the supplied article set.",
    )

    assert dispute.dispute_question.startswith("Does")
    assert dispute.side_a_support_level == "single-source"
    assert dispute.evidence_warning == "Side A is under-supported by the supplied article set."


def test_perspective_schema_supports_axis_and_inference_metadata() -> None:
    from agents.schemas import EvidenceItem, NarrativeProfile, PerspectiveProfile

    evidence = EvidenceItem(
        source="Tech Wire",
        title="Startups criticize compliance plan",
        url="https://tech.example/compliance",
        published_date="2026-06-29",
        bias_category="Industry",
        quote="Startup founders said compliance costs could favor larger incumbents.",
    )

    profile = PerspectiveProfile(
        classification_axis="industry/business role",
        profiles=[
            NarrativeProfile(
                perspective_group="Startup operators",
                core_narrative="Compliance costs may advantage larger incumbents.",
                key_arguments=["Audits and legal reviews increase fixed costs."],
                common_emotional_triggers=["barrier to entry"],
                notable_omissions=["Potential consumer-safety benefits"],
                representative_sources=["Tech Wire"],
                evidence=[evidence],
                support_status="reported perspective from sources",
                analytical_inference="",
                unsupported_warning="",
            )
        ],
        key_rhetorical_differences="Industry sources emphasized costs; safety sources emphasized risk reduction.",
        unsupported_perspectives=["Consumer advocates: not enough source support found."],
    )

    assert profile.classification_axis == "industry/business role"
    assert profile.profiles[0].support_status == "reported perspective from sources"
    assert profile.unsupported_perspectives == [
        "Consumer advocates: not enough source support found."
    ]


def test_input_validation_schema_supports_new_actions() -> None:
    from agents.schemas import InputValidationResult

    result = InputValidationResult(
        action="accept_with_notification",
        is_news_related=True,
        explanation="The topic is likely news-related but very broad.",
        notification_message="Your query is broad. Consider specifying a region or date.",
        converted_query="Keir Starmer recent news",
    )

    assert result.action == "accept_with_notification"
    assert result.is_news_related is True
    assert result.notification_message == "Your query is broad. Consider specifying a region or date."
    assert result.converted_query == "Keir Starmer recent news"


def test_article_list_schema_supports_search_verification_metadata() -> None:
    from agents.schemas import ArticleList

    article_list = ArticleList(
        topic="Example topic",
        query_used="Example topic latest news",
        search_status="Low",
        verification_summary="Only one distinct source was found.",
        warnings=["Do not continue without more sources."],
        articles=[],
    )

    assert article_list.search_status == "Low"
    assert article_list.warnings == ["Do not continue without more sources."]


def test_expert_and_outlook_schemas_support_evidence_grounding() -> None:
    from agents.schemas import (
        EvidenceItem,
        ExpertOpinion,
        FutureOutlookResult,
        ScenarioItem,
    )

    evidence = EvidenceItem(
        source="Reuters",
        title="Example title",
        url="https://www.reuters.com/example",
        published_date="2026-06-27",
        bias_category="Center",
        quote="Officials said the policy would be reviewed after public comment.",
    )

    opinion = ExpertOpinion(
        expert_name="Regulatory Policy Analyst",
        expertise_area="Public Policy",
        commentary="The comment period matters because it shapes implementation risk.",
        recommended_reading_or_context=["Administrative procedure overview"],
        cited_references=["Public consultation standards"],
        supporting_evidence=[evidence],
    )
    scenario = ScenarioItem(
        scenario_title="Review proceeds on schedule",
        description="The agency continues the consultation process.",
        trigger_conditions=["No injunction is filed"],
        likelihood_band="plausible if current process continues",
        supporting_evidence=[evidence],
        assumptions=["No major procedural delay occurs"],
    )
    most_likely = ScenarioItem(
        scenario_title="Public comment period continues",
        description="The review continues through the public comment period.",
        likelihood_band="most likely",
        supporting_evidence=[evidence],
    )
    outlook = FutureOutlookResult(
        most_likely_scenario=most_likely,
        alternative_scenarios=[scenario],
        monitoring_indicators=["New docket filings"],
        confidence_statement="Evidence is limited to currently available reporting.",
        time_horizon="next 30-90 days",
    )

    assert opinion.supporting_evidence[0].url == "https://www.reuters.com/example"
    assert outlook.most_likely_scenario.supporting_evidence[0].source == "Reuters"
    assert outlook.alternative_scenarios[0].assumptions == [
        "No major procedural delay occurs"
    ]


def test_public_report_takeaways_carry_evidence_chain() -> None:
    from agents.schemas import EvidenceItem, PublicReport, ReportTakeaway

    evidence = EvidenceItem(
        source="Reuters",
        url="https://www.reuters.com/example",
        published_date="2026-06-27",
        quote="Officials said the policy would be reviewed after public comment.",
    )
    report = PublicReport(
        title="Policy review briefing",
        lead_paragraph="The policy entered a public review phase.",
        key_takeaways=[
            ReportTakeaway(point="The review is underway.", evidence=[evidence])
        ],
        narrative_summary="Coverage is broadly consistent across outlets.",
        future_outlook="Watch for the end of the comment period.",
    )

    assert report.key_takeaways[0].evidence[0].url == "https://www.reuters.com/example"


def test_expert_pipeline_factories() -> None:
    from agents.expert_agent import (
        domain_slug,
        get_domain_expert_agent,
        get_expert_domain_selector,
        get_roundtable_summarizer,
        search_authoritative_data,
    )
    from agents.schemas import ExpertDomainSelection, ExpertOpinion, RoundtableSummary

    selector = get_expert_domain_selector("gemini-3.1-flash-lite")
    assert selector.output_schema == ExpertDomainSelection

    expert = get_domain_expert_agent(
        "Constitutional Law Specialist", "gemini-3.1-flash-lite"
    )
    assert expert.name == "expert_constitutional_law_specialist"
    assert expert.output_schema == ExpertOpinion
    assert "Constitutional Law Specialist" in expert.instruction
    assert search_authoritative_data in expert.tools

    # Simple smoke test for the tool function
    result = search_authoritative_data("test query")
    assert isinstance(result, str)
    assert len(result) > 0

    summarizer = get_roundtable_summarizer("gemini-3.1-flash-lite")
    assert summarizer.output_schema == RoundtableSummary

    assert domain_slug("AI & Governance Researcher!") == "ai_governance_researcher"


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


def test_dispute_and_perspective_audit_criteria_cover_traceability_and_inference() -> None:
    from agents.coordinator import DISPUTE_AUDIT_CRITERIA, PERSPECTIVE_AUDIT_CRITERIA

    dispute_criteria = DISPUTE_AUDIT_CRITERIA.lower()
    perspective_criteria = PERSPECTIVE_AUDIT_CRITERIA.lower()

    for required in ["neutral", "quote", "url", "unsupported", "schema"]:
        assert required in dispute_criteria

    for required in [
        "neutral",
        "quote",
        "url",
        "unsupported",
        "inference",
        "schema",
    ]:
        assert required in perspective_criteria


def test_merge_disputed_claims_preserves_unique_fact_and_dispute_agent_claims() -> None:
    from agents.coordinator import merge_disputed_claims

    fact_disputes = [
        {
            "claim": "Whether the rule raises compliance costs.",
            "side_a_assertion": "Supporters say costs are manageable.",
            "side_b_assertion": "Opponents say costs are material.",
        },
        {
            "claim": "Whether the rule improves transparency.",
            "side_a_assertion": "Supporters say disclosure improves transparency.",
            "side_b_assertion": "Opponents say disclosures are incomplete.",
        },
    ]
    dispute_agent_disputes = [
        {
            "claim": "Whether the rule raises compliance costs",
            "side_a_assertion": "Officials say costs are manageable.",
            "side_b_assertion": "Companies say costs are material.",
        },
        {
            "claim": "Whether small firms receive enough transition time.",
            "side_a_assertion": "Regulators say phased deadlines are enough.",
            "side_b_assertion": "Small firms say the timeline remains too short.",
        },
    ]

    merged = merge_disputed_claims(fact_disputes, dispute_agent_disputes)

    assert [item["claim"] for item in merged] == [
        "Whether the rule raises compliance costs.",
        "Whether the rule improves transparency.",
        "Whether small firms receive enough transition time.",
    ]


def test_merge_disputed_claims_deduplicates_dispute_question_fallbacks() -> None:
    from agents.coordinator import merge_disputed_claims

    fact_disputes = [
        {
            "claim": "",
            "dispute_question": "Whether emergency funding reached local agencies.",
            "side_a_assertion": "Officials say funds were distributed.",
            "side_b_assertion": "Local agencies say funds were delayed.",
        }
    ]
    dispute_agent_disputes = [
        {
            "claim": "",
            "dispute_question": "Whether emergency funding reached local agencies",
            "side_a_assertion": "Officials report the funding was distributed.",
            "side_b_assertion": "Local agencies report delays.",
        },
        {
            "claim": "",
            "dispute_question": "",
            "side_a_assertion": "Officials say the deadline remains unchanged.",
            "side_b_assertion": "Advocates say the deadline may move.",
        },
    ]

    merged = merge_disputed_claims(fact_disputes, dispute_agent_disputes)

    assert len(merged) == 2
    assert merged[0]["dispute_question"] == (
        "Whether emergency funding reached local agencies."
    )
    assert merged[1]["side_a_assertion"] == "Officials say the deadline remains unchanged."


def test_classify_search_results_combines_topic_and_bias_in_one_call() -> None:
    from unittest.mock import MagicMock, patch

    from agents.search_agent import classify_search_results

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = (
            '{"is_viewpoint_oriented": true, "complexity": "High", '
            '"article_bias": {"0": "left"}}'
        )
        mock_client.models.generate_content.return_value = mock_response

        res = classify_search_results(
            "Some topic", [{"title": "Test", "url": "http://example.com/a"}]
        )
        assert res["is_viewpoint_oriented"] is True
        assert res["complexity"] == "High"
        assert res["article_bias"] == {"http://example.com/a": "LEFT"}
        # A single combined call replaces what used to be two separate ones.
        assert mock_client.models.generate_content.call_count == 1


def test_classify_search_results_retries_transient_errors_then_falls_back() -> None:
    from unittest.mock import MagicMock, patch

    from google.genai import errors as genai_errors

    from agents.search_agent import classify_search_results

    with patch("google.genai.Client") as mock_client_cls, patch("time.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.side_effect = genai_errors.ServerError(
            503, {"error": {"message": "unavailable"}}
        )

        res = classify_search_results(
            "Some topic", [{"title": "Test", "url": "http://example.com/a"}], max_retries=1
        )

        # One initial attempt + one retry = 2 calls, with a backoff sleep in between.
        assert mock_client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once()
        assert res == {
            "is_viewpoint_oriented": False,
            "complexity": "Moderate",
            "article_bias": {},
        }


def test_classify_search_results_does_not_retry_content_errors() -> None:
    from unittest.mock import MagicMock, patch

    from agents.search_agent import classify_search_results

    with patch("google.genai.Client") as mock_client_cls, patch("time.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_client.models.generate_content.return_value = mock_response

        res = classify_search_results(
            "Some topic", [{"title": "Test", "url": "http://example.com/a"}], max_retries=1
        )

        # A malformed response will reproduce under the same prompt, so it
        # should fail fast without burning a retry/backoff.
        assert mock_client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()
        assert res["article_bias"] == {}


def test_get_live_news_articles_selection_logic_branches() -> None:
    from unittest.mock import MagicMock, patch

    from agents.search_agent import get_live_news_articles

    # Mock ddgs, classify_search_results, scrape_articles_parallel
    with patch("agents.search_agent.DDGS") as mock_ddgs, \
         patch("agents.search_agent.classify_search_results") as mock_classify, \
         patch("agents.web_tools.scrape_articles_parallel") as mock_scrape:

        # Setup mock search results
        mock_news = MagicMock()
        mock_ddgs.return_value.__enter__.return_value = mock_news

        dummy_results = [
            {"title": "Article Left 1", "url": "http://left1", "source": "Left Outlet 1", "body": "body 1"},
            {"title": "Article Right 1", "url": "http://right1", "source": "Right Outlet 1", "body": "body 2"},
            {"title": "Article Center 1", "url": "http://center1", "source": "Center Outlet 1", "body": "body 3"},
            {"title": "Article Wire Center 2", "url": "http://center2", "source": "Reuters", "body": "body 4"},
            {"title": "Article Other 1", "url": "http://other1", "source": "Other Outlet 1", "body": "body 5"},
        ]
        mock_news.news.return_value = dummy_results
        mock_scrape.return_value = {}

        article_bias = {
            "http://left1": "LEFT", "http://right1": "RIGHT", "http://center1": "CENTER",
            "http://center2": "CENTER", "http://other1": "OTHER/NON-POLITICAL"
        }

        # Case A: Factual-oriented (is_viewpoint_oriented = False, complexity = Simple)
        mock_classify.return_value = {
            "is_viewpoint_oriented": False, "complexity": "Simple", "article_bias": article_bias
        }

        res_factual = get_live_news_articles("Factual Topic")
        assert "TOPIC_TYPE: factual-oriented" in res_factual
        assert "TOPIC_COMPLEXITY: Simple" in res_factual
        # The factual selection should prioritize wire service (Reuters / http://center2) and keep others in search order.
        # First article should be the wire service: Article Wire Center 2
        assert "Article #1\nTitle: Article Wire Center 2" in res_factual
        # The pre-computed bias classification is surfaced to the agent instead of being discarded.
        assert "Prior Bias Signal: CENTER" in res_factual

        # Case B: Viewpoint-oriented (is_viewpoint_oriented = True, complexity = High)
        mock_classify.return_value = {
            "is_viewpoint_oriented": True, "complexity": "High", "article_bias": article_bias
        }
        res_viewpoint = get_live_news_articles("Viewpoint Topic")
        assert "TOPIC_TYPE: viewpoint-oriented" in res_viewpoint
        assert "TOPIC_COMPLEXITY: High" in res_viewpoint
        # The viewpoint selection should use round-robin: LEFT, RIGHT, CENTER, OTHER/NON-POLITICAL
        # Order should be Left 1, Right 1, Center 1, Other 1, then the rest (Reuters)
        assert "Article #1\nTitle: Article Left 1" in res_viewpoint
        assert "Article #2\nTitle: Article Right 1" in res_viewpoint
        assert "Article #3\nTitle: Article Center 1" in res_viewpoint


def test_is_transient_error_classifies_api_vs_content_failures() -> None:
    from google.genai import errors as genai_errors

    from agents.web_tools import is_transient_error

    server_error = genai_errors.ServerError(503, {"error": {"message": "unavailable"}})
    assert is_transient_error(server_error) is True

    rate_limited = genai_errors.ClientError(429, {"error": {"message": "rate limited"}})
    assert is_transient_error(rate_limited) is True

    bad_request = genai_errors.ClientError(400, {"error": {"message": "bad request"}})
    assert is_transient_error(bad_request) is False

    assert is_transient_error(ConnectionError("connection reset")) is True
    assert is_transient_error(ValueError("malformed json")) is False
    assert is_transient_error(KeyError("missing field")) is False


def test_run_agent_retries_immediately_and_injects_error_context() -> None:
    import asyncio
    from unittest.mock import MagicMock, patch

    from google.adk.agents import Agent

    from agents.coordinator import NewsAnalysisCoordinator
    from agents.schemas import AuditResult

    coordinator = NewsAnalysisCoordinator()
    agent = Agent(
        name="dummy_agent",
        model="gemini-3.1-flash-lite",
        instruction="Say hello.",
        output_schema=AuditResult,
        output_key="audit_result",
    )

    captured_prompts = []
    call_count = {"n": 0}

    async def fake_run_async(*, user_id, session_id, new_message):
        call_count["n"] += 1
        captured_prompts.append(new_message.parts[0].text)
        if call_count["n"] == 1:
            raise ValueError("malformed structured output")
        # InMemorySessionService.get_session() returns a copy, so mutating it
        # would not persist; write directly into the service's backing store
        # the way append_event() would, to simulate a successful agent turn.
        stored_session = coordinator.session_service.sessions["news_app"]["user"][
            session_id
        ]
        stored_session.state["audit_result"] = {
            "is_approved": True,
            "audit_feedback": [],
            "recommended_fixes": [],
        }
        return
        yield  # pragma: no cover - marks this as an async generator

    mock_runner = MagicMock()
    mock_runner.run_async = fake_run_async

    with patch("agents.coordinator.Runner", return_value=mock_runner):
        result = asyncio.run(
            coordinator._run_agent(agent, "Do the thing.", "sess_test", max_retries=3)
        )

    assert result == {
        "is_approved": True,
        "audit_feedback": [],
        "recommended_fixes": [],
    }
    assert call_count["n"] == 2
    assert captured_prompts[0] == "Do the thing."
    assert captured_prompts[1].startswith("Do the thing.")
    assert "malformed structured output" in captured_prompts[1]

