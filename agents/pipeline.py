"""ADK-native workflow for the NewsLens multi-agent news analysis.

The pipeline is expressed as a `google.adk.workflow.Workflow` graph::

    START -> review -> search -> recruiter -> (fact | dispute | perspective)
          -> analysis_join -> merge -> (expert | outlook) -> synthesis_join
          -> public_report -> public_editor -> finalize

Conditional routes ("abort") short-circuit from the review and search stages
straight to `finalize`, which assembles the rejection / search-failure result.

Each stage is a FunctionNode that dispatches its worker LlmAgent — and a
stage-specific audit LlmAgent — dynamically via `ctx.run_node()`. Every
dispatch gets a unique isolation scope, so a worker only sees its own prompt
(equivalent to a fresh session) even when stages run in parallel. The
audit/revision loop is bounded by `PipelineRun.audit_revision_cycles`, and
transient LLM failures are retried through the workflow-native `RetryConfig`.
"""

import asyncio
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.workflow import START as WORKFLOW_START
from google.adk.workflow import Edge, JoinNode, RetryConfig, Workflow, node

from agents.audit_criteria import (
    DISPUTE_AUDIT_CRITERIA,
    EXPERT_AUDIT_CRITERIA,
    FACT_AUDIT_CRITERIA,
    INPUT_AUDIT_CRITERIA,
    OUTLOOK_AUDIT_CRITERIA,
    PERSPECTIVE_AUDIT_CRITERIA,
    PUBLIC_EDITOR_AUDIT_CRITERIA,
    PUBLIC_REPORTER_AUDIT_CRITERIA,
    RECRUITER_AUDIT_CRITERIA,
    SEARCH_AUDIT_CRITERIA,
)
from agents.bias_agent import get_bias_agent
from agents.config import resolve_model
from agents.dispute_agent import get_dispute_agent
from agents.evidence_verifier import (
    format_verification_report,
    verify_analysis_evidence,
)
from agents.expert_agent import (
    get_domain_expert_agent,
    get_expert_domain_selector,
    get_roundtable_summarizer,
)
from agents.fact_agent import get_fact_agent
from agents.outlook_agent import get_outlook_agent
from agents.public_editor_agent import get_public_editor_agent
from agents.public_reporter_agent import get_public_reporter_agent
from agents.recruiter_agent import get_recruiter_agent
from agents.review_agent import get_review_agent
from agents.schemas import AuditResult
from agents.search_agent import get_search_agent

ROUTE_PROCEED = "proceed"
ROUTE_ABORT = "abort"

FAILED_SEARCH_STATUSES = {
    "no_results",
    "insufficient_corroboration",
    "unverified",
    "doubtful",
    "false_or_nonexistent",
}

STEP_KEYS = (
    "review",
    "search",
    "recruiter",
    "fact_bias",
    "dispute",
    "bias_agent",
    "expert",
    "outlook",
    "public_report",
    "public_editor",
)


class WorkflowStoppedException(Exception):
    """Exception raised when the workflow is stopped by the user."""


def to_prompt_json(data: Any) -> str:
    """Serializes structured data for prompt interpolation."""
    return json.dumps(data, ensure_ascii=False, default=str)


def articles_overview(articles_data: dict | None) -> dict:
    """Metadata-only view of the search output for agents that decide, not read.

    Drops the full content snippets so decision-only prompts (e.g. the
    recruiter's) stay small.
    """
    articles_data = articles_data or {}
    keep = (
        "title",
        "source",
        "url",
        "published_date",
        "bias_category",
        "media_scale",
        "media_type",
        "summary",
        "source_reliability_score",
        "objectivity_score",
        "wire_service",
        "duplicate_cluster",
    )
    return {
        "topic": articles_data.get("topic", ""),
        "query_used": articles_data.get("query_used", ""),
        "search_status": articles_data.get("search_status", ""),
        "verification_summary": articles_data.get("verification_summary", ""),
        "source_balance": articles_data.get("source_balance", {}),
        "warnings": articles_data.get("warnings", []),
        "articles": [
            {key: article.get(key) for key in keep if key in article}
            for article in articles_data.get("articles", [])
        ],
    }


def feedback_suffix(feedback: str, suggestions: list[str]) -> str:
    if not feedback:
        return ""
    return f"\n\nFeedback from Auditor: {feedback}\nSuggestions: {', '.join(suggestions)}"


def _normalize_dispute_claim(claim: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", claim.lower())
    return " ".join(normalized.split())


def merge_disputed_claims(
    fact_disputes: list[dict] | None, dispute_agent_disputes: list[dict] | None
) -> list[dict]:
    """Preserve fact-agent disputes and append unique standalone dispute-agent claims."""
    merged = []
    seen_claims = set()

    for item in (fact_disputes or []) + (dispute_agent_disputes or []):
        dedupe_text = str(item.get("claim") or item.get("dispute_question") or "")
        normalized_claim = _normalize_dispute_claim(dedupe_text)
        if not normalized_claim:
            side_a = str(item.get("side_a_assertion", ""))
            side_b = str(item.get("side_b_assertion", ""))
            normalized_claim = _normalize_dispute_claim(f"{side_a} {side_b}")
        if normalized_claim in seen_claims:
            continue
        seen_claims.add(normalized_claim)
        merged.append(item)

    return merged


def get_audit_agent(
    agent_name: str, criteria: str, model_name: str | None = None
) -> Agent:
    return Agent(
        name=f"{agent_name}_audit",
        model=resolve_model(model_name),
        instruction=(
            f"You are the Audit Agent for '{agent_name}'. Your task is to audit the output of '{agent_name}' "
            f"against the following criteria:\n\n{criteria}\n\n"
            "Evaluate the output. Return structured JSON matching AuditResult. "
            "Be constructive, practical, and lenient: set `is_approved` to `true` unless there is a severe, "
            "critical violation of the criteria (such as extreme bias, unsafe content, or completely missing "
            "required structure). For minor gaps or stylistic preferences, approve the output (set is_approved "
            "to true) but provide suggestions/feedback for future improvements. Only reject (set is_approved to "
            "false) if the output is completely unusable or directly violates a core requirement. "
            "If a deterministic verification report is provided and `passed` is false, treat that as a core "
            "requirement failure and set `is_approved` to false with concrete fixes."
        ),
        output_schema=AuditResult,
        output_key="audit_result",
    )


@dataclass
class PipelineRun:
    """Mutable per-run context shared by the workflow stage closures.

    Holds everything that cannot travel through session state: live progress
    callbacks, the cross-thread control dict from the UI, and the accumulating
    result fields used to assemble the final report.
    """

    topic: str
    model_name: str
    enable_editor: bool = True
    bypass_input_check: bool = False
    progress_callback: Callable[..., Awaitable[None]] | None = None
    control_state: dict | None = None
    results_dict: dict | None = None

    optimized_query: str = ""
    review_result: dict | None = None
    articles_data: dict | None = None
    recruitment_result: dict = field(default_factory=dict)
    facts_data: dict = field(
        default_factory=lambda: {
            "consensus_facts": [],
            "timeline_events": [],
            "timeline": [],
        }
    )
    dispute_data: dict = field(default_factory=lambda: {"disputed_claims": []})
    bias_data: dict = field(
        default_factory=lambda: {
            "profiles": [],
            "key_rhetorical_differences": "No media profiling recruited.",
        }
    )
    expert_data: dict = field(
        default_factory=lambda: {
            "expert_opinions": [],
            "roundtable_summary": "No expert roundtable recruited.",
        }
    )
    outlook_data: dict = field(
        default_factory=lambda: {
            "most_likely_scenario": None,
            "alternative_scenarios": [],
            "monitoring_indicators": [],
        }
    )
    public_report: dict | None = None
    public_editor_report: str = ""
    public_editor_warnings: list = field(default_factory=list)

    editor_logs: list = field(default_factory=list)
    unresolved_audit_warnings: list = field(default_factory=list)
    rejected: bool = False
    search_failed: bool = False
    stopped: bool = False
    final_result: dict = field(default_factory=dict)

    def __post_init__(self):
        self.optimized_query = self.optimized_query or self.topic

    @property
    def audit_revision_cycles(self) -> int:
        return 2 if self.enable_editor else 0

    async def call(self, step: str, message: str, payload: dict | None = None):
        if not self.progress_callback:
            return
        try:
            await self.progress_callback(step, message, payload)
        except TypeError:
            await self.progress_callback(step, message)

    def set_status(self, step: str, status: str):
        if self.control_state is not None:
            self.control_state.setdefault("step_statuses", {})[step] = status

    def update_results(self, **values):
        if self.results_dict is not None:
            self.results_dict.update(values)

    async def should_stop(self) -> bool:
        """Waits out a pause and reports whether the user stopped the run.

        The pause gate is a `threading.Event` set from the UI thread
        ("resume_event": set = running, cleared = paused; a stop also sets it
        so the wait wakes immediately). Falls back to flag polling when the
        control dict carries no event.
        """
        if self.stopped:
            return True
        if not self.control_state:
            return False
        control = self.control_state.get("control", {})
        if control.get("stopped"):
            self.stopped = True
            return True
        if control.get("paused"):
            self.control_state["status"] = "paused"
            resume_gate = control.get("resume_event")
            if resume_gate is not None:
                await asyncio.to_thread(resume_gate.wait)
            else:
                while control.get("paused") and not control.get("stopped"):
                    await asyncio.sleep(0.2)
            if control.get("stopped"):
                self.stopped = True
                return True
            self.control_state["status"] = "running"
        return False

    def add_unresolved(self, agent_name: str, step_name: str):
        related_logs = [
            log for log in self.editor_logs if log.get("agent") == agent_name
        ]
        last_log = related_logs[-1] if related_logs else {}
        feedback = last_log.get("feedback", "Audit did not approve the output.")
        self.unresolved_audit_warnings.append(
            {
                "agent": agent_name,
                "step": step_name,
                "feedback": feedback,
                "recommended_fixes": last_log.get("recommended_fixes", []),
            }
        )


async def dispatch_agent(ctx: Context, agent: Agent, prompt_text: str) -> Any:
    """Runs an LlmAgent as an isolated dynamic workflow node.

    The unique isolation scope guarantees the agent's LLM context contains
    only this prompt (and its own tool calls), even when other stages dispatch
    agents concurrently in the same session.
    """
    return await ctx.run_node(
        node(agent, retry_config=RetryConfig(max_attempts=3, initial_delay=2.0)),
        node_input=prompt_text,
        override_isolation_scope=f"{agent.name}_{uuid.uuid4().hex[:8]}",
    )


async def run_audited(
    ctx: Context,
    run: PipelineRun,
    *,
    step: str,
    agent: Agent,
    criteria: str,
    prompt_builder: Callable[[str, list[str]], str],
    deterministic_check: Callable[[Any], dict] | None = None,
    audit_context_builder: Callable[[Any], str] | None = None,
) -> tuple[Any, bool]:
    """Bounded generate -> deterministic-verify -> audit -> revise loop."""
    feedback_text = ""
    suggestions: list[str] = []
    output_data = None
    max_attempts = run.audit_revision_cycles + 1

    for attempt in range(1, max_attempts + 1):
        if await run.should_stop():
            return output_data, False
        prompt_text = prompt_builder(feedback_text, suggestions)
        output_data = await dispatch_agent(ctx, agent, prompt_text)

        deterministic_report: dict[str, Any] | None = None
        if deterministic_check:
            try:
                deterministic_report = deterministic_check(output_data)
            except Exception as e:
                deterministic_report = {
                    "passed": False,
                    "error_count": 1,
                    "warning_count": 0,
                    "issues": [
                        {
                            "severity": "error",
                            "path": "deterministic_check",
                            "message": f"Deterministic verification failed to run: {e!s}",
                            "fix": "Inspect the verifier input shape and retry.",
                        }
                    ],
                    "summary": "Deterministic verification failed to run.",
                }

        audit_context = ""
        if audit_context_builder:
            try:
                audit_context = str(audit_context_builder(output_data) or "")
            except Exception as e:
                audit_context = f"Audit context generation failed: {e!s}"

        audit_context_parts = []
        if audit_context:
            audit_context_parts.append(f"Additional audit context:\n{audit_context}")
        if deterministic_report:
            audit_context_parts.append(
                "Deterministic verification report:\n"
                f"{format_verification_report(deterministic_report)}"
            )
        audit_context_text = (
            "\n\n".join(audit_context_parts) + "\n\n" if audit_context_parts else ""
        )

        audit_agent = get_audit_agent(agent.name, criteria, model_name=run.model_name)
        audit_prompt = (
            f"Target Agent '{agent.name}' Output:\n{to_prompt_json(output_data)}\n\n"
            f"{audit_context_text}"
            f"Please audit the output against the criteria."
        )
        if await run.should_stop():
            return output_data, False
        await run.call(
            f"{step}_audit", f"Auditing {agent.name} (Attempt {attempt})..."
        )
        audit_result = await dispatch_agent(ctx, audit_agent, audit_prompt)

        is_approved = audit_result.get("is_approved", False) if audit_result else False
        feedback_items = (
            list(audit_result.get("audit_feedback", [])) if audit_result else []
        )
        suggestions = (
            list(audit_result.get("recommended_fixes", [])) if audit_result else []
        )
        if not audit_result:
            feedback_items.append("Audit agent returned no structured result.")

        if deterministic_report and not deterministic_report.get("passed", True):
            is_approved = False
            verification_feedback = deterministic_report.get(
                "summary", "Deterministic verification failed."
            )
            feedback_items.insert(0, verification_feedback)
            verification_fixes = [
                issue.get("fix") or issue.get("message", "")
                for issue in deterministic_report.get("issues", [])
                if issue.get("severity") == "error"
            ]
            suggestions = list(
                dict.fromkeys([fix for fix in verification_fixes if fix] + suggestions)
            )

        feedback_text = "; ".join(dict.fromkeys(feedback_items))

        run.editor_logs.append(
            {
                "agent": agent.name,
                "step": step,
                "attempt": attempt,
                "loop": f"{agent.name} - Attempt {attempt}",
                "approved": is_approved,
                "feedback": feedback_text,
                "audit_feedback": feedback_items,
                "recommended_fixes": suggestions,
                "suggestions": suggestions,
                "deterministic_verification": deterministic_report,
            }
        )

        if is_approved:
            await run.call(
                f"{step}_approved", f"{agent.name} output approved by Audit Agent."
            )
            return output_data, True

        await run.call(
            f"{step}_rejected",
            f"{agent.name} rejected: {feedback_text}. "
            + ("Revising..." if attempt < max_attempts else "Revision limit reached."),
        )

    return output_data, False


def build_news_workflow(run: PipelineRun) -> Workflow:
    """Builds the analysis Workflow graph around a per-run context object."""
    model = run.model_name

    # --- Stage functions (FunctionNodes) ---

    async def review_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            ctx.route = ROUTE_ABORT
            return None
        run.set_status("review", "running")
        await run.call("review", "Spawning Input Check Agent...")

        if run.bypass_input_check:
            run.review_result = {
                "is_safe": True,
                "is_news_relevant": True,
                "suggested_query_formulation": run.topic,
                "rejection_reason": None,
                "input_issue_type": "clear_news_query",
                "user_message": "Bypassed input check.",
                "suggested_options": [],
                "auto_modified": False,
                "needs_user_confirmation": False,
                "confidence": 1.0,
            }
            await run.call("review_approved", "Input check bypassed.")
        else:
            review_agent = get_review_agent(model)

            def review_prompt_gen(f, s):
                return f"Audit this input news topic: '{run.topic}'" + feedback_suffix(
                    f, s
                )

            run.review_result, review_ok = await run_audited(
                ctx,
                run,
                step="review",
                agent=review_agent,
                criteria=INPUT_AUDIT_CRITERIA,
                prompt_builder=review_prompt_gen,
            )
            if run.stopped:
                ctx.route = ROUTE_ABORT
                return None
            if not review_ok:
                run.add_unresolved(review_agent.name, "review")

        review_result = run.review_result
        if (
            not review_result
            or not review_result.get("is_safe", True)
            or not review_result.get("is_news_relevant", True)
        ):
            run.set_status("review", "failed")
            run.rejected = True
            ctx.route = ROUTE_ABORT
            return review_result

        run.set_status("review", "completed")
        run.optimized_query = review_result.get(
            "suggested_query_formulation", run.topic
        )
        run.update_results(
            review_result=review_result,
            optimized_query=run.optimized_query,
            reviewed=True,
        )
        await run.call(
            "review_complete",
            f"Input check passed. Query: '{run.optimized_query}'",
            {"review_result": review_result},
        )
        ctx.route = ROUTE_PROCEED
        return review_result

    async def search_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            ctx.route = ROUTE_ABORT
            return None
        run.set_status("search", "running")
        await run.call(
            "search", f"Searching news articles for: '{run.optimized_query}'..."
        )
        search_agent = get_search_agent(model)

        def search_prompt_gen(f, s):
            return (
                f"Search and categorize 15-18 articles for topic: '{run.optimized_query}'."
                + feedback_suffix(f, s)
            )

        articles_data, search_ok = await run_audited(
            ctx,
            run,
            step="search",
            agent=search_agent,
            criteria=SEARCH_AUDIT_CRITERIA,
            prompt_builder=search_prompt_gen,
        )
        if run.stopped:
            ctx.route = ROUTE_ABORT
            return None
        if not search_ok:
            run.add_unresolved(search_agent.name, "search")
        run.articles_data = articles_data

        search_status = str(
            (articles_data or {}).get("search_status", "verified")
        ).lower()
        if (
            not articles_data
            or not articles_data.get("articles")
            or search_status in FAILED_SEARCH_STATUSES
        ):
            run.set_status("search", "failed")
            run.search_failed = True
            ctx.route = ROUTE_ABORT
            return articles_data

        if articles_data.get("corrected_query"):
            run.optimized_query = articles_data["corrected_query"]

        run.set_status("search", "completed")
        run.update_results(articles=articles_data, optimized_query=run.optimized_query)
        await run.call("search_complete", "Search complete.", articles_data)
        ctx.route = ROUTE_PROCEED
        return articles_data

    async def recruiter_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        run.set_status("recruiter", "running")
        await run.call("recruiter", "Spawning Recruiter Agent to allocate modules...")
        recruiter_agent = get_recruiter_agent(model)
        overview_json = to_prompt_json(articles_overview(run.articles_data))

        def recruiter_prompt_gen(f, s):
            return (
                "Analyze these articles and decide agent recruitment:\n"
                f"{overview_json}" + feedback_suffix(f, s)
            )

        recruitment_result, recruit_ok = await run_audited(
            ctx,
            run,
            step="recruiter",
            agent=recruiter_agent,
            criteria=RECRUITER_AUDIT_CRITERIA,
            prompt_builder=recruiter_prompt_gen,
        )
        if run.stopped:
            return None

        if not recruitment_result:
            recruitment_result = {
                "recruit_dispute": True,
                "recruit_perspective": True,
                "recruit_expert": True,
                "recruit_future_outlook": True,
                "recruitment_justification": "Fallback recruitment plan after empty recruiter output.",
                "complexity_level": "moderate",
                "recruited_agents": [
                    "Dispute Agent",
                    "Perspective Agent",
                    "Expert Agent",
                    "Future Outlook Agent",
                ],
                "skipped_agents": [],
            }
        if not recruit_ok:
            run.add_unresolved(recruiter_agent.name, "recruiter")
        run.recruitment_result = recruitment_result

        run.set_status("recruiter", "completed")
        if not recruitment_result.get("recruit_dispute", True):
            run.set_status("dispute", "skipped")
        if not recruitment_result.get("recruit_perspective", True):
            run.set_status("bias_agent", "skipped")
        if not recruitment_result.get("recruit_expert", True):
            run.set_status("expert", "skipped")
        if not recruitment_result.get("recruit_future_outlook", True):
            run.set_status("outlook", "skipped")

        run.update_results(recruitment=recruitment_result)
        await run.call(
            "recruiter_complete", "Recruitment options finalized.", recruitment_result
        )
        return recruitment_result

    async def fact_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        run.set_status("fact_bias", "running")
        await run.call("fact_bias", "Running Fact & Consensus Analyzer...")
        fact_agent = get_fact_agent(model)
        articles_json = to_prompt_json(run.articles_data)

        def fact_prompt_gen(f, s):
            return (
                f"Topic: {run.topic}\n"
                "Analyze these articles to find verified consensus facts and timeline:\n"
                f"{articles_json}" + feedback_suffix(f, s)
            )

        facts, fact_ok = await run_audited(
            ctx,
            run,
            step="fact_bias",
            agent=fact_agent,
            criteria=FACT_AUDIT_CRITERIA,
            prompt_builder=fact_prompt_gen,
            deterministic_check=lambda output: verify_analysis_evidence(
                run.articles_data, facts_data=output
            ),
        )
        if run.stopped:
            return None
        if facts:
            run.facts_data = facts
        if not fact_ok:
            run.add_unresolved(fact_agent.name, "fact_bias")
        run.set_status("fact_bias", "completed")
        run.update_results(facts=run.facts_data)
        return run.facts_data

    async def dispute_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        if not run.recruitment_result.get("recruit_dispute", True):
            return None
        run.set_status("dispute", "running")
        await run.call("dispute", "Recruiting Dispute Agent...")
        dispute_agent = get_dispute_agent(model)
        articles_json = to_prompt_json(run.articles_data)

        def dispute_prompt_gen(f, s):
            return (
                f"Topic: {run.topic}\n"
                "Analyze these articles and extract contradictory claims:\n"
                f"{articles_json}" + feedback_suffix(f, s)
            )

        disputes, dispute_ok = await run_audited(
            ctx,
            run,
            step="dispute",
            agent=dispute_agent,
            criteria=DISPUTE_AUDIT_CRITERIA,
            prompt_builder=dispute_prompt_gen,
            deterministic_check=lambda output: verify_analysis_evidence(
                run.articles_data, dispute_data=output
            ),
        )
        if run.stopped:
            return None
        if disputes:
            run.dispute_data = disputes
        if not dispute_ok:
            run.add_unresolved(dispute_agent.name, "dispute")
        run.set_status("dispute", "completed")
        await run.call("dispute_complete", "Disputes mapped successfully.")
        return run.dispute_data

    async def perspective_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        if not run.recruitment_result.get("recruit_perspective", True):
            return None
        run.set_status("bias_agent", "running")
        await run.call("bias_agent", "Recruiting Perspective Agent...")
        bias_agent = get_bias_agent(model)
        articles_json = to_prompt_json(run.articles_data)

        def bias_prompt_gen(f, s):
            return (
                f"Topic: {run.topic}\n"
                "Classification Axis: Dynamically determined by you based on the articles\n"
                f"Analyze framing & omissions:\n{articles_json}" + feedback_suffix(f, s)
            )

        narratives, bias_ok = await run_audited(
            ctx,
            run,
            step="bias_agent",
            agent=bias_agent,
            criteria=PERSPECTIVE_AUDIT_CRITERIA,
            prompt_builder=bias_prompt_gen,
            deterministic_check=lambda output: verify_analysis_evidence(
                run.articles_data, narratives_data=output
            ),
        )
        if run.stopped:
            return None
        if narratives:
            run.bias_data = narratives
        if not bias_ok:
            run.add_unresolved(bias_agent.name, "bias_agent")
        run.set_status("bias_agent", "completed")
        run.update_results(narratives=run.bias_data)
        return run.bias_data

    async def merge_stage(ctx: Context, node_input: Any):
        if run.stopped:
            return None
        # Expose the Dispute Agent's claims on facts_data for dashboard compatibility
        run.facts_data["disputed_claims"] = merge_disputed_claims(
            run.facts_data.get("disputed_claims", []),
            run.dispute_data.get("disputed_claims", []),
        )
        run.update_results(facts=run.facts_data)

        if run.recruitment_result.get("recruit_perspective", True):
            message = "Factual & Perspective profiling completed."
        else:
            message = "Fact extraction completed."
        await run.call(
            "fact_bias_complete",
            message,
            {"facts": run.facts_data, "narratives": run.bias_data},
        )
        return {"facts": run.facts_data, "narratives": run.bias_data}

    async def expert_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        if not run.recruitment_result.get("recruit_expert", True):
            return None
        run.set_status("expert", "running")
        await run.call("expert", "Selecting expert domains...")

        # Step 1: pick 2-3 expert domains for this topic
        selector = get_expert_domain_selector(model)
        selection = await dispatch_agent(
            ctx,
            selector,
            (
                f"Topic: {run.topic}\n"
                f"Consensus Facts: {to_prompt_json(run.facts_data)}\n"
                f"Disputes: {to_prompt_json(run.dispute_data)}\n"
                "Select the 2-3 most appropriate expert domains."
            ),
        )
        domains = [
            str(domain).strip()
            for domain in (selection or {}).get("domains") or []
            if str(domain).strip()
        ][:3]
        if not domains:
            domains = ["Public Policy Analyst", "Media Ethics Analyst"]
        await run.call(
            "expert", f"Recruiting Expert Panel (Domains: {', '.join(domains)})..."
        )

        # Step 2: run one audited expert agent per domain in parallel
        upstream_json = (
            f"Consensus Facts: {to_prompt_json(run.facts_data)}\n"
            f"Disputes: {to_prompt_json(run.dispute_data)}\n"
            f"Media Narratives: {to_prompt_json(run.bias_data)}"
        )

        async def run_one_expert(domain: str):
            expert_agent = get_domain_expert_agent(domain, model)

            def expert_prompt_gen(f, s):
                return (
                    f"Topic: {run.topic}\n{upstream_json}\n\n"
                    f"Provide your commentary as '{domain}'." + feedback_suffix(f, s)
                )

            opinion, ok = await run_audited(
                ctx,
                run,
                step="expert",
                agent=expert_agent,
                criteria=EXPERT_AUDIT_CRITERIA,
                prompt_builder=expert_prompt_gen,
                deterministic_check=lambda output: verify_analysis_evidence(
                    run.articles_data,
                    experts_data={"expert_opinions": [output] if output else []},
                ),
            )
            if not ok and not run.stopped:
                run.add_unresolved(expert_agent.name, "expert")
            return opinion

        opinions = [
            opinion
            for opinion in await asyncio.gather(
                *(run_one_expert(domain) for domain in domains)
            )
            if opinion
        ]
        if run.stopped:
            return None

        # Step 3: moderator synthesizes the roundtable summary
        roundtable_summary = ""
        if opinions:
            summarizer = get_roundtable_summarizer(model)
            summary_result = await dispatch_agent(
                ctx,
                summarizer,
                f"Topic: {run.topic}\nExpert commentaries:\n{to_prompt_json(opinions)}",
            )
            roundtable_summary = (summary_result or {}).get("roundtable_summary", "")

        run.expert_data = {
            "expert_opinions": opinions,
            "roundtable_summary": roundtable_summary
            or "No expert commentary could be produced.",
        }
        run.set_status("expert", "completed")
        run.update_results(experts=run.expert_data)
        await run.call(
            "expert_complete", "Expert Roundtable analysis completed.", run.expert_data
        )
        return run.expert_data

    async def outlook_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        if not run.recruitment_result.get("recruit_future_outlook", True):
            return None
        run.set_status("outlook", "running")
        await run.call("outlook", "Recruiting Future Outlook Agent...")
        outlook_agent = get_outlook_agent(model)

        def outlook_prompt_gen(f, s):
            return (
                f"Topic: {run.topic}\n"
                f"Facts: {to_prompt_json(run.facts_data)}\n"
                f"Media Narratives: {to_prompt_json(run.bias_data)}"
                + feedback_suffix(f, s)
            )

        outlook, outlook_ok = await run_audited(
            ctx,
            run,
            step="outlook",
            agent=outlook_agent,
            criteria=OUTLOOK_AUDIT_CRITERIA,
            prompt_builder=outlook_prompt_gen,
            deterministic_check=lambda output: verify_analysis_evidence(
                run.articles_data, outlook_data=output
            ),
        )
        if run.stopped:
            return None
        if outlook:
            run.outlook_data = outlook
        if not outlook_ok:
            run.add_unresolved(outlook_agent.name, "outlook")
        run.set_status("outlook", "completed")
        run.update_results(outlook=run.outlook_data)
        await run.call("outlook_complete", "Future scenarios generated.")
        return run.outlook_data

    async def public_report_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        run.set_status("public_report", "running")
        await run.call(
            "public_report", "Spawning Public Reporter Agent to write summary..."
        )
        public_reporter = get_public_reporter_agent(model)

        prompt_public = (
            f"Topic: {run.topic}\n"
            f"Consensus & Disputes: {to_prompt_json(run.facts_data)}\n"
            f"Media Narratives: {to_prompt_json(run.bias_data)}\n"
            f"Expert Panel Commentary: {to_prompt_json(run.expert_data)}\n"
            f"Future Outlook Scenarios: {to_prompt_json(run.outlook_data)}\n\n"
            "Compile a comprehensive public summary report."
        )

        def public_report_prompt_gen(f, s):
            return prompt_public + feedback_suffix(f, s)

        def public_report_audit_context(_output):
            return json.dumps(
                {
                    "verified_facts": run.facts_data,
                    "media_narratives": run.bias_data,
                    "expert_panel": run.expert_data,
                    "future_outlook": run.outlook_data,
                    "unresolved_audit_warnings": run.unresolved_audit_warnings,
                },
                ensure_ascii=True,
            )

        public_report, public_report_ok = await run_audited(
            ctx,
            run,
            step="public_report",
            agent=public_reporter,
            criteria=PUBLIC_REPORTER_AUDIT_CRITERIA,
            prompt_builder=public_report_prompt_gen,
            deterministic_check=lambda output: verify_analysis_evidence(
                run.articles_data, report_data=output
            ),
            audit_context_builder=public_report_audit_context,
        )
        if run.stopped:
            return None
        run.public_report = public_report
        if not public_report_ok:
            run.add_unresolved(public_reporter.name, "public_report")
        run.set_status("public_report", "completed")
        run.update_results(public_report=public_report)
        await run.call(
            "public_report_complete", "Public report completed.", public_report
        )
        return public_report

    async def public_editor_stage(ctx: Context, node_input: Any):
        if await run.should_stop():
            return None
        run.set_status("public_editor", "running")
        await run.call(
            "public_editor",
            "Spawning Public Editor Agent to build consolidated dashboard...",
        )
        public_editor_agent = get_public_editor_agent(model)

        def public_editor_prompt_gen(f, s):
            return (
                f"Topic: {run.topic}\n"
                f"Public Summary Report (with citations): {to_prompt_json(run.public_report)}\n"
                f"Consensus & Facts: {to_prompt_json(run.facts_data)}\n"
                f"Media Narratives: {to_prompt_json(run.bias_data)}\n"
                f"Expert Commentary: {to_prompt_json(run.expert_data)}\n"
                f"Future Scenarios: {to_prompt_json(run.outlook_data)}\n"
                f"Unresolved Audit Warnings: {to_prompt_json(run.unresolved_audit_warnings)}"
                + feedback_suffix(f, s)
            )

        public_editor_data, editor_ok = await run_audited(
            ctx,
            run,
            step="public_editor",
            agent=public_editor_agent,
            criteria=PUBLIC_EDITOR_AUDIT_CRITERIA,
            prompt_builder=public_editor_prompt_gen,
        )
        if run.stopped:
            return None
        if not public_editor_data:
            public_editor_data = {"markdown_report": "", "unresolved_warnings": []}
        run.public_editor_report = public_editor_data.get("markdown_report", "")
        run.public_editor_warnings = public_editor_data.get("unresolved_warnings", [])
        if not editor_ok:
            run.add_unresolved(public_editor_agent.name, "public_editor")
        run.set_status("public_editor", "completed")
        run.update_results(
            public_editor_report=run.public_editor_report,
            public_editor_warnings=run.public_editor_warnings,
        )
        await run.call(
            "public_editor_complete",
            "Public consolidated dashboard ready.",
            run.public_editor_report,
        )
        return public_editor_data

    async def finalize_stage(ctx: Context, node_input: Any):
        if run.stopped:
            if run.control_state is not None:
                statuses = run.control_state.get("step_statuses", {})
                for step, status in list(statuses.items()):
                    if status in ["queued", "running"]:
                        statuses[step] = "stopped"
            res = {
                "reviewed": run.review_result is not None,
                "topic": run.topic,
                "optimized_query": run.optimized_query,
                "review_result": run.review_result or {},
                "articles": run.articles_data or {},
                "recruitment": run.recruitment_result,
                "facts": run.facts_data,
                "narratives": run.bias_data,
                "experts": run.expert_data,
                "outlook": run.outlook_data,
                "public_report": run.public_report or {},
                "public_editor_report": run.public_editor_report,
                "public_editor_warnings": run.public_editor_warnings,
                "editor_logs": run.editor_logs,
                "audit_warnings": run.unresolved_audit_warnings,
                "is_approved": False,
                "stopped": True,
            }
        elif run.rejected:
            res = {
                "reviewed": False,
                "review_result": run.review_result
                or {
                    "is_safe": False,
                    "is_news_relevant": False,
                    "suggested_query_formulation": run.topic,
                    "rejection_reason": "Failed input check audit.",
                },
                "editor_logs": run.editor_logs,
                "audit_warnings": run.unresolved_audit_warnings,
            }
        elif run.search_failed:
            res = {
                "reviewed": True,
                "search_failed": True,
                "topic": run.topic,
                "optimized_query": run.optimized_query,
                "review_result": run.review_result,
                "search_result": run.articles_data or {},
                "editor_logs": run.editor_logs,
                "audit_warnings": run.unresolved_audit_warnings,
                "is_approved": False,
            }
        else:
            is_approved = not run.unresolved_audit_warnings
            await run.call(
                "editor_complete",
                "All audits completed.",
                {
                    "editor_logs": run.editor_logs,
                    "audit_warnings": run.unresolved_audit_warnings,
                    "is_approved": is_approved,
                },
            )
            res = {
                "reviewed": True,
                "topic": run.topic,
                "optimized_query": run.optimized_query,
                "review_result": run.review_result,
                "articles": run.articles_data,
                "recruitment": run.recruitment_result,
                "facts": run.facts_data,
                "narratives": run.bias_data,
                "experts": run.expert_data,
                "outlook": run.outlook_data,
                "public_report": run.public_report,
                "public_editor_report": run.public_editor_report,
                "public_editor_warnings": run.public_editor_warnings,
                "editor_logs": run.editor_logs,
                "audit_warnings": run.unresolved_audit_warnings,
                "is_approved": is_approved,
            }

        run.update_results(**res)
        run.final_result = res
        return res

    # --- Graph assembly ---

    review = node(review_stage, name="review", rerun_on_resume=True)
    search = node(search_stage, name="search", rerun_on_resume=True)
    recruiter = node(recruiter_stage, name="recruiter", rerun_on_resume=True)
    fact = node(fact_stage, name="fact", rerun_on_resume=True)
    dispute = node(dispute_stage, name="dispute", rerun_on_resume=True)
    perspective = node(perspective_stage, name="perspective", rerun_on_resume=True)
    analysis_join = JoinNode(name="analysis_join")
    merge = node(merge_stage, name="merge", rerun_on_resume=True)
    expert = node(expert_stage, name="expert", rerun_on_resume=True)
    outlook = node(outlook_stage, name="outlook", rerun_on_resume=True)
    synthesis_join = JoinNode(name="synthesis_join")
    public_report = node(
        public_report_stage, name="public_report", rerun_on_resume=True
    )
    public_editor = node(
        public_editor_stage, name="public_editor", rerun_on_resume=True
    )
    finalize = node(finalize_stage, name="finalize", rerun_on_resume=True)

    edges = [
        Edge(from_node=WORKFLOW_START, to_node=review),
        Edge(from_node=review, to_node=search, route=ROUTE_PROCEED),
        Edge(from_node=review, to_node=finalize, route=ROUTE_ABORT),
        Edge(from_node=search, to_node=recruiter, route=ROUTE_PROCEED),
        Edge(from_node=search, to_node=finalize, route=ROUTE_ABORT),
        Edge(from_node=recruiter, to_node=fact),
        Edge(from_node=recruiter, to_node=dispute),
        Edge(from_node=recruiter, to_node=perspective),
        Edge(from_node=fact, to_node=analysis_join),
        Edge(from_node=dispute, to_node=analysis_join),
        Edge(from_node=perspective, to_node=analysis_join),
        Edge(from_node=analysis_join, to_node=merge),
        Edge(from_node=merge, to_node=expert),
        Edge(from_node=merge, to_node=outlook),
        Edge(from_node=expert, to_node=synthesis_join),
        Edge(from_node=outlook, to_node=synthesis_join),
        Edge(from_node=synthesis_join, to_node=public_report),
        Edge(from_node=public_report, to_node=public_editor),
        Edge(from_node=public_editor, to_node=finalize),
    ]

    return Workflow(name="news_analysis_pipeline", edges=edges)
