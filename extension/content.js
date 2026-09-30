// extension/content.js
/**
 * LiteSight In-Page Client Agent & Privacy Sentinel
 * Bridges client DOM, WebGPU on-device masking, and server reasoning.
 */

(function () {
    console.log("[LiteSight Extension] Content script loaded.");

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

    // Initialize detectors when ready
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

    /**
     * Resolves labels for input and select elements from associated markup.
     */
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

    /**
     * Extracts non-sensitive indexed interactive DOM elements.
     * Sensitive input values (passwords, credit cards) are redacted locally.
     */
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

            const tag = el.tagName.toLowerCase();
            let role = el.getAttribute('role') || tag;
            if (tag === 'select') role = 'combobox';
            else if (tag === 'input' && ['text', 'search', 'email', 'password'].includes(el.type)) role = 'textbox';

            const inputType = (el.getAttribute('type') || '').toLowerCase();

            // Local PII Redaction for DOM values
            const isSensitive = inputType === 'password' || 
                /card|cvv|ssn|pass|secret|token/i.test(el.name || el.id || '');

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

            sanitizedElements.push({
                index: index++,
                tag: tag,
                role: role,
                label: label,
                value: value,
                is_sensitive: isSensitive,
                bounding_box: {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                }
            });
        }

        return sanitizedElements;
    }

    /**
     * Executes a received action safely within page context.
     */
    async function executeAction(action) {
        const { operation, target_index, text_value } = action;
        console.log(`[LiteSight Extension] Executing ${operation} on target ${target_index}`);

        if (operation === "SCROLL_DOWN") {
            window.scrollBy({ top: 500, behavior: 'smooth' });
            await new Promise(r => setTimeout(r, 600));
            return { success: true };
        }
        if (operation === "SCROLL_UP") {
            window.scrollBy({ top: -500, behavior: 'smooth' });
            await new Promise(r => setTimeout(r, 600));
            return { success: true };
        }
        if (operation === "WAIT") {
            await new Promise(r => setTimeout(r, 800));
            return { success: true };
        }

        let targetEl = document.querySelector(`[data-litesight-index="${CSS.escape(String(target_index))}"]`);
        if (!targetEl) {
            const elements = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR))
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 &&
                        window.getComputedStyle(el).visibility !== 'hidden' &&
                        window.getComputedStyle(el).display !== 'none';
                });
            targetEl = elements[target_index];
        }

        if (!targetEl) {
            console.warn(`[LiteSight Extension] Target index ${target_index} not found.`);
            return { success: false, error: "Node not found" };
        }

        // Visual Execution Highlight
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
            const val = (text_value || "").trim().toLowerCase();
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
            targetEl.value = text_value || "";
            targetEl.dispatchEvent(new Event('input', { bubbles: true }));
            targetEl.dispatchEvent(new Event('change', { bubbles: true }));

            if (operation === "TYPE_AND_SUBMIT") {
                await new Promise(r => setTimeout(r, 200));
                const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
                targetEl.dispatchEvent(enterEvent);
                const form = targetEl.closest('form');
                if (form && typeof form.requestSubmit === 'function') {
                    try { form.requestSubmit(); } catch (_) {}
                }
            }
        }

        setTimeout(() => {
            targetEl.style.outline = originalOutline;
            targetEl.style.backgroundColor = originalBackground;
        }, 800);

        return { success: true };
    }

    // Listen for extension messages
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "GET_PAGE_STATE") {
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
                return true; // async
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
        } else if (request.action === "UPDATE_SETTINGS") {
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
        } else if (request.action === "GET_SETTINGS") {
            initEngines();
            sendResponse({
                config: piiDetector ? piiDetector.getConfig() : null
            });
        } else if (request.action === "TOGGLE_INDICATORS") {
            if (window.LiteSightInspector) {
                window.LiteSightInspector.toggleVisualIndicators(request.enabled);
            }
            sendResponse({ success: true });
        } else if (request.action === "EXECUTE_ACTION") {
            executeAction(request.payload).then(res => sendResponse(res));
            return true;
        } else if (request.action === "SHOW_HUD") {
            if (window.LiteSightInspector) {
                window.LiteSightInspector.mount();
            } else if (window.LiteSightInspectorOverlay) {
                window.LiteSightInspectorOverlay.init();
            }
            sendResponse({ success: true });
        }
    });

})();
