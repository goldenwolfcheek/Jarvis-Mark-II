# Changelog — Jarvis Mark II v2.0.0+

## 2026-06-25 — Auto-Update System & README Improvements

### New Feature: Auto-Update System

Jarvis can now check for and apply updates directly from the GitHub repo:

- **Check for Updates** — Hits the GitHub API, compares the latest commit SHA against the last-applied SHA
- **Apply Update** — Runs `git pull` in the project directory (preferred), or downloads/extracts a zip fallback if git isn't available
- **UI** — New "Updates" section in Settings panel with Check and Apply buttons, status display, and version info
- **Endpoints**: `GET /api/update`, `POST /api/update/check`, `POST /api/update/apply`

### Files Added
| File | Purpose |
|------|---------|
| `jarvis/updater.py` | Update checker and applier module |

### Files Modified
| File | Changes |
|------|---------|
| `jarvis/server.py` | Added 3 update endpoints + import |
| `electron_frontend/src/utils/api.js` | Added `checkForUpdate()`, `applyUpdate()`, `getUpdateStatus()` |
| `electron_frontend/src/components/SettingsPanel.jsx` | Added "Updates" section in Settings UI |

### README Improvements
- Rewrote Quick Start to focus on Electron app workflow: install → first launch (.bat) → daily use (.vbs) → system tray minimize
- Updated project structure table to match committed files
- Removed references to deleted files (`jarvis.bat`, `install-jarvis.ps1`, `SUMMARY.md`, etc.)

---

## 2026-06-24 — Code Quality Audit & Dead Code Cleanup

### Performance / Maintainability

#### Dead Code Removed
- **constants.py**: Removed 5 dead constants (`APP_FULL_NAME`, `WEBSITE`, `FRONTEND_DIR`, `CRON_DIR`, `CRON_JOBS_FILE`, `SESSIONS_DIR`) — all unreferenced outside constants.py
- **__init__.py**: Removed 11 dead re-exports (nobody imported from the `jarvis` package directly except `run.py` which uses `jarvis.constants.DEFAULT_HOST/DEFAULT_PORT`)
- **SidePanel.jsx**: Deleted entire 213-line component — never imported anywhere (replaced by LeftDrawer)
- **App.jsx**: Removed unused `APP_NAME` import

#### Silent Exception Swallows Fixed (P0)
- **agent_loop.py:250** — `except Exception: pass` → `logger.warning(..., exc_info=True)` when skill tool definitions fail to load
- **server.py:853** — `except Exception: pass` → `logger.exception()` when failing to send error to WebSocket client
- **server.py:916** — Same fix for the outer WS recovery path
- All previously `print()` → `traceback.print_exc()` replaced with structured `logger.exception()`

#### Print Statements Migrated to Logging
- **server.py**: 8 print() → logger.info/warning
- **agent_loop.py**: 9 print() → logger.info/debug/warning
- **llm_core.py**: 3 print() → logger.debug/warning (verbose debug payload downgraded to DEBUG level)
- **tts.py**: 2 print() → logger.error/info
- **loader.py**: 1 print() → logger.error
- **config.py**: 1 print() → logger.warning

### Files Modified (12)
| File | Changes |
|------|---------|
| `jarvis/constants.py` | Removed 6 dead constants |
| `jarvis/__init__.py` | Removed dead re-exports (11 lines) |
| `electron_frontend/src/components/SidePanel.jsx` | **Deleted** (213 lines, unused) |
| `electron_frontend/src/App.jsx` | Removed unused `APP_NAME` import |
| `jarvis/server.py` | Added `logging` module; 8 prints→logger; 2 silent swallows→exception logging |
| `jarvis/agent/agent_loop.py` | Added `logging` module; 9 prints→logger; 1 silent swallow→warning+exc_info |
| `jarvis/agent/llm_core.py` | Added `logging` module; 3 prints→logger.debug/warning |
| `jarvis/speech/tts.py` | Added `logging` module; 2 prints→logger |
| `jarvis/skills/loader.py` | Added `logging` module; 1 print→logger |
| `jarvis/config.py` | Added `logging` module; 1 print→logger |

### Build Verification
- Frontend: 38 modules, 0 errors (vite build clean in 3.65s)
- Python: All 8 modified .py files pass `py_compile`
- Remaining prints: `server.py` (0 — only comments about cp1252), `desktop.py` (5 — standalone dep installer, no logger available)

---

## 2026-06-21 — Streaming Controls & Display Settings

### Bug Fixes

#### Bug 1 — Auto-start on system boot
- **main.cjs**: Added `app.setLoginItemSettings({ openAtLogin: enabled })` IPC handler and default-initializer
- **preload.cjs**: Exposed `setAutoboot(enabled)` via `contextBridge` under `window.electronAPI`
- **SettingsPanel.jsx**: `handleAutobootChange` now calls `window.electronAPI?.setAutoboot(enabled)` to register/unregister with OS

#### Bug 2 — Empty assistant bubbles on history reload
- **App.jsx**: History loader now filters with `.filter(m => m.role !== 'assistant' || (m.content?.trim()))` to strip saved empty assistant messages

#### Bug 3 — Copy button doesn't copy in Electron
- **main.cjs**: Added `'clipboard-write'` to Chrome WebPermissions for the renderer process
- **ChatModule.jsx**: Robust copy handler with `navigator.clipboard.writeText()` fallback to `document.execCommand('copy')`, coerces content to string

#### Bug 4 — No stop button during tool/streaming loops
- **agent_loop.py**: Added `cancel_event: Optional[asyncio.Event]` parameter to `process_message()`, checked in main tool loop and streaming delta loop
- **server.py**: Restructured WebSocket `"message"` handler to spawn background task + sub-loop that listens for `"stop"` with 0.2s timeout, sets cancel_event, cancels task, sends `{"type":"done"}`
- **App.jsx**: `handleStop` sends `{"type":"stop"}` via WebSocket, immediately clears `isStreaming` and `activeTools`
- **ChatModule.jsx**: Send button becomes stop button (⏹ + `.btn-stop` class) during streaming, calls `onStop?.()`
- **index.css**: Added `.btn-stop` style (red glow, pulsing)

### Features

#### Feature 5 — Toggle chat history visibility
- **App.jsx**: `showChatHistory` state (persisted to localStorage), conditional render of `ChatModule` messages area
- **ChatModule.jsx**: Accepts `showChatHistory` prop, conditionally renders `#chat-messages` div
- **SettingsPanel.jsx**: "Show chat history" checkbox in new "Display" section, persisted to config + localStorage

#### Feature 6 — Animated subtitles below sphere
- **App.jsx**: `showSubtitles` and `currentSubtitle` state, tracking effect that syncs subtitle with latest assistant message, clears on user send and fades 2s after streaming ends, renders `#subtitle-overlay` with animated cursor
- **index.css**: `#subtitle-overlay` (fixed bottom-center, z-index 5 below HUD), `.subtitle-text` (glow, fade-in), `.subtitle-cursor` (blinking), keyframes `subtitleBlink` and `subtitleFadeIn`
- **SettingsPanel.jsx**: "Show subtitles" checkbox in "Display" section with description text

### Files Modified (9)
| File | Changes |
|------|---------|
| `electron_frontend/src/App.jsx` | 4 state vars, handleStop, subtitle tracking effect, conditional rendering, settings handlers, prop wiring |
| `electron_frontend/src/components/ChatModule.jsx` | showChatHistory prop, conditional messages render, stop button UI, robust copy handler |
| `electron_frontend/src/components/SettingsPanel.jsx` | showChatHistory/showSubtitles state+loaders+handlers, "Display" section with 2 checkboxes |
| `electron_frontend/electron/main.cjs` | clipboard permission (chromium), set-autoboot IPC handler + initializer |
| `electron_frontend/electron/preload.cjs` | setAutoboot bridge exposure |
| `electron_frontend/src/index.css` | .btn-stop (red/pulse), #subtitle-overlay, .subtitle-text/cursor, keyframes |
| `jarvis/server.py` | asyncio import, background task + cancel sub-loop in WebSocket handler |
| `jarvis/agent/agent_loop.py` | cancel_event parameter, abort checks in main + streaming loops |

### Build Verification
- Frontend: 38 modules, 0 errors, 0 warnings
- Python: jarvis/server.py and jarvis/agent/agent_loop.py compile clean

## 2026-06-21 — Subtitle Refinements (TTS Sync, Karaoke, Windowed View)

### Changes

#### TTS-Synced Word-by-Word Subtitles
- **App.jsx**: Added `isTtsPlaying`, `ttsWords`, `ttsWordIndex` state. `playTts` now splits text into words, sets subtitle state immediately on TTS start, tracks current word via audio progress (`currentTime / duration`), clears on end/error. Subtitle effect defers to TTS lifecycle when TTS enabled. `handleSendMessage` stops current TTS playback. Connected handler clears TTS state on reconnect.
- **index.css**: Added `.word-spoken` (dimmed), `.word-active` (bright cyan with glow).

#### Speed Tuning & Windowed View
- **App.jsx**: Word tracking speed set to 1.0× (tuned per user feedback — 1.4× was too fast). On TTS end, `ttsWordIndex` set to `words.length` so all words render in unified spoken color (no lingering highlight). Subtitle windowed to last ~35 words (2–3 sentences) — older text scrolls off.
- **index.css**: `max-width` increased from `min(80%, 600px)` to `min(85%, 750px)` to reduce paragraphing.

#### Non-TTS Fallback
- When TTS is disabled, subtitles sync with streaming (original behavior preserved).

### Files Modified (2)
| File | Changes |
|------|---------|
| `electron_frontend/src/App.jsx` | 3 new state vars, playTts word tracking + cleanup, subtitle effect TTS guard, windowed render, handleSendMessage TTS stop, connected handler TTS clear |
| `electron_frontend/src/index.css` | .word-spoken, .word-active classes; max-width widened |

### Build Verification
- Frontend: 38 modules, 0 errors
