from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from agents.coordinator import NewsAnalysisCoordinator


def _format_evidence_markdown(evidence: list[dict], indent: str = "  ", show_bias: bool = True) -> str:
    lines = []
    for item in evidence or []:
        source = item.get("source", "Unknown source")
        title = item.get("title", "")
        url = item.get("url", "")
        published = item.get("published_date", "")
        bias = (item.get("bias_category", "")) if show_bias else ""
        quote = item.get("quote", "")
        meta = ", ".join(part for part in [published, bias] if part)
        meta_text = f" ({meta})" if meta else ""

        if url:
            lines.append(f"{indent}- [{source}]({url}) - {title}{meta_text}")
        else:
            lines.append(f"{indent}- {source} - {title}{meta_text}")
        if quote:
            lines.append(f'{indent}  - Evidence quote: "{quote}"')
    return "\n".join(lines)


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

        # Initialize news analysis coordinator
        coordinator = NewsAnalysisCoordinator()
        try:
            results = await coordinator.analyze(user_message)

            # Format report as markdown response
            if not results.get("reviewed", True):
                rejection = results.get("review_result", {})
                response_text = (
                    f"# Input Check Rejection\n\n"
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
                facts = results.get("facts", {})
                narratives = results.get("narratives", {})
                experts = results.get("experts", {})
                public_report = results.get("public_report", {})
                is_approved = results.get("is_approved", True)
                editor_logs = results.get("editor_logs", [])

                response_text = ""
                review_res = results.get("review_result", {})
                if review_res.get("action") == "accept_with_notification":
                    response_text += (
                        f"> [!WARNING]\n"
                        f"> **Input validation note**: {review_res.get('notification_message')}\n\n"
                    )

                if not is_approved and editor_logs:
                    last_log = editor_logs[-1]
                    feedback = last_log.get("feedback", "")
                    suggestions = ", ".join(last_log.get("suggestions", []))
                    response_text += (
                        f"> [!WARNING]\n"
                        f"> **Editor-in-Chief Revision Warning**: This report was NOT fully approved by the Editor-in-Chief.\n"
                        f"> *Feedback*: {feedback}\n"
                        f"> *Suggestions*: {suggestions}\n\n"
                    )

                audit_warnings = results.get("audit_warnings", [])
                if audit_warnings:
                    response_text += "> [!WARNING]\n"
                    response_text += "> **Unresolved audit warnings remain.** Review the warnings before relying on this report.\n"
                    for warning in audit_warnings:
                        response_text += (
                            f"> - {warning.get('agent')}: {warning.get('feedback')}\n"
                        )
                    response_text += "\n"

                response_text += f"# Report: {results.get('topic')}\n\n"

                if public_report:
                    response_text += (
                        f"## Public Summary: {public_report.get('title')}\n"
                    )
                    response_text += f"{public_report.get('lead_paragraph')}\n\n"

                    response_text += "### Key Takeaways\n"
                    for takeaway in public_report.get("key_takeaways", []):
                        if isinstance(takeaway, dict):
                            response_text += f"- {takeaway.get('point', '')}"
                            links = [
                                f"[{item.get('source', 'Source')}]({item.get('url')})"
                                for item in takeaway.get("evidence") or []
                                if item.get("url")
                            ]
                            if links:
                                response_text += f" (Sources: {', '.join(links)})"
                            response_text += "\n"
                        else:
                            response_text += f"- {takeaway}\n"
                    response_text += "\n"

                    response_text += f"### Perspective Synthesis\n{public_report.get('narrative_summary')}\n\n"
                    response_text += (
                        f"### Future Outlook\n{public_report.get('future_outlook')}\n\n"
                    )
                    response_text += "---\n\n"

                # Consensus
                response_text += "## Consensus Facts\n"
                for item in facts.get("consensus_facts", []):
                    sources = ", ".join(item.get("supporting_sources") or [])
                    response_text += f"- {item.get('claim')} (Sources: {sources})\n"
                    explanation = item.get("explanation")
                    if explanation:
                        response_text += f"  <details>\n  <summary>Why this is considered a fact</summary>\n  {explanation}\n  </details>\n"
                    evidence_md = _format_evidence_markdown(
                        item.get("evidence", []), indent="  ", show_bias=False
                    )
                    if evidence_md:
                        response_text += f"  * Evidence trail:\n{evidence_md}\n"

                # Disputes
                response_text += "\n## Disputed Claims\n"
                for item in facts.get("disputed_claims", []):
                    response_text += f"- **Claim**: {item.get('claim')}\n"
                    side_a_sources = ", ".join(item.get("side_a_sources") or [])
                    side_b_sources = ", ".join(item.get("side_b_sources") or [])
                    response_text += f"  * Side A: {item.get('side_a_assertion')} (Sources: {side_a_sources})\n"
                    side_a_evidence = _format_evidence_markdown(
                        item.get("side_a_evidence", []), indent="    "
                    )
                    if side_a_evidence:
                        response_text += f"    * Evidence trail:\n{side_a_evidence}\n"
                    response_text += f"  * Side B: {item.get('side_b_assertion')} (Sources: {side_b_sources})\n"
                    side_b_evidence = _format_evidence_markdown(
                        item.get("side_b_evidence", []), indent="    "
                    )
                    if side_b_evidence:
                        response_text += f"    * Evidence trail:\n{side_b_evidence}\n"

                # Media Framing
                response_text += "\n## Media Framing\n"
                for profile in narratives.get("profiles", []):
                    response_text += f"### {profile.get('perspective_group')}\n"
                    response_text += f"*Narrative*: {profile.get('core_narrative')}\n"
                    response_text += "*Arguments*:\n"
                    for arg in profile.get("key_arguments", []):
                        response_text += f"  - {arg}\n"
                    response_text += f"*Omissions*: {', '.join(profile.get('notable_omissions', [])) or 'None'}\n\n"

                # Expert Panel
                response_text += "## Expert Roundtable\n"
                for opinion in experts.get("expert_opinions", []):
                    response_text += f"### {opinion.get('expert_name')} ({opinion.get('expertise_area')})\n"
                    response_text += f"{opinion.get('commentary')}\n"
                    response_text += (
                        f"Cites: {', '.join(opinion.get('cited_references', []))}\n\n"
                    )

                response_text += (
                    f"## Roundtable Summary\n{experts.get('roundtable_summary')}\n"
                )

                if results.get("public_editor_report"):
                    response_text += "\n\n---\n\n## Editor's Consolidated Dashboard\n"
                    response_text += results["public_editor_report"]

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


root_agent = NewsAnalysisWorkflowAgent(name="news_analysis_workflow")
