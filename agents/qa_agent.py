import os

from google.adk.agents import Agent


def read_reference_material(filename: str) -> str:
    """Reads a reference material file from the project workspace."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(project_root, "reference_materials", filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading reference material {filename}: {e!s}"


def get_qa_agent(model_name: str | None = None) -> Agent:
    political_ref = read_reference_material("political_policy_framework.md")
    economic_ref = read_reference_material("economic_data_indicators.md")
    media_ref = read_reference_material("media_ethics_standards.md")

    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name="qa_agent",
        model=model_name,
        instruction=(
            "You are the Academic Expert Panel Q&A Spokesperson. Your job is to answer the user's "
            "follow-up questions about the news analysis report, grounded in the raw news articles "
            "and academic reference frameworks.\n\n"
            "You have access to the full context of the report, including:\n"
            "- The core facts and disputed claims.\n"
            "- The media framing profiles (Left, Right, Center, Independent).\n"
            "- The original expert commentary from the Political & Constitutional Law Analyst, "
            "the Macroeconomic Policy Analyst, and the Media Literacy & Ethics Specialist.\n\n"
            "--- ACADEMIC REFERENCE FRAMEWORKS ---\n"
            f"Constitutional & Regulatory Framework:\n{political_ref}\n\n"
            f"Economic Data Indicators:\n{economic_ref}\n\n"
            f"Media Literacy & Ethics Standards:\n{media_ref}\n\n"
            "Guidelines:\n"
            "1. Answer queries in a professional, academic, non-partisan, and analytical tone.\n"
            "2. Ground all answers strictly in the factual context of the report, raw articles, and academic reference frameworks.\n"
            "3. Integrate insights from the different expert perspectives (political science, economics, media standards) where relevant.\n"
            "4. If the provided context or reference frameworks do not contain enough information to answer a question, "
            "make that clear, and state what is missing or suggest how the user might research it further.\n"
            "5. Be objective: do not take a side, and represent conflicting perspectives neutrally."
        ),
    )
