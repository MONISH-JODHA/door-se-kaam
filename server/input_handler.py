"""
Door Se Kaam — Input Handler Module

Processes remote mouse and keyboard commands received via WebSocket.

Backend selection:
  - Wayland (GNOME): Uses Mutter RemoteDesktop D-Bus API via helper subprocess
  - X11: Uses PyAutoGUI for direct input simulation
  - Fallback: PyAutoGUI (may not work on some Wayland configurations)
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("door-se-kaam")

_session_type = os.getenv("XDG_SESSION_TYPE", "").lower()
_is_wayland = _session_type == "wayland" or bool(os.getenv("WAYLAND_DISPLAY"))

# Path to Wayland input helper script
_WAYLAND_HELPER = Path(__file__).parent / "wayland_input.py"


# ── Lazy pyautogui (only for X11 fallback) ────────────────────
_pyautogui = None
_pyperclip = None


def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0
        _pyautogui = pyautogui
    return _pyautogui


def _get_pyperclip():
    global _pyperclip
    if _pyperclip is None:
        import pyperclip
        _pyperclip = pyperclip
    return _pyperclip


class WaylandInputBackend:
    """Input backend using Mutter RemoteDesktop D-Bus (GNOME Wayland)."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._ready = False

    def start(self):
        """Start the Wayland input helper process."""
        if self._process is not None and self._process.poll() is None:
            return  # Already running

        logger.info("Starting Wayland input backend (Mutter RemoteDesktop)...")

        self._process = subprocess.Popen(
            ["/usr/bin/python3", str(_WAYLAND_HELPER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Wait for "ready" signal
        try:
            import select
            for _ in range(20):  # Wait up to 10 seconds
                ready, _, _ = select.select([self._process.stdout], [], [], 0.5)
                if ready:
                    line = self._process.stdout.readline().strip()
                    if line:
                        data = json.loads(line)
                        if data.get("status") == "ready":
                            self._ready = True
                            logger.info(f"Wayland input backend ready (session: {data.get('session')})")
                            return
                        elif data.get("status") == "error":
                            logger.error(f"Wayland input error: {data.get('message')}")
                            break

            if not self._ready:
                logger.error("Wayland input backend failed to start")
                self.stop()
        except Exception as e:
            logger.error(f"Wayland input start failed: {e}")
            self.stop()

    def stop(self):
        """Stop the helper process."""
        if self._process:
            try:
                self._send({"type": "stop"})
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=1)
                except Exception:
                    self._process.kill()
            self._process = None
            self._ready = False

    def _send(self, command: dict) -> dict:
        """Send a command to the helper and read response."""
        if not self._ready or self._process is None or self._process.poll() is not None:
            # Process died, restart it
            self._ready = False
            self.start()
            if not self._ready:
                return {"status": "error", "message": "Input backend not available"}

        try:
            self._process.stdin.write(json.dumps(command) + "\n")
            self._process.stdin.flush()

            # Read response (with timeout)
            import select
            ready, _, _ = select.select([self._process.stdout], [], [], 2.0)
            if ready:
                line = self._process.stdout.readline().strip()
                if line:
                    return json.loads(line)
            return {"status": "ok"}  # Assume ok if no response
        except Exception as e:
            logger.error(f"Input command failed: {e}")
            self._ready = False
            return {"status": "error", "message": str(e)}

    def mouse_move(self, x: int, y: int, relative: bool = True):
        self._send({"type": "mouse_move", "x": x, "y": y, "relative": relative})

    def mouse_click(self, button="left", count=1, x=None, y=None):
        if x is not None and y is not None:
            self._send({"type": "mouse_move", "x": x, "y": y, "relative": False})
        self._send({"type": "mouse_click", "button": button, "count": count})

    def mouse_scroll(self, dx=0, dy=0):
        self._send({"type": "mouse_scroll", "dx": dx, "dy": dy})

    def mouse_down(self, button="left"):
        self._send({"type": "mouse_down", "button": button})

    def mouse_up(self, button="left"):
        self._send({"type": "mouse_up", "button": button})

    def key_press(self, key: str, modifiers: Optional[List[str]] = None):
        self._send({"type": "key_press", "key": key, "modifiers": modifiers or []})

    def key_combo(self, keys: List[str]):
        self._send({"type": "key_combo", "keys": keys})

    def type_text(self, text: str):
        self._send({"type": "type_text", "text": text})

    @property
    def is_available(self) -> bool:
        return self._ready


class X11InputBackend:
    """Input backend using PyAutoGUI (X11)."""

    # Key maps
    MODIFIER_MAP = {
        "ctrl": "ctrl", "control": "ctrl", "alt": "alt",
        "shift": "shift", "super": "win", "win": "win",
        "meta": "win", "cmd": "win",
    }

    SPECIAL_KEYS = {
        "enter": "enter", "return": "enter", "tab": "tab",
        "escape": "escape", "esc": "escape", "backspace": "backspace",
        "delete": "delete", "space": "space",
        "up": "up", "down": "down", "left": "left", "right": "right",
        "home": "home", "end": "end", "pageup": "pageup", "pagedown": "pagedown",
        "insert": "insert", "capslock": "capslock", "numlock": "numlock",
        "printscreen": "printscreen", "scrolllock": "scrolllock", "pause": "pause",
        **{f"f{i}": f"f{i}" for i in range(1, 25)},
    }

    def mouse_move(self, x: int, y: int, relative: bool = True):
        pag = _get_pyautogui()
        if relative:
            pag.moveRel(x, y, duration=0)
        else:
            pag.moveTo(x, y, duration=0)

    def mouse_click(self, button="left", count=1, x=None, y=None):
        pag = _get_pyautogui()
        kwargs = {"button": button, "clicks": count}
        if x is not None and y is not None:
            kwargs["x"] = x
            kwargs["y"] = y
        pag.click(**kwargs)

    def mouse_scroll(self, dx=0, dy=0):
        pag = _get_pyautogui()
        if dy != 0:
            pag.scroll(dy)
        if dx != 0:
            pag.hscroll(dx)

    def mouse_down(self, button="left"):
        _get_pyautogui().mouseDown(button=button)

    def mouse_up(self, button="left"):
        _get_pyautogui().mouseUp(button=button)

    def key_press(self, key: str, modifiers: Optional[List[str]] = None):
        pag = _get_pyautogui()
        resolved = self._resolve_key(key)
        if modifiers:
            mods = [self._resolve_modifier(m) for m in modifiers]
            pag.hotkey(*mods, resolved)
        else:
            pag.press(resolved)

    def key_combo(self, keys: List[str]):
        _get_pyautogui().hotkey(*[self._resolve_key(k) for k in keys])

    def type_text(self, text: str):
        pag = _get_pyautogui()
        pag.typewrite(text, interval=0.02) if text.isascii() else pag.write(text)

    def _resolve_key(self, key: str) -> str:
        k = key.lower()
        return self.MODIFIER_MAP.get(k) or self.SPECIAL_KEYS.get(k) or (key if len(key) == 1 else k)

    def _resolve_modifier(self, mod: str) -> str:
        return self.MODIFIER_MAP.get(mod.lower(), mod.lower())

    @property
    def is_available(self) -> bool:
        try:
            _get_pyautogui()
            return True
        except Exception:
            return False


class InputHandler:
    """
    Handles remote mouse and keyboard input commands.
    Auto-detects Wayland vs X11 and uses the appropriate backend.
    """

    def __init__(self):
        self._sensitivity = 1.0
        self._drag_active = False

        # Select backend
        if _is_wayland:
            self._backend = WaylandInputBackend()
            self._backend_name = "wayland"
            logger.info("Input handler: Wayland backend selected")
        else:
            self._backend = X11InputBackend()
            self._backend_name = "x11"
            logger.info("Input handler: X11 backend selected")

    def ensure_started(self):
        """Ensure the input backend is ready (starts Wayland helper if needed)."""
        if isinstance(self._backend, WaylandInputBackend) and not self._backend.is_available:
            self._backend.start()

    @property
    def sensitivity(self) -> float:
        return self._sensitivity

    @sensitivity.setter
    def sensitivity(self, value: float):
        self._sensitivity = max(0.1, min(5.0, value))

    def _handle_clipboard(self, command: dict) -> dict:
        """Handle clipboard sync commands."""
        action = command.get("action", "get")
        try:
            clip = _get_pyperclip()
            if action == "set":
                clip.copy(command.get("content", ""))
                return {"status": "ok", "action": "set"}
            else:
                return {"status": "ok", "action": "get", "content": clip.paste()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def process_command(self, command: dict) -> dict:
        """Process a single input command from WebSocket."""
        cmd_type = command.get("type", "")

        # Ensure backend is started on first command
        self.ensure_started()

        try:
            if cmd_type == "mouse_move":
                x = command.get("x", 0)
                y = command.get("y", 0)
                relative = command.get("relative", True)
                if relative:
                    x = int(x * self._sensitivity)
                    y = int(y * self._sensitivity)
                self._backend.mouse_move(x, y, relative)

            elif cmd_type == "mouse_click":
                self._backend.mouse_click(
                    button=command.get("button", "left"),
                    count=command.get("count", 1),
                    x=command.get("x"),
                    y=command.get("y"),
                )

            elif cmd_type == "mouse_scroll":
                self._backend.mouse_scroll(
                    dx=command.get("dx", 0),
                    dy=command.get("dy", 0),
                )

            elif cmd_type == "mouse_down":
                self._backend.mouse_down(command.get("button", "left"))
                self._drag_active = True

            elif cmd_type == "mouse_up":
                self._backend.mouse_up(command.get("button", "left"))
                self._drag_active = False

            elif cmd_type == "key_press":
                self._backend.key_press(
                    command.get("key", ""),
                    command.get("modifiers"),
                )

            elif cmd_type == "key_combo":
                self._backend.key_combo(command.get("keys", []))

            elif cmd_type == "type_text":
                self._backend.type_text(command.get("text", ""))

            elif cmd_type == "set_sensitivity":
                self.sensitivity = command.get("value", 1.0)

            elif cmd_type == "clipboard_sync":
                return self._handle_clipboard(command)

            else:
                return {"status": "error", "message": f"Unknown command: {cmd_type}"}

            return {"status": "ok"}

        except Exception as e:
            logger.error(f"Input error ({cmd_type}): {e}")
            return {"status": "error", "message": str(e)}

    def stop(self):
        """Clean up resources."""
        if isinstance(self._backend, WaylandInputBackend):
            self._backend.stop()


# Global input handler instance
input_handler = InputHandler()
