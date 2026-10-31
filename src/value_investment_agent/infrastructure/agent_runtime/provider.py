"""Provider-neutral request contract and an opt-in Chat Completions adapter."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from typing import Protocol
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


@dataclass(frozen=True)
class LLMRequest:
    role: str
    system: str
    user: str
    output_schema: dict
    max_completion_tokens: int = 512


@dataclass(frozen=True)
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model_id: str
    tool_calls: int = 0


class LLMProvider(Protocol):
    model_id: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


class MockLLMProvider:
    """Distinct fixed role replies for a no-network end-to-end rehearsal."""

    model_id = "MOCK_STRUCTURED_RESEARCH"

    def __init__(self, responses: dict[str, str]) -> None:
        if set(responses) != {"FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT"}:
            raise ValueError("Mock provider requires exactly three role responses")
        self._responses = dict(responses)
        self.responses_sha256 = hashlib.sha256(json.dumps(
            self._responses, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(self._responses[request.role], 200, 100, self.model_id)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("LLM endpoint redirects are forbidden")


class OpenAICompatibleChatProvider:
    """Explicit HTTPS adapter. Config/secret are supplied only for authorized runs."""

    def __init__(self, *, endpoint: str, model_id: str, api_key_env: str,
                 timeout_seconds: int = 20, max_completion_tokens_cap: int = 512,
                 response_size_cap: int = 65536, response_format_mode: str = "json_schema",
                 thinking_mode: str | None = None) -> None:
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or not parsed.path.endswith("/chat/completions")):
            raise ValueError("LLM endpoint must be an explicit HTTPS chat-completions URL")
        if not model_id.strip() or not api_key_env.startswith("VALUE_AGENT_"):
            raise ValueError("LLM model and dedicated credential environment key are required")
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("LLM timeout must be bounded")
        if type(max_completion_tokens_cap) is not int or not 1 <= max_completion_tokens_cap <= 8192:
            raise ValueError("LLM completion cap must be an integer within 1..8192")
        if type(response_size_cap) is not int or not 1 <= response_size_cap <= 262144:
            raise ValueError("LLM response size cap must be an integer within 1..262144")
        if response_format_mode not in ("json_schema", "json_object"):
            raise ValueError("LLM response format mode must be json_schema or json_object")
        if thinking_mode not in (None, "disabled"):
            raise ValueError("LLM thinking mode must be None or disabled")
        self.response_format_mode = response_format_mode
        self.thinking_mode = thinking_mode
        self.max_completion_tokens_cap = max_completion_tokens_cap
        self.response_size_cap = response_size_cap
        self.endpoint = endpoint
        self.model_id = model_id
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def complete(self, request: LLMRequest) -> LLMResponse:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError("LLM credential is absent")
        if (type(request.max_completion_tokens) is not int
                or not 1 <= request.max_completion_tokens <= self.max_completion_tokens_cap):
            raise ValueError("LLM completion budget exceeded")
        payload = {
            "model": self.model_id,
            "messages": [{"role": "system", "content": request.system},
                         {"role": "user", "content": request.user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "agent_research_finding", "strict": True,
                "schema": request.output_schema,
            }},
            "max_completion_tokens": request.max_completion_tokens,
            "store": False,
        }
        if self.response_format_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
            payload["max_tokens"] = payload.pop("max_completion_tokens")
            # JSON mode transports no schema contract. Carry the same trusted
            # request schema in the prompt; local validators remain mandatory.
            payload["messages"][1]["content"] += (
                "\n\nTRUSTED OUTPUT SCHEMA: Return only one JSON object strictly conforming "
                "to this JSON Schema. Do not add keys or surrounding prose.\n"
                + json.dumps(request.output_schema, ensure_ascii=False))
        if self.thinking_mode is not None:
            payload["thinking"] = {"type": self.thinking_mode}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        })
        with build_opener(_NoRedirect).open(http_request, timeout=self.timeout_seconds) as response:
            raw = response.read(self.response_size_cap + 1)
        if len(raw) > self.response_size_cap:
            raise ValueError("LLM response exceeds size limit")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("LLM response must be an object")
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("LLM response requires one choice")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ValueError("LLM choice must be an object")
        # Missing finish_reason remains compatible with retained adapter fixtures.
        if choice.get("finish_reason") not in (None, "stop"):
            raise ValueError("LLM response is truncated, filtered, refused or incomplete")
        message = choice.get("message") or {}
        if not isinstance(message, dict):
            raise ValueError("LLM message must be an object")
        if message.get("refusal"):
            raise ValueError("LLM response refusal is forbidden")
        if message.get("tool_calls") or message.get("function_call"):
            raise ValueError("LLM tool calls are forbidden")
        usage = payload.get("usage") or {}
        if (not isinstance(usage, dict)
                or type(usage.get("prompt_tokens")) is not int
                or type(usage.get("completion_tokens")) is not int
                or usage["prompt_tokens"] < 0
                or not 0 <= usage["completion_tokens"] <= request.max_completion_tokens):
            raise ValueError("LLM response usage must contain integer token counts")
        if not isinstance(message.get("content"), str):
            raise ValueError("LLM response content is missing")
        return LLMResponse(
            text=message["content"], prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            model_id=str(payload.get("model") or self.model_id), tool_calls=0,
        )
