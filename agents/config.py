"""Shared configuration for the NewsLens agents.

The model is always passed explicitly through the pipeline; this module only
provides the fallback default so no global (environment) state is needed.
"""

DEFAULT_MODEL = "gemini-3.1-flash-lite"


def resolve_model(model_name: str | None) -> str:
    """Returns the explicit model name, or the project default."""
    return model_name or DEFAULT_MODEL
