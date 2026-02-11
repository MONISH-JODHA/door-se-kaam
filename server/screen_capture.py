"""
Door Se Kaam — Screen Capture Module

Captures the Linux desktop screen and encodes frames as JPEG for streaming.

Supports multiple backends (auto-detected):
  1. Wayland: Mutter ScreenCast D-Bus + PipeWire + GStreamer
  2. X11: Uses the 'mss' library for fast direct capture
  3. Fallback: CLI screenshot tools (gnome-screenshot, grim, etc.)
"""

import io
import os
import sys
import time
import asyncio
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional, AsyncGenerator, List

from PIL import Image

from config import config

logger = logging.getLogger("door-se-kaam")

_session_type = os.getenv("XDG_SESSION_TYPE", "").lower()
_is_wayland = _session_type == "wayland" or bool(os.getenv("WAYLAND_DISPLAY"))

# Path to the wayland helper script (runs with system python for gi)
_HELPER_SCRIPT = Path(__file__).parent / "wayland_capture.py"


class ScreenCapture:
    """Fast screen capture with JPEG encoding for streaming."""

    def __init__(
        self,
        fps: int = None,
        quality: int = None,
        monitor: int = None,
    ):
        self.fps = fps or config.capture_fps
        self.quality = quality or config.capture_quality
        self.monitor = monitor if monitor is not None else config.capture_monitor
        self._running = False

        # Adaptive tracking (only FPS adapts, quality stays fixed)
        self._frame_times: list = []
        self._adaptive_quality = self.quality
        self._adaptive_fps = self.fps

        # Wayland PipeWire session state
        self._pw_node_id: Optional[int] = None
        self._pw_session_proc: Optional[subprocess.Popen] = None
        self._tmp_file = Path(tempfile.gettempdir()) / "dsk_screenshot.jpg"

        # Detect backend
        self._backend = self._detect_backend()
        logger.info(f"Screen capture backend: {self._backend} (session: {_session_type})")

    def _detect_backend(self) -> str:
        """Detect the best available screenshot backend."""
        if _is_wayland:
            try:
                result = subprocess.run(
                    ["gdbus", "introspect", "--session",
                     "--dest", "org.gnome.Mutter.ScreenCast",
                     "--object-path", "/org/gnome/Mutter/ScreenCast"],
                    capture_output=True, timeout=2,
                )
                if result.returncode == 0:
                    return "pipewire"
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            for tool in ["grim", "gnome-screenshot", "spectacle"]:
                if self._cmd_exists(tool):
                    return tool

            return "mss-fallback"

        return "mss"

    def _cmd_exists(self, cmd: str) -> bool:
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _start_pipewire_session(self):
        """Start a persistent ScreenCast D-Bus session via the helper."""
        if self._pw_session_proc is not None:
            return

        logger.info("Starting PipeWire ScreenCast session...")

        self._pw_session_proc = subprocess.Popen(
            ["/usr/bin/python3", str(_HELPER_SCRIPT), "session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            for _ in range(10):
                line = ""
                import select
                ready, _, _ = select.select([self._pw_session_proc.stdout], [], [], 0.5)
                if ready:
                    line = self._pw_session_proc.stdout.readline().strip()

                if line.startswith("NODE:"):
                    self._pw_node_id = int(line.split(":")[1])
                    logger.info(f"PipeWire node ID: {self._pw_node_id}")
                    break
                elif line.startswith("ERROR:"):
                    logger.error(f"PipeWire session error: {line}")
                    self._stop_pipewire_session()
                    return

            if self._pw_node_id is None:
                logger.error("Failed to get PipeWire node ID")
                self._stop_pipewire_session()
        except Exception as e:
            logger.error(f"PipeWire session start failed: {e}")
            self._stop_pipewire_session()

    def _stop_pipewire_session(self):
        """Stop the PipeWire ScreenCast session."""
        if self._pw_session_proc:
            try:
                self._pw_session_proc.stdin.write("stop\n")
                self._pw_session_proc.stdin.flush()
                self._pw_session_proc.wait(timeout=3)
            except Exception:
                try:
                    self._pw_session_proc.terminate()
                    self._pw_session_proc.wait(timeout=2)
                except Exception:
                    self._pw_session_proc.kill()
            self._pw_session_proc = None
            self._pw_node_id = None

    def get_monitors(self) -> List[dict]:
        """Return list of available monitors."""
        if self._backend == "mss":
            try:
                import mss
                with mss.mss() as sct:
                    return [
                        {
                            "index": i,
                            "left": m["left"], "top": m["top"],
                            "width": m["width"], "height": m["height"],
                            "is_combined": i == 0,
                        }
                        for i, m in enumerate(sct.monitors)
                    ]
            except Exception:
                pass

        try:
            result = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True, text=True, timeout=3,
                env={**os.environ, "DISPLAY": os.getenv("DISPLAY", ":0")},
            )
            if result.returncode == 0:
                monitors = [{"index": 0, "left": 0, "top": 0, "width": 0, "height": 0, "is_combined": True}]
                idx = 1
                for line in result.stdout.splitlines():
                    if " connected " in line:
                        for part in line.split():
                            if "x" in part and "+" in part:
                                dims = part.split("+")[0]
                                w, h = dims.split("x")
                                monitors.append({
                                    "index": idx, "left": 0, "top": 0,
                                    "width": int(w), "height": int(h),
                                    "is_combined": False,
                                })
                                monitors[0]["width"] = max(monitors[0]["width"], int(w))
                                monitors[0]["height"] = max(monitors[0]["height"], int(h))
                                idx += 1
                                break
                return monitors
        except Exception:
            pass

        return [{"index": 0, "left": 0, "top": 0, "width": 1920, "height": 1080, "is_combined": True}]

    def capture_frame(
        self,
        quality: int = None,
        monitor: int = None,
        max_width: int = None,
    ) -> bytes:
        """Capture a single frame as JPEG bytes."""
        q = quality or self._adaptive_quality
        img = self._capture_image()

        if img is None:
            img = Image.new("RGB", (640, 480), (30, 30, 50))

        if max_width and img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=False)
        return buf.getvalue()

    def _capture_image(self) -> Optional[Image.Image]:
        """Capture a screenshot and return as PIL Image."""
        try:
            if self._backend == "pipewire":
                return self._capture_pipewire()
            elif self._backend == "mss":
                return self._capture_mss()
            elif self._backend in ("grim", "gnome-screenshot", "spectacle"):
                return self._capture_cli(self._backend)
            else:
                return self._capture_mss()
        except Exception as e:
            if self._backend != "mss":
                try:
                    return self._capture_mss()
                except Exception:
                    pass
            logger.error(f"Screen capture failed: {e}")
            return None

    def _capture_pipewire(self) -> Image.Image:
        """Capture using PipeWire via GStreamer (JPEG output)."""
        if self._pw_node_id is None:
            self._start_pipewire_session()

        if self._pw_node_id is None:
            raise RuntimeError("No PipeWire session available")

        tmp = str(self._tmp_file)

        if self._tmp_file.exists():
            self._tmp_file.unlink()

        result = subprocess.run(
            [
                "gst-launch-1.0", "-e",
                "pipewiresrc", f"path={self._pw_node_id}", "num-buffers=1", "!",
                "videoconvert", "!",
                "jpegenc", "quality=95", "!",
                "filesink", f"location={tmp}",
            ],
            capture_output=True, timeout=10,
        )

        if result.returncode != 0 or not self._tmp_file.exists():
            self._stop_pipewire_session()
            raise RuntimeError("GStreamer capture failed")

        img = Image.open(tmp).convert("RGB")
        return img

    def _capture_pipewire_bytes(self, quality=95) -> Optional[bytes]:
        """Capture using PipeWire and return raw JPEG bytes (no PIL overhead)."""
        if self._pw_node_id is None:
            self._start_pipewire_session()

        if self._pw_node_id is None:
            return None

        tmp = str(self._tmp_file)

        if self._tmp_file.exists():
            self._tmp_file.unlink()

        result = subprocess.run(
            [
                "gst-launch-1.0", "-e",
                "pipewiresrc", f"path={self._pw_node_id}", "num-buffers=1", "!",
                "videoconvert", "!",
                "jpegenc", f"quality={quality}", "!",
                "filesink", f"location={tmp}",
            ],
            capture_output=True, timeout=10,
        )

        if result.returncode != 0 or not self._tmp_file.exists():
            self._stop_pipewire_session()
            return None

        return self._tmp_file.read_bytes()

    def _capture_mss(self) -> Image.Image:
        """Capture using mss (X11)."""
        import mss
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[self.monitor])
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def _capture_cli(self, tool: str) -> Image.Image:
        """Capture using a CLI screenshot tool."""
        tmp = str(self._tmp_file)

        if tool == "grim":
            cmd = ["grim", tmp]
        elif tool == "gnome-screenshot":
            cmd = ["gnome-screenshot", "-f", tmp]
        elif tool == "spectacle":
            cmd = ["spectacle", "-b", "-n", "-o", tmp]
        else:
            raise RuntimeError(f"Unknown tool: {tool}")

        subprocess.run(cmd, capture_output=True, timeout=5)
        return Image.open(tmp).convert("RGB")

    async def stream_frames(
        self,
        max_width: int = None,
    ) -> AsyncGenerator[bytes, None]:
        """Async generator that yields JPEG frames at the configured FPS."""
        self._running = True
        self._adaptive_quality = self.quality
        self._adaptive_fps = self.fps
        error_count = 0

        if self._backend == "pipewire":
            self._start_pipewire_session()

        try:
            while self._running:
                frame_start = time.monotonic()

                try:
                    frame_data = None

                    if self._backend == "pipewire" and self._pw_node_id:
                        # Direct JPEG bytes — skip PIL decode/re-encode
                        frame_data = self._capture_pipewire_bytes(
                            quality=self._adaptive_quality,
                        )
                    else:
                        # PIL path for other backends
                        img = self._capture_image()
                        if img is not None:
                            if max_width and img.width > max_width:
                                ratio = max_width / img.width
                                new_size = (max_width, int(img.height * ratio))
                                img = img.resize(new_size, Image.LANCZOS)
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG",
                                     quality=self._adaptive_quality, optimize=False)
                            frame_data = buf.getvalue()

                    if frame_data is None:
                        error_count += 1
                        if error_count > 10:
                            logger.error("Too many capture failures, stopping")
                            break
                        await asyncio.sleep(0.5)
                        continue

                    error_count = 0

                    frame_time = time.monotonic() - frame_start
                    self._update_adaptive(frame_time)

                    yield frame_data

                    target_interval = 1.0 / self._adaptive_fps
                    sleep_time = max(0.001, target_interval - frame_time)
                    await asyncio.sleep(sleep_time)

                except Exception as e:
                    error_count += 1
                    logger.warning(f"Frame error: {e}")
                    if error_count > 10:
                        break
                    await asyncio.sleep(0.5)

        finally:
            self._running = False
            if self._backend == "pipewire":
                self._stop_pipewire_session()

    def _update_adaptive(self, frame_time: float):
        """Adapt FPS to match capture speed. Quality stays fixed."""
        self._frame_times.append(frame_time)
        if len(self._frame_times) > 30:
            self._frame_times = self._frame_times[-30:]
        if len(self._frame_times) < 5:
            return

        avg_time = sum(self._frame_times) / len(self._frame_times)
        target_time = 1.0 / self.fps

        if avg_time > target_time * 1.5:
            # Only reduce FPS, NEVER quality
            self._adaptive_fps = max(3, self._adaptive_fps - 1)
        elif avg_time < target_time * 0.5:
            self._adaptive_fps = min(self.fps, self._adaptive_fps + 1)

        # Quality always stays at configured level
        self._adaptive_quality = self.quality

    def stop(self):
        self._running = False

    @property
    def current_quality(self) -> int:
        return self._adaptive_quality

    @property
    def current_fps(self) -> int:
        return self._adaptive_fps
