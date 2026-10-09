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
                 timeout_seconds: int = 20) -> None:
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or not parsed.path.endswith("/chat/completions")):
            raise ValueError("LLM endpoint must be an explicit HTTPS chat-completions URL")
        if not model_id.strip() or not api_key_env.startswith("VALUE_AGENT_"):
            raise ValueError("LLM model and dedicated credential environment key are required")
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("LLM timeout must be bounded")
        self.endpoint = endpoint
        self.model_id = model_id
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def complete(self, request: LLMRequest) -> LLMResponse:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError("LLM credential is absent")
        if not 1 <= request.max_completion_tokens <= 512:
            raise ValueError("LLM completion budget exceeded")
        body = json.dumps({
            "model": self.model_id,
            "messages": [{"role": "system", "content": request.system},
                         {"role": "user", "content": request.user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "agent_research_finding", "strict": True,
                "schema": request.output_schema,
            }},
            "max_completion_tokens": request.max_completion_tokens,
            "store": False,
        }, ensure_ascii=False).encode("utf-8")
        http_request = Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        })
        with build_opener(_NoRedirect).open(http_request, timeout=self.timeout_seconds) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("LLM response exceeds size limit")
        payload = json.loads(raw)
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("LLM response requires one choice")
        message = choices[0].get("message") or {}
        if message.get("tool_calls") or message.get("function_call"):
            raise ValueError("LLM tool calls are forbidden")
        usage = payload.get("usage") or {}
        if (type(usage.get("prompt_tokens")) is not int
                or type(usage.get("completion_tokens")) is not int):
            raise ValueError("LLM response usage must contain integer token counts")
        if not isinstance(message.get("content"), str):
            raise ValueError("LLM response content is missing")
        return LLMResponse(
            text=message["content"], prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            model_id=str(payload.get("model") or self.model_id), tool_calls=0,
        )
