"""Analysis mode configuration for runtime/cost tuning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agents.app_utils.analysis_context import (
    article_context_stats,
    build_compact_articles_data,
)

DEFAULT_ANALYSIS_MODE = "balanced"
ANALYSIS_MODE_OPTIONS = ("balanced", "fast", "deep")


@dataclass(frozen=True)
class AnalysisModeConfig:
    mode: str
    label: str
    description: str
    compact_downstream_context: bool
    downstream_article_limit: int | None
    max_summary_chars: int
    audit_revision_cycles: int
    light_audit_revision_cycles: int
    search_profile: str
    search_prompt_article_target: str
    fast_optional_module_policy: bool


_MODE_CONFIGS: dict[str, AnalysisModeConfig] = {
    "balanced": AnalysisModeConfig(
        mode="balanced",
        label="Balanced",
        description="Recommended",
        compact_downstream_context=False,
        downstream_article_limit=None,
        max_summary_chars=700,
        audit_revision_cycles=2,
        light_audit_revision_cycles=1,
        search_profile="balanced",
        search_prompt_article_target="15-18",
        fast_optional_module_policy=False,
    ),
    "fast": AnalysisModeConfig(
        mode="fast",
        label="Fast",
        description="Quicker briefing with less comprehensive context",
        compact_downstream_context=True,
        downstream_article_limit=10,
        max_summary_chars=700,
        audit_revision_cycles=1,
        light_audit_revision_cycles=0,
        search_profile="fast",
        search_prompt_article_target="8-10",
        fast_optional_module_policy=True,
    ),
    "deep": AnalysisModeConfig(
        mode="deep",
        label="Deep",
        description="Full-depth analysis",
        compact_downstream_context=False,
        downstream_article_limit=None,
        max_summary_chars=700,
        audit_revision_cycles=2,
        light_audit_revision_cycles=1,
        search_profile="balanced",
        search_prompt_article_target="15-18",
        fast_optional_module_policy=False,
    ),
}

_MODE_ALIASES = {
    "": DEFAULT_ANALYSIS_MODE,
    "default": DEFAULT_ANALYSIS_MODE,
    "recommended": DEFAULT_ANALYSIS_MODE,
    "standard": DEFAULT_ANALYSIS_MODE,
    "normal": DEFAULT_ANALYSIS_MODE,
}


def normalize_analysis_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = _MODE_ALIASES.get(normalized, normalized)
    if normalized in _MODE_CONFIGS:
        return normalized
    return DEFAULT_ANALYSIS_MODE


def get_analysis_mode_config(mode: str | None) -> dict[str, Any]:
    return asdict(_MODE_CONFIGS[normalize_analysis_mode(mode)])


def should_use_compact_context(mode: str | None) -> bool:
    config = _MODE_CONFIGS[normalize_analysis_mode(mode)]
    return config.compact_downstream_context


def audit_revision_cycles_for(mode: str | None, stage: str = "default") -> int:
    config = _MODE_CONFIGS[normalize_analysis_mode(mode)]
    if stage in {"recruiter", "routing", "light"}:
        return config.light_audit_revision_cycles
    return config.audit_revision_cycles


def max_articles_for_downstream(mode: str | None) -> int | None:
    config = _MODE_CONFIGS[normalize_analysis_mode(mode)]
    return config.downstream_article_limit


def search_profile_for_mode(mode: str | None) -> str:
    config = _MODE_CONFIGS[normalize_analysis_mode(mode)]
    return config.search_profile


def max_articles_for_qa(mode: str | None) -> int | None:
    return None


def build_articles_context_for_mode(
    articles_data: dict,
    mode: str | None,
) -> dict:
    config = _MODE_CONFIGS[normalize_analysis_mode(mode)]
    if not config.compact_downstream_context:
        return articles_data
    return build_compact_articles_data(
        articles_data,
        max_articles=config.downstream_article_limit,
        max_summary_chars=config.max_summary_chars,
    )


def article_context_stats_for_mode(
    articles_data: dict,
    mode: str | None,
) -> dict:
    config = _MODE_CONFIGS[normalize_analysis_mode(mode)]
    stats = article_context_stats(
        articles_data,
        max_articles=config.downstream_article_limit,
        max_summary_chars=config.max_summary_chars,
    )
    stats["mode"] = config.mode
    stats["compact_context_enabled"] = config.compact_downstream_context
    return stats
