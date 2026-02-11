/**
 * Door Se Kaam — File Transfer
 *
 * File browser, upload, and download functionality.
 */

class FileTransfer {
    constructor() {
        this.currentPath = '~';
        this.fileList = document.getElementById('file-list');
        this.pathBar = document.getElementById('current-path');
        this.uploadInput = document.getElementById('file-upload-input');
        this.uploadBtn = document.getElementById('btn-upload');
        this.backBtn = document.getElementById('btn-files-back');

        this._bindEvents();
    }

    _bindEvents() {
        if (this.uploadBtn) {
            this.uploadBtn.addEventListener('click', () => this.uploadInput.click());
        }

        if (this.uploadInput) {
            this.uploadInput.addEventListener('change', (e) => this._handleUpload(e));
        }

        if (this.backBtn) {
            this.backBtn.addEventListener('click', () => {
                window.app.showScreen('desktop');
            });
        }
    }

    async loadDirectory(path = '~') {
        try {
            const data = await window.connectionManager.apiGet(
                `/api/files/list?path=${encodeURIComponent(path)}`
            );

            this.currentPath = data.path;
            if (this.pathBar) {
                this.pathBar.textContent = data.path;
            }

            this._renderFiles(data);
        } catch (e) {
            window.app.toast('Failed to load directory: ' + e.message, 'error');
        }
    }

    _renderFiles(data) {
        if (!this.fileList) return;

        let html = '';

        // Parent directory link
        if (data.parent) {
            html += `
                <div class="file-item" data-path="${this._escapeHtml(data.parent)}" data-isdir="true">
                    <span class="file-icon">📁</span>
                    <div class="file-info">
                        <div class="file-name">..</div>
                        <div class="file-meta">Parent directory</div>
                    </div>
                </div>
            `;
        }

        // Files & directories
        for (const item of data.items) {
            const icon = this._getIcon(item);
            const size = item.is_dir ? '' : this._formatSize(item.size);
            const modified = item.modified
                ? new Date(item.modified).toLocaleDateString()
                : '';
            const meta = [size, modified].filter(Boolean).join(' • ');

            html += `
                <div class="file-item" 
                     data-path="${this._escapeHtml(item.path)}" 
                     data-isdir="${item.is_dir}"
                     data-name="${this._escapeHtml(item.name)}">
                    <span class="file-icon">${icon}</span>
                    <div class="file-info">
                        <div class="file-name">${this._escapeHtml(item.name)}</div>
                        <div class="file-meta">${meta}</div>
                    </div>
                    ${!item.is_dir ? `
                        <button class="file-action download-btn" data-path="${this._escapeHtml(item.path)}" title="Download">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                            </svg>
                        </button>
                    ` : ''}
                </div>
            `;
        }

        if (data.items.length === 0) {
            html = '<div class="file-item"><span class="file-icon">📂</span><div class="file-info"><div class="file-name">Empty directory</div></div></div>';
        }

        this.fileList.innerHTML = html;

        // Bind click handlers
        this.fileList.querySelectorAll('.file-item').forEach(el => {
            el.addEventListener('click', (e) => {
                // Don't navigate if clicking download button
                if (e.target.closest('.download-btn')) return;

                const path = el.dataset.path;
                const isDir = el.dataset.isdir === 'true';
                if (isDir) {
                    this.loadDirectory(path);
                }
            });
        });

        this.fileList.querySelectorAll('.download-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this._downloadFile(btn.dataset.path);
            });
        });
    }

    async _downloadFile(path) {
        try {
            const url = `${window.connectionManager.baseUrl}/api/files/download?path=${encodeURIComponent(path)}`;
            const headers = {};
            if (window.connectionManager.token) {
                headers['Authorization'] = `Bearer ${window.connectionManager.token}`;
            }

            const res = await fetch(url, { headers });
            if (!res.ok) throw new Error('Download failed');

            const blob = await res.blob();
            const filename = path.split('/').pop();

            // Create download link
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(a.href);

            window.app.toast(`Downloaded: ${filename}`, 'success');
        } catch (e) {
            window.app.toast('Download failed: ' + e.message, 'error');
        }
    }

    async _handleUpload(e) {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        for (const file of files) {
            await this._uploadFile(file);
        }

        // Reset input
        this.uploadInput.value = '';

        // Reload current directory
        this.loadDirectory(this.currentPath);
    }

    async _uploadFile(file) {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const headers = {};
            if (window.connectionManager.token) {
                headers['Authorization'] = `Bearer ${window.connectionManager.token}`;
            }

            // Show progress toast
            window.app.toast(`Uploading: ${file.name}...`, 'info');

            const res = await fetch(`${window.connectionManager.baseUrl}/api/files/upload`, {
                method: 'POST',
                headers,
                body: formData,
            });

            if (!res.ok) {
                const error = await res.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await res.json();
            window.app.toast(`Uploaded: ${file.name}`, 'success');
            return result;
        } catch (e) {
            window.app.toast(`Upload failed: ${e.message}`, 'error');
        }
    }

    _getIcon(item) {
        if (item.is_dir) return '📁';
        if (item.error) return '🔒';

        const ext = (item.name.split('.').pop() || '').toLowerCase();
        const iconMap = {
            // Documents
            pdf: '📄', doc: '📝', docx: '📝', txt: '📃', md: '📋',
            xls: '📊', xlsx: '📊', csv: '📊',
            ppt: '📑', pptx: '📑',
            // Code
            py: '🐍', js: '📜', ts: '📜', html: '🌐', css: '🎨',
            json: '📋', xml: '📋', yaml: '📋', yml: '📋',
            sh: '⚡', bash: '⚡',
            java: '☕', c: '⚙️', cpp: '⚙️', h: '⚙️',
            go: '🔵', rs: '🦀', rb: '💎',
            // Images
            png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️',
            svg: '🖼️', webp: '🖼️', bmp: '🖼️', ico: '🖼️',
            // Media
            mp4: '🎬', mkv: '🎬', avi: '🎬', mov: '🎬', webm: '🎬',
            mp3: '🎵', wav: '🎵', flac: '🎵', ogg: '🎵', m4a: '🎵',
            // Archives
            zip: '📦', tar: '📦', gz: '📦', bz2: '📦', xz: '📦',
            rar: '📦', '7z': '📦',
            // Executables
            deb: '📥', rpm: '📥', appimage: '📥', exe: '📥',
            // Config
            conf: '⚙️', cfg: '⚙️', ini: '⚙️', env: '⚙️',
            // Database
            db: '🗃️', sqlite: '🗃️', sql: '🗃️',
        };

        return iconMap[ext] || '📄';
    }

    _formatSize(bytes) {
        if (bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

// Global instance
window.fileTransfer = new FileTransfer();
