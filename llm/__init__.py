"""LLM NLU + R code editing. Raw dataframe values never enter prompts."""

from llm.llm_client import LLMClient, LLMConfig, LLMError
from llm.r_code_editor import RCodeEditor, looks_like_science_transform

__all__ = [
    "IntentParser",
    "LLMClient",
    "LLMConfig",
    "LLMError",
    "RCodeEditor",
    "looks_like_science_transform",
]


def __getattr__(name: str):
    if name == "IntentParser":
        from llm.intent_parser import IntentParser

        return IntentParser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
