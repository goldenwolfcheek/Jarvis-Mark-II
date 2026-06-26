"""
Jarvis Mark II — PC Control tools.
Windows-specific desktop automation: app launching, window management,
keyboard/mouse simulation, clipboard, and system commands.

Category: pc

All functions are registered by calling ``load_pc_control_tools()``.
"""

import json
import os
import platform
import shutil
import subprocess
import ctypes
from ctypes import (
    POINTER, CFUNCTYPE, c_float, c_void_p, byref, cast, HRESULT, Structure, WinError,
)
from ctypes.wintypes import DWORD, WORD, BYTE
import time
from pathlib import Path
from typing import Optional

from ..constants import APPS_FILE
from .registry import get_tool_registry

_IS_WINDOWS = platform.system() == "Windows"


# ═══════════════════════════════════════════════════════════════════════════
# App launching
# ═══════════════════════════════════════════════════════════════════════════

def _tool_launch_app(name: str) -> str:
    """Launch a registered application by name.

    Args:
        name: The friendly name of the app (must be in registered_apps.json).
    """
    try:
        apps = []
        if APPS_FILE.exists():
            apps = json.loads(APPS_FILE.read_text(encoding="utf-8"))

        app = next((a for a in apps if a["name"].lower() == name.lower()), None)
        if not app:
            return json.dumps({"error": f"App '{name}' not found in registered apps."})

        target = app["path"]
        if _IS_WINDOWS:
            subprocess.Popen(target, shell=True)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(target, shell=True)

        return json.dumps({"status": "ok", "app": name, "path": target})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_launch_path(path: str) -> str:
    """Launch a file or URL using the OS default handler.

    Args:
        path: File path, directory, or URL to open.
    """
    try:
        resolved = Path(path).expanduser().resolve()
        if _IS_WINDOWS:
            os.startfile(str(resolved))  # type: ignore
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(resolved)])
        else:
            subprocess.Popen(["xdg-open", str(resolved)])
        return json.dumps({"status": "ok", "path": str(resolved)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_run_command(command: str, timeout: int = 30) -> str:
    """Run a shell command and return its output.

    Args:
        command: The shell command to execute.
        timeout: Max execution time in seconds (default: 30).

    Note:
        Commands starting with "start " launch a new window and are
        fire-and-forget (subprocess.Popen).  They always return success
        immediately because the started process lives independently.
    """
    try:
        # ── "start" launches a new window — fire-and-forget ──
        stripped = command.strip()
        if stripped.lower().startswith("start "):
            subprocess.Popen(stripped, shell=True)
            return json.dumps({
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "note": "Launched in a separate window (fire-and-forget).",
            })

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout
        stderr = result.stderr

        # Truncate output if too long
        max_out = 10000
        if len(stdout) > max_out:
            stdout = stdout[:max_out] + "\n...[TRUNCATED]"
        if len(stderr) > max_out:
            stderr = stderr[:max_out] + "\n...[TRUNCATED]"

        return json.dumps({
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {timeout}s", "command": command})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Window management
# ═══════════════════════════════════════════════════════════════════════════

def _tool_list_windows() -> str:
    """List all visible windows with their titles (Windows only)."""
    if not _IS_WINDOWS:
        return json.dumps({"error": "Window listing is only supported on Windows", "windows": []})

    try:
        import ctypes
        from ctypes import wintypes

        enum_windows = ctypes.windll.user32.EnumWindows
        get_window_text = ctypes.windll.user32.GetWindowTextW
        get_window_text_length = ctypes.windll.user32.GetWindowTextLengthW
        is_window_visible = ctypes.windll.user32.IsWindowVisible

        windows = []

        def callback(hwnd, _lparam):
            if is_window_visible(hwnd):
                length = get_window_text_length(hwnd) + 1
                buffer = ctypes.create_unicode_buffer(length)
                get_window_text(hwnd, buffer, length)
                title = buffer.value
                if title:
                    windows.append({"hwnd": hwnd, "title": title})
            return True

        WndEnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        enum_windows(WndEnumProc(callback), 0)

        return json.dumps({"windows": windows, "count": len(windows)})
    except Exception as e:
        return json.dumps({"error": str(e), "windows": []})


def _tool_focus_window(title: str) -> str:
    """Bring a window matching *title* to the foreground (Windows only).

    Args:
        title: Substring of the window title to match.
    """
    if not _IS_WINDOWS:
        return json.dumps({"error": "Window focus is only supported on Windows"})

    try:
        import ctypes
        from ctypes import wintypes

        enum_windows = ctypes.windll.user32.EnumWindows
        get_window_text = ctypes.windll.user32.GetWindowTextW
        get_window_text_length = ctypes.windll.user32.GetWindowTextLengthW
        is_window_visible = ctypes.windll.user32.IsWindowVisible
        set_foreground = ctypes.windll.user32.SetForegroundWindow
        show_window = ctypes.windll.user32.ShowWindow

        found = []

        def callback(hwnd, _lparam):
            if is_window_visible(hwnd):
                length = get_window_text_length(hwnd) + 1
                buffer = ctypes.create_unicode_buffer(length)
                get_window_text(hwnd, buffer, length)
                if title.lower() in buffer.value.lower():
                    found.append(hwnd)
            return True

        WndEnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        enum_windows(WndEnumProc(callback), 0)

        if found:
            hwnd = found[0]
            show_window(hwnd, 9)  # SW_RESTORE
            set_foreground(hwnd)
            return json.dumps({"status": "ok", "title": title, "hwnd": hwnd})
        return json.dumps({"error": f"No window found matching '{title}'"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_minimize_all_windows() -> str:
    """Minimize all windows (show desktop). Windows only."""
    if not _IS_WINDOWS:
        return json.dumps({"error": "Only supported on Windows"})

    try:
        import ctypes
        ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)   # LWin down
        ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)   # 'd' down
        ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)   # 'd' up
        ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)   # LWin up
        return json.dumps({"status": "ok", "action": "minimized_all"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Keyboard & Mouse (Windows-only via ctypes / optional pyautogui)
# ═══════════════════════════════════════════════════════════════════════════

def _tool_send_keys(text: str) -> str:
    """Type text using keyboard simulation (Windows only, basic Latin chars).

    Args:
        text: The text to type.
    """
    if not _IS_WINDOWS:
        return json.dumps({"error": "Keyboard simulation is only supported on Windows"})

    try:
        # Try pyautogui first for reliable typing
        import pyautogui
        pyautogui.write(text, interval=0.01)
        return json.dumps({"status": "ok", "typed": text})
    except ImportError:
        pass

    # Fallback: SendKeys via PowerShell
    try:
        # Escape for PowerShell (double single quotes)
        escaped = text.replace("'", "''")
        # Escape SendKeys metacharacters: + ^ % ~ { } ( )
        # Each meta-character must be wrapped in braces to be treated literally
        sendkeys_magic = {"+", "^", "%", "~", "{", "}", "(", ")"}
        escaped = "".join(f"{{{c}}}" if c in sendkeys_magic else c for c in escaped)
        ps_script = f"""
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.SendKeys]::SendWait('{escaped}')
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return json.dumps({"status": "ok", "typed": text})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_press_keys(keys: str) -> str:
    """Press a key combination (e.g. 'ctrl+c', 'alt+tab').

    Args:
        keys: Key combination string, e.g. 'ctrl+c', 'alt+f4', 'win+d'.
    """
    try:
        import pyautogui
        modifiers = {
            "ctrl": "ctrl",
            "alt": "alt",
            "shift": "shift",
            "win": "win",
            "cmd": "command",
        }
        parts = keys.lower().split("+")
        if len(parts) > 1:
            mod = modifiers.get(parts[0], parts[0])
            key = parts[-1]
            pyautogui.hotkey(mod, key)
        else:
            pyautogui.press(parts[0])
        return json.dumps({"status": "ok", "keys": keys})
    except ImportError:
        pass

    # Fallback via PowerShell
    if _IS_WINDOWS:
        try:
            mapping = {
                "ctrl+c": "^c", "ctrl+v": "^v", "ctrl+x": "^x",
                "ctrl+z": "^z", "ctrl+a": "^a", "ctrl+s": "^s",
                "alt+tab": "%{tab}", "alt+f4": "%{F4}",
                "enter": "{ENTER}", "esc": "{ESC}",
                "backspace": "{BACKSPACE}", "delete": "{DELETE}",
                "tab": "{TAB}", "space": " ",
            }
            ps_key = mapping.get(keys.lower(), keys)
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.SendKeys]::SendWait('{ps_key}')
            """
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                timeout=10,
            )
            return json.dumps({"status": "ok", "keys": keys})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "Keyboard simulation not available"})


def _tool_get_mouse_position() -> str:
    """Get the current mouse cursor position."""
    try:
        import pyautogui
        x, y = pyautogui.position()
        return json.dumps({"x": x, "y": y})
    except ImportError:
        pass

    if _IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            return json.dumps({"x": point.x, "y": point.y})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "Mouse position not available"})


def _tool_click(x: int, y: int, button: str = "left") -> str:
    """Click at screen coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        button: Mouse button ('left', 'right', 'middle').
    """
    try:
        import pyautogui
        pyautogui.click(x, y, button=button)
        return json.dumps({"status": "ok", "x": x, "y": y, "button": button})
    except ImportError:
        return json.dumps({"error": "pyautogui is required for mouse click. Install: pip install pyautogui"})


# ═══════════════════════════════════════════════════════════════════════════
# System
# ═══════════════════════════════════════════════════════════════════════════

def _set_volume_core_audio(level: int) -> bool:
    """Set system master volume using Windows Core Audio API (ctypes COM).
    Returns True on success, False if COM fails (fallback to SendKeys)."""
    try:
        # ── GUID for COM ──
        class GUID(Structure):
            _fields_ = [
                ("Data1", DWORD),
                ("Data2", WORD),
                ("Data3", WORD),
                ("Data4", BYTE * 8),
            ]

        CLSID_MMDeviceEnumerator = GUID(
            0xBCDE0395, 0xE52F, 0x467C,
            (0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E),
        )
        IID_IMMDeviceEnumerator = GUID(
            0xA95664D2, 0x9614, 0x4F35,
            (0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6),
        )
        IID_IAudioEndpointVolume = GUID(
            0x5CDF2C82, 0x841E, 0x4546,
            (0x97, 0x22, 0x0C, 0xF7, 0x40, 0x78, 0x22, 0x9A),
        )

        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED

        # Create device enumerator
        pEnumerator = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(CLSID_MMDeviceEnumerator), None, 1,  # CLSCTX_INPROC_SERVER
            byref(IID_IMMDeviceEnumerator), byref(pEnumerator),
        )
        if hr != 0:
            return False

        # Get default audio endpoint (render, console)
        pDevice = c_void_p()
        enum_vtbl = cast(pEnumerator, POINTER(c_void_p)).contents.value
        GetDefaultAudioEndpoint = CFUNCTYPE(
            HRESULT, c_void_p, DWORD, DWORD, POINTER(c_void_p),
        )(cast(c_void_p(enum_vtbl + 4 * 8), c_void_p).value)
        hr = GetDefaultAudioEndpoint(pEnumerator, 0, 0, byref(pDevice))
        if hr != 0:
            return False

        # Activate IAudioEndpointVolume
        pEndpointVolume = c_void_p()
        dev_vtbl = cast(pDevice, POINTER(c_void_p)).contents.value
        Activate = CFUNCTYPE(
            HRESULT, c_void_p, POINTER(GUID), DWORD, c_void_p, POINTER(c_void_p),
        )(cast(c_void_p(dev_vtbl + 3 * 8), c_void_p).value)
        hr = Activate(pDevice, byref(IID_IAudioEndpointVolume), 1, None, byref(pEndpointVolume))
        if hr != 0:
            return False

        # Set master volume level scalar (0.0–1.0)
        epv_vtbl = cast(pEndpointVolume, POINTER(c_void_p)).contents.value
        SetMasterVolumeLevelScalar = CFUNCTYPE(
            HRESULT, c_void_p, c_float, c_void_p,
        )(cast(c_void_p(epv_vtbl + 7 * 8), c_void_p).value)
        scalar = c_float(max(0.0, min(1.0, level / 100.0)))
        hr = SetMasterVolumeLevelScalar(pEndpointVolume, scalar, None)
        return hr == 0
    except Exception:
        return False
    finally:
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


def _tool_volume(level: int) -> str:
    """Set system volume (0-100). Windows only.

    Uses Windows Core Audio API via ctypes COM for instant reliable control.
    Falls back to PowerShell SendKeys if COM is unavailable.

    Args:
        level: Volume level 0-100.
    """
    if not _IS_WINDOWS:
        return json.dumps({"error": "Volume control is only supported on Windows"})

    level = max(0, min(100, level))

    # Primary: Core Audio API (instant, precise)
    if _set_volume_core_audio(level):
        return json.dumps({"status": "ok", "volume": level})

    # Fallback: PowerShell SendKeys stepping
    try:
        ps_script = f"""$obj = New-Object -ComObject WScript.Shell
for ($i = 0; $i -le 100; $i += 2) {{ $obj.SendKeys([char]174) }}
for ($i = 0; $i -lt {level}; $i += 2) {{ $obj.SendKeys([char]175) }}"""
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, timeout=10,
        )
        return json.dumps({"status": "ok", "volume": level})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_mute() -> str:
    """Toggle system mute."""
    if not _IS_WINDOWS:
        return json.dumps({"error": "Mute is only supported on Windows"})

    try:
        ps_script = """
        $obj = New-Object -ComObject WScript.Shell
        $obj.SendKeys([char]173)
        """
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            timeout=10,
        )
        return json.dumps({"status": "ok", "action": "toggle_mute"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_sleep(milliseconds: int = 1000) -> str:
    """Sleep for a given duration (useful for pacing after other actions).

    Args:
        milliseconds: Time to sleep in milliseconds (default: 1000).
    """
    time.sleep(milliseconds / 1000.0)
    return json.dumps({"status": "ok", "slept_ms": milliseconds})


# ═══════════════════════════════════════════════════════════════════════════
# Clipboard
# ═══════════════════════════════════════════════════════════════════════════

def _tool_get_clipboard() -> str:
    """Get the current clipboard text content."""
    try:
        import pyperclip
        text = pyperclip.paste()
        return json.dumps({"content": text, "length": len(text)})
    except ImportError:
        pass

    if _IS_WINDOWS:
        try:
            ps_script = "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::GetText()"
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return json.dumps({"content": result.stdout.strip()})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "Clipboard access not available. Install pyperclip."})


def _tool_set_clipboard(text: str) -> str:
    """Set clipboard text content.

    Args:
        text: Text to copy to clipboard.
    """
    try:
        import pyperclip
        pyperclip.copy(text)
        return json.dumps({"status": "ok", "copied": text[:100], "length": len(text)})
    except ImportError:
        pass

    if _IS_WINDOWS:
        try:
            escaped = text.replace("'", "''")
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.Clipboard]::SetText('{escaped}')
            """
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                timeout=10,
            )
            return json.dumps({"status": "ok", "copied": text[:100]})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "Clipboard access not available. Install pyperclip."})


# ═══════════════════════════════════════════════════════════════════════════
# Loader
# ═══════════════════════════════════════════════════════════════════════════

def load_pc_control_tools():
    """Register all PC control tools into the global registry."""
    registry = get_tool_registry()

    registry.register_fn(_tool_launch_app, category="pc")
    registry.register_fn(_tool_launch_path, category="pc")
    registry.register_fn(_tool_run_command, category="pc")
    registry.register_fn(_tool_list_windows, category="pc")
    registry.register_fn(_tool_focus_window, category="pc")
    registry.register_fn(_tool_minimize_all_windows, category="pc")
    registry.register_fn(_tool_send_keys, category="pc")
    registry.register_fn(_tool_press_keys, category="pc")
    registry.register_fn(_tool_get_mouse_position, category="pc")
    registry.register_fn(_tool_click, category="pc")
    registry.register_fn(_tool_volume, category="pc")
    registry.register_fn(_tool_mute, category="pc")
    registry.register_fn(_tool_sleep, category="pc")
    registry.register_fn(_tool_get_clipboard, category="pc")
    registry.register_fn(_tool_set_clipboard, category="pc")
