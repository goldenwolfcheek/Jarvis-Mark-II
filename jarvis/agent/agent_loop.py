"""
Jarvis Mark II — Agent Loop.
The main execution loop that orchestrates conversation, tool calling,
memory management, and LLM interaction.

This is the brain of Jarvis — it ties together:
  - LLM Core (chat/stream)
  - Tool Registry (execute tools)
  - State DB (persist messages)
  - Memory Store (long-term & user profile)
  - Speech/TTS
  - Skill Loader
"""

import asyncio
import json
import re
import threading
import time
import logging
import traceback
import uuid

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from ..config import get_config
from ..constants import FILE_READ_MAX_CHARS, MAX_TOOL_TURNS, TOOL_OUTPUT_MAX_CHARS, MAX_TOOL_DEFS
from ..memory.store import MemoryStore, get_memory_store
from ..state.db import StateDB, get_state_db
from ..tools.registry import ToolRegistry, get_tool_registry
from ..skills.loader import SkillLoader, get_skill_loader
from .llm_core import LLMCore, get_llm_core

# Known reasoning_effort values supported by providers like Anthropic, Gemini
VALID_REASONING_EFFORTS = frozenset({"low", "medium", "high"})


# ── Data structures ───────────────────────────────────────────────────────

@dataclass
class AgentContext:
    """Mutable context carried through a single agent turn."""
    session_id: str
    messages: list[dict] = field(default_factory=list)
    system_prompt: str = ""
    tool_turns: int = 0
    tool_results: list[dict] = field(default_factory=list)
    should_stop: bool = False
    abort_reason: str = ""


# ── Default system prompt ─────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are **Jarvis Mark II**, an intelligent AI desktop assistant.

You can:
- Answer questions and have natural conversations
- Read and write files on the local filesystem
- Execute shell commands and control the PC (launch apps, manage windows, type, click)
- Take screenshots and make web requests
- Manage the user's long-term memory
- Speak responses aloud via text-to-speech
- Run dynamically loaded skills

Guidelines:
- Be concise, helpful, and direct.
- When you need information, use your tools rather than guessing.
- When performing actions, explain what you're doing.
- If a tool call fails, try an alternative approach or report clearly.
- Respect the user's privacy and system integrity.
- Use long-term memory to remember important facts about the user.
- After using a tool, interpret the result and continue toward the user's goal.
- CRITICAL: Tool results are returned as raw JSON. NEVER echo or repeat the raw JSON in your response. Always interpret the result and respond conversationally.

Current configuration:
- Provider: {provider}
- Model: {model}
- Toolsets enabled: {toolsets}

{memory_block}"""


def _build_system_prompt() -> str:
    """Construct the system prompt with current config and memory."""
    config = get_config()
    memory = get_memory_store()
    mem_info = memory.get_for_system_prompt()

    memory_block = ""
    personality_text = mem_info.get("personality", "").strip()
    if personality_text and personality_text != "# Personality":
        lines = [l for l in personality_text.split("\n") if l.strip() and not l.strip().startswith("#")]
        if lines:
            memory_block += "## Personality\n" + "\n".join(lines)
            memory_block += "\n\nIMPORTANT: This is your active personality — embody it fully in every response.\n"

    user_text = mem_info.get("user_profile", "").strip()
    if user_text and user_text != "# User Profile":
        lines = [l for l in user_text.split("\n") if l.strip() and not l.strip().startswith("#")]
        if lines:
            memory_block += "\n## User Profile\n" + "\n".join(lines)

    memory_text = mem_info.get("memory", "").strip()
    if memory_text and memory_text != "# Memory":
        lines = [l for l in memory_text.split("\n") if l.strip() and not l.strip().startswith("#")]
        if lines:
            memory_block += "\n## Memory\n" + "\n".join(lines)

    toolsets = config.get("toolsets", ["core", "memory", "files", "web", "pc", "skills"])

    prompt = DEFAULT_SYSTEM_PROMPT
    prompt = prompt.replace("{provider}", config.get_active_provider())
    prompt = prompt.replace("{model}", config.get_active_model())
    prompt = prompt.replace("{toolsets}", ", ".join(toolsets))
    prompt = prompt.replace("{memory_block}", memory_block.strip())
    return prompt


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

# Regex matching JSON object blocks whose FIRST key matches common tool-result fields.
# This catches cases where the LLM echoes raw tool output verbatim.
_TOOL_JSON_RE = re.compile(
    r'\{\s*"(?:status|error|ok|path|bytes_written|success|result|output|stdout|stderr|exit_code)"[^}]*\}'
)

def _strip_tool_json(text: str) -> str:
    """Strip raw tool-result JSON blocks from assistant response text.

    Only strips if the result is non-empty after stripping — if the ENTIRE
    response is a tool-JSON block, keep it as-is (it's the real LLM output
    and should not be replaced by the generic fallback).
    """
    cleaned = _TOOL_JSON_RE.sub("", text)
    # Clean up any double spaces or awkward whitespace left behind
    cleaned = re.sub(r'  +', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    # If stripping consumed the entire response, revert to original
    # (the LLM genuinely produced a JSON-looking response — show it)
    return cleaned if cleaned else text.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Agent Loop
# ═══════════════════════════════════════════════════════════════════════════

class AgentLoop:
    """Main agent execution loop.

    Orchestrates the full turn loop:
      1. Build messages (system + history + new input)
      2. Call LLM
      3. If tool calls -> execute tools -> loop back to LLM
      4. If text response -> return to caller
    """

    def __init__(
        self,
        llm: Optional[LLMCore] = None,
        registry: Optional[ToolRegistry] = None,
        db: Optional[StateDB] = None,
        memory: Optional[MemoryStore] = None,
        skills: Optional[SkillLoader] = None,
    ):
        self._config = get_config()
        self._llm = llm or get_llm_core()
        self._registry = registry or get_tool_registry()
        self._db = db or get_state_db()
        self._memory = memory or get_memory_store()
        self._skills = skills or get_skill_loader()

    # ── Public API ────────────────────────────────────────────────────────

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        stream: bool = True,
        max_tool_turns: int = MAX_TOOL_TURNS,
        reasoning_effort: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[dict]:
        """Process a user message through the full agent loop.

        Args:
            session_id: The conversation session identifier.
            user_message: The user's text input.
            stream: Whether to yield streaming deltas from the LLM.
            max_tool_turns: Maximum number of tool-calling iterations.
            cancel_event: Optional event that, when set, stops processing.

        Yields:
            Event dicts with types:
              - "delta": streaming text chunk
              - "tool_call": tool invocation details
              - "tool_result": result of a tool execution
              - "turn_end": final assistant message for this turn
              - "error": something went wrong
              - "done": end of processing
        """
        # Reset tool turn counter for each new message (prevents global counter from blocking tools across sessions)
        self._registry.reset_turn_count()

        # Ensure session exists
        self._db.create_session(session_id, title="New Session")

        # Store user message
        self._db.append_message(session_id, "user", user_message)

        # Build context
        ctx = AgentContext(session_id=session_id)
        ctx.system_prompt = _build_system_prompt()

        # Load history (last 20 messages)
        history = self._db.get_recent_messages(session_id, count=20)
        if history and history[-1]["role"] == "user" and history[-1]["content"] == user_message:
            pass  # already appended
        else:
            history.append({"role": "user", "content": user_message})

        ctx.messages = self._build_message_list(ctx.system_prompt, history)

        # Build tool definitions
        toolsets = self._config.get("toolsets", ["core", "memory", "files", "web", "pc", "skills"])
        tool_defs = self._registry.get_tool_definitions(categories=toolsets)

        # Prioritise essential categories when we have too many tools
        # (many providers reject requests with 50+ tool definitions)
        if len(tool_defs) > MAX_TOOL_DEFS:
            priority_order = ["core", "files", "web", "pc", "memory", "system"]
            prioritized = []
            for cat in priority_order:
                for t in tool_defs:
                    if t.get("category") == cat or t.get("function", {}).get("category") == cat:
                        prioritized.append(t)
            # Any remaining that weren't in priority categories
            for t in tool_defs:
                if t not in prioritized:
                    prioritized.append(t)
            tool_defs = prioritized[:MAX_TOOL_DEFS]

        # Add skill tool definitions (lower priority — capped to prevent 400 errors)
        try:
            skill_defs = self._skills.get_tool_definitions()
            remaining = MAX_TOOL_DEFS - len(tool_defs)
            if remaining > 0:
                tool_defs.extend(skill_defs[:remaining])
        except Exception:
            logger.warning("[Agent] Failed to load skill tool definitions", exc_info=True)

        # Main loop
        last_assistant_text = None

        while ctx.tool_turns < max_tool_turns and not ctx.should_stop:
            # Check for user cancellation
            if cancel_event and cancel_event.is_set():
                logger.info("[Agent] Processing cancelled by user")
                yield {"type": "done"}
                return

            extra_kwargs = {}
            if reasoning_effort:
                if reasoning_effort not in VALID_REASONING_EFFORTS:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Ignoring unsupported reasoning_effort=%r; valid: %s",
                        reasoning_effort, sorted(VALID_REASONING_EFFORTS),
                    )
                else:
                    extra_kwargs["reasoning_effort"] = reasoning_effort

            if stream:
                # Streaming mode — propagate deltas to WebSocket
                content_parts = []
                tool_calls_accumulated = []
                logger.debug("[Agent] Turn %d: calling LLM (stream)", ctx.tool_turns + 1)
                logger.debug("[Agent] ctx.messages count=%d roles=%s", len(ctx.messages), [m.get("role", "?") for m in ctx.messages])
                async for event in self._stream_llm_turn(ctx, tool_defs, **extra_kwargs):
                    # Check for user cancellation between streaming events
                    if cancel_event and cancel_event.is_set():
                        logger.info("[Agent] Stream cancelled by user")
                        yield {"type": "done"}
                        return
                    if event["type"] == "delta":
                        yield event
                        if "content" in event and event["content"]:
                            content_parts.append(event["content"])
                        # Accumulate tool call deltas (OpenAI streaming: index-based chunks)
                        if "tool_calls" in event and event["tool_calls"]:
                            for tc_delta in event["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                while len(tool_calls_accumulated) <= idx:
                                    tool_calls_accumulated.append({
                                        "id": uuid.uuid4().hex[:12],
                                        "function": {"name": "", "arguments": ""}
                                    })
                                tc = tool_calls_accumulated[idx]
                                if tc_delta.get("id"):
                                    tc["id"] = tc_delta["id"]
                                fn_delta = tc_delta.get("function", {})
                                if fn_delta.get("name"):
                                    tc["function"]["name"] = fn_delta["name"]
                                if fn_delta.get("arguments"):
                                    tc["function"]["arguments"] += fn_delta["arguments"]
                    elif event["type"] == "error":
                        yield event
                        content_parts.append(f"[Error: {event['error']}]")
                # Build the assistant message from accumulated parts
                content = "".join(content_parts)
                tool_calls = tool_calls_accumulated if tool_calls_accumulated else None
                # When tool_calls are present, set content to None (null) if empty
                # to avoid provider validation issues with content="" alongside tool_calls
                if tool_calls and not content:
                    content = None
                assistant_message = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_message["tool_calls"] = tool_calls
                logger.debug("[Agent] Assistant message: content_len=%d tool_calls=%s", len(content or ""), bool(tool_calls))
                if tool_calls:
                    for i, tc in enumerate(tool_calls):
                        logger.debug("[Agent]   tool_call[%d]: id=%r name=%s", i, tc.get("id", "?"), tc.get("function", {}).get("name", "?"))
            else:
                # Non-streaming mode
                assistant_message = await self._llm_turn(ctx, tool_defs, **extra_kwargs)
                # Yield the full response
                if assistant_message.get("content"):
                    yield {
                        "type": "delta",
                        "content": assistant_message["content"],
                        "finish_reason": "stop",
                    }

            ctx.messages.append(assistant_message)

            # Validate: if the assistant message has no content AND no tool_calls,
            # it is a dead message that will cause a 400 error on the next turn
            # (providers like DeepSeek reject assistant messages with both empty).
            # Remove it immediately and end the turn.
            msg_content = assistant_message.get("content") or ""
            has_tc = bool(assistant_message.get("tool_calls"))
            if not msg_content and not has_tc:
                ctx.messages.pop()
                logger.warning("[Agent] Dropped empty assistant message (no content, no tool_calls)")
                break

            # Store assistant message
            # Use "" for DB storage to satisfy NOT NULL constraint,
            # even when content=None (tool_calls-only response).
            msg_id = self._db.append_message(
                session_id=session_id,
                role="assistant",
                content=assistant_message.get("content") or "",
                tool_calls=assistant_message.get("tool_calls"),
            )

            # Track last text response (for turn_end — uses the final one,
            # not just the first. Without this, tool-using responses like
            # web search get overwritten by the first "let me search..." text.)
            if assistant_message.get("content"):
                last_assistant_text = assistant_message["content"]

            # Check for tool calls
            tool_calls = assistant_message.get("tool_calls", [])
            if not tool_calls:
                # No more tool calls — we're done
                break

            # Execute each tool call
            yield {"type": "tool_calls", "tool_calls": tool_calls}

            tool_results = []
            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args_raw = tc.get("function", {}).get("arguments", "{}")
                tool_call_id = tc.get("id", "")

                try:
                    func_args = json.loads(func_args_raw) if isinstance(func_args_raw, str) else func_args_raw
                except json.JSONDecodeError:
                    func_args = {}

                yield {
                    "type": "tool_call",
                    "tool_call_id": tool_call_id,
                    "name": func_name,
                    "arguments": func_args,
                }

                # Execute
                result = await self._execute_tool(ctx, func_name, func_args)

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                })

                yield {
                    "type": "tool_result",
                    "tool_call_id": tool_call_id,
                    "name": func_name,
                    "result": result,
                }

            # Append tool results to messages and store
            for tr in tool_results:
                ctx.messages.append(tr)
                self._db.append_message(
                    session_id=session_id,
                    role="tool",
                    content=tr["content"],
                    tool_results=[{"tool_call_id": tr.get("tool_call_id", "")}],
                )

            ctx.tool_turns += 1
            ctx.tool_results = tool_results

        # Turn complete — use the LAST assistant message content (the actual
        # response after tools), not the first "let me search..." preamble.
        final_content = last_assistant_text or "I've completed the requested actions."
        # Safety net: strip any raw tool- JSON the LLM may have echoed
        final_content = _strip_tool_json(final_content)
        # If stripping left us with nothing useful, keep the last text
        if not final_content.strip() and last_assistant_text:
            final_content = last_assistant_text
        if not final_content:
            final_content = "I've completed the requested actions."
        yield {
            "type": "turn_end",
            "content": final_content,
            "tool_turns": ctx.tool_turns,
        }
        yield {"type": "done"}

        # Update memory if we learned something
        await self._maybe_update_memory(ctx)

    # ── LLM Interaction ───────────────────────────────────────────────────

    async def _llm_turn(self, ctx: AgentContext, tool_defs: list[dict], **extra_kwargs) -> dict:
        """One non-streaming LLM call."""
        response = await self._llm.chat(
            messages=ctx.messages,
            tools=tool_defs if tool_defs else None,
            **extra_kwargs,
        )

        if "error" in response:
            ctx.should_stop = True
            return {"role": "assistant", "content": f"[Error: {response['error']}]"}

        message = self._llm.extract_assistant_message(response)
        # NOTE: do NOT append to ctx.messages here — process_message()
        # handles the append at line 283 so it works uniformly for both
        # streaming and non-streaming paths. Appending here would
        # double-append the assistant message in non-streaming mode,
        # corrupting the conversation context on the next LLM call.
        return message

    async def _stream_llm_turn(self, ctx: AgentContext, tool_defs: list[dict], **extra_kwargs):
        """One streaming LLM call, yielding delta and error events.
        If tool definitions cause a 4xx error, automatically retry without tools.
        """
        retry_without_tools = False
        while True:
            current_tools = tool_defs if not retry_without_tools else None
            had_error_400 = False
            async for event in self._llm.chat_stream(
                messages=ctx.messages,
                tools=current_tools,
                **extra_kwargs,
            ):
                if event["type"] == "delta":
                    if "content" in event and event["content"]:
                        yield {
                            "type": "delta",
                            "content": event["content"],
                            "finish_reason": event.get("finish_reason"),
                        }
                    # Also pass tool call deltas through
                    if "tool_calls" in event and event["tool_calls"]:
                        yield {
                            "type": "delta",
                            "tool_calls": event["tool_calls"],
                            "finish_reason": event.get("finish_reason"),
                        }
                elif event["type"] == "error":
                    error_text = event.get("error", "") or ""
                    is_4xx_tool_error = (
                        any(f"{code} " in error_text or f"HTTP {code}" in error_text
                            for code in ("400", "401", "402", "403", "404", "405", "406",
                                         "407", "408", "409", "410", "411", "412", "413",
                                         "414", "415", "416", "417", "429"))
                        and not retry_without_tools
                        and current_tools
                    )
                    if is_4xx_tool_error:
                        logger.warning("[Agent] Model rejected tool definitions (4xx), retrying without tools. Error: %s", error_text[:200])
                        retry_without_tools = True
                        had_error_400 = True
                        break  # retry without tools
                    # For other errors, propagate
                    logger.warning("[Agent] Propagating error (retry_without_tools=%s, has_tools=%s): %s", retry_without_tools, bool(current_tools), error_text[:200])
                    yield {"type": "error", "error": event["error"]}
                    return

            if not had_error_400:
                break  # Successful stream, exit retry loop

        # Return value is ignored — use process_message's accumulation instead
        return

    # ── Tool execution ───────────────────────────────────────────────────

    async def _execute_tool(self, ctx: AgentContext, func_name: str, func_args: dict) -> str:
        """Execute a single tool call, supporting both registry tools and skill tools."""
        # Check registry tools first
        if self._registry.has_tool(func_name):
            result = await self._registry.execute(func_name, func_args)
            return result

        # Check skill tools (pattern: skill_{name}_{func})
        if func_name.startswith("skill_"):
            parts = func_name.split("_", 2)
            if len(parts) >= 3:
                skill_name = parts[1]
                skill_func = parts[2]
                try:
                    result = self._skills.call_function(skill_name, skill_func, **func_args)
                    if result is None:
                        result = ""
                    elif not isinstance(result, str):
                        result = json.dumps(result, ensure_ascii=False, default=str)
                    if len(result) > TOOL_OUTPUT_MAX_CHARS:
                        result = result[:TOOL_OUTPUT_MAX_CHARS] + "\n[TRUNCATED]"
                    return result
                except Exception as e:
                    return json.dumps({"error": str(e)})

        return json.dumps({"error": f"Unknown tool: {func_name}"})

    # ── Message preparation ──────────────────────────────────────────────

    def _build_message_list(self, system_prompt: str, history: list[dict]) -> list[dict]:
        """Build the full message list for the LLM API call.

        Ensures every tool response message has a corresponding assistant
        message with tool_calls. Drops orphaned tool messages and their
        unmatched tool_calls to prevent provider validation errors
        (e.g. DeepSeek requires every 'tool' role message to be preceded
        by an assistant message with matching tool_calls).
        """
        # Build set of tool_call_ids that have corresponding tool responses.
        # Also build a fallback mapping: for each assistant tool_call, remember
        # its ID (even empty) by position.
        tool_call_ids_answered = set()
        assistant_tc_ids: list[str] = []
        for msg in history:
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        tcid = tc.get("id", "")
                        assistant_tc_ids.append(tcid)
            if msg.get("tool_results") and isinstance(msg["tool_results"], list):
                for tr in msg["tool_results"]:
                    tcid = tr.get("tool_call_id") if isinstance(tr, dict) else None
                    if tcid:
                        tool_call_ids_answered.add(tcid)

        messages = [{"role": "system", "content": system_prompt}]

        # Drop orphaned leading TOOL messages so the message list never starts
        # with a tool message (which would lack its parent assistant with
        # tool_calls). This can happen when the history window is truncated
        # mid-turn by get_recent_messages(count=20), and providers like
        # DeepSeek reject such lists with 400 errors.
        orphans_dropped = 0
        while history and history[0]["role"] == "tool" and orphans_dropped < 10:
            dropped = history.pop(0)
            tool_call_ids = (
                [t.get("tool_call_id", "?") for t in dropped.get("tool_results", [])]
                if isinstance(dropped.get("tool_results"), list)
                else []
            )
            logger.debug(
                "[MessageBuilder] Dropped orphaned tool message at window boundary "
                "(tool_call_ids=%s)", tool_call_ids
            )
            orphans_dropped += 1

        tc_index = 0
        # Flag: set when the most recent assistant message had its tool_calls
        # stripped because not all IDs were answered. Subsequent tool messages
        # referencing those IDs are dropped.
        strip_tool_responses = False
        unmatched_tc_ids: set[str] = set()

        for msg in history:
            # ── Assistant message ──────────────────────────────────────
            if msg["role"] == "assistant":
                entry = {"role": "assistant", "content": msg["content"]}

                # tool_calls with empty content → content=null per OpenAI spec
                if msg.get("tool_calls") and not msg["content"]:
                    entry["content"] = None

                # Include tool_calls only when every ID has a matching response
                if msg.get("tool_calls"):
                    all_answered = all(
                        tc["id"] in tool_call_ids_answered
                        for tc in msg["tool_calls"]
                        if isinstance(tc, dict) and tc.get("id")
                    )
                    if all_answered:
                        entry["tool_calls"] = msg["tool_calls"]
                        strip_tool_responses = False
                        unmatched_tc_ids.clear()
                    else:
                        # Partial turn — strip this assistant's tool_calls AND
                        # any subsequent tool messages that belong to it.
                        strip_tool_responses = True
                        unmatched_tc_ids = {
                            tc["id"] for tc in msg["tool_calls"]
                            if isinstance(tc, dict) and tc.get("id")
                        }

                messages.append(entry)
                continue

            # ── Tool response message ──────────────────────────────────
            if msg["role"] == "tool":
                # Determine the tool_call_id for this message
                tool_call_id = ""
                if msg.get("tool_results") and isinstance(msg["tool_results"], list):
                    for tr_item in msg["tool_results"]:
                        if isinstance(tr_item, dict) and tr_item.get("tool_call_id"):
                            tool_call_id = tr_item["tool_call_id"]
                            break
                    else:
                        # Fallback from assistant position
                        if tc_index < len(assistant_tc_ids):
                            tool_call_id = assistant_tc_ids[tc_index] or ""
                    tc_index += len(msg["tool_results"])

                # Drop orphaned tool messages whose assistant side was stripped
                if strip_tool_responses and tool_call_id in unmatched_tc_ids:
                    continue

                entry = {"role": "tool", "content": msg["content"]}
                if tool_call_id:
                    entry["tool_call_id"] = tool_call_id
                messages.append(entry)
                continue

            # ── User message ───────────────────────────────────────────
            if msg["role"] == "user":
                # Reset the strip flag — a new user message starts a fresh turn
                strip_tool_responses = False
                unmatched_tc_ids.clear()

                messages.append({
                    "role": "user",
                    "content": msg["content"],
                })
                continue

            # ── Fallback (system, etc.) ─────────────────────────────────
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        return messages

    # ── Memory updates ───────────────────────────────────────────────────

    async def _maybe_update_memory(self, ctx: AgentContext):
        """Heuristic: after a turn, check if we should update memory."""
        # This is intentionally simple — a production version could use
        # a separate LLM call to extract facts. For now, we just note
        # that the conversation happened.
        pass

    async def save_conversation_to_memory(self, session_id: str, summary: str):
        """Save a conversation summary to long-term memory."""
        memory = self._memory
        memory.append_memory(f"\n## Session {session_id[:8]}\n{summary.strip()}")

    # ── Session management ───────────────────────────────────────────────

    async def get_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get conversation history for a session."""
        return self._db.get_messages(session_id, limit=limit)

    async def new_session(self) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        self._db.create_session(session_id, title=f"Session {session_id[:8]}")
        return session_id

    async def delete_session(self, session_id: str):
        """Delete a session and its messages."""
        self._db.delete_session(session_id)


# ── Singleton ─────────────────────────────────────────────────────────────
_agent_instance: Optional[AgentLoop] = None
_agent_lock = threading.Lock()


def get_agent_loop() -> AgentLoop:
    """Return the global AgentLoop singleton."""
    global _agent_instance
    if _agent_instance is None:
        with _agent_lock:
            if _agent_instance is None:
                _agent_instance = AgentLoop()
    return _agent_instance
