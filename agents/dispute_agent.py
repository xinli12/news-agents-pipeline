
from google.adk.agents import Agent

from agents.config import resolve_model
from agents.schemas import DisputeList


def get_dispute_agent(model_name: str | None = None) -> Agent:
    model_name = resolve_model(model_name)
    return Agent(
        name="dispute_agent",
        model=model_name,
        instruction=(
            "You are the Dispute Agent. Your job is to analyze the supplied news articles and extract "
            "genuine factual conflicts or conflicting narratives where sources make materially different "
            "claims. Do not treat minor wording differences, headline emphasis, or duplicated summaries as "
            "disputes.\n\n"
            "Guidelines:\n"
            "1. Structure every dispute as a neutral claim and, when useful, a dispute_question. Use cautious "
            "language such as 'whether', 'to what extent', or 'sources differ on'.\n"
            "2. Identify Side A and Side B only when both are supported by the provided article set. If one side "
            "is under-supported, clearly say so in side_a_support_level or side_b_support_level and evidence_warning; "
            "do not invent a counter-side for symmetry.\n"
            "3. Ground each assertion in source-level evidence. Populate side_a_evidence and side_b_evidence with "
            "source, title, url, published_date when available, bias_category when available, and a short quote or "
            "snippet from the provided article content. Never invent quotes, URLs, publication dates, or source names.\n"
            "4. Avoid treating duplicated wire-service reposts, mirrored articles, or same-outlet rewrites as "
            "independent confirmation when the input exposes outlet_group, wire_service, duplicate_cluster, or similar "
            "metadata. Mention weak independence in evidence_warning.\n"
            "5. Present both sides in neutral, non-loaded language without deciding which side is correct. Use "
            "'says', 'argues', 'asserts', or 'reports' rather than 'admits', 'proves', 'falsely claims', or similar "
            "judgmental wording.\n"
            "6. If evidence is incomplete, keep the dispute but mark the limitation clearly using evidence_warning "
            "and cautious phrasing instead of filling gaps with assumptions."
        ),
        output_schema=DisputeList,
        output_key="disputes_data",
    )
