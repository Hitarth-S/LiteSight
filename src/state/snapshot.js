// src/state/snapshot.js
/**
 * Fast-Path Indexed DOM State Snapshot Generator.
 * Adheres strictly to ARCHITECTURE.md Section 7.B.1 schema.
 * Extracts interactable DOM nodes with discrete integer indices.
 */

(function () {
    function isElementVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
            return false;
        }
        const rect = el.getBoundingClientRect();
        // Must have non-zero dimensions and not be positioned off-screen (e.g. left: -10000px screen-reader cloaks)
        return rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.left > -500;
    }

    function normalizeText(str) {
        if (!str) return '';
        return str
            .replace(/[★⭐]/g, ' star ')
            .replace(/&/g, ' and ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function findAssociatedLabel(el) {
        const tag = el.tagName.toLowerCase();
        if (!['input', 'select', 'textarea'].includes(tag)) return '';

        // 1. Native el.labels (when <label for="id"> is used)
        if (el.labels && el.labels.length > 0) {
            const txt = Array.from(el.labels).map(l => l.innerText || l.textContent || '').join(' ').trim();
            if (txt) return txt;
        }
        // 2. Query label[for="id"] directly
        if (el.id) {
            try {
                const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (lbl && (lbl.innerText || lbl.textContent)) return (lbl.innerText || lbl.textContent).trim();
            } catch(e) {}
        }
        // 3. Parent label wrapping element: <label>Username <input></label>
        const parentLabel = el.closest('label');
        if (parentLabel) {
            const clone = parentLabel.cloneNode(true);
            clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
            const txt = (clone.innerText || clone.textContent || '').trim();
            if (txt) return txt;
        }
        // 4. Sibling label in immediate wrapper container (form-group, field, div, tr, p)
        const container = el.closest('.form-group, .form-row, .field, .input-group, div, tr, p');
        if (container && container.tagName.toLowerCase() !== 'form' && container.tagName.toLowerCase() !== 'body') {
            const siblingLabel = container.querySelector('label');
            if (siblingLabel && (siblingLabel.innerText || siblingLabel.textContent)) {
                return (siblingLabel.innerText || siblingLabel.textContent).trim();
            }
            const prev = el.previousElementSibling;
            if (prev && ['span', 'label', 'div', 'p', 'b', 'strong', 'td', 'th'].includes(prev.tagName.toLowerCase())) {
                const txt = (prev.innerText || prev.textContent || '').trim();
                if (txt && txt.length < 50) return txt;
            }
        }
        return '';
    }

    function getElementLabel(el) {
        const tag = el.tagName.toLowerCase();
        let explicit = '';
        if (el.getAttribute('aria-label')) explicit = el.getAttribute('aria-label').trim();
        else if (el.getAttribute('placeholder')) explicit = el.getAttribute('placeholder').trim();
        else if (el.getAttribute('title')) explicit = el.getAttribute('title').trim();
        else if (el.getAttribute('alt')) explicit = el.getAttribute('alt').trim();

        const associated = findAssociatedLabel(el);
        const nameId = [el.name, el.id].filter(Boolean).join(' ');

        // For <select> dropdowns: combine associated label + name + selected/all options
        if (tag === 'select') {
            const options = Array.from(el.options || []).map(o => o.text || o.value).join(' ');
            const parts = [associated, explicit, nameId, options].filter(Boolean);
            return normalizeText(parts.join(' ')).substring(0, 100);
        }

        // For inputs & textareas: combine associated label + explicit/placeholder + name/id
        if (tag === 'input' || tag === 'textarea') {
            const parts = [associated, explicit, nameId].filter(Boolean);
            if (parts.length > 0) return normalizeText(parts.join(' ')).substring(0, 100);
            return normalizeText(el.value || el.type || '').substring(0, 100);
        }

        // For buttons, links, etc.
        let base = explicit || el.innerText || el.textContent || associated || nameId;
        return normalizeText(base).substring(0, 100);
    }

    function getElementRole(el) {
        const explicitRole = el.getAttribute('role');
        if (explicitRole) return explicitRole.toLowerCase();
        
        const tag = el.tagName.toLowerCase();
        if (tag === 'button' || (tag === 'input' && ['button', 'submit', 'reset'].includes(el.type))) return 'button';
        if (tag === 'a' && el.href) return 'link';
        if (tag === 'input') {
            if (['checkbox', 'radio'].includes(el.type)) return el.type;
            return 'textbox';
        }
        if (tag === 'summary') return 'button';
        if (tag === 'textarea') return 'textbox';
        if (tag === 'select') return 'combobox';
        if (tag === 'canvas') return 'canvas';
        if (tag === 'iframe') return 'iframe';
        return tag;
    }

    function generateDOMSnapshot(root = document) {
        const interactiveSelector = [
            'button',
            'a[href]',
            'input',
            'textarea',
            'select',
            'summary',
            '[role="button"]',
            '[role="link"]',
            '[role="textbox"]',
            '[role="combobox"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[role="tab"]',
            '[role="option"]',
            '[role="menuitem"]',
            '[tabindex]:not([tabindex="-1"])',
            '[onclick]',
            'canvas',
            'iframe'
        ].join(', ');

        const allNodes = Array.from(root.querySelectorAll(interactiveSelector));
        const elements = [];
        let currentIndex = 1;

        for (const el of allNodes) {
            const rect = el.getBoundingClientRect();
            const visible = isElementVisible(el);
            const tag = el.tagName.toLowerCase();
            const role = getElementRole(el);
            const label = getElementLabel(el);
            // Redact password fields to prevent plaintext PII leakage
            let val;
            if (el.type === 'password') {
                val = '[REDACTED]';
            } else {
                val = el.value !== undefined ? String(el.value).substring(0, 100) : (el.innerText || '').substring(0, 100);
            }

            // Bounding box strictly conforming to schema
            const bounding_box = {
                x: Math.round(rect.x + window.scrollX),
                y: Math.round(rect.y + window.scrollY),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            };

            // Store internal reference for fast execution
            el.setAttribute('data-litesight-index', currentIndex);

            elements.push({
                index: currentIndex,
                tag: tag,
                role: role,
                label: label,
                value: val,
                is_visible: visible,
                bounding_box: bounding_box
            });

            currentIndex++;
        }

        return {
            timestamp: Date.now(),
            url: window.location.href,
            elements: elements
        };
    }

    // Expose globally for evaluate calls
    window.generateLiteSightSnapshot = generateDOMSnapshot;

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { generateDOMSnapshot };
    }
})();
