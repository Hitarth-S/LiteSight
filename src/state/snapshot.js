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
        return rect.width > 0 && rect.height > 0 &&
               rect.bottom >= 0 && rect.right >= 0 &&
               rect.top <= (window.innerHeight || document.documentElement.clientHeight) &&
               rect.left <= (window.innerWidth || document.documentElement.clientWidth);
    }

    function getElementLabel(el) {
        // Check aria-label, aria-labelledby, placeholder, title, alt, textContent
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
        if (el.getAttribute('placeholder')) return el.getAttribute('placeholder').trim();
        if (el.getAttribute('title')) return el.getAttribute('title').trim();
        if (el.getAttribute('alt')) return el.getAttribute('alt').trim();
        if (el.labels && el.labels.length > 0) {
            return Array.from(el.labels).map(l => l.innerText.trim()).join(' ');
        }
        
        // For buttons/links/headings, get immediate text
        const text = el.innerText || el.textContent || '';
        return text.trim().substring(0, 100);
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
            '[role="button"]',
            '[role="link"]',
            '[role="textbox"]',
            '[role="combobox"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[tabindex]:not([tabindex="-1"])',
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
            const val = el.value !== undefined ? String(el.value).substring(0, 100) : (el.innerText || '').substring(0, 100);

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

        const snapshot = {
            timestamp: Date.now(),
            url: window.location.href,
            elements: elements
        };

        return snapshot;
    }

    // Expose globally for evaluate calls
    window.generateLiteSightSnapshot = generateDOMSnapshot;

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { generateDOMSnapshot };
    }
})();
