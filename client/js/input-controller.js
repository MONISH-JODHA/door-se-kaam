/**
 * Door Se Kaam — Input Controller
 *
 * Maps touch gestures on the canvas to remote mouse/keyboard events.
 * Supports touchpad mode (relative) and direct touch mode (absolute).
 */

class InputController {
    constructor() {
        this.mode = 'touchpad'; // 'touchpad' or 'direct'
        this.sensitivity = 1.0;
        this.canvas = document.getElementById('remote-screen');
        this.cursorIndicator = document.getElementById('cursor-indicator');

        // Touch state
        this._touches = {};
        this._lastTouchPos = null;
        this._touchStartTime = 0;
        this._touchStartPos = null;
        this._isTapping = false;
        this._longPressTimer = null;
        this._isDragging = false;
        this._scrollActive = false;

        // Two-finger state
        this._twoFingerStart = null;
        this._pinchStartDist = 0;

        // Double-tap detection for zoom reset
        this._lastTapTime = 0;

        // Thresholds
        this.tapThreshold = 10;    // px movement to cancel tap
        this.tapTimeout = 200;     // ms for tap vs hold
        this.longPressTime = 500;  // ms for long press
        this.scrollMultiplier = 0.5;

        this._bindEvents();
    }

    _bindEvents() {
        // Touch events on the canvas
        this.canvas.addEventListener('touchstart', (e) => this._onTouchStart(e), { passive: false });
        this.canvas.addEventListener('touchmove', (e) => this._onTouchMove(e), { passive: false });
        this.canvas.addEventListener('touchend', (e) => this._onTouchEnd(e), { passive: false });
        this.canvas.addEventListener('touchcancel', (e) => this._onTouchEnd(e), { passive: false });

        // Also handle mouse events for desktop testing
        this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
        this.canvas.addEventListener('mouseup', (e) => this._onMouseUp(e));
        this.canvas.addEventListener('wheel', (e) => this._onWheel(e), { passive: false });
        this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    }

    // ── Touch Handlers ──────────────────────────────────────

    _onTouchStart(e) {
        e.preventDefault();
        const touches = e.touches;

        if (touches.length === 1) {
            const t = touches[0];
            this._lastTouchPos = { x: t.clientX, y: t.clientY };
            this._touchStartPos = { x: t.clientX, y: t.clientY };
            this._touchStartTime = Date.now();
            this._isTapping = true;
            this._scrollActive = false;

            // Start long press timer
            this._longPressTimer = setTimeout(() => {
                if (this._isTapping) {
                    // Long press → start drag
                    this._isDragging = true;
                    this._isTapping = false;
                    this._showCursorRipple();
                    window.connectionManager.sendInput({
                        type: 'mouse_down',
                        button: 'left',
                    });
                    this._vibrate(50);
                }
            }, this.longPressTime);

        } else if (touches.length === 2) {
            clearTimeout(this._longPressTimer);
            this._isTapping = false;

            const t1 = touches[0];
            const t2 = touches[1];
            this._twoFingerStart = {
                x: (t1.clientX + t2.clientX) / 2,
                y: (t1.clientY + t2.clientY) / 2,
            };
            this._pinchStartDist = this._getTouchDist(t1, t2);
            this._scrollActive = true;

        } else if (touches.length === 3) {
            // Three-finger tap → middle click
            window.connectionManager.sendInput({
                type: 'mouse_click',
                button: 'middle',
            });
            this._vibrate(30);
        }
    }

    _onTouchMove(e) {
        e.preventDefault();
        const touches = e.touches;

        if (touches.length === 1 && this._lastTouchPos) {
            const t = touches[0];
            const dx = t.clientX - this._lastTouchPos.x;
            const dy = t.clientY - this._lastTouchPos.y;

            // Check if moved beyond tap threshold
            if (this._isTapping) {
                const dist = Math.sqrt(
                    Math.pow(t.clientX - this._touchStartPos.x, 2) +
                    Math.pow(t.clientY - this._touchStartPos.y, 2)
                );
                if (dist > this.tapThreshold) {
                    this._isTapping = false;
                    clearTimeout(this._longPressTimer);
                }
            }

            if (!this._isTapping) {
                if (this.mode === 'touchpad') {
                    // Relative mouse movement
                    window.connectionManager.sendInput({
                        type: 'mouse_move',
                        x: Math.round(dx * this.sensitivity),
                        y: Math.round(dy * this.sensitivity),
                        relative: true,
                    });
                } else {
                    // Direct / absolute mode
                    const remote = window.screenViewer.canvasToRemote(t.clientX, t.clientY);
                    if (remote) {
                        window.connectionManager.sendInput({
                            type: 'mouse_move',
                            x: remote.x,
                            y: remote.y,
                            relative: false,
                        });
                    }
                }
            }

            this._lastTouchPos = { x: t.clientX, y: t.clientY };

        } else if (touches.length === 2) {
            const t1 = touches[0];
            const t2 = touches[1];
            const midX = (t1.clientX + t2.clientX) / 2;
            const midY = (t1.clientY + t2.clientY) / 2;
            const dist = this._getTouchDist(t1, t2);

            // Detect if this is a pinch gesture or a scroll gesture
            const distDelta = Math.abs(dist - this._pinchStartDist);
            const moveDelta = this._twoFingerStart ?
                Math.abs(midY - this._twoFingerStart.y) : 0;

            if (distDelta > 15) {
                // Pinch-to-zoom — zoom into the area under the fingers
                if (this._pinchStartDist > 0) {
                    const factor = dist / this._pinchStartDist;
                    window.screenViewer.zoom(factor, midX, midY);
                    this._pinchStartDist = dist;
                }
                this._scrollActive = false; // disable scroll during pinch
            } else if (this._scrollActive && this._twoFingerStart && moveDelta > 3) {
                // Two-finger scroll (no pinch detected)
                const dy = midY - this._twoFingerStart.y;
                const dx = midX - this._twoFingerStart.x;

                if (Math.abs(dy) > 3 || Math.abs(dx) > 3) {
                    window.connectionManager.sendInput({
                        type: 'mouse_scroll',
                        dx: Math.round(-dx * this.scrollMultiplier),
                        dy: Math.round(-dy * this.scrollMultiplier),
                    });
                    this._twoFingerStart = { x: midX, y: midY };
                }
            }
        }
    }

    _onTouchEnd(e) {
        e.preventDefault();
        clearTimeout(this._longPressTimer);

        if (this._isDragging) {
            window.connectionManager.sendInput({
                type: 'mouse_up',
                button: 'left',
            });
            this._isDragging = false;
            return;
        }

        const elapsed = Date.now() - this._touchStartTime;
        const remainingTouches = e.touches.length;

        if (this._isTapping && elapsed < this.tapTimeout && remainingTouches === 0) {
            // Was a two-finger tap? (check changedTouches)
            if (e.changedTouches.length === 2 || this._scrollActive) {
                // Two-finger tap → right click
                window.connectionManager.sendInput({
                    type: 'mouse_click',
                    button: 'right',
                });
            } else {
                // Single tap → left click
                if (this.mode === 'direct' && this._touchStartPos) {
                    const remote = window.screenViewer.canvasToRemote(
                        this._touchStartPos.x,
                        this._touchStartPos.y
                    );
                    if (remote) {
                        window.connectionManager.sendInput({
                            type: 'mouse_click',
                            button: 'left',
                            x: remote.x,
                            y: remote.y,
                        });
                    }
                } else {
                    window.connectionManager.sendInput({
                        type: 'mouse_click',
                        button: 'left',
                    });
                }
            }

            this._showCursorRipple();
            this._vibrate(20);

            // Double-tap to reset zoom
            const now = Date.now();
            if (now - this._lastTapTime < 300 && window.screenViewer.scale > 1) {
                window.screenViewer.resetView();
                this._lastTapTime = 0;
            } else {
                this._lastTapTime = now;
            }
        }

        this._isTapping = false;
        this._scrollActive = false;
        this._lastTouchPos = null;
        this._twoFingerStart = null;
    }

    // ── Mouse Handlers (desktop testing) ────────────────────

    _onMouseDown(e) {
        // Only in direct mode on desktop
        if (e.button === 2) {
            window.connectionManager.sendInput({
                type: 'mouse_click',
                button: 'right',
            });
        }
    }

    _onMouseMove(e) {
        // Only act when a button is held
        if (e.buttons === 0) return;

        if (this.mode === 'direct') {
            const remote = window.screenViewer.canvasToRemote(e.clientX, e.clientY);
            if (remote) {
                window.connectionManager.sendInput({
                    type: 'mouse_move',
                    x: remote.x,
                    y: remote.y,
                    relative: false,
                });
            }
        }
    }

    _onMouseUp(e) {
        // No-op for now; we handle clicks differently
    }

    _onWheel(e) {
        e.preventDefault();
        window.connectionManager.sendInput({
            type: 'mouse_scroll',
            dx: Math.round(-e.deltaX / 10),
            dy: Math.round(-e.deltaY / 10),
        });
    }

    // ── Helpers ──────────────────────────────────────────────

    _getTouchDist(t1, t2) {
        return Math.sqrt(
            Math.pow(t2.clientX - t1.clientX, 2) +
            Math.pow(t2.clientY - t1.clientY, 2)
        );
    }

    _showCursorRipple() {
        if (!this.cursorIndicator) return;
        const ripple = this.cursorIndicator.querySelector('.cursor-ripple');
        if (ripple) {
            ripple.classList.remove('active');
            // Force reflow to restart animation
            void ripple.offsetWidth;
            ripple.classList.add('active');
        }
    }

    _vibrate(ms) {
        if (navigator.vibrate) navigator.vibrate(ms);
    }

    setSensitivity(value) {
        this.sensitivity = value;
        // Also tell the server
        window.connectionManager.sendInput({
            type: 'set_sensitivity',
            value: value,
        });
    }

    setMode(mode) {
        this.mode = mode;
        const modeText = document.getElementById('mode-text');
        if (modeText) {
            modeText.textContent = mode === 'touchpad' ? 'Touchpad Mode' : 'Direct Touch Mode';
        }
    }
}

// Global instance
window.inputController = new InputController();
