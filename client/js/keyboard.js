/**
 * Door Se Kaam — Virtual Keyboard
 *
 * Integrates the system keyboard and provides a special keys bar
 * for modifier keys, function keys, and shortcuts.
 */

class VirtualKeyboard {
    constructor() {
        this.isVisible = false;
        this.hiddenInput = document.getElementById('hidden-keyboard-input');
        this.specialKeysBar = document.getElementById('special-keys-bar');
        this.keyboardBtn = document.getElementById('btn-keyboard');

        // Active modifiers
        this.activeModifiers = new Set();

        this._bindEvents();
    }

    _bindEvents() {
        // Toggle keyboard
        if (this.keyboardBtn) {
            this.keyboardBtn.addEventListener('click', () => this.toggle());
        }

        // Hidden input captures system keyboard
        if (this.hiddenInput) {
            this.hiddenInput.addEventListener('input', (e) => this._onInput(e));
            this.hiddenInput.addEventListener('keydown', (e) => this._onKeyDown(e));
        }

        // Special key buttons
        document.querySelectorAll('.skey').forEach(btn => {
            btn.addEventListener('click', (e) => this._onSpecialKey(e));
        });
    }

    toggle() {
        this.isVisible = !this.isVisible;

        if (this.isVisible) {
            this.show();
        } else {
            this.hide();
        }
    }

    show() {
        this.isVisible = true;
        this.hiddenInput.classList.add('visible');
        this.hiddenInput.focus();
        this.specialKeysBar.classList.remove('hidden');
        this.keyboardBtn.classList.add('active');
    }

    hide() {
        this.isVisible = false;
        this.hiddenInput.classList.remove('visible');
        this.hiddenInput.blur();
        this.specialKeysBar.classList.add('hidden');
        this.keyboardBtn.classList.remove('active');
        this.activeModifiers.clear();
        this._updateModifierUI();
    }

    _onInput(e) {
        const text = e.target.value;
        if (text) {
            // Get active modifiers
            const mods = Array.from(this.activeModifiers);

            if (mods.length > 0) {
                // Send each character with modifiers
                for (const char of text) {
                    window.connectionManager.sendInput({
                        type: 'key_press',
                        key: char,
                        modifiers: mods,
                    });
                }
                // Clear modifiers after use (non-sticky)
                this.activeModifiers.clear();
                this._updateModifierUI();
            } else {
                // Type text without modifiers
                window.connectionManager.sendInput({
                    type: 'type_text',
                    text: text,
                });
            }

            // Clear the input
            e.target.value = '';
        }
    }

    _onKeyDown(e) {
        // Handle special keys from system keyboard
        const specialKeys = [
            'Enter', 'Tab', 'Backspace', 'Delete', 'Escape',
            'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
            'Home', 'End', 'PageUp', 'PageDown',
        ];

        const keyMap = {
            'Enter': 'enter',
            'Tab': 'tab',
            'Backspace': 'backspace',
            'Delete': 'delete',
            'Escape': 'escape',
            'ArrowUp': 'up',
            'ArrowDown': 'down',
            'ArrowLeft': 'left',
            'ArrowRight': 'right',
            'Home': 'home',
            'End': 'end',
            'PageUp': 'pageup',
            'PageDown': 'pagedown',
        };

        if (specialKeys.includes(e.key)) {
            e.preventDefault();
            const mods = Array.from(this.activeModifiers);

            window.connectionManager.sendInput({
                type: 'key_press',
                key: keyMap[e.key] || e.key.toLowerCase(),
                modifiers: mods.length > 0 ? mods : undefined,
            });

            if (mods.length > 0) {
                this.activeModifiers.clear();
                this._updateModifierUI();
            }
        }
    }

    _onSpecialKey(e) {
        const btn = e.currentTarget;
        const key = btn.dataset.key;
        const modifier = btn.dataset.modifier;
        const combo = btn.dataset.combo;

        if (modifier) {
            // Toggle modifier
            if (this.activeModifiers.has(modifier)) {
                this.activeModifiers.delete(modifier);
            } else {
                this.activeModifiers.add(modifier);
            }
            this._updateModifierUI();
            return;
        }

        if (combo) {
            // Send key combination
            const keys = combo.split('+');
            window.connectionManager.sendInput({
                type: 'key_combo',
                keys: keys,
            });
            // Clear modifiers
            this.activeModifiers.clear();
            this._updateModifierUI();
            return;
        }

        if (key) {
            const mods = Array.from(this.activeModifiers);
            window.connectionManager.sendInput({
                type: 'key_press',
                key: key,
                modifiers: mods.length > 0 ? mods : undefined,
            });

            // Clear modifiers after use
            if (mods.length > 0) {
                this.activeModifiers.clear();
                this._updateModifierUI();
            }
        }
    }

    _updateModifierUI() {
        document.querySelectorAll('.mod-key').forEach(btn => {
            const mod = btn.dataset.modifier;
            if (this.activeModifiers.has(mod)) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }
}

// Global instance
window.virtualKeyboard = new VirtualKeyboard();
