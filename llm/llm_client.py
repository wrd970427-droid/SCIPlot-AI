"""OpenAI-compatible LLM client. API keys come from the environment only."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return
    load_dotenv(env_path)


_load_dotenv()

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "claude": "https://api.anthropic.com/v1",
    "openai_compatible": "",
}


class LLMError(RuntimeError):
    """Raised when the remote LLM call fails. Callers must fall back."""


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    api_key: str
    model_name: str
    base_url: str
    timeout_sec: float = 30.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        enabled_raw = os.environ.get("LLM_ENABLED", "false").strip().lower()
        enabled = enabled_raw in {"1", "true", "yes", "on"}
        provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower() or "openai"
        api_key = os.environ.get("API_KEY", "").strip()
        model_name = os.environ.get("MODEL_NAME", "gpt-4o-mini").strip() or "gpt-4o-mini"
        base_url = os.environ.get("LLM_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            base_url = PROVIDER_BASE_URLS.get(provider, PROVIDER_BASE_URLS["openai"])
        if provider == "openai_compatible" and not os.environ.get("LLM_BASE_URL"):
            enabled = False
        if not api_key:
            enabled = False
        return cls(
            enabled=enabled,
            provider=provider,
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
        )


class LLMClient:
    """Minimal chat client. Does not generate R and does not log secrets."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()

    @property
    def available(self) -> bool:
        return bool(self.config.enabled and self.config.api_key and self.config.base_url)

    def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.available:
            raise LLMError("LLM disabled or API_KEY/LLM_BASE_URL missing")
        if self.config.provider == "claude" and "anthropic" in self.config.base_url:
            raise LLMError("Native Claude Messages API is not wired; set LLM_BASE_URL to an OpenAI-compatible gateway")
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model_name,
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            data: dict[str, Any] = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            raise LLMError("LLM response missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM returned empty content")
        return content
