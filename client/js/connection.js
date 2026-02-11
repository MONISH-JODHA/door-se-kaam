/**
 * Door Se Kaam — Connection Manager
 *
 * Handles WebSocket connections for screen streaming and input,
 * with auto-reconnect, auth token management, and latency tracking.
 */

class ConnectionManager {
    constructor() {
        this.screenWs = null;
        this.inputWs = null;
        this.token = null;
        this.baseUrl = '';
        this.wsBaseUrl = '';
        this.state = 'disconnected'; // disconnected, connecting, connected
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectTimer = null;
        this.pingInterval = null;
        this.latency = 0;

        // Callbacks
        this.onStateChange = null;
        this.onScreenFrame = null;
        this.onError = null;
        this.onLatencyUpdate = null;

        // Detect base URL from current page
        this._detectBaseUrl();
    }

    _detectBaseUrl() {
        const loc = window.location;
        this.baseUrl = `${loc.protocol}//${loc.host}`;
        const wsProtocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
        this.wsBaseUrl = `${wsProtocol}//${loc.host}`;
    }

    _setState(state) {
        this.state = state;
        if (this.onStateChange) this.onStateChange(state);
    }

    // ── Auth API ────────────────────────────────────────────

    async checkAuthStatus() {
        try {
            const headers = {};
            if (this.token) {
                headers['Authorization'] = `Bearer ${this.token}`;
            }
            const res = await fetch(`${this.baseUrl}/api/auth/status`, { headers });
            return await res.json();
        } catch (e) {
            return { authenticated: false, error: e.message };
        }
    }

    async login(password) {
        try {
            const res = await fetch(`${this.baseUrl}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password }),
            });

            const data = await res.json();
            if (res.ok && data.token) {
                this.token = data.token;
                localStorage.setItem('dsk_token', data.token);
                return { success: true };
            }
            return { success: false, error: data.detail || 'Login failed' };
        } catch (e) {
            return { success: false, error: e.message };
        }
    }

    async setupPassword(password) {
        try {
            const res = await fetch(`${this.baseUrl}/api/auth/setup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password }),
            });

            const data = await res.json();
            if (res.ok) {
                // Now login with the new password
                return await this.login(password);
            }
            return { success: false, error: data.detail || 'Setup failed' };
        } catch (e) {
            return { success: false, error: e.message };
        }
    }

    loadSavedToken() {
        const saved = localStorage.getItem('dsk_token');
        if (saved) {
            this.token = saved;
            return true;
        }
        return false;
    }

    // ── WebSocket Connections ───────────────────────────────

    connect(options = {}) {
        this._setState('connecting');
        this.reconnectAttempts = 0;

        const params = new URLSearchParams();
        if (this.token) params.set('token', this.token);
        if (options.maxWidth) params.set('max_width', options.maxWidth);
        if (options.fps) params.set('fps', options.fps);
        if (options.quality) params.set('quality', options.quality);

        const query = params.toString() ? `?${params.toString()}` : '';

        this._connectScreen(query);
        this._connectInput(query);
    }

    _connectScreen(query) {
        try {
            this.screenWs = new WebSocket(`${this.wsBaseUrl}/ws/screen${query}`);
            this.screenWs.binaryType = 'arraybuffer';

            this.screenWs.onopen = () => {
                console.log('[Screen] Connected');
                this._setState('connected');
                this.reconnectAttempts = 0;
                this._startPing();
            };

            this.screenWs.onmessage = (event) => {
                if (event.data instanceof ArrayBuffer) {
                    if (this.onScreenFrame) {
                        this.onScreenFrame(event.data);
                    }
                }
            };

            this.screenWs.onclose = (event) => {
                console.log(`[Screen] Closed: ${event.code}`);
                this._handleDisconnect(event.code, query);
            };

            this.screenWs.onerror = (error) => {
                console.error('[Screen] Error:', error);
            };
        } catch (e) {
            console.error('[Screen] Connection failed:', e);
            this._handleDisconnect(0, query);
        }
    }

    _connectInput(query) {
        try {
            // For input, we only need the token
            const inputQuery = this.token ? `?token=${this.token}` : '';
            this.inputWs = new WebSocket(`${this.wsBaseUrl}/ws/input${inputQuery}`);

            this.inputWs.onopen = () => {
                console.log('[Input] Connected');
            };

            this.inputWs.onmessage = (event) => {
                // Handle responses from input commands if needed
                try {
                    const data = JSON.parse(event.data);
                    console.log('[Input] Response:', data);
                } catch (e) {}
            };

            this.inputWs.onclose = () => {
                console.log('[Input] Closed');
            };

            this.inputWs.onerror = (error) => {
                console.error('[Input] Error:', error);
            };
        } catch (e) {
            console.error('[Input] Connection failed:', e);
        }
    }

    _handleDisconnect(code, query) {
        this._stopPing();

        if (code === 4001) {
            // Auth failure, don't reconnect
            this._setState('disconnected');
            if (this.onError) this.onError('Authentication failed');
            return;
        }

        this._setState('disconnected');

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 10000);
            console.log(`[Reconnect] Attempt ${this.reconnectAttempts + 1} in ${delay}ms`);
            this.reconnectAttempts++;
            this.reconnectTimer = setTimeout(() => {
                this._setState('connecting');
                this._connectScreen(query);
                this._connectInput(query);
            }, delay);
        } else {
            if (this.onError) this.onError('Connection lost. Please reconnect.');
        }
    }

    disconnect() {
        this._stopPing();
        clearTimeout(this.reconnectTimer);
        this.reconnectAttempts = this.maxReconnectAttempts; // prevent auto-reconnect

        if (this.screenWs) {
            this.screenWs.close();
            this.screenWs = null;
        }
        if (this.inputWs) {
            this.inputWs.close();
            this.inputWs = null;
        }
        this._setState('disconnected');
    }

    // ── Send Input Commands ─────────────────────────────────

    sendInput(command) {
        if (this.inputWs && this.inputWs.readyState === WebSocket.OPEN) {
            this.inputWs.send(JSON.stringify(command));
        }
    }

    sendScreenControl(command) {
        if (this.screenWs && this.screenWs.readyState === WebSocket.OPEN) {
            this.screenWs.send(JSON.stringify(command));
        }
    }

    // ── Latency Tracking ────────────────────────────────────

    _startPing() {
        this._stopPing();
        this.pingInterval = setInterval(() => {
            if (this.screenWs && this.screenWs.readyState === WebSocket.OPEN) {
                const start = performance.now();
                // We approximate latency from frame interval
                this._lastPingTime = start;
            }
        }, 3000);
    }

    _stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    updateLatency(frameTime) {
        // Simple running average
        this.latency = Math.round(this.latency * 0.7 + frameTime * 0.3);
        if (this.onLatencyUpdate) this.onLatencyUpdate(this.latency);
    }

    // ── REST API Helpers ────────────────────────────────────

    async apiGet(path) {
        const headers = {};
        if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
        const res = await fetch(`${this.baseUrl}${path}`, { headers });
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
    }

    async apiPost(path, body) {
        const headers = { 'Content-Type': 'application/json' };
        if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
        const res = await fetch(`${this.baseUrl}${path}`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
    }

    get isConnected() {
        return this.state === 'connected';
    }
}

// Global instance
window.connectionManager = new ConnectionManager();
