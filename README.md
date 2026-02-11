# 🖥️ Door Se Kaam 📱

**Remote Desktop Controller for Linux** — Control your Linux laptop from your phone's browser.

> **"Door Se Kaam"** = "Working from a Distance" (Hindi)

## ✨ Features

- **📺 Real-time Screen Streaming** — MJPEG over WebSocket with adaptive quality
- **🖱️ Cursor Control** — Touchpad & direct touch modes with gesture support
- **⌨️ Virtual Keyboard** — System keyboard + special keys bar (Ctrl, Alt, F-keys, shortcuts)
- **📁 File Transfer** — Browse, upload, and download files between phone and laptop
- **🔐 Secure Auth** — Bcrypt password hashing + JWT session tokens
- **🌐 PWA Support** — "Add to Home Screen" for native app-like experience
- **🖥️ Multi-Monitor** — Switch between displays

## 🚀 Quick Start

### 1. Install

```bash
cd server
chmod +x install.sh
./install.sh
```

### 2. Run

```bash
cd server
source .venv/bin/activate
python main.py
```

### 3. Connect

Open the URL shown in the terminal on your phone's browser:

```
https://<your-laptop-ip>:8443
```

> Accept the self-signed certificate warning on first visit.

## 📱 Touch Gestures

| Gesture            | Action       |
| ------------------ | ------------ |
| Single finger drag | Move cursor  |
| Single tap         | Left click   |
| Two-finger tap     | Right click  |
| Two-finger drag    | Scroll       |
| Pinch              | Zoom view    |
| Long press         | Drag mode    |
| Three-finger tap   | Middle click |

## 🏗️ Architecture

```
door-se-kaam/
├── server/           # Python/FastAPI server
│   ├── main.py       # FastAPI app (WebSocket + REST API)
│   ├── screen_capture.py   # mss-based screen capture
│   ├── input_handler.py    # PyAutoGUI mouse/keyboard
│   ├── auth.py             # Authentication (bcrypt + JWT)
│   ├── file_manager.py     # Secure file operations
│   └── config.py           # Configuration
└── client/           # PWA web client
    ├── index.html    # App shell
    ├── css/style.css # Dark theme design system
    └── js/           # Modules
        ├── app.js            # Orchestrator
        ├── connection.js     # WebSocket manager
        ├── screen-viewer.js  # Canvas MJPEG renderer
        ├── input-controller.js  # Touch gesture mapper
        ├── keyboard.js       # Virtual keyboard
        └── file-transfer.js  # File browser
```

## ⚙️ Configuration

Set via environment variables:

| Variable      | Default | Description           |
| ------------- | ------- | --------------------- |
| `DSK_PORT`    | `8443`  | Server port           |
| `DSK_FPS`     | `15`    | Target FPS            |
| `DSK_QUALITY` | `60`    | JPEG quality (1-100)  |
| `DSK_MONITOR` | `0`     | Monitor index (0=all) |

## 📋 Roadmap

- [x] Phase 1: Screen streaming, input, keyboard, file transfer (local network)
- [ ] Phase 2: Internet access (STUN/TURN/signaling server)
- [ ] Phase 3: Audio streaming, clipboard sync, session recording
- [ ] Phase 4: Performance optimization, polish

## 📄 License

MIT
