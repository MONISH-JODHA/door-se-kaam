/**
 * Door Se Kaam — Screen Viewer
 *
 * Renders MJPEG frames onto a canvas.
 * Zoom uses source-rect cropping — the image never moves on screen,
 * only the visible region changes (like a virtual camera).
 */

class ScreenViewer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.frameCount = 0;
        this.fps = 0;
        this.lastFpsTime = performance.now();
        this.lastFrameTime = 0;
        this._fpsFrames = 0;

        // Zoom: virtual camera
        this.scale = 1;
        this.minScale = 1;
        this.maxScale = 5;
        this.focalX = 0.5;
        this.focalY = 0.5;

        this._img = new Image();
        this._imgReady = true;
        this.remoteWidth = 0;
        this.remoteHeight = 0;
        this._drawRect = null;
        this._srcRect = null;

        this._img.onload = () => this._drawFrame();
    }

    processFrame(arrayBuffer) {
        if (!this._imgReady) return;
        this._imgReady = false;
        const blob = new Blob([arrayBuffer], { type: 'image/jpeg' });
        const url = URL.createObjectURL(blob);

        this._img.onload = () => {
            this._drawFrame();
            URL.revokeObjectURL(url);
            this._imgReady = true;
        };
        this._img.onerror = () => {
            URL.revokeObjectURL(url);
            this._imgReady = true;
        };
        this._img.src = url;

        this._fpsFrames++;
        const now = performance.now();
        if (now - this.lastFpsTime >= 1000) {
            this.fps = this._fpsFrames;
            this._fpsFrames = 0;
            this.lastFpsTime = now;
        }
        if (this.lastFrameTime > 0) {
            window.connectionManager.updateLatency(now - this.lastFrameTime);
        }
        this.lastFrameTime = now;
        this.frameCount++;
    }

    _drawFrame() {
        const img = this._img;
        if (!img.width || !img.height) return;

        this.remoteWidth = img.width;
        this.remoteHeight = img.height;

        const container = this.canvas.parentElement;
        this.canvas.width = container.clientWidth;
        this.canvas.height = container.clientHeight;

        const cw = this.canvas.width;
        const ch = this.canvas.height;

        // Source rect — what part of the image to show
        const srcW = img.width / this.scale;
        const srcH = img.height / this.scale;

        let srcX = this.focalX * img.width - srcW / 2;
        let srcY = this.focalY * img.height - srcH / 2;

        // Clamp to image bounds
        srcX = Math.max(0, Math.min(img.width - srcW, srcX));
        srcY = Math.max(0, Math.min(img.height - srcH, srcY));

        // Dest rect — always centered, aspect-fit
        const fitScale = Math.min(cw / srcW, ch / srcH);
        const drawW = srcW * fitScale;
        const drawH = srcH * fitScale;
        const drawX = (cw - drawW) / 2;
        const drawY = (ch - drawH) / 2;

        this.ctx.fillStyle = '#0a0a1a';
        this.ctx.fillRect(0, 0, cw, ch);
        this.ctx.drawImage(img,
            srcX, srcY, srcW, srcH,
            drawX, drawY, drawW, drawH
        );

        this._drawRect = { x: drawX, y: drawY, w: drawW, h: drawH };
        this._srcRect = { x: srcX, y: srcY, w: srcW, h: srcH };
    }

    canvasToRemote(canvasX, canvasY) {
        if (!this._drawRect || !this._srcRect || !this.remoteWidth) return null;
        const r = this._drawRect;
        const s = this._srcRect;
        const normX = (canvasX - r.x) / r.w;
        const normY = (canvasY - r.y) / r.h;
        if (normX < 0 || normX > 1 || normY < 0 || normY > 1) return null;
        return {
            x: Math.round(s.x + normX * s.w),
            y: Math.round(s.y + normY * s.h),
        };
    }

    zoom(factor, canvasX, canvasY) {
        const newScale = Math.max(this.minScale, Math.min(this.maxScale, this.scale * factor));
        if (newScale === this.scale) return;

        // Set focal point to pinch center
        if (this._drawRect && this._srcRect) {
            const r = this._drawRect;
            const s = this._srcRect;
            const normX = (canvasX - r.x) / r.w;
            const normY = (canvasY - r.y) / r.h;
            this.focalX = Math.max(0, Math.min(1, (s.x + normX * s.w) / this.remoteWidth));
            this.focalY = Math.max(0, Math.min(1, (s.y + normY * s.h) / this.remoteHeight));
        }
        this.scale = newScale;
    }

    pan(dx, dy) {
        if (this.scale <= 1 || !this._drawRect) return;
        const r = this._drawRect;
        const s = this._srcRect;
        this.focalX -= (dx / r.w) * (s.w / this.remoteWidth);
        this.focalY -= (dy / r.h) * (s.h / this.remoteHeight);
        this.focalX = Math.max(0, Math.min(1, this.focalX));
        this.focalY = Math.max(0, Math.min(1, this.focalY));
    }

    resetView() {
        this.scale = 1;
        this.focalX = 0.5;
        this.focalY = 0.5;
    }

    toggleFitMode() {
        this.scale > 1 ? this.resetView() : (this.scale = 2);
    }

    get currentFps() { return this.fps; }
}

window.screenViewer = new ScreenViewer('remote-screen');
