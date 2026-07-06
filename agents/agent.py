from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from agents.bias_agent import get_bias_agent
from agents.coordinator import (
    DISPUTE_AUDIT_CRITERIA,
    EXPERT_AUDIT_CRITERIA,
    FACT_AUDIT_CRITERIA,
    INPUT_AUDIT_CRITERIA,
    OUTLOOK_AUDIT_CRITERIA,
    PERSPECTIVE_AUDIT_CRITERIA,
    PUBLIC_REPORTER_AUDIT_CRITERIA,
    RECRUITER_AUDIT_CRITERIA,
    SEARCH_AUDIT_CRITERIA,
    NewsAnalysisCoordinator,
    get_audit_agent,
)
from agents.dispute_agent import get_dispute_agent
from agents.expert_agent import (
    get_domain_expert_agent,
    get_expert_domain_selector,
    get_roundtable_summarizer,
)
from agents.fact_agent import get_fact_agent
from agents.input_check_agent import get_input_check_agent
from agents.outlook_agent import get_outlook_agent
from agents.public_reporter_agent import get_public_reporter_agent
from agents.recruiter_agent import get_recruiter_agent
from agents.search_agent import get_search_agent


class NewsAnalysisWorkflowAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Extract user message from context
        user_message = ""
        for event in reversed(ctx.session.events):
            if event.author == "user" and event.content and event.content.parts:
                user_message = event.content.parts[0].text
                break

        if not user_message:
            from google.genai import types as genai_types

            yield Event(
                author=self.name,
                content=genai_types.Content(
                    role="model",
                    parts=[genai_types.Part.from_text(text="No user prompt provided.")],
                ),
            )
            return

        results = {}
        coordinator = NewsAnalysisCoordinator()
        try:
            from google.adk.utils.context_utils import Aclosing

            async with Aclosing(
                coordinator.analyze_async(
                    topic=user_message,
                    ctx=ctx,
                    results_dict=results,
                )
            ) as agen:
                async for event in agen:
                    yield event

            # Format report as markdown response
            if not results.get("input_checked", True):
                rejection = results.get("input_check_result", {})
                response_text = (
                    f"Rejected: Input Check Rejection\n\n"
                    f"**Action**: {rejection.get('action', 'reject_with_confirmation')}\n"
                    f"**Reason**: {rejection.get('explanation', 'Not news-relevant or safe.')}\n\n"
                    f"{rejection.get('notification_message', 'Would you like to revise the request or add news context?')}"
                )
            elif results.get("search_failed"):
                search_result = results.get("search_result", {})
                response_text = (
                    f"# Search could not be verified: {results.get('topic')}\n\n"
                    f"**Query used:** {results.get('optimized_query', '')}\n\n"
                    f"**Status:** {search_result.get('search_status', 'unverified')}\n\n"
                    f"{search_result.get('verification_summary', 'No sufficiently corroborated news sources were found.')}\n"
                )
            else:
                # All content sections (consensus facts, disputes, media framing,
                # expert roundtable, outlook, sources) are already assembled by
                # the deterministic report_renderer during the pipeline run, so
                # the response here only adds banners that renderer doesn't know
                # about and then reuses that markdown as-is instead of rebuilding
                # the same sections from raw results a second time.
                response_text = ""
                review_res = results.get("input_check_result", {})
                if review_res.get("action") == "accept_with_notification":
                    response_text += (
                        f"> [!WARNING]\n"
                        f"> **Input validation note**: {review_res.get('notification_message')}\n\n"
                    )

                response_text += results.get(
                    "public_editor_report", "No report content was generated."
                )

            from google.genai import types as genai_types

            yield Event(
                author=self.name,
                content=genai_types.Content(
                    role="model", parts=[genai_types.Part.from_text(text=response_text)]
                ),
            )
        except BaseException as e:
            import sys
            import traceback

            print(f"Error running news pipeline: {type(e)}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            from google.genai import types as genai_types

            yield Event(
                author=self.name,
                content=genai_types.Content(
                    role="model",
                    parts=[
                        genai_types.Part.from_text(
                            text=f"Error running news pipeline: {e!s}"
                        )
                    ],
                ),
            )


root_agent = NewsAnalysisWorkflowAgent(
    name="news_analysis_workflow",
    sub_agents=[
        get_input_check_agent(),
        get_search_agent(),
        get_recruiter_agent(),
        get_fact_agent(),
        get_dispute_agent(),
        get_bias_agent(),
        get_expert_domain_selector(),
        get_roundtable_summarizer(),
        get_outlook_agent(),
        get_public_reporter_agent(),
        # Default expert domain examples for visualization
        get_domain_expert_agent("Public Policy Analyst"),
        get_domain_expert_agent("Media Ethics Analyst"),
        get_domain_expert_agent("Financial Analyst"),
        # Audit agents
        get_audit_agent("input_check", INPUT_AUDIT_CRITERIA),
        get_audit_agent("search", SEARCH_AUDIT_CRITERIA),
        get_audit_agent("recruiter", RECRUITER_AUDIT_CRITERIA),
        get_audit_agent("fact_bias", FACT_AUDIT_CRITERIA),
        get_audit_agent("dispute", DISPUTE_AUDIT_CRITERIA),
        get_audit_agent("bias_agent", PERSPECTIVE_AUDIT_CRITERIA),
        get_audit_agent("expert", EXPERT_AUDIT_CRITERIA),
        get_audit_agent("outlook", OUTLOOK_AUDIT_CRITERIA),
        get_audit_agent("public_report", PUBLIC_REPORTER_AUDIT_CRITERIA),
    ],
)
