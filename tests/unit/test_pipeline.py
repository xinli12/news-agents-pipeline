"""Workflow orchestration tests driven by fake (non-LLM) worker nodes.

These tests run the full ADK Workflow graph through the coordinator with every
LlmAgent factory replaced by a deterministic FunctionNode, validating routing,
parallel fan-out/join, the audit-revision loop, and the final result shape
without any API calls.
"""

import pytest
from google.adk.workflow import node

import agents.pipeline as pipeline
from agents.coordinator import NewsAnalysisCoordinator

pytestmark = pytest.mark.asyncio

REVIEW_OK = {
    "is_safe": True,
    "is_news_relevant": True,
    "suggested_query_formulation": "ai regulation bill",
    "rejection_reason": None,
    "input_issue_type": "clear_news_query",
    "user_message": "",
    "suggested_options": [],
    "auto_modified": False,
    "needs_user_confirmation": False,
    "confidence": 1.0,
}

REVIEW_REJECTED = {**REVIEW_OK, "is_safe": False, "rejection_reason": "Unsafe input."}

ARTICLES = {
    "topic": "ai regulation bill",
    "articles": [
        {
            "title": "Congress debates AI bill",
            "url": "https://example.com/a",
            "source": "CNN",
            "published_date": "2026-06-21",
            "bias_category": "Left",
            "media_scale": "National",
            "media_type": "Mainstream",
            "summary": "Debate over the bill.",
            "full_content_snippet": "Lawmakers are debating a new bill.",
            "source_reliability_score": 0.8,
            "objectivity_score": 0.7,
        },
        {
            "title": "Tech pushes back on AI rules",
            "url": "https://example.com/b",
            "source": "Fox News",
            "published_date": "2026-06-22",
            "bias_category": "Right",
            "media_scale": "National",
            "media_type": "Mainstream",
            "summary": "Industry criticism.",
            "full_content_snippet": "Entrepreneurs are alarmed by the rules.",
            "source_reliability_score": 0.75,
            "objectivity_score": 0.6,
        },
    ],
    "query_used": "ai regulation bill",
    "corrected_query": None,
    "search_status": "verified",
    "verification_summary": "Multiple distinct sources found.",
    "source_balance": {"LEFT": 1, "RIGHT": 1},
    "warnings": [],
    "wire_groups": [],
}

SEARCH_FAILED = {
    **ARTICLES,
    "articles": [],
    "search_status": "no_results",
    "verification_summary": "No sources found.",
}

RECRUIT_ALL = {
    "recruit_dispute": True,
    "recruit_perspective": True,
    "recruit_expert": True,
    "recruit_future_outlook": True,
    "recruitment_justification": "Contested topic.",
    "complexity_level": "moderate",
    "recruited_agents": ["Dispute Agent", "Perspective Agent"],
    "skipped_agents": [],
}

FACTS = {
    "consensus_facts": [
        {
            "claim": "A bill is being debated.",
            "supporting_sources": ["CNN", "Fox News"],
            "evidence": [],
            "explanation": "Both outlets report the debate.",
            "cross_verification_score": 0.9,
        }
    ],
    "timeline_events": [],
    "timeline": [],
    "disputed_claims": [
        {
            "claim": "Whether the bill stifles innovation.",
            "side_a_assertion": "Supporters say it will not.",
            "side_b_assertion": "Opponents say it will.",
        }
    ],
}

DISPUTES = {
    "disputed_claims": [
        {
            "claim": "Whether the bill stifles innovation.",
            "side_a_assertion": "Different wording, same claim.",
            "side_b_assertion": "Also same claim.",
        },
        {
            "claim": "Whether startups get transition time.",
            "side_a_assertion": "Regulators say yes.",
            "side_b_assertion": "Startups say no.",
        },
    ]
}

NARRATIVES = {
    "classification_axis": "ideology",
    "profiles": [],
    "key_rhetorical_differences": "Frames differ.",
    "unsupported_perspectives": [],
}

OPINION = {
    "expert_name": "Policy Analyst",
    "expertise_area": "Public Policy",
    "commentary": "The bill matters.",
    "recommended_reading_or_context": [],
    "cited_references": [],
    "supporting_evidence": [],
}

OUTLOOK = {
    "most_likely_scenario": None,
    "alternative_scenarios": [],
    "monitoring_indicators": ["Committee votes"],
    "confidence_statement": "",
    "time_horizon": "30 days",
}

PUBLIC_REPORT = {
    "title": "AI bill briefing",
    "lead_paragraph": "Congress is debating an AI bill.",
    "key_takeaways": [],
    "narrative_summary": "Coverage differs by outlet.",
    "future_outlook": "Watch the committee vote.",
}

EDITOR_OUTPUT = {"markdown_report": "# Briefing", "unresolved_warnings": []}

PASSED_VERIFICATION = {
    "passed": True,
    "error_count": 0,
    "warning_count": 0,
    "issues": [],
    "summary": "ok",
}

APPROVAL = {"is_approved": True, "audit_feedback": [], "recommended_fixes": []}


def fake_agent_node(name: str, result, calls: dict | None = None):
    """Builds a FunctionNode standing in for an LlmAgent with a canned output."""

    def impl(node_input: str):
        if calls is not None:
            calls.setdefault(name, []).append(node_input)
        return result

    impl.__name__ = name
    return node(impl, name=name)


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Replaces every agent factory and the deterministic verifier with fakes."""
    calls: dict[str, list[str]] = {}

    factories = {
        "get_review_agent": ("review_agent", REVIEW_OK),
        "get_search_agent": ("search_agent", ARTICLES),
        "get_recruiter_agent": ("recruiter_agent", RECRUIT_ALL),
        "get_fact_agent": ("fact_agent", FACTS),
        "get_dispute_agent": ("dispute_agent", DISPUTES),
        "get_bias_agent": ("bias_agent", NARRATIVES),
        "get_outlook_agent": ("outlook_agent", OUTLOOK),
        "get_public_reporter_agent": ("public_reporter_agent", PUBLIC_REPORT),
        "get_public_editor_agent": ("public_editor_agent", EDITOR_OUTPUT),
    }
    for factory_name, (agent_name, result) in factories.items():
        monkeypatch.setattr(
            pipeline,
            factory_name,
            lambda model=None, agent_name=agent_name, result=result: fake_agent_node(
                agent_name, result, calls
            ),
        )

    monkeypatch.setattr(
        pipeline,
        "get_expert_domain_selector",
        lambda model=None: fake_agent_node(
            "expert_domain_selector",
            {"domains": ["Policy Analyst", "Economist"], "selection_rationale": ""},
            calls,
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "get_domain_expert_agent",
        lambda domain, model=None: fake_agent_node(
            f"expert_{domain.lower().replace(' ', '_')}",
            {**OPINION, "expert_name": domain},
            calls,
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "get_roundtable_summarizer",
        lambda model=None: fake_agent_node(
            "roundtable_summarizer", {"roundtable_summary": "Experts agree."}, calls
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "get_audit_agent",
        lambda agent_name, criteria, model_name=None: fake_agent_node(
            f"{agent_name}_audit", APPROVAL, calls
        ),
    )
    monkeypatch.setattr(
        pipeline, "verify_analysis_evidence", lambda *args, **kwargs: PASSED_VERIFICATION
    )
    return calls


async def test_full_pipeline_happy_path(fake_pipeline):
    coordinator = NewsAnalysisCoordinator()
    progress_steps = []

    async def progress_callback(step, message, payload=None):
        progress_steps.append(step)

    control_state = {"control": {"paused": False, "stopped": False}}
    results_dict = {}
    result = await coordinator.analyze(
        "ai regulation bill",
        progress_callback=progress_callback,
        control_state=control_state,
        results_dict=results_dict,
    )

    assert result["reviewed"] is True
    assert result["is_approved"] is True
    assert result["articles"]["articles"], "articles should be populated"
    assert result["public_report"]["title"] == "AI bill briefing"
    assert result["public_editor_report"] == "# Briefing"

    # Dispute merge: fact-agent claim kept, unique dispute-agent claim appended
    merged_claims = [item["claim"] for item in result["facts"]["disputed_claims"]]
    assert merged_claims == [
        "Whether the bill stifles innovation.",
        "Whether startups get transition time.",
    ]

    # Expert fan-out ran one agent per selected domain plus the summarizer
    names = [opinion["expert_name"] for opinion in result["experts"]["expert_opinions"]]
    assert sorted(names) == ["Economist", "Policy Analyst"]
    assert result["experts"]["roundtable_summary"] == "Experts agree."

    # All steps completed and progress was reported end to end
    assert set(control_state["step_statuses"].values()) == {"completed"}
    assert "review_complete" in progress_steps
    assert "editor_complete" in progress_steps
    assert results_dict["facts"] == result["facts"]

    # The recruiter prompt must use the trimmed article overview (no full text)
    recruiter_prompt = fake_pipeline["recruiter_agent"][0]
    assert "Lawmakers are debating" not in recruiter_prompt
    assert "Congress debates AI bill" in recruiter_prompt


async def test_rejected_review_short_circuits(fake_pipeline, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "get_review_agent",
        lambda model=None: fake_agent_node("review_agent", REVIEW_REJECTED),
    )
    coordinator = NewsAnalysisCoordinator()
    control_state = {"control": {}}
    result = await coordinator.analyze("bad input", control_state=control_state)

    assert result["reviewed"] is False
    assert result["review_result"]["rejection_reason"] == "Unsafe input."
    assert control_state["step_statuses"]["review"] == "failed"
    # Downstream stages never dispatched their workers
    assert "search_agent" not in fake_pipeline
    assert "fact_agent" not in fake_pipeline


async def test_failed_search_short_circuits(fake_pipeline, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "get_search_agent",
        lambda model=None: fake_agent_node("search_agent", SEARCH_FAILED),
    )
    coordinator = NewsAnalysisCoordinator()
    result = await coordinator.analyze("obscure topic")

    assert result["search_failed"] is True
    assert result["is_approved"] is False
    assert result["search_result"]["search_status"] == "no_results"
    assert "fact_agent" not in fake_pipeline
    assert "public_reporter_agent" not in fake_pipeline


async def test_audit_rejection_triggers_revision(fake_pipeline, monkeypatch):
    rejection = {
        "is_approved": False,
        "audit_feedback": ["Facts lack sources."],
        "recommended_fixes": ["Add citations."],
    }
    audit_calls = {"fact_agent_audit": 0}

    def fake_get_audit_agent(agent_name, criteria, model_name=None):
        if agent_name == "fact_agent":
            audit_calls["fact_agent_audit"] += 1
            outcome = rejection if audit_calls["fact_agent_audit"] == 1 else APPROVAL
            return fake_agent_node("fact_agent_audit", outcome)
        return fake_agent_node(f"{agent_name}_audit", APPROVAL)

    monkeypatch.setattr(pipeline, "get_audit_agent", fake_get_audit_agent)

    coordinator = NewsAnalysisCoordinator()
    result = await coordinator.analyze("ai regulation bill")

    fact_attempts = [
        log for log in result["editor_logs"] if log["agent"] == "fact_agent"
    ]
    assert [log["approved"] for log in fact_attempts] == [False, True]
    # The revision prompt carried the auditor feedback back to the worker
    second_prompt = fake_pipeline["fact_agent"][1]
    assert "Facts lack sources." in second_prompt
    assert "Add citations." in second_prompt
    assert result["is_approved"] is True


async def test_skipped_recruitment_uses_defaults(fake_pipeline, monkeypatch):
    recruit_none = {
        **RECRUIT_ALL,
        "recruit_dispute": False,
        "recruit_perspective": False,
        "recruit_expert": False,
        "recruit_future_outlook": False,
    }
    monkeypatch.setattr(
        pipeline,
        "get_recruiter_agent",
        lambda model=None: fake_agent_node("recruiter_agent", recruit_none),
    )
    coordinator = NewsAnalysisCoordinator()
    control_state = {"control": {}}
    result = await coordinator.analyze("simple topic", control_state=control_state)

    assert "dispute_agent" not in fake_pipeline
    assert "bias_agent" not in fake_pipeline
    assert "expert_domain_selector" not in fake_pipeline
    assert "outlook_agent" not in fake_pipeline
    assert control_state["step_statuses"]["dispute"] == "skipped"
    assert control_state["step_statuses"]["expert"] == "skipped"
    assert result["experts"]["roundtable_summary"] == "No expert roundtable recruited."
    assert result["is_approved"] is True


async def test_stop_returns_partial_result(fake_pipeline, monkeypatch):
    control_state = {"control": {"paused": False, "stopped": False}}

    def stopping_search_factory(model=None):
        def impl(node_input: str):
            control_state["control"]["stopped"] = True
            return ARTICLES

        impl.__name__ = "search_agent"
        return node(impl, name="search_agent")

    monkeypatch.setattr(pipeline, "get_search_agent", stopping_search_factory)

    coordinator = NewsAnalysisCoordinator()
    result = await coordinator.analyze("ai regulation bill", control_state=control_state)

    assert result["stopped"] is True
    assert result["is_approved"] is False
    assert "fact_agent" not in fake_pipeline
    statuses = set(control_state["step_statuses"].values())
    assert "stopped" in statuses
