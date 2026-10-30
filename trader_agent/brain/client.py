"""Thin wrapper over the Anthropic Python SDK for strict-JSON calls.

- model IDs per tier come from .env (BRAIN_MODEL_FAST / _BALANCED / _DEEP)
- every call has a hard timeout and no automatic retries (a late answer is useless)
- answers are constrained to a JSON schema (structured outputs)
- every call — ok or not — is written to SSoR `ai_usage`; a daily cap on calls
  and tokens is checked before each call
"""

from __future__ import annotations

import json
import time

import pandas as pd

from ..ssor import SSoR


class BrainUnavailable(RuntimeError):
    """The AI could not give a usable answer. `status` says why."""

    def __init__(self, status: str, detail: str = ""):
        super().__init__(f"{status}: {detail}" if detail else status)
        self.status = status


_STATUS_BY_ERROR = {
    "APITimeoutError": "timeout",
    "RateLimitError": "rate_limited",
    "APIConnectionError": "connection",
    "AuthenticationError": "auth",  # wrong ANTHROPIC_API_KEY
    "PermissionDeniedError": "auth",
    "NotFoundError": "model_not_found",  # wrong BRAIN_MODEL_* id
    "BadRequestError": "bad_request",
}


def _classify(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    return _STATUS_BY_ERROR.get(type(exc).__name__, "error")


class BrainClient:
    def __init__(self, ssor: SSoR, models: dict[str, str], max_calls_per_day: int = 300,
                 max_tokens_per_day: int = 2_000_000, sdk_client=None):
        self.ssor = ssor
        self.models = dict(models)
        self.max_calls_per_day = max_calls_per_day
        self.max_tokens_per_day = max_tokens_per_day
        self._sdk_client = sdk_client  # injected in tests

    def _sdk(self):
        if self._sdk_client is None:
            import anthropic  # reads ANTHROPIC_API_KEY from the environment

            self._sdk_client = anthropic.Anthropic()
        return self._sdk_client

    def budget_left(self, now) -> bool:
        day_start = pd.Timestamp(now).tz_convert("UTC").normalize()
        used = self.ssor.ai_usage_between(day_start, day_start + pd.Timedelta(days=1))
        return used["calls"] < self.max_calls_per_day and used["tokens"] < self.max_tokens_per_day

    def ask_json(self, *, purpose: str, tier: str, system: str, prompt: str, schema: dict, now,
                 max_tokens: int = 2048, timeout: float = 8.0, effort: str = "low", stream: bool = False) -> dict:
        model = self.models.get(tier)
        if not model:
            raise BrainUnavailable("no_model", f"set BRAIN_MODEL_{tier.upper()} in .env")
        if not self.budget_left(now):
            raise BrainUnavailable("budget", "daily AI limit reached")
        request = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        }
        started = time.monotonic()
        try:
            client = self._sdk().with_options(timeout=timeout, max_retries=0)
            if stream:
                with client.messages.stream(**request) as live:
                    response = live.get_final_message()
            else:
                response = client.messages.create(**request)
        except Exception as exc:  # noqa: BLE001 — any failure means "no answer", recorded below
            status = _classify(exc)
            self.ssor.record_ai_usage(now, purpose, model, status, latency_ms=int((time.monotonic() - started) * 1000))
            raise BrainUnavailable(status, type(exc).__name__) from None
        usage = response.usage
        tokens_in = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) + (
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        )
        tokens_out = getattr(usage, "output_tokens", 0) or 0
        latency = int((time.monotonic() - started) * 1000)
        stop = getattr(response, "stop_reason", None)
        status = "ok" if stop in ("end_turn", "stop_sequence", None) else str(stop)
        self.ssor.record_ai_usage(now, purpose, model, status, tokens_in, tokens_out, latency)
        if stop == "refusal":
            raise BrainUnavailable("refusal")
        if stop == "max_tokens":
            raise BrainUnavailable("truncated")
        text = next((block.text for block in response.content if getattr(block, "type", "") == "text"), None)
        if not text:
            raise BrainUnavailable("empty")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise BrainUnavailable("bad_json") from None
        missing = [key for key in schema.get("required", []) if key not in data]
        if missing:
            raise BrainUnavailable("bad_json", f"missing {missing}")
        return data
