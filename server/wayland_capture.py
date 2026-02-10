#!/usr/bin/env python3
"""
Door Se Kaam — Wayland Screenshot Helper

Uses Mutter ScreenCast D-Bus API + PipeWire + GStreamer to capture
screenshots on GNOME Wayland. This script runs with the SYSTEM Python
(not venv) because it needs python3-gi (GObject Introspection).

Modes:
    session  - Create a ScreenCast session and print the PipeWire node ID.
               Keeps running until stdin receives 'stop' or process is killed.
    capture  - Capture a single frame from a PipeWire node to a file.
               Usage: wayland_capture.py capture <pw_node_id> <output_path>

Usage:
    /usr/bin/python3 wayland_capture.py session
    /usr/bin/python3 wayland_capture.py capture <node_id> <output.png>
"""

import sys
import os
import time
import signal
import subprocess


def create_screencast_session():
    """
    Create a Mutter ScreenCast session and output the PipeWire node ID.
    Keeps running to maintain the session alive.
    """
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION)

    # Create ScreenCast session
    proxy = Gio.DBusProxy.new_sync(
        bus, 0, None,
        'org.gnome.Mutter.ScreenCast',
        '/org/gnome/Mutter/ScreenCast',
        'org.gnome.Mutter.ScreenCast',
        None,
    )

    options = GLib.Variant.new_tuple(GLib.Variant('a{sv}', {}))
    result = proxy.call_sync(
        'CreateSession', options,
        Gio.DBusCallFlags.NONE, 5000, None,
    )
    session_path = result.unpack()[0]

    # Create a session proxy
    session = Gio.DBusProxy.new_sync(
        bus, 0, None,
        'org.gnome.Mutter.ScreenCast', session_path,
        'org.gnome.Mutter.ScreenCast.Session', None,
    )

    # Record primary monitor (empty string = primary)
    record_opts = GLib.Variant.new_tuple(
        GLib.Variant('s', ''),
        GLib.Variant('a{sv}', {}),
    )
    result = session.call_sync(
        'RecordMonitor', record_opts,
        Gio.DBusCallFlags.NONE, 5000, None,
    )
    stream_path = result.unpack()[0]

    # Listen for PipeWireStreamAdded signal
    stream = Gio.DBusProxy.new_sync(
        bus, 0, None,
        'org.gnome.Mutter.ScreenCast', stream_path,
        'org.gnome.Mutter.ScreenCast.Stream', None,
    )

    pw_node_id = [None]

    def on_signal(proxy, sender, signal_name, params):
        if signal_name == 'PipeWireStreamAdded':
            pw_node_id[0] = params.unpack()[0]

    stream.connect('g-signal', on_signal)

    # Start session
    session.call_sync('Start', None, Gio.DBusCallFlags.NONE, 5000, None)

    # Run mainloop briefly to receive PipeWireStreamAdded signal
    loop = GLib.MainLoop()
    GLib.timeout_add(500, loop.quit)
    loop.run()

    # Also try the property directly
    if pw_node_id[0] is None:
        pw_prop = stream.get_cached_property('PipeWireNodeId')
        if pw_prop:
            pw_node_id[0] = pw_prop.unpack()

    if pw_node_id[0] is None:
        print("ERROR:no_pipewire_node", flush=True)
        sys.exit(1)

    # Print the node ID so the parent process can read it
    print(f"NODE:{pw_node_id[0]}", flush=True)
    print(f"SESSION:{session_path}", flush=True)

    # Keep alive — wait for stop command or signal
    def handle_stop(signum, frame):
        try:
            session.call_sync('Stop', None, Gio.DBusCallFlags.NONE, 5000, None)
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    # Read stdin for stop command
    try:
        for line in sys.stdin:
            if line.strip().lower() == 'stop':
                break
    except (EOFError, KeyboardInterrupt):
        pass

    # Clean up
    try:
        session.call_sync('Stop', None, Gio.DBusCallFlags.NONE, 5000, None)
    except Exception:
        pass


def capture_frame(pw_node_id: int, output_path: str):
    """Capture a single frame from PipeWire using GStreamer."""
    cmd = [
        'gst-launch-1.0', '-e',
        'pipewiresrc', f'path={pw_node_id}', 'num-buffers=1', '!',
        'videoconvert', '!',
        'pngenc', '!',
        'filesink', f'location={output_path}',
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=10)

    if result.returncode == 0 and os.path.exists(output_path):
        print(f"OK:{os.path.getsize(output_path)}", flush=True)
    else:
        stderr = result.stderr.decode()[-200:] if result.stderr else ""
        print(f"ERROR:{stderr}", flush=True, file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} session|capture [args...]", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "session":
        create_screencast_session()
    elif mode == "capture" and len(sys.argv) >= 4:
        pw_node_id = int(sys.argv[2])
        output_path = sys.argv[3]
        capture_frame(pw_node_id, output_path)
    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
