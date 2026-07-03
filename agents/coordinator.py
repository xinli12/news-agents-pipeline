"""Coordinator entrypoint for the ADK-native news analysis workflow.

The actual orchestration graph lives in `agents.pipeline`; this module keeps
the stable `NewsAnalysisCoordinator` API used by the Streamlit app, the CLI,
and the ADK root agent, and re-exports the audit criteria and helpers that
tests and callers import from here.
"""

import uuid

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Re-exported for backward compatibility (tests and callers import from here).
from agents.audit_criteria import (  # noqa: F401
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
from agents.config import DEFAULT_MODEL
from agents.pipeline import (  # noqa: F401
    STEP_KEYS,
    PipelineRun,
    WorkflowStoppedException,
    build_news_workflow,
    get_audit_agent,
    merge_disputed_claims,
)
from agents.review_agent import get_review_agent


class NewsAnalysisCoordinator:
    """Runs the news analysis Workflow graph and returns the report dict."""

    def __init__(self):
        self.session_service = InMemorySessionService()

    async def _run_single_agent(self, agent, prompt_text: str) -> dict | None:
        """Runs one LlmAgent in a throwaway session and returns its output state."""
        session_id = f"single_{agent.name}_{uuid.uuid4().hex[:8]}"
        await self.session_service.create_session(
            app_name="news_app", user_id="user", session_id=session_id
        )
        try:
            runner = Runner(
                agent=agent, app_name="news_app", session_service=self.session_service
            )
            async for _event in runner.run_async(
                user_id="user",
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=prompt_text)]
                ),
            ):
                pass
            session = await self.session_service.get_session(
                app_name="news_app", user_id="user", session_id=session_id
            )
            value = session.state.get(agent.output_key) if agent.output_key else None
            if hasattr(value, "model_dump"):
                return value.model_dump()
            return value
        finally:
            try:
                await self.session_service.delete_session(
                    app_name="news_app", user_id="user", session_id=session_id
                )
            except Exception:
                pass

    async def run_input_check(self, topic: str, model_name: str = DEFAULT_MODEL) -> dict:
        """Run the Input Check Agent synchronously to pre-audit user's input."""
        review_agent = get_review_agent(model_name)
        result = await self._run_single_agent(
            review_agent, f"Audit this input news topic: '{topic}'"
        )
        if not result:
            result = {
                "is_safe": True,
                "is_news_relevant": True,
                "suggested_query_formulation": topic,
                "input_issue_type": "clear_news_query",
                "user_message": "Failed to get review result.",
                "suggested_options": [],
                "auto_modified": False,
                "needs_user_confirmation": False,
                "confidence": 1.0,
            }
        return result

    async def analyze(
        self,
        topic: str,
        progress_callback=None,
        enable_editor: bool = True,
        control_state: dict | None = None,
        results_dict: dict | None = None,
        model_name: str = DEFAULT_MODEL,
        bypass_input_check: bool = False,
    ) -> dict:
        """Runs the full analysis workflow with audit gates and returns the report."""
        run = PipelineRun(
            topic=topic,
            model_name=model_name,
            enable_editor=enable_editor,
            bypass_input_check=bypass_input_check,
            progress_callback=progress_callback,
            control_state=control_state,
            results_dict=results_dict,
        )
        if control_state is not None:
            control_state["step_statuses"] = dict.fromkeys(STEP_KEYS, "queued")

        workflow = build_news_workflow(run)
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        await self.session_service.create_session(
            app_name="news_app", user_id="user", session_id=session_id
        )
        runner = Runner(
            agent=workflow, app_name="news_app", session_service=self.session_service
        )
        try:
            async for _event in runner.run_async(
                user_id="user",
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=topic)]
                ),
            ):
                pass
        except Exception:
            if control_state is not None:
                statuses = control_state.get("step_statuses", {})
                for step, status in list(statuses.items()):
                    if status == "running":
                        statuses[step] = "failed"
                    elif status == "queued":
                        statuses[step] = "stopped"
            raise
        finally:
            try:
                await self.session_service.delete_session(
                    app_name="news_app", user_id="user", session_id=session_id
                )
            except Exception:
                pass

        return run.final_result
