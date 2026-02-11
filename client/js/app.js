/**
 * Door Se Kaam — Main Application
 *
 * Orchestrates screens, modules, settings, and global state.
 */

class App {
    constructor() {
        this.currentScreen = 'connection';
        this.tabOrder = ['desktop', 'files', 'settings'];
        this.settings = this._loadSettings();

        // DOM refs
        this.screens = {
            connection: document.getElementById('screen-connection'),
            desktop: document.getElementById('screen-desktop'),
            files: document.getElementById('screen-files'),
            settings: document.getElementById('screen-settings'),
        };

        this.elements = {
            setupForm: document.getElementById('setup-form'),
            loginForm: document.getElementById('login-form'),
            setupPassword: document.getElementById('setup-password'),
            setupPasswordConfirm: document.getElementById('setup-password-confirm'),
            loginPassword: document.getElementById('login-password'),
            btnSetup: document.getElementById('btn-setup'),
            btnLogin: document.getElementById('btn-login'),
            setupError: document.getElementById('setup-error'),
            loginError: document.getElementById('login-error'),
            statusDot: document.getElementById('status-dot'),
            statusText: document.getElementById('status-text'),
            statFps: document.getElementById('stat-fps'),
            statLatency: document.getElementById('stat-latency'),
            statQuality: document.getElementById('stat-quality'),
            systemInfo: document.getElementById('system-info'),
            btnDisconnect: document.getElementById('btn-disconnect'),
            btnWsLeft: document.getElementById('btn-ws-left'),
            btnWsRight: document.getElementById('btn-ws-right'),
            btnAltTab: document.getElementById('btn-alt-tab'),
            btnSettingsBack: document.getElementById('btn-settings-back'),
            btnFullscreen: document.getElementById('btn-fullscreen'),
            // Tab bar
            bottomTabBar: document.getElementById('bottom-tab-bar'),
            tabArrowLeft: document.getElementById('tab-arrow-left'),
            tabArrowRight: document.getElementById('tab-arrow-right'),
            tabBtns: document.querySelectorAll('.tab-btn'),
        };

        this._init();
    }

    async _init() {
        this._bindEvents();
        this._applySettings();
        this._setupConnectionCallbacks();
        this._startStatsUpdate();

        // Check if we have a saved token
        window.connectionManager.loadSavedToken();

        // Check server status
        await this._checkServer();
    }

    _bindEvents() {
        // Auth buttons
        this.elements.btnSetup?.addEventListener('click', () => this._handleSetup());
        this.elements.btnLogin?.addEventListener('click', () => this._handleLogin());

        // Enter key on password fields
        this.elements.loginPassword?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this._handleLogin();
        });
        this.elements.setupPassword?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.elements.setupPasswordConfirm?.focus();
        });
        this.elements.setupPasswordConfirm?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this._handleSetup();
        });

        // Toolbar
        this.elements.btnDisconnect?.addEventListener('click', () => this._handleDisconnect());

        // Desktop shortcuts
        this.elements.btnWsLeft?.addEventListener('click', () => {
            window.connectionManager.sendInput({ type: 'key_combo', keys: ['super', 'pageup'] });
        });
        this.elements.btnWsRight?.addEventListener('click', () => {
            window.connectionManager.sendInput({ type: 'key_combo', keys: ['super', 'pagedown'] });
        });
        this.elements.btnAltTab?.addEventListener('click', () => {
            window.connectionManager.sendInput({ type: 'key_combo', keys: ['alt', 'tab'] });
        });

        // Tab bar navigation
        this.elements.tabArrowLeft?.addEventListener('click', () => this._navigateTab(-1));
        this.elements.tabArrowRight?.addEventListener('click', () => this._navigateTab(1));
        this.elements.tabBtns?.forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                if (tab) {
                    this.showScreen(tab);
                    if (tab === 'files') window.fileTransfer.loadDirectory('~');
                    if (tab === 'settings') this._loadSystemInfo();
                }
            });
        });

        // Settings sliders
        document.getElementById('setting-quality')?.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            document.getElementById('quality-label').textContent = val + '%';
            this.settings.quality = val;
            this._saveSettings();
            window.connectionManager.sendScreenControl({ type: 'set_quality', quality: val });
        });

        document.getElementById('setting-fps')?.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            document.getElementById('fps-label').textContent = val;
            this.settings.fps = val;
            this._saveSettings();
            window.connectionManager.sendScreenControl({ type: 'set_fps', fps: val });
        });

        document.getElementById('setting-sensitivity')?.addEventListener('input', (e) => {
            const val = parseInt(e.target.value) / 10;
            document.getElementById('sensitivity-label').textContent = val.toFixed(1) + 'x';
            this.settings.sensitivity = val;
            this._saveSettings();
            window.inputController.setSensitivity(val);
        });

        document.getElementById('setting-input-mode')?.addEventListener('change', (e) => {
            this.settings.inputMode = e.target.value;
            this._saveSettings();
            window.inputController.setMode(e.target.value);
        });

        document.getElementById('setting-monitor')?.addEventListener('change', (e) => {
            const val = parseInt(e.target.value);
            this.settings.monitor = val;
            this._saveSettings();
            window.connectionManager.sendScreenControl({ type: 'set_monitor', monitor: val });
        });
    }

    _setupConnectionCallbacks() {
        const cm = window.connectionManager;

        cm.onStateChange = (state) => {
            this._updateStatus(state);
        };

        cm.onScreenFrame = (frame) => {
            window.screenViewer.processFrame(frame);
        };

        cm.onError = (error) => {
            this.toast(error, 'error');
        };

        cm.onLatencyUpdate = (latency) => {
            if (this.elements.statLatency) {
                this.elements.statLatency.textContent = latency + ' ms';
            }
        };
    }

    // ── Server Check & Auth ─────────────────────────────────

    async _checkServer() {
        this._updateStatus('connecting');

        try {
            const status = await window.connectionManager.checkAuthStatus();

            if (status.error) {
                this._updateStatus('error', 'Server unreachable');
                return;
            }

            if (status.setup_required) {
                // First time — show setup form
                this.elements.setupForm?.classList.remove('hidden');
                this.elements.loginForm?.classList.add('hidden');
                this._updateStatus('disconnected', 'Setup required');
            } else if (status.authenticated) {
                // Already authenticated — connect
                this._updateStatus('connected', 'Authenticated');
                this._startDesktopSession();
            } else {
                // Need to login
                this.elements.setupForm?.classList.add('hidden');
                this.elements.loginForm?.classList.remove('hidden');
                this._updateStatus('disconnected', 'Login required');
            }
        } catch (e) {
            this._updateStatus('error', 'Cannot reach server');
        }
    }

    async _handleSetup() {
        const pass = this.elements.setupPassword?.value || '';
        const confirm = this.elements.setupPasswordConfirm?.value || '';

        if (pass.length < 4) {
            this._showError('setup', 'Password must be at least 4 characters');
            return;
        }
        if (pass !== confirm) {
            this._showError('setup', 'Passwords do not match');
            return;
        }

        this._clearErrors();
        this.elements.btnSetup.textContent = 'Setting up...';
        this.elements.btnSetup.disabled = true;

        const result = await window.connectionManager.setupPassword(pass);

        if (result.success) {
            this.toast('Password set! Connecting...', 'success');
            this._startDesktopSession();
        } else {
            this._showError('setup', result.error);
        }

        this.elements.btnSetup.textContent = 'Set Password & Connect';
        this.elements.btnSetup.disabled = false;
    }

    async _handleLogin() {
        const pass = this.elements.loginPassword?.value || '';

        if (!pass) {
            this._showError('login', 'Enter your password');
            return;
        }

        this._clearErrors();
        this.elements.btnLogin.textContent = 'Connecting...';
        this.elements.btnLogin.disabled = true;

        const result = await window.connectionManager.login(pass);

        if (result.success) {
            this.toast('Connected!', 'success');
            this._startDesktopSession();
        } else {
            this._showError('login', result.error);
        }

        this.elements.btnLogin.textContent = 'Connect';
        this.elements.btnLogin.disabled = false;
    }

    _startDesktopSession() {
        // Connect WebSockets — send full resolution for best quality
        window.connectionManager.connect({
            maxWidth: this.settings.maxWidth || 0,
            fps: this.settings.fps,
            quality: this.settings.quality,
        });

        // Apply saved settings
        window.inputController.setSensitivity(this.settings.sensitivity);
        window.inputController.setMode(this.settings.inputMode);

        // Show desktop screen
        this.showScreen('desktop');
    }

    _handleDisconnect() {
        window.connectionManager.disconnect();
        this.showScreen('connection');
        // Re-check server
        setTimeout(() => this._checkServer(), 500);
    }

    // ── Screen Management ───────────────────────────────────

    showScreen(name) {
        Object.entries(this.screens).forEach(([key, el]) => {
            if (el) {
                el.classList.toggle('active', key === name);
            }
        });
        this.currentScreen = name;

        // Show/hide bottom tab bar (only visible when connected)
        const showTabBar = this.tabOrder.includes(name);
        if (this.elements.bottomTabBar) {
            this.elements.bottomTabBar.classList.toggle('hidden', !showTabBar);
        }

        // Update active tab button
        this.elements.tabBtns?.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === name);
        });
    }

    _navigateTab(direction) {
        const currentIdx = this.tabOrder.indexOf(this.currentScreen);
        if (currentIdx === -1) return;

        let newIdx = currentIdx + direction;
        if (newIdx < 0) newIdx = this.tabOrder.length - 1;
        if (newIdx >= this.tabOrder.length) newIdx = 0;

        const newTab = this.tabOrder[newIdx];
        this.showScreen(newTab);
        if (newTab === 'files') window.fileTransfer.loadDirectory('~');
        if (newTab === 'settings') this._loadSystemInfo();
    }

    // ── Status Updates ──────────────────────────────────────

    _updateStatus(state, text) {
        const dot = this.elements.statusDot;
        const statusText = this.elements.statusText;

        if (dot) {
            dot.className = 'status-dot';
            if (state === 'connected') dot.classList.add('connected');
            else if (state === 'connecting') dot.classList.add('connecting');
            else if (state === 'error') dot.classList.add('error');
        }

        if (statusText && text) {
            statusText.textContent = text;
        } else if (statusText) {
            const labels = {
                connected: 'Connected',
                connecting: 'Connecting...',
                disconnected: 'Disconnected',
                error: 'Error',
            };
            statusText.textContent = labels[state] || state;
        }
    }

    _startStatsUpdate() {
        setInterval(() => {
            if (this.currentScreen !== 'desktop') return;

            if (this.elements.statFps) {
                this.elements.statFps.textContent = window.screenViewer.currentFps + ' FPS';
            }
            if (this.elements.statQuality) {
                this.elements.statQuality.textContent = (this.settings.quality || 60) + '% Q';
            }
        }, 1000);
    }

    // ── System Info ─────────────────────────────────────────

    async _loadSystemInfo() {
        try {
            const info = await window.connectionManager.apiGet('/api/system');
            const monitors = info.monitors || [];

            // Update monitor dropdown
            const select = document.getElementById('setting-monitor');
            if (select) {
                select.innerHTML = monitors.map(m =>
                    `<option value="${m.index}">${m.is_combined ? 'All Monitors' : `Monitor ${m.index}`} (${m.width}×${m.height})</option>`
                ).join('');
                select.value = this.settings.monitor || 0;
            }

            // Update info display
            if (this.elements.systemInfo) {
                this.elements.systemInfo.innerHTML = `
                    <p><strong>Hostname:</strong> ${info.hostname}</p>
                    <p><strong>OS:</strong> ${info.os}</p>
                    <p><strong>Desktop:</strong> ${info.desktop}</p>
                    <p><strong>Display:</strong> ${info.display_server}</p>
                    <p><strong>Monitors:</strong> ${monitors.length - 1} display(s)</p>
                    <p><strong>Uptime:</strong> ${info.uptime}</p>
                    <p><strong>Server:</strong> v${info.server_version}</p>
                `;
            }
        } catch (e) {
            if (this.elements.systemInfo) {
                this.elements.systemInfo.innerHTML = '<p>Failed to load system info</p>';
            }
        }
    }

    // ── Settings ────────────────────────────────────────────

    _loadSettings() {
        try {
            const saved = localStorage.getItem('dsk_settings');
            return saved ? JSON.parse(saved) : this._defaultSettings();
        } catch {
            return this._defaultSettings();
        }
    }

    _defaultSettings() {
        return {
            quality: 80,
            fps: 15,
            sensitivity: 1.0,
            inputMode: 'touchpad',
            monitor: 0,
            maxWidth: 0,
        };
    }

    _saveSettings() {
        localStorage.setItem('dsk_settings', JSON.stringify(this.settings));
    }

    _applySettings() {
        // Set slider values
        const q = document.getElementById('setting-quality');
        const f = document.getElementById('setting-fps');
        const s = document.getElementById('setting-sensitivity');
        const m = document.getElementById('setting-input-mode');

        if (q) { q.value = this.settings.quality; document.getElementById('quality-label').textContent = this.settings.quality + '%'; }
        if (f) { f.value = this.settings.fps; document.getElementById('fps-label').textContent = this.settings.fps; }
        if (s) { s.value = Math.round(this.settings.sensitivity * 10); document.getElementById('sensitivity-label').textContent = this.settings.sensitivity.toFixed(1) + 'x'; }
        if (m) { m.value = this.settings.inputMode; }
    }

    // ── Fullscreen ──────────────────────────────────────────

    _toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(() => {});
        } else {
            document.exitFullscreen().catch(() => {});
        }
    }

    // ── Toast Notifications ─────────────────────────────────

    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const icons = { success: '✓', error: '✗', info: 'ℹ', warning: '⚠' };
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${icons[type] || ''}</span> ${message}`;
        container.appendChild(toast);

        // Auto-remove
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, 3000);
    }

    // ── Error Display ───────────────────────────────────────

    _showError(form, message) {
        const el = form === 'setup' ? this.elements.setupError : this.elements.loginError;
        if (el) {
            el.textContent = message;
            el.classList.remove('hidden');
        }
    }

    _clearErrors() {
        this.elements.setupError?.classList.add('hidden');
        this.elements.loginError?.classList.add('hidden');
    }
}

// ── Initialize App ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});
