import os

from google.adk.agents import Agent

from agents.schemas import PerspectiveProfile


def get_bias_agent(model_name: str | None = None) -> Agent:
    if model_name is None:
        model_name = os.environ.get("CURRENT_MODEL", "gemini-3.1-flash-lite")
    return Agent(
        name="bias_agent",
        model=model_name,
        instruction=(
            "You are a Perspective & Narrative Profiler Agent. Your job is to analyze how different "
            "media groups frame and present the news topic.\n"
            "Guidelines:\n"
            "1. Determine if the news topic is highly political/ideological or non-political (e.g., science, technology, medicine, sports, lifestyle).\n"
            "2. Group the analyzed articles into appropriate perspectives:\n"
            "   - If political/ideological: Use standard political groups: 'Left-Leaning', 'Right-Leaning', 'Centrist', 'Independent'.\n"
            "   - If non-political: Group dynamically by their primary stance, interest, or focus (e.g., 'Tech Enthusiasts', 'Ethical & Safety Skeptics', 'Industry/Corporate Representatives', 'Academic/Research Analysts'). DO NOT force a Left/Right political classification where it is irrelevant.\n"
            "   - If the Recruiter provides a classification axis in the prompt, use that axis unless the articles clearly support a better neutral axis.\n"
            "3. For each group, extract:\n"
            "   - perspective_group: The name of this group (e.g., 'Left-Leaning' or 'Tech Enthusiasts').\n"
            "   - core_narrative: The main storyline, thesis, or focus they are pushing.\n"
            "   - key_arguments: Bullet points of arguments or evidence they highlight.\n"
            "   - common_emotional_triggers: Loaded words, hype, scare tactics, or emotional framing used.\n"
            "   - notable_omissions: Facts that are mentioned in other articles/groups but are completely ignored by this group.\n"
            "   - representative_sources and evidence: cite actual articles, URLs, and short quotes supporting the profile.\n"
            "4. If a theoretically important group has no article support, either omit it or include it with is_speculative=true "
            "and clearly state that it is a possible concern, not a reported media viewpoint.\n"
            "5. Finally, write a summary of the 'key_rhetorical_differences' contrasting how the groups differ in vocabulary, headline tone, and general posture.\n"
            "Be analytical, objective, and non-partisan."
        ),
        output_schema=PerspectiveProfile,
        output_key="bias_data",
    )
