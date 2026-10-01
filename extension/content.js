// extension/content.js
/**
 * LiteSight In-Page Client Agent & Privacy Sentinel
 * Bridges client DOM, WebGPU on-device masking, in-place redaction preview & restore, and server reasoning.
 */

(function () {
    console.log("[LiteSight Extension] Content script loaded.");

    // ─────────────────────────────────────────────────────────────────────────────
    // SECTION 1: Verhoeff Mathematical Checksum & PII Engine
    // ─────────────────────────────────────────────────────────────────────────────

    /** Verhoeff tables for Aadhaar check-digit validation */
    const _V_D = [
        [0,1,2,3,4,5,6,7,8,9],
        [1,2,3,4,0,6,7,8,9,5],
        [2,3,4,0,1,7,8,9,5,6],
        [3,4,0,1,2,8,9,5,6,7],
        [4,0,1,2,3,9,5,6,7,8],
        [5,9,8,7,6,0,4,3,2,1],
        [6,5,9,8,7,1,0,4,3,2],
        [7,6,5,9,8,2,1,0,4,3],
        [8,7,6,5,9,3,2,1,0,4],
        [9,8,7,6,5,4,3,2,1,0]
    ];
    const _V_P = [
        [0,1,2,3,4,5,6,7,8,9],
        [1,5,7,6,2,8,3,0,9,4],
        [5,8,0,3,7,9,6,1,4,2],
        [8,9,1,6,0,4,3,5,2,7],
        [9,4,5,3,1,2,6,8,7,0],
        [4,2,8,6,5,7,3,9,0,1],
        [2,7,9,3,8,0,6,4,1,5],
        [7,0,4,6,9,1,3,2,5,8]
    ];

    function _verhoeffValid(numStr) {
        const clean = String(numStr).replace(/[\s-]/g, '');
        if (clean.length !== 12 || !/^\d{12}$/.test(clean)) return false;
        const digits = clean.split('').reverse().map(Number);
        let c = 0;
        for (let i = 0; i < digits.length; i++) {
            c = _V_D[c][_V_P[i % 8][digits[i]]];
        }
        return c === 0;
    }

    const PII_RULES = [
        {
            type: 'AADHAAR',
            regex: /\b(\d{4}[\s-]\d{4}[\s-]\d{4}|\d{12})\b/g,
            validate: (m) => _verhoeffValid(m.replace(/[\s-]/g, ''))
        },
        {
            type: 'PAN',
            regex: /\b[A-Z]{5}\d{4}[A-Z]\b/g,
            validate: null
        },
        {
            type: 'PHONE',
            regex: /\+91[\s-]?\d{5}[\s-]?\d{5}\b/g,
            validate: null
        },
        {
            type: 'EMAIL',
            regex: /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g,
            validate: null
        }
    ];

    let _piiMap = {};
    let _piiCounters = {};

    function _resetPiiState() {
        _piiMap = {};
        _piiCounters = {};
    }

    function _makePlaceholder(type) {
        _piiCounters[type] = (_piiCounters[type] || 0) + 1;
        return `[${type}_${_piiCounters[type]}]`;
    }

    function _maskForDisplay(text, type) {
        if (type === 'AADHAAR') {
            const digits = text.replace(/[\s-]/g, '');
            return '**** **** ' + digits.slice(8);
        }
        if (type === 'PAN') {
            return text.slice(0, 3) + '**' + text.slice(5, 9) + '*';
        }
        if (type === 'PHONE') {
            const digits = text.replace(/\D/g, '');
            return '+91 ' + digits.slice(2, 4) + '*** ***' + digits.slice(10, 12);
        }
        if (type === 'EMAIL') {
            const atIdx = text.indexOf('@');
            const local = text.slice(0, atIdx);
            const domain = text.slice(atIdx + 1);
            return local[0] + '*'.repeat(Math.max(1, local.length - 1)) + '@' + domain;
        }
        if (type === 'PASSWORD') {
            return '********';
        }
        return '***';
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // SECTION 2: In-Place Redaction Preview & Stack-Based Byte-Identical Restore
    // ─────────────────────────────────────────────────────────────────────────────

    let _previewActive = false;
    let _previewRestoreOps = [];

    function _injectRedactCss() {
        if (document.getElementById('ls-redact-css')) return;
        const style = document.createElement('style');
        style.id = 'ls-redact-css';
        style.textContent = `
            span.ls-redacted {
                display: inline;
                border: 2px solid #2563EB;
                border-radius: 6px;
                background: rgba(37,99,235,0.08);
                padding: 2px 6px;
                font-family: 'Courier New', Courier, monospace;
                font-size: inherit;
                box-sizing: border-box;
            }
            input.ls-redacted-input {
                outline: 2px solid #2563EB !important;
                outline-offset: 2px !important;
            }
        `;
        document.head.appendChild(style);
        _previewRestoreOps.push({ type: 'style', el: style });
    }

    function _wrapTextNodeMatch(textNode, original, masked) {
        const txt = textNode.textContent;
        const idx = txt.indexOf(original);
        if (idx === -1) return false;

        const parent = textNode.parentNode;
        if (!parent) return false;
        if (parent.classList && parent.classList.contains('ls-redacted')) return false;

        const before = txt.slice(0, idx);
        const after  = txt.slice(idx + original.length);

        _previewRestoreOps.push({
            type: 'text',
            originalNode: textNode,
            parent,
            nextSibling: textNode.nextSibling,
            originalText: txt
        });

        const beforeNode = document.createTextNode(before);
        const span = document.createElement('span');
        span.className = 'ls-redacted';
        span.textContent = masked;
        const afterNode = document.createTextNode(after);

        parent.insertBefore(beforeNode, textNode);
        parent.insertBefore(span, textNode);
        parent.insertBefore(afterNode, textNode);
        parent.removeChild(textNode);

        return true;
    }

    function previewRedaction() {
        if (_previewActive) restorePage();

        _resetPiiState();
        _previewRestoreOps = [];

        const bodyText = document.body.innerText;
        const seen = new Set();
        const findings = [];

        for (const rule of PII_RULES) {
            rule.regex.lastIndex = 0;
            let m;
            while ((m = rule.regex.exec(bodyText)) !== null) {
                const original = m[0];
                if (seen.has(original)) continue;
                if (rule.validate && !rule.validate(original)) continue;
                seen.add(original);
                const placeholder = _makePlaceholder(rule.type);
                _piiMap[placeholder] = original;
                const masked = _maskForDisplay(original, rule.type);
                findings.push({ type: rule.type, original, placeholder, masked });
            }
        }

        document.querySelectorAll('input[type="password"]').forEach(inp => {
            const placeholder = _makePlaceholder('PASSWORD');
            const original = inp.value || '(password field)';
            _piiMap[placeholder] = original;
            findings.push({ type: 'PASSWORD', original, placeholder, masked: '********' });
        });

        _injectRedactCss();

        const textNodes = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
                const p = node.parentElement;
                if (!p) return NodeFilter.FILTER_REJECT;
                const tag = p.tagName && p.tagName.toLowerCase();
                if (tag === 'script' || tag === 'style') return NodeFilter.FILTER_REJECT;
                if (p.id === '__ls_pii_badge__') return NodeFilter.FILTER_REJECT;
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        let n;
        while ((n = walker.nextNode())) textNodes.push(n);

        for (const textNode of textNodes) {
            if (!textNode.isConnected) continue;
            for (const f of findings) {
                if (f.type === 'PASSWORD') continue;
                if (textNode.textContent.includes(f.original)) {
                    _wrapTextNodeMatch(textNode, f.original, f.masked);
                    break;
                }
            }
        }

        document.querySelectorAll('input[type="password"]').forEach(inp => {
            const pwdFinding = findings.find(f => f.type === 'PASSWORD');
            if (!pwdFinding) return;
            _previewRestoreOps.push({
                type: 'input',
                el: inp,
                originalValue: inp.value,
                hadPlaceholder: inp.hasAttribute('placeholder'),
                originalPlaceholder: inp.getAttribute('placeholder') || ''
            });
            inp.value = '';
            inp.setAttribute('placeholder', '******** redacted');
            inp.classList.add('ls-redacted-input');
        });

        const badge = document.createElement('div');
        badge.id = '__ls_pii_badge__';
        const total = findings.length;
        badge.textContent = `\uD83D\uDD12 ${total} PII item${total !== 1 ? 's' : ''} redacted`;
        Object.assign(badge.style, {
            position: 'fixed', bottom: '20px', right: '20px',
            background: 'linear-gradient(135deg,#2563EB,#6366f1)',
            color: '#fff', fontFamily: 'system-ui,sans-serif',
            fontWeight: '700', fontSize: '13px',
            padding: '10px 18px', borderRadius: '99px',
            boxShadow: '0 4px 20px rgba(37,99,235,.35)',
            zIndex: '2147483647', letterSpacing: '.3px',
            pointerEvents: 'none'
        });
        document.body.appendChild(badge);
        _previewRestoreOps.push({ type: 'badge', el: badge });

        _previewActive = true;

        const counts = { ..._piiCounters };
        const original = findings.map(f => ({ field: f.type, value: f.original }));
        const sent     = findings.map(f => ({ field: f.type, value: f.placeholder }));
        return { counts, original, sent };
    }

    function restorePage() {
        for (let i = _previewRestoreOps.length - 1; i >= 0; i--) {
            const op = _previewRestoreOps[i];

            if (op.type === 'badge') {
                op.el.remove();
            } else if (op.type === 'style') {
                op.el.remove();
            } else if (op.type === 'input') {
                op.el.value = op.originalValue;
                op.el.classList.remove('ls-redacted-input');
                if (op.hadPlaceholder) {
                    op.el.setAttribute('placeholder', op.originalPlaceholder);
                } else {
                    op.el.removeAttribute('placeholder');
                }
            } else if (op.type === 'text') {
                const parent = op.parent;
                if (!parent || !parent.isConnected) continue;

                const spans = Array.from(parent.querySelectorAll(':scope > span.ls-redacted'));
                let matched = null;
                for (const sp of spans) {
                    const before = sp.previousSibling;
                    const after  = sp.nextSibling;
                    const beforeTxt = (before && before.nodeType === Node.TEXT_NODE) ? before.textContent : '';
                    const afterTxt  = (after  && after.nodeType  === Node.TEXT_NODE) ? after.textContent  : '';
                    if (op.originalText.startsWith(beforeTxt) && op.originalText.endsWith(afterTxt)) {
                        matched = sp;
                        break;
                    }
                }

                if (matched) {
                    const before = matched.previousSibling;
                    const after  = matched.nextSibling;
                    const restored = document.createTextNode(op.originalText);
                    parent.insertBefore(restored, matched);
                    parent.removeChild(matched);
                    if (before && before.nodeType === Node.TEXT_NODE) parent.removeChild(before);
                    if (after && after.nodeType === Node.TEXT_NODE) parent.removeChild(after);
                } else {
                    if (parent.childNodes.length <= 3) {
                        parent.textContent = op.originalText;
                    }
                }
            }
        }
        _previewRestoreOps = [];
        _previewActive = false;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // SECTION 3: DOM Observation & Engine Initialization
    // ─────────────────────────────────────────────────────────────────────────────

    let piiDetector = null;
    let canvasMasker = null;

    function loadSavedSettings() {
        if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
            try {
                chrome.storage.local.get(['litesight_privacy_settings'], (result) => {
                    if (result && result.litesight_privacy_settings && piiDetector) {
                        piiDetector.setConfig(result.litesight_privacy_settings);
                    }
                });
            } catch (_) {}
        }
    }

    function initEngines() {
        if (!piiDetector) {
            if (window.LiteSightPIIDetector) {
                piiDetector = window.LiteSightPIIDetector;
            } else if (window.liteSightPIIDetector) {
                piiDetector = new window.liteSightPIIDetector();
            }
            if (piiDetector) {
                piiDetector.init().then(() => {
                    console.log("[LiteSight Extension] WebGPU PII Detector active.");
                });
                loadSavedSettings();
            }
        }
        if (window.LiteSightCanvasMasker && !canvasMasker) {
            canvasMasker = window.LiteSightCanvasMasker;
        } else if (window.liteSightCanvasMasker && !canvasMasker) {
            canvasMasker = new window.liteSightCanvasMasker();
        }
    }
    initEngines();

    function findAssociatedLabel(el) {
        const tag = el.tagName.toLowerCase();
        if (!['input', 'select', 'textarea'].includes(tag)) return '';

        if (el.labels && el.labels.length > 0) {
            const txt = Array.from(el.labels).map(l => l.innerText || l.textContent || '').join(' ').trim();
            if (txt) return txt;
        }
        if (el.id) {
            try {
                const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (lbl && (lbl.innerText || lbl.textContent)) return (lbl.innerText || lbl.textContent).trim();
            } catch(e) {}
        }
        const parentLabel = el.closest('label');
        if (parentLabel) {
            const clone = parentLabel.cloneNode(true);
            clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
            const txt = (clone.innerText || clone.textContent || '').trim();
            if (txt) return txt;
        }
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

    const INTERACTIVE_SELECTOR = `
        a[href], button, input, select, textarea, [role="button"], [role="link"], 
        [role="checkbox"], [role="menuitem"], [role="tab"], [role="combobox"], 
        [role="searchbox"], [role="option"], summary, [onclick]
    `;

    function extractSanitizedDOM() {
        const rawElements = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR));
        const sanitizedElements = [];
        let index = 0;

        for (const el of rawElements) {
            const rect = el.getBoundingClientRect();
            const isVisible = rect.width > 0 && rect.height > 0 &&
                window.getComputedStyle(el).visibility !== 'hidden' &&
                window.getComputedStyle(el).display !== 'none';

            if (!isVisible) continue;

            el.setAttribute('data-litesight-index', index);
            el.setAttribute('data-ls-id', String(index));

            const tag = el.tagName.toLowerCase();
            let role = el.getAttribute('role') || tag;
            if (tag === 'select') role = 'combobox';
            else if (tag === 'input' && ['text', 'search', 'email', 'password'].includes(el.type)) role = 'textbox';

            const inputType = (el.getAttribute('type') || '').toLowerCase();

            const isSensitive = inputType === 'password' || 
                /card|cvv|ssn|pass|secret|token|aadhaar|pan/i.test(el.name || el.id || '');

            let explicit = (
                el.getAttribute('aria-label') || 
                el.getAttribute('title') || 
                el.getAttribute('placeholder') || 
                ''
            ).trim();

            const associated = findAssociatedLabel(el);
            const nameId = [el.name, el.id].filter(Boolean).join(' ');

            let label = '';
            if (tag === 'select') {
                const options = Array.from(el.options || []).map(o => o.text || o.value).join(' ');
                label = [associated, explicit, nameId, options].filter(Boolean).join(' ');
            } else if (tag === 'input' || tag === 'textarea') {
                label = [associated, explicit, nameId].filter(Boolean).join(' ');
                if (!label) label = el.value || el.type || '';
            } else {
                label = explicit || el.innerText || el.textContent || associated || nameId;
            }

            label = label.replace(/\s+/g, ' ').trim().substring(0, 100);
            let value = isSensitive ? "[REDACTED_PII]" : (el.value || "");

            const inViewport = (
                rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
                rect.bottom > 0 &&
                rect.left < (window.innerWidth || document.documentElement.clientWidth) &&
                rect.right > 0
            );

            sanitizedElements.push({
                index: index,
                id: index,
                tag: tag,
                role: role,
                type: inputType,
                label: label,
                value: value,
                is_sensitive: isSensitive,
                is_visible: true,
                in_viewport: inViewport,
                x: Math.round(rect.left + rect.width / 2),
                y: Math.round(rect.top + rect.height / 2),
                bounding_box: {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                },
                bbox: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)]
            });
            index++;
        }

        return sanitizedElements;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // SECTION 4: Action Execution
    // ─────────────────────────────────────────────────────────────────────────────

    async function executeAction(actionData) {
        if (!actionData) return { success: false, error: "Empty action" };

        let operation = (actionData.operation || actionData.action || '').toUpperCase();
        let targetIndex = actionData.target_index !== undefined ? actionData.target_index : actionData.target;
        let textValue = actionData.text_value !== undefined ? actionData.text_value : actionData.value;

        if (operation === 'SEARCH') operation = 'TYPE_AND_SUBMIT';
        if (operation === 'TYPE') operation = 'TYPE_TEXT';
        if (operation === 'SCROLL') operation = 'SCROLL_DOWN';

        console.log(`[LiteSight Extension] Executing ${operation} on target ${targetIndex}`);

        if (operation === "SCROLL_DOWN") {
            window.scrollBy({ top: 500, behavior: 'smooth' });
            await new Promise(r => setTimeout(r, 600));
            return { success: true, url: window.location.href };
        }
        if (operation === "SCROLL_UP") {
            window.scrollBy({ top: -500, behavior: 'smooth' });
            await new Promise(r => setTimeout(r, 600));
            return { success: true, url: window.location.href };
        }
        if (operation === "WAIT") {
            await new Promise(r => setTimeout(r, 800));
            return { success: true, url: window.location.href };
        }
        if (operation === "PRESS") {
            const keyName = textValue || 'Enter';
            const keyEvt = new KeyboardEvent('keydown', { key: keyName, code: keyName, bubbles: true });
            (document.activeElement || document.body).dispatchEvent(keyEvt);
            return { success: true, url: window.location.href };
        }

        let targetEl = null;
        if (targetIndex !== null && targetIndex !== undefined) {
            targetEl = document.querySelector(`[data-litesight-index="${CSS.escape(String(targetIndex))}"]`) ||
                       document.querySelector(`[data-ls-id="${CSS.escape(String(targetIndex))}"]`);
        }

        if (!targetEl && targetIndex !== null && targetIndex !== undefined) {
            const elements = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR))
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 &&
                        window.getComputedStyle(el).visibility !== 'hidden' &&
                        window.getComputedStyle(el).display !== 'none';
                });
            targetEl = elements[targetIndex];
        }

        if (!targetEl && !["WAIT", "SCROLL_DOWN", "SCROLL_UP", "PRESS", "DONE"].includes(operation)) {
            console.warn(`[LiteSight Extension] Target index ${targetIndex} not found.`);
            return { success: false, error: "Node not found", url: window.location.href };
        }

        if (targetEl) {
            const originalOutline = targetEl.style.outline;
            const originalBackground = targetEl.style.backgroundColor;
            targetEl.style.outline = "3px solid #22c55e";
            targetEl.style.backgroundColor = "rgba(34, 197, 94, 0.15)";
            targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await new Promise(r => setTimeout(r, 350));

            if (operation === "CLICK") {
                targetEl.focus();
                targetEl.click();
            } else if (operation === "SELECT") {
                targetEl.focus();
                const val = (textValue || "").trim().toLowerCase();
                let matched = false;
                if (targetEl.options && targetEl.options.length > 0) {
                    for (let i = 0; i < targetEl.options.length; i++) {
                        const opt = targetEl.options[i];
                        const oText = (opt.text || "").trim().toLowerCase();
                        const oVal = (opt.value || "").trim().toLowerCase();
                        if (oVal === val || oText === val || oText.includes(val) || (val.length > 2 && val.includes(oText))) {
                            targetEl.selectedIndex = i;
                            matched = true;
                            break;
                        }
                    }
                    if (!matched && targetEl.options.length > 0) {
                        targetEl.selectedIndex = 0;
                    }
                    targetEl.dispatchEvent(new Event('input', { bubbles: true }));
                    targetEl.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    targetEl.click();
                }
            } else if (operation === "TYPE_TEXT" || operation === "TYPE_AND_SUBMIT") {
                targetEl.focus();
                targetEl.value = textValue || "";
                targetEl.dispatchEvent(new Event('input', { bubbles: true }));
                targetEl.dispatchEvent(new Event('change', { bubbles: true }));

                if (operation === "TYPE_AND_SUBMIT") {
                    await new Promise(r => setTimeout(r, 200));
                    // 1. Dispatch full keyboard Enter cycle
                    ['keydown', 'keypress', 'keyup'].forEach(type => {
                        targetEl.dispatchEvent(new KeyboardEvent(type, {
                            key: 'Enter',
                            code: 'Enter',
                            keyCode: 13,
                            which: 13,
                            bubbles: true,
                            cancelable: true
                        }));
                    });

                    // 2. Locate and click associated submit button if present (Amazon #nav-search-submit-button, etc.)
                    const form = targetEl.closest('form');
                    const submitBtn = (form && form.querySelector('input[type="submit"], button[type="submit"], #nav-search-submit-button, [aria-label*="search" i], [title*="search" i]')) ||
                        document.querySelector('#nav-search-submit-button, input[type="submit"].nav-input');

                    if (submitBtn) {
                        try { submitBtn.click(); } catch (_) {}
                    } else if (form && typeof form.requestSubmit === 'function') {
                        try { form.requestSubmit(); } catch (_) {}
                    }
                }
            }

            setTimeout(() => {
                targetEl.style.outline = originalOutline;
                targetEl.style.backgroundColor = originalBackground;
            }, 800);
        }

        return { success: true, url: window.location.href };
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // SECTION 5: Universal Message Listener
    // ─────────────────────────────────────────────────────────────────────────────

    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        const actionType = request.action || request.type;

        // 1. Observe state
        if (actionType === "GET_PAGE_STATE" || actionType === "OBSERVE") {
            initEngines();
            if (piiDetector) {
                piiDetector.detect(document).then(boxes => {
                    const config = piiDetector.getConfig();
                    if (window.LiteSightInspector && typeof window.LiteSightInspector.renderVisualIndicators === 'function') {
                        window.LiteSightInspector.renderVisualIndicators(boxes, config);
                    }
                    const elements = extractSanitizedDOM();
                    const redactedCount = boxes.filter(b => b.status === "REDACTED").length;
                    const monitoredCount = boxes.filter(b => b.status === "MONITORED").length;
                    sendResponse({
                        url: window.location.href,
                        title: document.title,
                        elements: elements,
                        pii_count: boxes.length,
                        redacted_count: redactedCount,
                        monitored_count: monitoredCount,
                        pii_boxes: boxes,
                        config: config
                    });
                });
                return true;
            } else {
                sendResponse({
                    url: window.location.href,
                    title: document.title,
                    elements: extractSanitizedDOM(),
                    pii_count: 0,
                    redacted_count: 0,
                    monitored_count: 0,
                    pii_boxes: [],
                    config: {}
                });
            }
        }

        // 2. Action execution
        else if (actionType === "EXECUTE_ACTION") {
            const data = request.actionData || request.payload || request;
            executeAction(data).then(res => sendResponse(res));
            return true;
        }

        // 3. Redaction preview & byte-identical restore demo
        else if (actionType === "PREVIEW_REDACTION") {
            try {
                const res = previewRedaction();
                sendResponse(res);
            } catch (err) {
                console.error("[LiteSight Extension] PREVIEW_REDACTION failed:", err);
                sendResponse({ counts: {}, original: [], sent: [], error: String(err) });
            }
        } else if (actionType === "RESTORE_PAGE") {
            try {
                restorePage();
                sendResponse({ restored: true });
            } catch (err) {
                sendResponse({ restored: false, error: String(err) });
            }
        } else if (actionType === "PING") {
            sendResponse({ pong: true });
        }

        // 4. Settings & HUD toggles
        else if (actionType === "UPDATE_SETTINGS") {
            initEngines();
            if (piiDetector && request.config) {
                piiDetector.setConfig(request.config);
                piiDetector.detect(document).then(boxes => {
                    const config = piiDetector.getConfig();
                    if (window.LiteSightInspector && typeof window.LiteSightInspector.renderVisualIndicators === 'function') {
                        window.LiteSightInspector.renderVisualIndicators(boxes, config);
                    }
                    sendResponse({
                        success: true,
                        count: boxes.length,
                        monitored: boxes.filter(b => b.status === "MONITORED").length,
                        redacted: boxes.filter(b => b.status === "REDACTED").length,
                        config: config
                    });
                });
                return true;
            }
            sendResponse({ success: true });
        } else if (actionType === "GET_SETTINGS") {
            initEngines();
            sendResponse({ config: piiDetector ? piiDetector.getConfig() : null });
        } else if (actionType === "TOGGLE_INDICATORS") {
            if (window.LiteSightInspector) {
                window.LiteSightInspector.toggleVisualIndicators(request.enabled);
            }
            sendResponse({ success: true });
        } else if (actionType === "SHOW_HUD") {
            if (window.LiteSightInspector) {
                window.LiteSightInspector.mount();
            } else if (window.LiteSightInspectorOverlay) {
                window.LiteSightInspectorOverlay.init();
            }
            sendResponse({ success: true });
        }
    });

})();
