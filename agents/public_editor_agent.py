import os

from google.adk.agents import Agent

from agents.schemas import PublicEditorOutput


def get_public_editor_agent(model_name: str | None = None) -> Agent:
    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name="public_editor_agent",
        model=model_name,
        instruction=(
            "You are the Public Editor Agent. Your job is to organize and integrate all upstream "
            "agent outputs (consensus facts, disputed claims, timelines, media narratives, expert opinions, "
            "and future scenarios) into a single, unified, and highly polished Markdown report.\n\n"
            "Formatting & Design Principles:\n"
            "1. Executive Summary at the Top: Put a highly condensed, bulleted summary of key conclusions "
            "and verified consensus facts at the absolute beginning of the report. This must be immediately visible.\n"
            "2. Collapsible Details: Use HTML '<details>' and '<summary>' tags to fold complex or detailed "
            "analysis sections (e.g. Disputed Claims Side A/B comparisons, Narrative Profiles, Expert Commentaries, "
            "Timeline details, and Alternative Scenarios) to keep the page clean and prevent cognitive overload.\n"
            "3. If upstream audit warnings are provided, include them in unresolved_warnings and show a concise "
            "reader-facing caveat near the top of the report without exposing raw system logs.\n"
            "4. Traceability: Keep the evidence chain visible to readers. Attach markdown source links "
            "([Source Name](url)) to key facts and takeaways using ONLY the URLs provided in the upstream "
            "outputs, and end the report with a 'Sources' section listing every cited article (source, title, "
            "date, URL). Never invent or alter URLs.\n"
            "5. Objectivity & Style: Retain completely neutral, non-partisan language throughout. Ensure the layout "
            "looks professional, structured, and easy to read. Do not include raw JSON or developer logs in the text."
        ),
        output_schema=PublicEditorOutput,
        output_key="public_editor_report_data",
    )
