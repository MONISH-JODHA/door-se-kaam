"""
Door Se Kaam — Main Server

FastAPI application that serves the remote desktop:
- WebSocket screen streaming (MJPEG)
- WebSocket input handling (mouse/keyboard)
- REST API for auth, files, and system info
- Static file serving for the PWA client
"""

import os
import sys
import json
import asyncio
import logging
import platform
import subprocess
from pathlib import Path
from datetime import datetime, timezone

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Request,
    UploadFile,
    File,
    Query,
    Depends,
)
from fastapi.responses import (
    HTMLResponse,
    FileResponse,
    StreamingResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ── Internal modules ─────────────────────────────────────────
from config import config
from auth import auth_manager
from screen_capture import ScreenCapture
from input_handler import InputHandler, input_handler
from file_manager import file_manager

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("door-se-kaam")

# ── App ──────────────────────────────────────────────────────
app = FastAPI(
    title="Door Se Kaam",
    description="Remote Desktop Controller for Linux",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Screen capture instance (created lazily to avoid X11 at import)
_screen_capture = None

def get_screen_capture():
    global _screen_capture
    if _screen_capture is None:
        _screen_capture = ScreenCapture()
    return _screen_capture

# Client directory (served as static files)
CLIENT_DIR = Path(__file__).parent.parent / "client"

# ── Helpers ──────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def verify_ws_token(websocket: WebSocket) -> bool:
    """Verify JWT token from WebSocket query params or first message."""
    token = websocket.query_params.get("token", "")
    if token and auth_manager.verify_token(token):
        return True
    return False


def require_auth(request: Request):
    """Dependency: require a valid JWT token in Authorization header."""
    if not auth_manager.is_password_set:
        return  # No password set yet, allow access for setup

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth_header[7:]
    if not auth_manager.verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ═══════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.post("/api/auth/setup")
async def auth_setup(request: Request):
    """Set the initial password (only works if no password is set)."""
    if auth_manager.is_password_set:
        raise HTTPException(status_code=403, detail="Password already configured")

    body = await request.json()
    password = body.get("password", "")

    if not auth_manager.set_password(password):
        raise HTTPException(
            status_code=400,
            detail="Password too short (minimum 4 characters)",
        )

    logger.info("✔ Initial password configured")
    return {"status": "ok", "message": "Password set successfully"}


@app.post("/api/auth/login")
async def auth_login(request: Request):
    """Authenticate and receive a JWT token."""
    if not auth_manager.is_password_set:
        return {"status": "setup_required", "message": "No password configured"}

    client_ip = get_client_ip(request)
    lockout = auth_manager.get_lockout_remaining(client_ip)
    if lockout > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {lockout} seconds.",
        )

    body = await request.json()
    password = body.get("password", "")

    token = auth_manager.create_token(password, client_ip)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid password")

    logger.info(f"✔ Login from {client_ip}")
    return {"status": "ok", "token": token}


@app.get("/api/auth/status")
async def auth_status(request: Request):
    """Check authentication status."""
    if not auth_manager.is_password_set:
        return {"authenticated": False, "setup_required": True}

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if auth_manager.verify_token(token):
            return {"authenticated": True, "setup_required": False}

    return {"authenticated": False, "setup_required": False}


# ═══════════════════════════════════════════════════════════════
#  SCREEN STREAMING
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws/screen")
async def ws_screen(websocket: WebSocket):
    """WebSocket endpoint for MJPEG screen streaming."""
    await websocket.accept()

    # Auth check
    if auth_manager.is_password_set:
        if not await verify_ws_token(websocket):
            await websocket.close(code=4001, reason="Unauthorized")
            return

    client = websocket.client.host if websocket.client else "unknown"
    logger.info(f"📺 Screen stream started → {client}")

    # Get optional params
    max_width = int(websocket.query_params.get("max_width", "0")) or None
    requested_fps = int(websocket.query_params.get("fps", "0")) or None
    requested_quality = int(websocket.query_params.get("quality", "0")) or None

    capture = ScreenCapture(
        fps=requested_fps or config.capture_fps,
        quality=requested_quality or config.capture_quality,
        monitor=config.capture_monitor,
    )

    try:
        async for frame in capture.stream_frames(max_width=max_width):
            try:
                await websocket.send_bytes(frame)
            except (WebSocketDisconnect, RuntimeError):
                break

            # Check for incoming control messages (non-blocking)
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=0.001
                )
                data = json.loads(msg)
                # Handle quality/fps changes
                if data.get("type") == "set_quality":
                    capture.quality = data.get("quality", capture.quality)
                    capture._adaptive_quality = capture.quality
                elif data.get("type") == "set_fps":
                    capture.fps = data.get("fps", capture.fps)
                    capture._adaptive_fps = capture.fps
                elif data.get("type") == "set_monitor":
                    capture.monitor = data.get("monitor", capture.monitor)
            except (asyncio.TimeoutError, WebSocketDisconnect):
                pass

    except WebSocketDisconnect:
        pass
    finally:
        capture.stop()
        logger.info(f"📺 Screen stream ended → {client}")


# ═══════════════════════════════════════════════════════════════
#  INPUT HANDLING
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws/input")
async def ws_input(websocket: WebSocket):
    """WebSocket endpoint for receiving mouse/keyboard commands."""
    await websocket.accept()

    # Auth check
    if auth_manager.is_password_set:
        if not await verify_ws_token(websocket):
            await websocket.close(code=4001, reason="Unauthorized")
            return

    client = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🎮 Input channel opened → {client}")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                command = json.loads(raw)
                result = input_handler.process_command(command)

                # Optionally send response for commands that return data
                if command.get("type") in ("get_cursor", "get_screen_size"):
                    if command["type"] == "get_cursor":
                        data = input_handler.get_cursor_position()
                    else:
                        data = input_handler.get_screen_size()
                    await websocket.send_text(json.dumps(data))

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"status": "error", "message": "Invalid JSON"})
                )
    except WebSocketDisconnect:
        pass
    finally:
        logger.info(f"🎮 Input channel closed → {client}")


# ═══════════════════════════════════════════════════════════════
#  FILE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@app.get("/api/files/list")
async def api_files_list(
    path: str = Query(default="~"),
    _auth=Depends(require_auth),
):
    """List directory contents."""
    if path == "~":
        path = str(Path.home())
    result = file_manager.list_directory(path)
    if "error" in result:
        raise HTTPException(status_code=403, detail=result["error"])
    return result


@app.get("/api/files/download")
async def api_files_download(
    path: str = Query(...),
    _auth=Depends(require_auth),
):
    """Download a file."""
    file_path, error = file_manager.validate_download(path)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return FileResponse(
        str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@app.post("/api/files/upload")
async def api_files_upload(
    file: UploadFile = File(...),
    _auth=Depends(require_auth),
):
    """Upload a file to the server."""
    target, error = file_manager.validate_upload(
        file.filename or "upload",
        file.size or 0,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    try:
        with open(target, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
        logger.info(f"📁 File uploaded: {target}")
        return {"status": "ok", "path": target, "size": os.path.getsize(target)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/files/disk")
async def api_disk_usage(_auth=Depends(require_auth)):
    """Get disk usage for allowed directories."""
    return file_manager.get_disk_usage()


# ═══════════════════════════════════════════════════════════════
#  SYSTEM INFO
# ═══════════════════════════════════════════════════════════════

@app.get("/api/system")
async def api_system(_auth=Depends(require_auth)):
    """Return system information."""
    monitors = get_screen_capture().get_monitors()

    # Get hostname
    hostname = platform.node()

    # Get uptime (Linux-specific)
    uptime = ""
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            uptime = f"{hours}h {minutes}m"
    except Exception:
        uptime = "unknown"

    return {
        "hostname": hostname,
        "os": f"{platform.system()} {platform.release()}",
        "desktop": os.getenv("XDG_CURRENT_DESKTOP", "unknown"),
        "display_server": os.getenv("XDG_SESSION_TYPE", "unknown"),
        "monitors": monitors,
        "uptime": uptime,
        "server_version": "0.1.0",
    }


@app.get("/api/monitors")
async def api_monitors(_auth=Depends(require_auth)):
    """List available monitors."""
    return {"monitors": get_screen_capture().get_monitors()}


# ═══════════════════════════════════════════════════════════════
#  STATIC FILES & CLIENT SERVING
# ═══════════════════════════════════════════════════════════════

# Serve the PWA client
if CLIENT_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(CLIENT_DIR)),
        name="static",
    )


@app.get("/")
async def serve_client():
    """Serve the main client HTML."""
    index_path = CLIENT_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    return HTMLResponse(
        content="<h1>Door Se Kaam</h1><p>Client not found. "
        "Place client files in ../client/</p>"
    )


# ═══════════════════════════════════════════════════════════════
#  TLS CERTIFICATE GENERATION
# ═══════════════════════════════════════════════════════════════

def generate_self_signed_cert():
    """Generate a self-signed TLS certificate if one doesn't exist."""
    if config.cert_path.exists() and config.key_path.exists():
        return

    logger.info("🔐 Generating self-signed TLS certificate...")

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        import ipaddress

        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "Door Se Kaam"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Self-Signed"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime(2030, 1, 1, tzinfo=timezone.utc))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName("*.local"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    x509.IPAddress(ipaddress.IPv4Address("0.0.0.0")),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256(), default_backend())
        )

        config.cert_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config.cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(config.key_path, "wb") as f:
            f.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                )
            )

        logger.info(f"🔐 Certificate saved to {config.cert_path}")

    except ImportError:
        logger.warning(
            "⚠ 'cryptography' package not installed. "
            "Running without HTTPS. Install with: pip install cryptography"
        )
        config.use_https = False


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    import uvicorn

    # Print banner
    print(r"""
    ╔══════════════════════════════════════════════╗
    ║         🖥️  Door Se Kaam  📱               ║
    ║    Remote Desktop Controller for Linux       ║
    ╚══════════════════════════════════════════════╝
    """)

    # Ensure directories
    config.ensure_directories()

    # Generate TLS cert
    if config.use_https:
        generate_self_signed_cert()

    # Check password
    if not auth_manager.is_password_set:
        print("\n⚠️  No password configured!")
        print("   You'll be prompted to set one in the web UI.")
        print("   Or set it via: python -c \"from auth import auth_manager; auth_manager.set_password('your_pass')\"")

    # Get local IPs for the user
    local_ips = []
    try:
        import socket
        hostname = socket.gethostname()
        # Get all IPs
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in local_ips and ip != "127.0.0.1":
                local_ips.append(ip)
    except Exception:
        pass

    protocol = "https" if config.use_https else "http"
    print(f"\n   🌐 Server starting on {protocol}://{config.host}:{config.port}")
    print(f"   🏠 Local access: {protocol}://localhost:{config.port}")
    for ip in local_ips:
        print(f"   📱 Mobile access: {protocol}://{ip}:{config.port}")
    print()

    # Launch
    ssl_kwargs = {}
    if config.use_https and config.cert_path.exists() and config.key_path.exists():
        ssl_kwargs = {
            "ssl_certfile": str(config.cert_path),
            "ssl_keyfile": str(config.key_path),
        }

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
