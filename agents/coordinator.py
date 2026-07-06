import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.bias_agent import get_bias_agent
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
from agents.public_reporter_agent import get_public_reporter_agent
from agents.report_renderer import render_public_editor_report
from agents.recruiter_agent import get_recruiter_agent
from agents.input_check_agent import get_input_check_agent
from agents.schemas import AuditResult, InputValidationResult
from agents.search_agent import get_search_agent
from agents.web_tools import is_transient_error


class WorkflowStoppedException(Exception):
    """Exception raised when the workflow is stopped by the user."""

    pass

# --- Audit Criteria Definitions ---
INPUT_AUDIT_CRITERIA = (
    "1. The action must be exactly one of: 'accept', 'accept_with_notification', 'reject_with_confirmation', 'convert'.\n"
    "2. If the input does not contain a URL or a copy-pasted article or paragraph, the action must not be convert, and converted_query must be null.\n"
    "3. If the input contains a URL or copy-pasted article, the action must be 'convert'.\n"
    "4. If action is 'convert', check if the URL/article is news-related. If it is, converted_query must be populated. If it is not, the action must be 'reject_with_confirmation'.\n"
    "5. If action is 'accept_with_notification' or 'reject_with_confirmation', notification_message must be populated."
)


SEARCH_AUDIT_CRITERIA = (
    "1. Ideological balance (Left, Right, Center, Other/Non-Political) is preferred but optional. DO NOT reject if the search query simply returns limited viewpoints or articles.\n"
    "2. Wire service grouping should be checked, but do not reject if grouping is not applicable or minor.\n"
    "3. Verify search_status, verification_summary, warnings, query_used, and corrected_query are populated consistently.\n"
    "4. Crucially: Do not invent articles if unsupported by search. Only reject if the Search Agent invents completely fake articles or fails to return any results for a known topic."
)

RECRUITER_AUDIT_CRITERIA = "1. Verify recruitment decisions: only recruit Dispute, Expert, Perspective, and Future Outlook agents if needed. Keep simple topics non-recruited."

FACT_AUDIT_CRITERIA = (
    "1. Verify factual neutrality: no evaluative adjectives or loaded terms.\n"
    "2. Each consensus fact must have at least two independent sources and a valid, detailed explanation of why it is considered a fact.\n"
    "3. Verify dates and timelines are chronologically consistent and cited accurately with URLs and short quotes.\n"
    "4. Verify the structured timeline includes evidence objects, not only uncited prose."
)

DISPUTE_AUDIT_CRITERIA = (
    "1. Verify schema compliance with DisputeList and DisputeItem, including claim, side assertions, "
    "source lists, and evidence fields.\n"
    "2. Maintain neutral, non-loaded language; do not validate either side or use judgmental wording.\n"
    "3. Verify source traceability: evidence should include source, title when available, quote or snippet, "
    "and URL where available. Do not approve hallucinated quotes, URLs, dates, sources, or claims.\n"
    "4. Reject invented or unsupported counter-sides. If one side is weak, under-supported, or absent in "
    "the source set, the output must explicitly warn about unsupported or weak evidence.\n"
    "5. Check that duplicated wire-service reposts or same-cluster articles are not treated as independent "
    "confirmation when metadata reveals duplication.\n"
    "6. Prefer genuine material conflicts over minor wording differences, and require cautious language when "
    "evidence is incomplete."
)

PERSPECTIVE_AUDIT_CRITERIA = (
    "1. Verify schema compliance with PerspectiveProfile and NarrativeProfile, including profiles, "
    "classification_axis when available, evidence, and key_rhetorical_differences.\n"
    "2. Describe narrative frames objectively, respectfully, and with neutral, non-loaded language; avoid "
    "over-generalizing political, social, national, or stakeholder groups.\n"
    "3. Verify source traceability: reported perspectives should include representative sources, quote or "
    "snippet evidence, and URL where available. Do not approve hallucinated groups, quotes, URLs, sources, "
    "or claims.\n"
    "4. Ensure the selected classification axis fits the article set, such as ideology, stakeholder role, "
    "geopolitical position, industry role, geography, affected group, or media ecosystem.\n"
    "5. Check that evidence-backed reporting is clearly distinguished from analytical inference or likely "
    "concern. Unsupported or theoretically important perspectives must be marked as speculative or "
    "'not enough source support found', not presented as reported news.\n"
    "6. Ensure there is sufficient diversity of sources and perspectives for the topic, or explicit warnings "
    "for missing, weak, or unsupported evidence.\n"
    "7. Ensure notable omissions are logically based on comparisons across source-supported perspectives."
)

EXPERT_AUDIT_CRITERIA = (
    "1. Ensure the expert's commentary stays within their designated professional domain and matches the news topic context.\n"
    "2. Ensure the commentary cites specific external regulations, economic indicators, or ethical codes.\n"
    "3. Maintain academic, non-partisan commentary."
)

OUTLOOK_AUDIT_CRITERIA = (
    "1. Verify scenario divergence: Most-likely vs Alternative Scenarios must represent distinct logical paths.\n"
    "2. Ensure trigger conditions are specific and observable.\n"
    "3. Use probabilistic language instead of false certainty.\n"
    "4. Ensure scenarios cite upstream evidence and state assumptions/time horizon."
)

PUBLIC_REPORTER_AUDIT_CRITERIA = (
    "1. Ensure the public summary only summarizes upstream verified facts, disputes, expert commentary, and scenarios.\n"
    "2. Ensure it does not introduce new factual claims, stronger certainty, or unsupported causal claims.\n"
    "3. Preserve material caveats, unresolved audit warnings, and uncertainty in public-friendly language.\n"
    "4. Every key takeaway must carry an evidence trail (source, URL, quote) copied from upstream outputs."
)

def get_audit_agent(
    agent_name: str, criteria: str, model_name: str | None = None
) -> Agent:
    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name=f"{agent_name}_audit",
        model=model_name,
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


# --- Coordination Helper Functions ---



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


class NewsAnalysisCoordinator:
    """Coordinator that orchestrates the execution of multiple specialized sub-agents."""

    def __init__(self):
        self.session_service = InMemorySessionService()

    async def _check_controls(self, control_state: dict | None):
        if not control_state:
            return
        if control_state.get("control", {}).get("stopped"):
            raise WorkflowStoppedException("Workflow stopped by user.")
        if control_state.get("control", {}).get("paused"):
            control_state["status"] = "paused"
            while control_state.get("control", {}).get(
                "paused"
            ) and not control_state.get("control", {}).get("stopped"):
                await asyncio.sleep(0.2)
            if control_state.get("control", {}).get("stopped"):
                raise WorkflowStoppedException("Workflow stopped by user.")
            control_state["status"] = "running"

    async def _run_agent(
        self, agent, prompt_text: str, session_id: str, max_retries: int = 3
    ):
        """Helper to invoke an ADK Agent using the Runner and retrieve the structured output state."""
        logger = logging.getLogger(__name__)

        import datetime
        now = datetime.datetime.now()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        local_date = now.strftime('%B %d, %Y')
        utc_date = now_utc.strftime('%B %d, %Y')
        current_date_prefix = (
            f"The current date is {local_date} (local system time) / {utc_date} (UTC). "
            f"Note: news articles may be dated 1 day ahead or behind due to international timezone differences; "
            f"treat such minor discrepancies as valid and current, not as future events or hallucinations.\n"
            f"Do not treat real-world events that occur after your training data cutoff date as fictional, hypothetical, or speculative. If search results and evidence items report them as real news, treat them as authentic real-world events.\n\n"
        )
        if hasattr(agent, "instruction") and agent.instruction and not agent.instruction.startswith("The current date is"):
            agent.instruction = current_date_prefix + agent.instruction

        current_prompt = prompt_text

        for attempt in range(1, max_retries + 1):
            try:
                agent_session_id = f"{session_id}_{agent.name}_{attempt}"

                # Ensure session exists in the service
                session = await self.session_service.get_session(
                    app_name="news_app", user_id="user", session_id=agent_session_id
                )
                if session is None:
                    await self.session_service.create_session(
                        app_name="news_app", user_id="user", session_id=agent_session_id
                    )

                runner = Runner(
                    agent=agent,
                    app_name="news_app",
                    session_service=self.session_service,
                )

                # Execute the agent run to completion
                async for _event in runner.run_async(
                    user_id="user",
                    session_id=agent_session_id,
                    new_message=types.Content(
                        role="user", parts=[types.Part.from_text(text=current_prompt)]
                    ),
                ):
                    pass

                session = await self.session_service.get_session(
                    app_name="news_app", user_id="user", session_id=agent_session_id
                )

                if agent.output_key:
                    val = session.state.get(agent.output_key)
                    if hasattr(val, "model_dump"):
                        return val.model_dump()
                    elif hasattr(val, "dict"):
                        return val.dict()
                    return val
                return None

            except Exception as e:
                if attempt == max_retries:
                    logger.error(
                        "Agent '%s' failed after %d attempts: %s",
                        agent.name,
                        max_retries,
                        e,
                    )
                    raise
                if is_transient_error(e):
                    backoff = 2**attempt
                    logger.warning(
                        "Agent '%s' hit a transient error (attempt %d/%d): %s. "
                        "Retrying in %ds...",
                        agent.name,
                        attempt,
                        max_retries,
                        e,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.warning(
                        "Agent '%s' produced an unusable response (attempt %d/%d): %s. "
                        "Retrying immediately with the error appended to the prompt...",
                        agent.name,
                        attempt,
                        max_retries,
                        e,
                    )
                    current_prompt = (
                        f"{prompt_text}\n\n"
                        f"NOTE: Your previous response could not be processed due to: "
                        f"{e!s}\nEnsure your output is well-formed and matches the "
                        "required schema exactly."
                    )

    async def _run_agent_with_audit(
        self,
        agent,
        prompt_generator,
        criteria: str,
        session_id: str,
        call_callback,
        step_name: str,
        editor_logs: list,
        max_revision_cycles: int = 2,
        control_state: dict | None = None,
        model_name: str | None = None,
        deterministic_check=None,
        audit_context_generator=None,
    ):
        feedback_text = ""
        suggestions = []
        output_data = None
        max_attempts = max_revision_cycles + 1

        for attempt in range(1, max_attempts + 1):
            await self._check_controls(control_state)
            prompt_text = prompt_generator(feedback_text, suggestions)
            output_data = await self._run_agent(agent, prompt_text, session_id)

            deterministic_report = None
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
            if audit_context_generator:
                try:
                    audit_context = str(audit_context_generator(output_data) or "")
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
                "\n\n".join(audit_context_parts) + "\n\n"
                if audit_context_parts
                else ""
            )

            # Spawn Audit Agent
            audit_agent = get_audit_agent(agent.name, criteria, model_name=model_name)
            audit_prompt = (
                f"Target Agent '{agent.name}' Output:\n{output_data}\n\n"
                f"{audit_context_text}"
                f"Please audit the output against the criteria."
            )
            await call_callback(
                f"{step_name}_audit", f"Auditing {agent.name} (Attempt {attempt})..."
            )

            await self._check_controls(control_state)
            audit_result = await self._run_agent(audit_agent, audit_prompt, session_id)

            is_approved = (
                audit_result.get("is_approved", False) if audit_result else False
            )
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
                    dict.fromkeys(
                        [fix for fix in verification_fixes if fix] + suggestions
                    )
                )

            feedback_text = "; ".join(dict.fromkeys(feedback_items))

            editor_logs.append(
                {
                    "agent": agent.name,
                    "step": step_name,
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
                await call_callback(
                    f"{step_name}_approved",
                    f"{agent.name} output approved by Audit Agent.",
                )
                return output_data, True

            await call_callback(
                f"{step_name}_rejected",
                f"{agent.name} rejected: {feedback_text}. "
                + (
                    "Revising..."
                    if attempt < max_attempts
                    else "Revision limit reached."
                ),
            )

        return output_data, False

    async def run_input_check(
        self, topic: str, model_name: str = "gemini-3.1-flash-lite"
    ) -> dict:
        """Run the Input Check Agent synchronously to pre-audit user's input."""
        os.environ["CURRENT_MODEL"] = model_name
        session_id = f"input_check_sess_{uuid.uuid4().hex[:8]}"
        await self.session_service.create_session(
            app_name="news_app", user_id="user", session_id=session_id
        )
        input_agent = get_input_check_agent(model_name)
        prompt_text = f"Validate this input topic: '{topic}'"
        result = await self._run_agent(input_agent, prompt_text, session_id)
        if not result:
            result = {
                "action": "accept",
                "is_news_related": True,
                "explanation": "Failed to get input check result.",
                "notification_message": None,
                "converted_query": None,
            }
        return result

    async def analyze(
        self,
        topic: str,
        progress_callback=None,
        enable_editor: bool = True,
        control_state: dict | None = None,
        results_dict: dict[str, Any] | None = None,
        model_name: str = "gemini-3.1-flash-lite",
        bypass_input_check: bool = False,
    ) -> dict:
        """Runs the news analysis pipeline sequentially with modular sub-agents and audit gates."""
        os.environ["CURRENT_MODEL"] = model_name

        async def call_callback(step: str, message: str, payload: dict | None = None):
            if not progress_callback:
                return
            import inspect

            try:
                sig = inspect.signature(progress_callback)
                has_var_positional = any(
                    p.kind == inspect.Parameter.VAR_POSITIONAL
                    for p in sig.parameters.values()
                )
                num_params = len(sig.parameters)
                if num_params >= 3 or has_var_positional:
                    await progress_callback(step, message, payload)
                else:
                    await progress_callback(step, message)
            except Exception:
                try:
                    await progress_callback(step, message, payload)
                except TypeError:
                    await progress_callback(step, message)

        # Initialize step statuses if control state is provided
        if control_state is not None:
            control_state["step_statuses"] = {
                "input_check": "queued",
                "search": "queued",
                "recruiter": "queued",
                "fact_bias": "queued",
                "dispute": "queued",
                "bias_agent": "queued",
                "expert": "queued",
                "outlook": "queued",
                "public_report": "queued",
                "public_editor": "queued",
            }

        # Initialize unique session and logs
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        await self.session_service.create_session(
            app_name="news_app", user_id="user", session_id=session_id
        )
        editor_logs = []
        unresolved_audit_warnings = []
        # High-risk, user-facing stages (search, fact/dispute/perspective, expert,
        # outlook, public report) get the full revision budget since their output
        # feeds directly into the final briefing. Low-risk routing/gating stages
        # (input check, recruiter) only decide what runs next, not final content,
        # so one revision is enough to catch a bad decision without doubling their
        # LLM-call cost on every run.
        audit_revision_cycles = 2 if enable_editor else 0
        light_revision_cycles = 1 if enable_editor else 0

        def add_unresolved(agent_name: str, step_name: str):
            related_logs = [
                log for log in editor_logs if log.get("agent") == agent_name
            ]
            last_log = related_logs[-1] if related_logs else {}
            feedback = last_log.get("feedback", "Audit did not approve the output.")
            unresolved_audit_warnings.append(
                {
                    "agent": agent_name,
                    "step": step_name,
                    "feedback": feedback,
                    "recommended_fixes": last_log.get("recommended_fixes", []),
                }
            )

        input_check_result = {}
        articles_data = None
        recruitment_result = None
        facts_data = None
        dispute_data = None
        bias_data = None
        expert_data = None
        outlook_data = None
        public_report = None
        public_editor_report = ""
        public_editor_warnings = []
        optimized_query = topic

        try:
            # Step 0: Input Check Agent
            await self._check_controls(control_state)
            if control_state is not None:
                control_state["step_statuses"]["input_check"] = "running"
            await call_callback("input_check", "Spawning Input Check Agent...")

            if bypass_input_check:
                input_check_result = {
                    "action": "accept",
                    "is_news_related": True,
                    "explanation": "Bypassed input check.",
                    "notification_message": None,
                    "converted_query": None,
                }
                input_check_ok = True
                await call_callback("input_check_approved", "Input check bypassed.")
            else:
                input_agent = get_input_check_agent(model_name)

                def input_check_prompt_gen(f, s):
                    return f"Validate this input topic: '{topic}'" + (
                        f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                        if f
                        else ""
                    )

                input_check_result, input_check_ok = await self._run_agent_with_audit(
                    input_agent,
                    input_check_prompt_gen,
                    INPUT_AUDIT_CRITERIA,
                    session_id,
                    call_callback,
                    "input_check",
                    editor_logs,
                    max_revision_cycles=light_revision_cycles,
                    control_state=control_state,
                    model_name=model_name,
                )

            if not input_check_ok:
                add_unresolved(input_agent.name, "input_check")

            action = input_check_result.get("action", "accept")
            if action == "reject_with_confirmation":
                if control_state is not None:
                    control_state["step_statuses"]["input_check"] = "failed"
                res = {
                    "input_checked": False,
                    "input_check_result": input_check_result,
                    "editor_logs": editor_logs,
                    "audit_warnings": unresolved_audit_warnings,
                }
                if results_dict is not None:
                    results_dict.update(res)
                return res

            if control_state is not None:
                control_state["step_statuses"]["input_check"] = "completed"

            if action == "convert" and input_check_result.get("is_news_related", True):
                optimized_query = input_check_result.get("converted_query") or topic
            else:
                optimized_query = topic

            if results_dict is not None:
                results_dict["input_check_result"] = input_check_result
                results_dict["optimized_query"] = optimized_query
                results_dict["input_checked"] = True

            await call_callback(
                "input_check_complete",
                f"Input check passed with action '{action}'. Query: '{optimized_query}'",
                {"input_check_result": input_check_result},
            )

            # Step 1: Search Agent
            await self._check_controls(control_state)
            if control_state is not None:
                control_state["step_statuses"]["search"] = "running"
            await call_callback(
                "search", f"Searching news articles for: '{optimized_query}'..."
            )
            search_agent = get_search_agent(model_name)

            def search_prompt_gen(f, s):
                return (
                    f"Search and categorize 15-18 articles for topic: '{optimized_query}'."
                    + (
                        f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                        if f
                        else ""
                    )
                )

            articles_data, search_ok = await self._run_agent_with_audit(
                search_agent,
                search_prompt_gen,
                SEARCH_AUDIT_CRITERIA,
                session_id,
                call_callback,
                "search",
                editor_logs,
                max_revision_cycles=audit_revision_cycles,
                control_state=control_state,
                model_name=model_name,
            )

            if not search_ok:
                add_unresolved(search_agent.name, "search")

            if not articles_data or not articles_data.get("articles"):
                if control_state is not None:
                    control_state["step_statuses"]["search"] = "failed"
                res = {
                    "input_checked": True,
                    "search_failed": True,
                    "topic": topic,
                    "optimized_query": optimized_query,
                    "input_check_result": input_check_result,
                    "search_result": articles_data or {},
                    "editor_logs": editor_logs,
                    "audit_warnings": unresolved_audit_warnings,
                    "is_approved": False,
                }
                if results_dict is not None:
                    results_dict.update(res)
                return res

            search_status = str(articles_data.get("search_status", "verified")).lower()
            if search_status in {
                "no_results",
                "low",
                "unverified",
                "doubtful",
                "false_or_nonexistent",
            }:
                if control_state is not None:
                    control_state["step_statuses"]["search"] = "failed"
                res = {
                    "input_checked": True,
                    "search_failed": True,
                    "topic": topic,
                    "optimized_query": optimized_query,
                    "input_check_result": input_check_result,
                    "search_result": articles_data,
                    "editor_logs": editor_logs,
                    "audit_warnings": unresolved_audit_warnings,
                    "is_approved": False,
                }
                if results_dict is not None:
                    results_dict.update(res)
                return res

            if articles_data.get("corrected_query"):
                optimized_query = articles_data["corrected_query"]

            if control_state is not None:
                control_state["step_statuses"]["search"] = "completed"

            if results_dict is not None:
                results_dict["articles"] = articles_data
                results_dict["optimized_query"] = optimized_query

            await call_callback("search_complete", "Search complete.", articles_data)

            # Step 2: Recruiter Agent
            await self._check_controls(control_state)
            if control_state is not None:
                control_state["step_statuses"]["recruiter"] = "running"
            await call_callback(
                "recruiter", "Spawning Recruiter Agent to allocate modules..."
            )
            recruiter_agent = get_recruiter_agent(model_name)

            def recruiter_prompt_gen(f, s):
                return (
                    f"Analyze these articles and decide agent recruitment:\n{articles_data}"
                    + (
                        f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                        if f
                        else ""
                    )
                )

            recruitment_result, recruit_ok = await self._run_agent_with_audit(
                recruiter_agent,
                recruiter_prompt_gen,
                RECRUITER_AUDIT_CRITERIA,
                session_id,
                call_callback,
                "recruiter",
                editor_logs,
                max_revision_cycles=light_revision_cycles,
                control_state=control_state,
                model_name=model_name,
            )

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
                add_unresolved(recruiter_agent.name, "recruiter")

            if control_state is not None:
                control_state["step_statuses"]["recruiter"] = "completed"
                # Mark optionally skipped steps as skipped
                if not recruitment_result.get("recruit_dispute", True):
                    control_state["step_statuses"]["dispute"] = "skipped"
                if not recruitment_result.get("recruit_perspective", True):
                    control_state["step_statuses"]["bias_agent"] = "skipped"
                if not recruitment_result.get("recruit_expert", True):
                    control_state["step_statuses"]["expert"] = "skipped"
                if not recruitment_result.get("recruit_future_outlook", True):
                    control_state["step_statuses"]["outlook"] = "skipped"

            if results_dict is not None:
                results_dict["recruitment"] = recruitment_result

            await call_callback(
                "recruiter_complete",
                "Recruitment options finalized.",
                recruitment_result,
            )

            # Parallel Group 1: Fact, Dispute, and Perspective
            facts_data = {
                "consensus_facts": [],
                "timeline_events": [],
                "timeline": [],
            }
            fact_ok = True

            dispute_data = {"disputed_claims": []}
            dispute_ok = True

            bias_data = {
                "profiles": [],
                "key_rhetorical_differences": "No media profiling recruited.",
            }
            bias_ok = True

            async def run_fact_agent():
                nonlocal facts_data, fact_ok
                await self._check_controls(control_state)
                if control_state is not None:
                    control_state["step_statuses"]["fact_bias"] = "running"
                await call_callback("fact_bias", "Running Fact & Consensus Analyzer...")
                fact_agent = get_fact_agent(model_name)

                def fact_prompt_gen(f, s):
                    return (
                        f"Topic: {topic}\nAnalyze these articles to find verified consensus facts and timeline:\n{articles_data}"
                        + (
                            f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                            if f
                            else ""
                        )
                    )

                res_facts, ok = await self._run_agent_with_audit(
                    fact_agent,
                    fact_prompt_gen,
                    FACT_AUDIT_CRITERIA,
                    session_id,
                    call_callback,
                    "fact_bias",
                    editor_logs,
                    max_revision_cycles=audit_revision_cycles,
                    control_state=control_state,
                    model_name=model_name,
                    deterministic_check=lambda output: verify_analysis_evidence(
                        articles_data, facts_data=output
                    ),
                )
                if res_facts:
                    facts_data = res_facts
                fact_ok = ok
                if not fact_ok:
                    add_unresolved(fact_agent.name, "fact_bias")
                if control_state is not None:
                    control_state["step_statuses"]["fact_bias"] = "completed"
                if results_dict is not None:
                    results_dict["facts"] = facts_data

            async def run_dispute_agent():
                nonlocal dispute_data, dispute_ok
                if recruitment_result.get("recruit_dispute", True):
                    await self._check_controls(control_state)
                    if control_state is not None:
                        control_state["step_statuses"]["dispute"] = "running"
                    await call_callback("dispute", "Recruiting Dispute Agent...")
                    dispute_agent = get_dispute_agent(model_name)

                    def dispute_prompt_gen(f, s):
                        return (
                            f"Topic: {topic}\nAnalyze these articles and extract contradictory claims:\n{articles_data}"
                            + (
                                f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                                if f
                                else ""
                            )
                        )

                    res_dispute, ok = await self._run_agent_with_audit(
                        dispute_agent,
                        dispute_prompt_gen,
                        DISPUTE_AUDIT_CRITERIA,
                        session_id,
                        call_callback,
                        "dispute",
                        editor_logs,
                        max_revision_cycles=audit_revision_cycles,
                        control_state=control_state,
                        model_name=model_name,
                        deterministic_check=lambda output: verify_analysis_evidence(
                            articles_data, dispute_data=output
                        ),
                    )
                    if res_dispute:
                        dispute_data = res_dispute
                    dispute_ok = ok
                    if not dispute_ok:
                        add_unresolved(dispute_agent.name, "dispute")
                    if control_state is not None:
                        control_state["step_statuses"]["dispute"] = "completed"
                    await call_callback(
                        "dispute_complete", "Disputes mapped successfully."
                    )

            async def run_perspective_agent():
                nonlocal bias_data, bias_ok
                if recruitment_result.get("recruit_perspective", True):
                    await self._check_controls(control_state)
                    if control_state is not None:
                        control_state["step_statuses"]["bias_agent"] = "running"
                    await call_callback(
                        "bias_agent",
                        "Recruiting Perspective Agent...",
                    )
                    bias_agent = get_bias_agent(model_name)

                    def bias_prompt_gen(f, s):
                        return (
                            f"Topic: {topic}\n"
                            "Classification Axis: Dynamically determined by you based on the articles\n"
                            f"Analyze framing & omissions:\n{articles_data}"
                            + (
                                f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                                if f
                                else ""
                            )
                        )

                    res_bias, ok = await self._run_agent_with_audit(
                        bias_agent,
                        bias_prompt_gen,
                        PERSPECTIVE_AUDIT_CRITERIA,
                        session_id,
                        call_callback,
                        "bias_agent",
                        editor_logs,
                        max_revision_cycles=audit_revision_cycles,
                        control_state=control_state,
                        model_name=model_name,
                        deterministic_check=lambda output: verify_analysis_evidence(
                            articles_data, narratives_data=output
                        ),
                    )
                    if res_bias:
                        bias_data = res_bias
                    bias_ok = ok
                    if not bias_ok:
                        add_unresolved(bias_agent.name, "bias_agent")
                    if control_state is not None:
                        control_state["step_statuses"]["bias_agent"] = "completed"
                    if results_dict is not None:
                        results_dict["narratives"] = bias_data

            # Execute parallel Group 1
            await asyncio.gather(
                run_fact_agent(), run_dispute_agent(), run_perspective_agent()
            )

            # Expose the Dispute Agent's claims on facts_data for dashboard compatibility
            if not dispute_data:
                dispute_data = {"disputed_claims": []}
            facts_data["disputed_claims"] = merge_disputed_claims(
                facts_data.get("disputed_claims", []),
                dispute_data.get("disputed_claims", []),
            )

            if results_dict is not None:
                results_dict["facts"] = facts_data

            # Broadcast completion of facts & perspectives
            if recruitment_result.get("recruit_perspective", True):
                await call_callback(
                    "fact_bias_complete",
                    "Factual & Perspective profiling completed.",
                    {"facts": facts_data, "narratives": bias_data},
                )
            else:
                await call_callback(
                    "fact_bias_complete",
                    "Fact extraction completed.",
                    {"facts": facts_data, "narratives": bias_data},
                )

            # Parallel Group 2: Expert Panel and Future Outlook
            reference_text = ""
            expert_data = {
                "expert_opinions": [],
                "roundtable_summary": "No expert roundtable recruited.",
            }
            expert_ok = True

            outlook_data = {
                "most_likely_scenario": None,
                "alternative_scenarios": [],
                "monitoring_indicators": [],
            }
            outlook_ok = True

            async def run_expert_agent():
                nonlocal expert_data, expert_ok
                if not recruitment_result.get("recruit_expert", True):
                    return
                await self._check_controls(control_state)
                if control_state is not None:
                    control_state["step_statuses"]["expert"] = "running"
                await call_callback("expert", "Selecting expert domains...")

                # Step 1: pick 2-3 expert domains for this topic
                selector = get_expert_domain_selector(model_name)
                selection = await self._run_agent(
                    selector,
                    (
                        f"Topic: {topic}\n"
                        f"Consensus Facts: {facts_data}\n"
                        f"Disputes: {dispute_data}\n"
                        "Select the 2-3 most appropriate expert domains."
                    ),
                    session_id,
                )
                domains = [
                    str(domain).strip()
                    for domain in (selection or {}).get("domains") or []
                    if str(domain).strip()
                ][:3]
                if not domains:
                    domains = ["Public Policy Analyst", "Media Ethics Analyst"]
                await call_callback(
                    "expert",
                    f"Recruiting Expert Panel (Domains: {', '.join(domains)})...",
                )

                # Step 2: run one expert agent per domain in parallel, each audited
                async def run_one_expert(domain: str):
                    expert_agent = get_domain_expert_agent(domain, model_name)

                    def expert_prompt_gen(f, s):
                        return (
                            f"Topic: {topic}\n"
                            f"Consensus Facts: {facts_data}\n"
                            f"Disputes: {dispute_data}\n"
                            f"Media Narratives: {bias_data}\n\n"
                            f"Provide your commentary as '{domain}'."
                            + (
                                f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                                if f
                                else ""
                            )
                        )

                    opinion, ok = await self._run_agent_with_audit(
                        expert_agent,
                        expert_prompt_gen,
                        EXPERT_AUDIT_CRITERIA,
                        session_id,
                        call_callback,
                        "expert",
                        editor_logs,
                        max_revision_cycles=audit_revision_cycles,
                        control_state=control_state,
                        model_name=model_name,
                        deterministic_check=lambda output: verify_analysis_evidence(
                            articles_data,
                            experts_data={
                                "expert_opinions": [output] if output else []
                            },
                            reference_text=reference_text,
                        ),
                    )
                    if not ok:
                        add_unresolved(expert_agent.name, "expert")
                    return opinion, ok

                expert_results = await asyncio.gather(
                    *(run_one_expert(domain) for domain in domains)
                )
                opinions = [opinion for opinion, _ in expert_results if opinion]
                expert_ok = all(ok for _, ok in expert_results)

                # Step 3: moderator synthesizes the roundtable summary
                roundtable_summary = ""
                if opinions:
                    summarizer = get_roundtable_summarizer(model_name)
                    summary_result = await self._run_agent(
                        summarizer,
                        f"Topic: {topic}\nExpert commentaries:\n{json.dumps(opinions, ensure_ascii=True)}",
                        session_id,
                    )
                    roundtable_summary = (summary_result or {}).get(
                        "roundtable_summary", ""
                    )

                expert_data = {
                    "expert_opinions": opinions,
                    "roundtable_summary": roundtable_summary
                    or "No expert commentary could be produced.",
                }
                if control_state is not None:
                    control_state["step_statuses"]["expert"] = "completed"
                if results_dict is not None:
                    results_dict["experts"] = expert_data
                await call_callback(
                    "expert_complete",
                    "Expert Roundtable analysis completed.",
                    expert_data,
                )

            async def run_outlook_agent():
                nonlocal outlook_data, outlook_ok
                if recruitment_result.get("recruit_future_outlook", True):
                    await self._check_controls(control_state)
                    if control_state is not None:
                        control_state["step_statuses"]["outlook"] = "running"
                    await call_callback("outlook", "Recruiting Future Outlook Agent...")
                    outlook_agent = get_outlook_agent(model_name)

                    def outlook_prompt_gen(f, s):
                        return (
                            f"Topic: {topic}\nFacts: {facts_data}\nMedia Narratives: {bias_data}"
                            + (
                                f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                                if f
                                else ""
                            )
                        )

                    res_outlook, ok = await self._run_agent_with_audit(
                        outlook_agent,
                        outlook_prompt_gen,
                        OUTLOOK_AUDIT_CRITERIA,
                        session_id,
                        call_callback,
                        "outlook",
                        editor_logs,
                        max_revision_cycles=audit_revision_cycles,
                        control_state=control_state,
                        model_name=model_name,
                        deterministic_check=lambda output: verify_analysis_evidence(
                            articles_data, outlook_data=output
                        ),
                    )
                    if res_outlook:
                        outlook_data = res_outlook
                    outlook_ok = ok
                    if not outlook_ok:
                        add_unresolved(outlook_agent.name, "outlook")
                    if control_state is not None:
                        control_state["step_statuses"]["outlook"] = "completed"
                    if results_dict is not None:
                        results_dict["outlook"] = outlook_data
                    await call_callback(
                        "outlook_complete", "Future scenarios generated."
                    )

            # Execute parallel Group 2
            await asyncio.gather(run_expert_agent(), run_outlook_agent())

            # Step 8: Public Reporter Agent
            await self._check_controls(control_state)
            if control_state is not None:
                control_state["step_statuses"]["public_report"] = "running"
            await call_callback(
                "public_report", "Spawning Public Reporter Agent to write summary..."
            )
            public_reporter = get_public_reporter_agent(model_name)

            prompt_public = (
                f"Topic: {topic}\n"
                f"Consensus & Disputes: {facts_data}\n"
                f"Media Narratives: {bias_data}\n"
                f"Expert Panel Commentary: {expert_data}\n"
                f"Future Outlook Scenarios: {outlook_data}\n\n"
                f"Compile a comprehensive public summary report."
            )

            def public_report_prompt_gen(f, s):
                return prompt_public + (
                    f"\n\nFeedback from Auditor: {f}\nSuggestions: {', '.join(s)}"
                    if f
                    else ""
                )

            def public_report_audit_context(_output):
                return json.dumps(
                    {
                        "verified_facts": facts_data,
                        "media_narratives": bias_data,
                        "expert_panel": expert_data,
                        "future_outlook": outlook_data,
                        "unresolved_audit_warnings": unresolved_audit_warnings,
                    },
                    ensure_ascii=True,
                )

            public_report, public_report_ok = await self._run_agent_with_audit(
                public_reporter,
                public_report_prompt_gen,
                PUBLIC_REPORTER_AUDIT_CRITERIA,
                session_id,
                call_callback,
                "public_report",
                editor_logs,
                max_revision_cycles=audit_revision_cycles,
                control_state=control_state,
                model_name=model_name,
                deterministic_check=lambda output: verify_analysis_evidence(
                    articles_data, report_data=output
                ),
                audit_context_generator=public_report_audit_context,
            )
            if not public_report_ok:
                add_unresolved(public_reporter.name, "public_report")

            if control_state is not None:
                control_state["step_statuses"]["public_report"] = "completed"

            if results_dict is not None:
                results_dict["public_report"] = public_report

            await call_callback(
                "public_report_complete", "Public report completed.", public_report
            )

            # Step 9: Consolidated Markdown Dashboard (deterministic renderer, no LLM)
            #
            # Folding upstream output into <details> blocks and building a Sources
            # section is pure templating over already-audited data, so this runs as
            # a direct function call instead of another agent + audit cycle.
            await self._check_controls(control_state)
            if control_state is not None:
                control_state["step_statuses"]["public_editor"] = "running"
            await call_callback(
                "public_editor", "Rendering consolidated dashboard report..."
            )

            public_editor_data = render_public_editor_report(
                topic,
                public_report,
                facts_data,
                bias_data,
                expert_data,
                outlook_data,
                articles_data,
                unresolved_audit_warnings,
            )
            public_editor_report = public_editor_data.get("markdown_report", "")
            public_editor_warnings = public_editor_data.get("unresolved_warnings", [])

            if control_state is not None:
                control_state["step_statuses"]["public_editor"] = "completed"

            if results_dict is not None:
                results_dict["public_editor_report"] = public_editor_report
                results_dict["public_editor_warnings"] = public_editor_warnings

            await call_callback(
                "public_editor_complete",
                "Public consolidated dashboard ready.",
                public_editor_report,
            )

            # Step 10: Callbacks finished
            is_approved = not unresolved_audit_warnings
            await call_callback(
                "editor_complete",
                "All audits completed.",
                {
                    "editor_logs": editor_logs,
                    "audit_warnings": unresolved_audit_warnings,
                    "is_approved": is_approved,
                },
            )

            final_res = {
                "input_checked": True,
                "topic": topic,
                "optimized_query": optimized_query,
                "input_check_result": input_check_result,
                "articles": articles_data,
                "recruitment": recruitment_result,
                "facts": facts_data,
                "narratives": bias_data,
                "experts": expert_data,
                "outlook": outlook_data,
                "public_report": public_report,
                "public_editor_report": public_editor_report,
                "public_editor_warnings": public_editor_warnings,
                "editor_logs": editor_logs,
                "audit_warnings": unresolved_audit_warnings,
                "is_approved": is_approved,
            }
            if results_dict is not None:
                results_dict.update(final_res)
            return final_res

        except WorkflowStoppedException:
            # Update statuses
            if control_state is not None:
                for step, status in list(control_state["step_statuses"].items()):
                    if status in ["queued", "running"]:
                        control_state["step_statuses"][step] = "stopped"
            partial_res = {
                "input_checked": "input_check_result" in locals() and input_check_result is not None,
                "topic": topic,
                "optimized_query": optimized_query
                if "optimized_query" in locals()
                else topic,
                "input_check_result": input_check_result if "input_check_result" in locals() else {},
                "articles": articles_data if "articles_data" in locals() else {},
                "recruitment": recruitment_result
                if "recruitment_result" in locals()
                else {},
                "facts": facts_data if "facts_data" in locals() else {},
                "narratives": bias_data if "bias_data" in locals() else {},
                "experts": expert_data if "expert_data" in locals() else {},
                "outlook": outlook_data if "outlook_data" in locals() else {},
                "public_report": public_report if "public_report" in locals() else {},
                "public_editor_report": public_editor_report
                if "public_editor_report" in locals()
                else "",
                "public_editor_warnings": public_editor_warnings
                if "public_editor_warnings" in locals()
                else [],
                "editor_logs": editor_logs,
                "audit_warnings": unresolved_audit_warnings,
                "is_approved": False,
                "stopped": True,
            }
            if results_dict is not None:
                results_dict.update(partial_res)
            return partial_res
        except Exception as e:
            if control_state is not None:
                for step, status in list(control_state["step_statuses"].items()):
                    if status == "running":
                        control_state["step_statuses"][step] = "failed"
                    elif status == "queued":
                        control_state["step_statuses"][step] = "stopped"
            raise e
