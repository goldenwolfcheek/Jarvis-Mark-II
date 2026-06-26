"""
Jarvis Mark II — LLM Core.
OpenAI-compatible HTTP client for chatting with any provider.
Handles streaming, tool calling, retries, and error handling.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, AsyncIterator, Optional

import httpx

from ..config import get_config
from ..providers import ProviderRegistry
from ..security import resolve_api_key

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120.0


class LLMCore:
    """Async LLM client compatible with any OpenAI-compatible API endpoint.

    Features:
      - Streaming and non-streaming completions
      - Tool calling support (function calling)
      - Automatic API key resolution from config / key store / env
      - Configurable retries with exponential backoff
      - Token usage tracking
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = 2,
    ):
        config = get_config()
        self._provider = provider or config.get_active_provider()
        self._model = model or config.get_active_model()

        # Resolve base URL — try ProviderRegistry first, then fall back to config
        if base_url:
            self._base_url = base_url.rstrip("/")
        else:
            registry = ProviderRegistry.get_instance()
            profile = registry.get(self._provider)
            if profile and profile.base_url:
                self._base_url = profile.base_url.rstrip("/")
            else:
                provider_cfg = config.get_provider(self._provider) or {}
                self._base_url = (provider_cfg.get("base_url") or "http://localhost:11434/v1").rstrip("/")

        # Resolve API key
        self._api_key = resolve_api_key(self._provider, explicit_key=api_key)
        self._timeout = timeout
        self._max_retries = max_retries

        # Token tracking
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_cost = 0.0

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def total_prompt_tokens(self) -> int:
        return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        return self._total_completion_tokens

    @property
    def total_tokens(self) -> int:
        return self._total_prompt_tokens + self._total_completion_tokens

    def get_usage_summary(self) -> dict:
        """Return a summary of token usage."""
        return {
            "provider": self._provider,
            "model": self._model,
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens,
            "total_tokens": self.total_tokens,
        }

    # ── Chat completion (non-streaming) ───────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 0.9,
        **extra_kwargs: Any,
    ) -> dict:
        """Send a chat completion request (non-streaming).

        Args:
            messages: List of message dicts (role, content, etc).
            tools: Optional list of OpenAI-compatible tool definitions.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens to generate.
            top_p: Nucleus sampling parameter.
            **extra_kwargs: Additional parameters passed to the API.

        Returns:
            The full API response dict, or an error dict on failure.
        """
        payload = self._build_payload(messages, tools, temperature, max_tokens, top_p, extra_kwargs)
        if extra_kwargs.get("stream"):
            payload["stream"] = False  # non-streaming mode

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    headers = self._build_headers()
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("retry-after", 2 ** attempt))
                        await self._sleep(retry_after)
                        continue

                    if resp.status_code == 401:
                        return {"error": "Authentication failed. Check your API key.", "status": 401}

                    if resp.status_code >= 500:
                        if attempt < self._max_retries:
                            await self._sleep(2 ** attempt)
                            continue
                        return {"error": f"Server error ({resp.status_code})", "status": resp.status_code}

                    data = resp.json()
                    self._track_usage(data)
                    return data

            except httpx.TimeoutException:
                last_error = "Request timed out"
                if attempt < self._max_retries:
                    await self._sleep(2 ** attempt)
                    continue
            except httpx.HTTPError as e:
                last_error = str(e)
                if attempt < self._max_retries:
                    await self._sleep(2 ** attempt)
                    continue
            except Exception as e:
                return {"error": str(e)}

        return {"error": last_error or "Max retries exceeded"}

    # ── Streaming ─────────────────────────────────────────────────────────

    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 0.9,
        **extra_kwargs: Any,
    ) -> AsyncIterator[dict]:
        """Stream a chat completion. Yields delta dicts.

        Each yield has the shape:
            {"type": "delta", "content": "...", "finish_reason": None}
            {"type": "delta", "tool_calls": [...]}
            {"type": "done", "usage": {...}}
            {"type": "error", "error": "..."}
        """
        payload = self._build_payload(messages, tools, temperature, max_tokens, top_p, extra_kwargs)
        payload["stream"] = True

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    headers = self._build_headers(stream=True)
                    # Debug: log the message payload for troubleshooting tool_call_id issues
                    logger.debug("[LLM] Sending to %s/chat/completions (model=%s)", self._base_url, self._model)
                    for i, msg in enumerate(payload.get("messages", [])):
                        role = msg.get("role", "?")
                        has_tc = "tool_calls" in msg
                        has_tcid = "tool_call_id" in msg
                        tc_tcid_info = ""
                        if has_tc:
                            tc_ids = [tc.get("id", "?") for tc in msg["tool_calls"]]
                            tc_tcid_info = f" tool_calls={tc_ids}"
                        if has_tcid:
                            tc_tcid_info = f" tool_call_id={msg['tool_call_id']}"
                        content_preview = (msg.get("content") or "")[:80]
                        logger.debug("  [%d] role=%s content=%r%s", i, role, content_preview, tc_tcid_info)
                    async with client.stream(
                        "POST",
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as resp:

                        if resp.status_code == 401:
                            yield {"type": "error", "error": "Authentication failed. Check your API key."}
                            return

                        if resp.status_code >= 500:
                            if attempt < self._max_retries:
                                await self._sleep(2 ** attempt)
                                continue
                            yield {"type": "error", "error": f"Server error ({resp.status_code})"}
                            return

                        if resp.status_code != 200:
                            body = await resp.aread()
                            body_text = body.decode(errors='replace')[:500]
                            logger.warning("[LLM] HTTP %d response body: %s", resp.status_code, body_text)
                            yield {"type": "error", "error": f"HTTP {resp.status_code}: {body_text}"}
                            return

                        usage_data = None
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            chunk = line[6:].strip()
                            if chunk == "[DONE]":
                                break

                            try:
                                data = json.loads(chunk)
                            except json.JSONDecodeError:
                                continue

                            choices = data.get("choices", [])
                            if not choices:
                                # Some providers send usage in a separate chunk
                                if "usage" in data:
                                    usage_data = data["usage"]
                                continue

                            choice = choices[0]
                            delta = choice.get("delta", {})
                            finish_reason = choice.get("finish_reason")

                            if delta.get("content"):
                                yield {
                                    "type": "delta",
                                    "content": delta["content"],
                                    "finish_reason": finish_reason,
                                }

                            if delta.get("tool_calls"):
                                yield {
                                    "type": "delta",
                                    "tool_calls": delta["tool_calls"],
                                    "finish_reason": finish_reason,
                                }

                            if finish_reason:
                                # Try to get usage from the choice or data
                                usage = choice.get("usage") or data.get("usage") or usage_data
                                if usage:
                                    self._accumulate_usage(usage)
                                yield {
                                    "type": "done",
                                    "finish_reason": finish_reason,
                                    "usage": usage,
                                }
                                return

                        # Stream ended without finish_reason
                        yield {"type": "done", "finish_reason": "stop", "usage": usage_data}

            except httpx.TimeoutException:
                yield {"type": "error", "error": "Request timed out"}
                return
            except httpx.HTTPError as e:
                if attempt < self._max_retries:
                    await self._sleep(2 ** attempt)
                    continue
                yield {"type": "error", "error": str(e)}
                return
            except Exception as e:
                yield {"type": "error", "error": str(e)}
                return

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        temperature: float,
        max_tokens: Optional[int],
        top_p: float,
        extra: dict,
    ) -> dict:
        # Normalise messages so every one has a 'type' field.
        # Some providers (DeepSeek, etc.) enforce strict deserialisation and
        # reject messages that lack 'type' even though standard OpenAI format
        # uses 'role' only. We also ensure every tool-call item has "type": "function".
        normalized = []
        for msg in messages:
            m = dict(msg)
            # Safety filter: drop assistant messages that have empty content
            # AND no tool_calls — some providers (DeepSeek, etc.) reject these
            # with 400 errors.
            if m.get("role") == "assistant":
                has_content = bool(m.get("content"))
                has_tc = bool(m.get("tool_calls"))
                if not has_content and not has_tc:
                    continue
            if "type" not in m:
                m["type"] = m.get("role", "user")
            if "tool_calls" in m:
                for tc in m["tool_calls"]:
                    if "type" not in tc:
                        tc["type"] = "function"
            normalized.append(m)

        payload = {
            "model": self._model,
            "messages": normalized,
            "temperature": temperature,
            "top_p": top_p,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        # Merge extra params (stream already handled)
        for k, v in extra.items():
            if k not in ("stream",):
                payload[k] = v
        return payload

    def _build_headers(self, stream: bool = False) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "User-Agent": "Jarvis-Mark-II/2.0",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _track_usage(self, data: dict):
        """Track usage from a non-streaming response."""
        usage = data.get("usage")
        if usage:
            self._accumulate_usage(usage)

    def _accumulate_usage(self, usage: dict):
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        self._total_prompt_tokens += prompt
        self._total_completion_tokens += completion

    @staticmethod
    async def _sleep(seconds: float):
        await asyncio.sleep(seconds)

    # ── Convenience ───────────────────────────────────────────────────────

    def extract_assistant_message(self, response: dict) -> dict:
        """Extract the assistant message dict from an API response."""
        if "error" in response:
            return {"role": "assistant", "content": f"[Error: {response['error']}]"}
        choices = response.get("choices", [])
        if not choices:
            return {"role": "assistant", "content": "[Empty response]"}
        return choices[0].get("message", {"role": "assistant", "content": "[No message]"})


# ── Singleton ─────────────────────────────────────────────────────────────

_llm_instance: Optional[LLMCore] = None
_llm_lock = threading.Lock()


def get_llm_core(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMCore:
    """Return the global LLMCore singleton (re-created if provider/model change)."""
    global _llm_instance
    config = get_config()
    p = provider or config.get_active_provider()
    m = model or config.get_active_model()

    with _llm_lock:
        if _llm_instance is None or _llm_instance.provider != p or _llm_instance.model != m:
            _llm_instance = LLMCore(provider=p, model=m)
        return _llm_instance
