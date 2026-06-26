"""
Jarvis Mark II — Native Desktop GUI.
A proper native Windows desktop application using tkinter + ttk.
No browser, no WebView2, no WebUI — just a real desktop app.
"""

import asyncio
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, font, messagebox, scrolledtext
from typing import Any, Optional

from .agent import get_agent_loop, AgentLoop
from .config import get_config
from .constants import APP_NAME, VERSION
from .state.db import get_state_db
from .tools import discover_tools, get_tool_registry
from .skills.loader import get_skill_loader

logger = logging.getLogger("jarvis.gui")

# ── Colour palette (dark theme) ─────────────────────────────────────────────
BG_DARK = "#1a1a2e"
BG_MID = "#16213e"
BG_INPUT = "#0f3460"
ACCENT = "#00d9ff"
TEXT_PRIMARY = "#e0e0e0"
TEXT_DIM = "#8888aa"
TEXT_USER = "#4fc3f7"
TEXT_ASSISTANT = "#81c784"
TEXT_TOOL = "#ffb74d"
TEXT_ERROR = "#ef5350"
INPUT_BG = "#0d1b3e"
CHAT_BG = "#12122a"
SIDEBAR_BG = "#0f1a35"


class AsyncBridge:
    """Bridges the tkinter GUI thread with the asyncio agent event loop.

    The agent's ``process_message()`` is async.  We run the asyncio loop
    on a dedicated daemon thread and use thread-safe queues + tkinter
    ``after()`` callbacks to ferry data between the two worlds.
    """

    def __init__(self, parent: tk.Tk, agent: AgentLoop):
        self.parent = parent
        self.agent = agent
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # Callbacks that the async thread fills; main thread drains
        self._output_queue: queue.Queue[dict] = queue.Queue()
        self._poll_id: Optional[str] = None  # tkinter 'after' id

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        """Spawn the asyncio event loop thread."""
        self._loop = asyncio.new_event_loop()

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="jarvis-async",
        )
        self._thread.start()
        # Start polling the output queue
        self._poll()

    def stop(self):
        if self._poll_id:
            self.parent.after_cancel(self._poll_id)
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self):
        """Target for the daemon thread — runs the asyncio loop forever."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    # ── Send a message to the agent ────────────────────────────────────────

    def send_message(
        self,
        session_id: str,
        text: str,
        on_delta=None,
        on_tool=None,
        on_tool_result=None,
        on_turn_end=None,
        on_error=None,
        on_done=None,
    ):
        """Submit a user message to the async agent loop.

        Each callback receives the event dict.  All callbacks are
        invoked on the main tkinter thread via the poll loop.
        """
        if not self._loop or not self._loop.is_running():
            self._enqueue_output({"type": "error", "error": "Agent loop not running"})
            return

        async def _run():
            try:
                async for event in self.agent.process_message(session_id, text):
                    self._enqueue_output(event)
            except Exception as exc:
                self._enqueue_output({"type": "error", "error": str(exc)})

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    def _enqueue_output(self, event: dict):
        """Thread-safe enqueue from async thread."""
        self._output_queue.put_nowait(event)

    # ── Poll loop (runs on tkinter main thread) ────────────────────────────

    def _poll(self):
        """Called via ``after()`` — drains the output queue and dispatches."""
        try:
            while True:
                event = self._output_queue.get_nowait()
                self._dispatch(event)
        except queue.Empty:
            pass
        self._poll_id = self.parent.after(50, self._poll)

    def _dispatch(self, event: dict):
        """Route an event to the registered handler on the gui instance."""
        etype = event.get("type", "")
        handler = getattr(self.parent, "_on_" + etype, None)
        if handler:
            handler(event)


# ═══════════════════════════════════════════════════════════════════════════
# Main GUI
# ═══════════════════════════════════════════════════════════════════════════


class JarvisGUI(tk.Tk):
    """Native desktop chat interface for Jarvis Mark II."""

    def __init__(self):
        super().__init__()

        # ── Window setup ───────────────────────────────────────────────────
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("1100x700")
        self.minsize(800, 500)
        self.configure(bg=BG_DARK)

        # Try to set dark title bar on Windows 10/11
        try:
            from ctypes import c_bool, c_int, pointer, windll

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            windll.dwmapi.DwmSetWindowAttribute(
                windll.user32.GetParent(self.winfo_id()),
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                pointer(c_bool(True)),
                c_int(4 if os.name == "nt" else 2),
            )
        except Exception:
            pass

        # ── State ──────────────────────────────────────────────────────────
        self._config = get_config()
        self._agent: AgentLoop = get_agent_loop()
        self._session_id: str = ""
        self._current_message = ""  # accumulating streaming text

        # ── Resources ──────────────────────────────────────────────────────
        self._font_normal = font.nametofont("TkDefaultFont")
        self._font_normal.configure(size=10)
        self._font_bold = font.Font(family=self._font_normal.cget("family"), size=10, weight="bold")
        self._font_code = font.Font(family="Consolas", size=10)
        self._font_small = font.Font(family=self._font_normal.cget("family"), size=9)

        # Initialise subsystems (tools, skills, DB)
        tool_count = discover_tools()
        registry = get_tool_registry()
        logger.info(f"Loaded {tool_count} tools ({registry.count()} registered)")

        try:
            skills = get_skill_loader()
            skills.load_all()
            logger.info(f"Skills: {skills.get_skill_names()}")
        except Exception as e:
            logger.info(f"Skills: none loaded ({e})")

        db = get_state_db()
        logger.info(f"State DB ready ({db.get_stats()['sessions']} sessions)")
        self._build_menu()
        self._build_layout()
        self._start_async_bridge()

        # Create a fresh session
        self._new_session()

        # ── Bindings ───────────────────────────────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-Return>", lambda e: self._send_message())
        self.bind("<Control-l>", lambda e: self._clear_chat())

        logger.info(f"{APP_NAME} v{VERSION} GUI started")

    # ── Menu ───────────────────────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self, bg=BG_MID, fg=TEXT_PRIMARY, activebackground=ACCENT, activeforeground=BG_DARK)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0, bg=BG_MID, fg=TEXT_PRIMARY, activebackground=ACCENT)
        file_menu.add_command(label="New Session", command=self._new_session, accelerator="Ctrl+N")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close, accelerator="Alt+F4")
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0, bg=BG_MID, fg=TEXT_PRIMARY, activebackground=ACCENT)
        edit_menu.add_command(label="Clear Chat", command=self._clear_chat, accelerator="Ctrl+L")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        tools_menu = tk.Menu(menubar, tearoff=0, bg=BG_MID, fg=TEXT_PRIMARY, activebackground=ACCENT)
        tools_menu.add_command(label="Reload Tools", command=self._reload_tools)
        tools_menu.add_command(label="View Tools", command=self._show_tools)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0, bg=BG_MID, fg=TEXT_PRIMARY, activebackground=ACCENT)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    # ── Layout ─────────────────────────────────────────────────────────────

    def _build_layout(self):
        """Create the three-pane layout: sidebar | chat | input."""

        # Outer paned window for sidebar + main area
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True)

        # ── Sidebar ────────────────────────────────────────────────────────
        self._sidebar = tk.Frame(self._paned, bg=SIDEBAR_BG, width=200)
        self._sidebar.pack_propagate(False)
        self._paned.add(self._sidebar, weight=0)

        # Sidebar title
        tk.Label(
            self._sidebar,
            text="Sessions",
            bg=SIDEBAR_BG,
            fg=ACCENT,
            font=self._font_bold,
            anchor="w",
            padx=10,
            pady=8,
        ).pack(fill=tk.X)

        self._sessions_list = tk.Listbox(
            self._sidebar,
            bg=BG_MID,
            fg=TEXT_PRIMARY,
            selectbackground=ACCENT,
            selectforeground=BG_DARK,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            font=self._font_normal,
        )
        self._sessions_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self._sessions_list.bind("<Double-Button-1>", lambda e: self._switch_session())

        # New session button
        tk.Button(
            self._sidebar,
            text="+ New Session",
            bg=ACCENT,
            fg=BG_DARK,
            font=self._font_bold,
            relief=tk.FLAT,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._new_session,
        ).pack(fill=tk.X, padx=6, pady=(0, 6))

        # ── Main (chat) area ───────────────────────────────────────────────
        self._main = tk.Frame(self._paned, bg=BG_DARK)
        self._paned.add(self._main, weight=1)

        # Chat display
        chat_frame = tk.Frame(self._main, bg=CHAT_BG)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        self._chat_display = tk.Text(
            chat_frame,
            bg=CHAT_BG,
            fg=TEXT_PRIMARY,
            font=self._font_normal,
            wrap=tk.WORD,
            padx=12,
            pady=8,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            state=tk.DISABLED,
            cursor="arrow",
        )
        self._chat_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollbar for chat
        scrollbar = tk.Scrollbar(
            chat_frame,
            orient=tk.VERTICAL,
            command=self._chat_display.yview,
            bg=BG_MID,
            troughcolor=BG_DARK,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._chat_display.configure(yscrollcommand=scrollbar.set)

        # Text tags for message formatting
        self._chat_display.tag_configure("user", foreground=TEXT_USER, font=self._font_bold, spacing1=8, spacing3=4)
        self._chat_display.tag_configure("assistant", foreground=TEXT_ASSISTANT, font=self._font_bold, spacing1=8, spacing3=2)
        self._chat_display.tag_configure("assistant_text", foreground=TEXT_PRIMARY, font=self._font_normal, spacing3=4)
        self._chat_display.tag_configure("tool", foreground=TEXT_TOOL, font=self._font_small, spacing1=4, spacing3=2)
        self._chat_display.tag_configure("error", foreground=TEXT_ERROR, font=self._font_bold, spacing1=8, spacing3=4)
        self._chat_display.tag_configure("code", foreground=TEXT_PRIMARY, font=self._font_code, background="#1a1a3a", spacing1=2, spacing3=2)
        self._chat_display.tag_configure("dim", foreground=TEXT_DIM, font=self._font_small, spacing1=2)
        self._chat_display.tag_configure("separator", foreground=TEXT_DIM, font=self._font_small, spacing1=4)

        # ── Input area ─────────────────────────────────────────────────────
        input_frame = tk.Frame(self._main, bg=BG_DARK)
        input_frame.pack(fill=tk.X, padx=6, pady=(4, 6))

        self._input_box = tk.Text(
            input_frame,
            height=3,
            bg=INPUT_BG,
            fg=TEXT_PRIMARY,
            font=self._font_normal,
            insertbackground=ACCENT,
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=BG_DARK,
            highlightcolor=ACCENT,
            padx=8,
            pady=6,
        )
        self._input_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._input_box.bind("<Return>", self._on_enter_key)
        self._input_box.focus_set()

        self._send_btn = tk.Button(
            input_frame,
            text="Send",
            bg=ACCENT,
            fg=BG_DARK,
            font=self._font_bold,
            relief=tk.FLAT,
            padx=16,
            pady=6,
            cursor="hand2",
            activebackground="#00b8d4",
            command=self._send_message,
        )
        self._send_btn.pack(side=tk.RIGHT, padx=(6, 0))

        # ── Status bar ─────────────────────────────────────────────────────
        self._status_bar = tk.Frame(self._main, bg=BG_MID, height=28)
        self._status_bar.pack(fill=tk.X)

        provider = self._config.get_active_provider() or "?"
        model = self._config.get_active_model() or "?"

        self._status_text = tk.Label(
            self._status_bar,
            text=f"● Connected  |  {provider}:{model}  |  0 tokens",
            bg=BG_MID,
            fg=TEXT_DIM,
            font=self._font_small,
            anchor="w",
            padx=10,
        )
        self._status_text.pack(side=tk.LEFT)

        tk.Label(
            self._status_bar,
            text=f"{APP_NAME} v{VERSION}",
            bg=BG_MID,
            fg=TEXT_DIM,
            font=self._font_small,
            anchor="e",
            padx=10,
        ).pack(side=tk.RIGHT)

    # ── Async bridge ───────────────────────────────────────────────────────

    def _start_async_bridge(self):
        self._bridge = AsyncBridge(self, self._agent)
        self._bridge.start()

    # ── Event handlers (called from AsyncBridge._dispatch) ────────────────

    def _on_delta(self, event: dict):
        """Streaming text chunk from the LLM."""
        content = event.get("content", "")
        self._current_message += content
        self._append_chat(content, "assistant_text")

    def _on_tool_call(self, event: dict):
        """Tool invocation."""
        name = event.get("name", "?")
        args = event.get("arguments", {})
        args_str = json.dumps(args, ensure_ascii=False)[:200]
        self._append_chat(f"🔧 Using tool: {name}({args_str})", "tool")

    def _on_tool_result(self, event: dict):
        """Result returned from a tool."""
        name = event.get("name", "?")
        result = event.get("result", "")
        result_str = str(result)[:300]
        self._append_chat(f"  └─ Result: {result_str}", "tool")

    def _on_turn_end(self, event: dict):
        """Final assistant message for this turn."""
        self._current_message = ""

    def _on_error(self, event: dict):
        """Something went wrong."""
        error = event.get("error", "Unknown error")
        self._append_chat(f"✗ Error: {error}", "error")
        self._enable_input()

    def _on_done(self, event: dict):
        """Processing finished."""
        self._enable_input()

    # ── Chat helpers ───────────────────────────────────────────────────────

    def _append_chat(self, text: str, tag: str = "dim"):
        """Append text to the chat display with a given tag."""
        self._chat_display.configure(state=tk.NORMAL)
        self._chat_display.insert(tk.END, text, tag)
        self._chat_display.see(tk.END)
        self._chat_display.configure(state=tk.DISABLED)

    def _append_message_block(self, role: str, content: str):
        """Append a complete message block with role label + content."""
        self._chat_display.configure(state=tk.NORMAL)

        label = {"user": "You", "assistant": APP_NAME, "tool": "System"}.get(role, role)
        tag_role = role if role in ("user", "assistant", "tool") else "dim"

        # Role label
        self._chat_display.insert(tk.END, f"\n{label}\n", tag_role)
        self._chat_display.insert(tk.END, f"{content}\n", tag_role + "_text" if tag_role != "tool" else "tool")
        self._chat_display.see(tk.END)
        self._chat_display.configure(state=tk.DISABLED)

    def _clear_chat(self):
        """Clear the chat display."""
        self._chat_display.configure(state=tk.NORMAL)
        self._chat_display.delete("1.0", tk.END)
        self._chat_display.configure(state=tk.DISABLED)

    def _enable_input(self):
        """Re-enable the input box and send button."""
        self._input_box.configure(state=tk.NORMAL)
        self._send_btn.configure(state=tk.NORMAL, text="Send")
        self._input_box.focus_set()

    def _disable_input(self):
        """Disable input while the agent is processing."""
        self._input_box.configure(state=tk.DISABLED)
        self._send_btn.configure(state=tk.DISABLED, text="...")

    # ── Events from user ──────────────────────────────────────────────────

    def _on_enter_key(self, event: tk.Event):
        """Handle Enter key in input box.

        Shift+Enter = newline, plain Enter = send.
        """
        if event.state & 0x0001:  # Shift held
            return  # Let tkinter insert the newline
        self._send_message()
        return "break"  # Prevent the default newline

    def _send_message(self):
        """Send the user's message to the agent."""
        text = self._input_box.get("1.0", tk.END).strip()
        if not text:
            return

        if not self._session_id:
            self._new_session()

        # Show user message
        self._append_message_block("user", text)

        # Clear input
        self._input_box.delete("1.0", tk.END)
        self._disable_input()

        # Send to agent
        self._bridge.send_message(self._session_id, text)

    def _new_session(self):
        """Create a new conversation session."""
        import uuid

        self._session_id = str(uuid.uuid4())

        # Create session in DB
        self._agent._db.create_session(
            self._session_id,
            title=f"Chat {time.strftime('%H:%M')}",
        )

        # Update session list
        self._refresh_sessions()

        self._clear_chat()
        self._append_chat(f"\n── New Session ──\n", "separator")
        self._append_chat("How can I help you?\n", "dim")

        # Update status
        self._update_status()
        self._input_box.focus_set()

    def _switch_session(self):
        """Switch to the selected session."""
        selection = self._sessions_list.curselection()
        if not selection:
            return
        sid = self._sessions_list.get(selection[0]).split(" ")[0]
        self._session_id = sid

        # Load messages into chat
        self._clear_chat()
        messages = self._agent._db.get_messages(sid, limit=100)
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                continue
            if content:
                self._append_message_block(role, content[:2000])
            # Also show tool calls
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in (tool_calls if isinstance(tool_calls, list) else [tool_calls]):
                    name = tc.get("function", {}).get("name", "?")
                    self._append_chat(f"  🔧 {name}\n", "tool")

        self._chat_display.see(tk.END)
        self._update_status()

    def _refresh_sessions(self):
        """Refresh the sessions listbox from the DB."""
        self._sessions_list.delete(0, tk.END)
        sessions = self._agent._db.list_sessions(limit=50)
        for s in sessions:
            sid = s.get("id", "?")
            title = s.get("title", "Untitled")
            label = f"{sid[:8]}  {title}"
            self._sessions_list.insert(tk.END, label)

    def _reload_tools(self):
        """Reload all tools from the registry."""
        from ..tools import discover_tools

        count = discover_tools()
        self._append_chat(f"── Reloaded {count} tools ──\n", "dim")
        self._update_status()

    def _show_tools(self):
        """Show registered tools in a popup."""
        from ..tools import get_tool_registry

        registry = get_tool_registry()
        tools = registry.get_all()
        lines = []
        for t in tools:
            lines.append(f"  {t.name}  ({t.category})")
        text = "\n".join(lines) if lines else "  No tools registered."

        win = tk.Toplevel(self)
        win.title("Registered Tools")
        win.geometry("500x400")
        win.configure(bg=BG_DARK)

        tk.Label(
            win,
            text=f"{len(tools)} Tools Loaded",
            bg=BG_DARK,
            fg=ACCENT,
            font=self._font_bold,
            pady=6,
        ).pack(fill=tk.X)

        st = scrolledtext.ScrolledText(
            win,
            bg=CHAT_BG,
            fg=TEXT_PRIMARY,
            font=self._font_code,
            wrap=tk.NONE,
            padx=8,
            pady=8,
        )
        st.insert("1.0", text)
        st.configure(state=tk.DISABLED)
        st.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    def _show_about(self):
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} v{VERSION}\n\n"
            "A native AI desktop assistant.\n"
            f"Provider: {self._config.get_active_provider()}\n"
            f"Model: {self._config.get_active_model()}\n"
            f"Python: {sys.version}",
        )

    def _update_status(self):
        """Update the status bar."""
        provider = self._config.get_active_provider() or "?"
        model = self._config.get_active_model() or "?"
        llm = self._agent._llm
        tokens = llm.total_tokens if llm else 0
        self._status_text.configure(
            text=f"● Connected  |  {provider}:{model}  |  {tokens} tokens"
        )

    # ── Cleanup ────────────────────────────────────────────────────────────

    def _on_close(self):
        """Shutdown cleanly."""
        logger.info("Shutting down GUI...")
        self._bridge.stop()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════


def launch_gui() -> int:
    """Launch the native desktop GUI. Returns exit code."""
    root = JarvisGUI()
    root.mainloop()
    return 0


def main():
    """CLI entry for ``python -m jarvis.gui``."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="[Jarvis] %(levelname)s: %(message)s",
    )

    sys.exit(launch_gui())


if __name__ == "__main__":
    main()
