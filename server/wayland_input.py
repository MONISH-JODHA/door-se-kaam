#!/usr/bin/env python3
"""
Door Se Kaam — Wayland Input Helper

Uses Mutter RemoteDesktop D-Bus API to simulate mouse/keyboard input
on GNOME Wayland. Runs with SYSTEM Python for python3-gi access.

Protocol: reads JSON commands from stdin, writes JSON responses to stdout.
One command per line. Send {"type":"stop"} to quit.

Commands:
  mouse_move:   {"type":"mouse_move", "x": 10, "y": 10, "relative": true}
  mouse_click:  {"type":"mouse_click", "button": "left"}
  mouse_down:   {"type":"mouse_down", "button": "left"}
  mouse_up:     {"type":"mouse_up", "button": "left"}
  mouse_scroll: {"type":"mouse_scroll", "dx": 0, "dy": -3}
  key_press:    {"type":"key_press", "keysym": 65293}
  key_combo:    {"type":"key_combo", "keysyms": [65507, 99]}
  type_text:    {"type":"type_text", "text": "hello"}
"""

import sys
import json
import time

# Button code mappings (Linux evdev)
BUTTON_MAP = {
    "left": 0x110,     # BTN_LEFT = 272
    "right": 0x111,    # BTN_RIGHT = 273
    "middle": 0x112,   # BTN_MIDDLE = 274
}

# XKB Keysym mappings for common keys
KEYSYM_MAP = {
    # Letters (lowercase)
    **{chr(c): c for c in range(ord('a'), ord('z') + 1)},
    **{chr(c): c for c in range(ord('A'), ord('Z') + 1)},
    # Digits
    **{chr(c): c for c in range(ord('0'), ord('9') + 1)},
    # Special keys
    "enter": 0xff0d,
    "return": 0xff0d,
    "tab": 0xff09,
    "escape": 0xff1b,
    "esc": 0xff1b,
    "backspace": 0xff08,
    "delete": 0xffff,
    "space": 0x0020,
    "up": 0xff52,
    "down": 0xff54,
    "left": 0xff51,
    "right": 0xff53,
    "home": 0xff50,
    "end": 0xff57,
    "pageup": 0xff55,
    "pagedown": 0xff56,
    "insert": 0xff63,
    "capslock": 0xffe5,
    "numlock": 0xff7f,
    "printscreen": 0xff61,
    "scrolllock": 0xff14,
    "pause": 0xff13,
    # Modifiers
    "ctrl": 0xffe3,
    "control": 0xffe3,
    "alt": 0xffe9,
    "shift": 0xffe1,
    "super": 0xffeb,
    "win": 0xffeb,
    "meta": 0xffeb,
    "cmd": 0xffeb,
    # Function keys
    **{f"f{i}": 0xffbe + i - 1 for i in range(1, 25)},
    # Punctuation and symbols
    " ": 0x0020,
    "!": 0x0021,
    '"': 0x0022,
    "#": 0x0023,
    "$": 0x0024,
    "%": 0x0025,
    "&": 0x0026,
    "'": 0x0027,
    "(": 0x0028,
    ")": 0x0029,
    "*": 0x002a,
    "+": 0x002b,
    ",": 0x002c,
    "-": 0x002d,
    ".": 0x002e,
    "/": 0x002f,
    ":": 0x003a,
    ";": 0x003b,
    "<": 0x003c,
    "=": 0x003d,
    ">": 0x003e,
    "?": 0x003f,
    "@": 0x0040,
    "[": 0x005b,
    "\\": 0x005c,
    "]": 0x005d,
    "^": 0x005e,
    "_": 0x005f,
    "`": 0x0060,
    "{": 0x007b,
    "|": 0x007c,
    "}": 0x007d,
    "~": 0x007e,
}


def resolve_keysym(key: str) -> int:
    """Convert a key name or character to an X11 keysym."""
    if isinstance(key, int):
        return key

    # Direct lookup
    key_lower = key.lower()
    if key_lower in KEYSYM_MAP:
        return KEYSYM_MAP[key_lower]

    # Single character — use Unicode codepoint (works for basic ASCII keysyms)
    if len(key) == 1:
        return ord(key)

    return KEYSYM_MAP.get(key, 0)


def main():
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION)

    # Create RemoteDesktop session
    proxy = Gio.DBusProxy.new_sync(
        bus, 0, None,
        'org.gnome.Mutter.RemoteDesktop',
        '/org/gnome/Mutter/RemoteDesktop',
        'org.gnome.Mutter.RemoteDesktop', None,
    )

    result = proxy.call_sync('CreateSession', None, Gio.DBusCallFlags.NONE, 5000, None)
    session_path = result.unpack()[0]

    session = Gio.DBusProxy.new_sync(
        bus, 0, None,
        'org.gnome.Mutter.RemoteDesktop', session_path,
        'org.gnome.Mutter.RemoteDesktop.Session', None,
    )

    # Start session
    session.call_sync('Start', None, Gio.DBusCallFlags.NONE, 5000, None)

    # Signal ready
    print(json.dumps({"status": "ready", "session": session_path}), flush=True)

    def move_relative(dx, dy):
        args = GLib.Variant.new_tuple(GLib.Variant('d', float(dx)), GLib.Variant('d', float(dy)))
        session.call_sync('NotifyPointerMotionRelative', args, Gio.DBusCallFlags.NONE, 1000, None)

    def move_absolute(stream, x, y):
        args = GLib.Variant.new_tuple(
            GLib.Variant('s', stream),
            GLib.Variant('d', float(x)),
            GLib.Variant('d', float(y)),
        )
        session.call_sync('NotifyPointerMotionAbsolute', args, Gio.DBusCallFlags.NONE, 1000, None)

    def button_press(button_code, state):
        args = GLib.Variant.new_tuple(GLib.Variant('i', button_code), GLib.Variant('b', state))
        session.call_sync('NotifyPointerButton', args, Gio.DBusCallFlags.NONE, 1000, None)

    def click(button_code, count=1):
        for _ in range(count):
            button_press(button_code, True)
            time.sleep(0.02)
            button_press(button_code, False)
            time.sleep(0.02)

    def scroll(dx, dy):
        # Use discrete scroll for better compatibility
        if dy != 0:
            # axis 0 = vertical
            args = GLib.Variant.new_tuple(GLib.Variant('u', 0), GLib.Variant('i', int(dy)))
            session.call_sync('NotifyPointerAxisDiscrete', args, Gio.DBusCallFlags.NONE, 1000, None)
        if dx != 0:
            # axis 1 = horizontal
            args = GLib.Variant.new_tuple(GLib.Variant('u', 1), GLib.Variant('i', int(dx)))
            session.call_sync('NotifyPointerAxisDiscrete', args, Gio.DBusCallFlags.NONE, 1000, None)

    def key_event(keysym, state):
        args = GLib.Variant.new_tuple(GLib.Variant('u', keysym), GLib.Variant('b', state))
        session.call_sync('NotifyKeyboardKeysym', args, Gio.DBusCallFlags.NONE, 1000, None)

    def key_press(keysym):
        key_event(keysym, True)
        time.sleep(0.02)
        key_event(keysym, False)

    def type_text(text):
        for char in text:
            ks = resolve_keysym(char)
            if ks:
                key_press(ks)
                time.sleep(0.02)

    # Process commands from stdin
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                cmd = json.loads(line)
                cmd_type = cmd.get("type", "")

                if cmd_type == "stop":
                    break

                elif cmd_type == "mouse_move":
                    if cmd.get("relative", True):
                        move_relative(cmd.get("x", 0), cmd.get("y", 0))
                    else:
                        move_absolute("", cmd.get("x", 0), cmd.get("y", 0))

                elif cmd_type == "mouse_click":
                    btn = BUTTON_MAP.get(cmd.get("button", "left"), BUTTON_MAP["left"])
                    count = cmd.get("count", 1)
                    click(btn, count)

                elif cmd_type == "mouse_down":
                    btn = BUTTON_MAP.get(cmd.get("button", "left"), BUTTON_MAP["left"])
                    button_press(btn, True)

                elif cmd_type == "mouse_up":
                    btn = BUTTON_MAP.get(cmd.get("button", "left"), BUTTON_MAP["left"])
                    button_press(btn, False)

                elif cmd_type == "mouse_scroll":
                    scroll(cmd.get("dx", 0), cmd.get("dy", 0))

                elif cmd_type == "key_press":
                    key = cmd.get("key", "")
                    keysym = resolve_keysym(key)
                    modifiers = cmd.get("modifiers", [])
                    if modifiers:
                        # Press modifiers
                        mod_syms = [resolve_keysym(m) for m in modifiers]
                        for ms in mod_syms:
                            if ms:
                                key_event(ms, True)
                        # Press key
                        if keysym:
                            key_press(keysym)
                        # Release modifiers
                        for ms in reversed(mod_syms):
                            if ms:
                                key_event(ms, False)
                    else:
                        if keysym:
                            key_press(keysym)

                elif cmd_type == "key_combo":
                    keys = cmd.get("keys", [])
                    syms = [resolve_keysym(k) for k in keys]
                    # Press all
                    for s in syms:
                        if s:
                            key_event(s, True)
                    time.sleep(0.02)
                    # Release all
                    for s in reversed(syms):
                        if s:
                            key_event(s, False)

                elif cmd_type == "type_text":
                    type_text(cmd.get("text", ""))

                # Send OK response
                print(json.dumps({"status": "ok"}), flush=True)

            except Exception as e:
                print(json.dumps({"status": "error", "message": str(e)}), flush=True)

    except (EOFError, KeyboardInterrupt):
        pass

    # Cleanup
    try:
        session.call_sync('Stop', None, Gio.DBusCallFlags.NONE, 5000, None)
    except Exception:
        pass


if __name__ == '__main__':
    main()
