// content.js - LiteSight DOM Observer and Executor

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 1: PII Redaction Engine
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
    const digits = numStr.split('').reverse().map(Number);
    let c = 0;
    for (let i = 0; i < digits.length; i++) {
        c = _V_D[c][_V_P[i % 8][digits[i]]];
    }
    return c === 0;
}

/**
 * PII detection rules.
 * Each rule: { type, regex, validate? }
 * validate(match) → bool (extra check after regex, e.g. Verhoeff)
 */
const PII_RULES = [
    {
        type: 'AADHAAR',
        // 12-digit Aadhaar: groups of 4 separated by spaces or hyphens
        regex: /\b(\d{4}[\s-]\d{4}[\s-]\d{4}|\d{12})\b/g,
        validate: (m) => _verhoeffValid(m.replace(/[\s-]/g, ''))
    },
    {
        type: 'PAN',
        // Indian PAN: ABCDE1234F (5 letters, 4 digits, 1 letter)
        regex: /\b[A-Z]{5}\d{4}[A-Z]\b/g,
        validate: null
    },
    {
        type: 'PHONE',
        // Indian mobile: +91 followed by 10 digits (with optional spaces)
        regex: /\+91[\s-]?\d{5}[\s-]?\d{5}\b/g,
        validate: null
    },
    {
        type: 'EMAIL',
        regex: /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g,
        validate: null
    }
];

// In-memory placeholder → original map (never sent to background/server)
let _piiMap = {};
let _piiCounters = {};

function _resetPiiState() {
    _piiMap = {};
    _piiCounters = {};
}

function _makePlaceholder(type) {
    _piiCounters[type] = (_piiCounters[type] || 0) + 1;
    const key = `[${type}_${_piiCounters[type]}]`;
    return key;
}

/**
 * Redact a single string value.
 * Returns { redacted: string, hits: [{type, placeholder, original}] }
 */
function _redactString(raw) {
    if (typeof raw !== 'string' || raw === '') return { redacted: raw, hits: [] };
    let result = raw;
    const hits = [];

    for (const rule of PII_RULES) {
        rule.regex.lastIndex = 0; // reset stateful regex
        result = result.replace(rule.regex, (match) => {
            if (rule.validate && !rule.validate(match)) return match; // failed extra check
            const placeholder = _makePlaceholder(rule.type);
            _piiMap[placeholder] = match;
            hits.push({ type: rule.type, placeholder, original: match });
            return placeholder;
        });
    }
    return { redacted: result, hits };
}

/**
 * Redact password-type inputs by replacing their value with a placeholder.
 * Returns { redacted: string, hit } or null if not a password field.
 */
function _redactPasswordField(candidate) {
    if (candidate.type !== 'password') return null;
    const original = candidate.label || candidate.placeholder || '(password)';
    const placeholder = _makePlaceholder('PASSWORD');
    _piiMap[placeholder] = original;
    return { placeholder, original };
}

/**
 * Public redact() — called by collectCandidates().
 * Returns { elements: [...], counts: {AADHAAR, PAN, PHONE, EMAIL, PASSWORD} }
 * Fail-closed: on any exception returns { elements: [], counts: {} }
 */
function redact(elements) {
    try {
        _resetPiiState();
        const redacted = elements.map(el => {
            // Password fields
            const pwdResult = _redactPasswordField(el);
            if (pwdResult) {
                return { ...el, label: pwdResult.placeholder, placeholder: pwdResult.placeholder };
            }

            // Text fields: redact label, name, aria_label, placeholder
            const fieldsToRedact = ['label', 'name', 'aria_label', 'placeholder'];
            const copy = { ...el };
            for (const field of fieldsToRedact) {
                if (copy[field]) {
                    const { redacted: r } = _redactString(copy[field]);
                    copy[field] = r;
                }
            }
            return copy;
        });

        const counts = {};
        for (const [k, v] of Object.entries(_piiCounters)) {
            counts[k] = v;
        }

        return { elements: redacted, counts };
    } catch (err) {
        console.error('[LiteSight] redact() failed:', err);
        return { elements: [], counts: {} };
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 2: Demo Preview — in-place page masking (never during agent run)
// ─────────────────────────────────────────────────────────────────────────────

let _previewActive = false;

/**
 * Each restore op is one of:
 *   { type:'text',  node, parentNode, nextSibling, originalText }  — text node replaced by span
 *   { type:'input', el, originalValue, hadPlaceholder, originalPlaceholder } — password input
 *   { type:'badge', el }  — floating badge
 *   { type:'style', el }  — injected <style> tag
 */
let _previewRestoreOps = [];

/** Return an asterisk-based masked display string */
function _maskForDisplay(text, type) {
    if (type === 'AADHAAR') {
        const digits = text.replace(/[\s-]/g, '');
        // **** **** 0124
        return '**** **** ' + digits.slice(8);
    }
    if (type === 'PAN') {
        // ABC**1234*
        return text.slice(0, 3) + '**' + text.slice(5, 9) + '*';
    }
    if (type === 'PHONE') {
        // +91 98*** ***10 — strip spaces/hyphens, always produce fixed format
        const digits = text.replace(/\D/g, ''); // e.g. "919876543210"
        // digits[0..1] = "91", [2..3] = first 2 of mobile, [4..8] = middle 5, [9..11] = last 2
        return '+91 ' + digits.slice(2, 4) + '*** ***' + digits.slice(10, 12);
    }
    if (type === 'EMAIL') {
        const atIdx = text.indexOf('@');
        const local = text.slice(0, atIdx);
        const domain = text.slice(atIdx + 1);
        // t*********@example.com  (mask all local chars after first)
        return local[0] + '*'.repeat(local.length - 1) + '@' + domain;
    }
    return '***';
}

/** Inject the blue-highlight CSS into the page once */
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
            /* No layout shift: box-sizing compensates for padding */
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

/**
 * Replace a text node that contains `original` with:
 *   [leading-text-node] <span class="ls-redacted">masked</span> [trailing-text-node]
 * Records restore op so we can put the original text node back exactly.
 */
function _wrapTextNodeMatch(textNode, original, masked) {
    const txt = textNode.textContent;
    const idx = txt.indexOf(original);
    if (idx === -1) return false;

    const parent = textNode.parentNode;
    if (!parent) return false;
    // Skip if parent is our own span (avoid double-wrapping)
    if (parent.classList && parent.classList.contains('ls-redacted')) return false;

    const before = txt.slice(0, idx);
    const after  = txt.slice(idx + original.length);

    // Record restore info: we will remove [beforeNode, span, afterNode] and put textNode back
    _previewRestoreOps.push({
        type: 'text',
        originalNode: textNode,
        parent,
        nextSibling: textNode.nextSibling,
        originalText: txt
    });

    // Build replacement nodes
    const beforeNode = document.createTextNode(before);
    const span = document.createElement('span');
    span.className = 'ls-redacted';
    span.textContent = masked; // textContent only — never innerHTML with page text
    const afterNode = document.createTextNode(after);

    parent.insertBefore(beforeNode, textNode);
    parent.insertBefore(span, textNode);
    parent.insertBefore(afterNode, textNode);
    parent.removeChild(textNode);

    return true;
}

/**
 * PREVIEW_REDACTION handler.
 * Scans the page for PII, wraps matched text in blue-bordered spans,
 * applies blue outline to password inputs, injects CSS, adds floating badge.
 * Returns { counts, original, sent }.
 */
function previewRedaction() {
    if (_previewActive) restorePage();

    _resetPiiState();
    _previewRestoreOps = [];

    // ── 1. Collect all PII findings from visible text ──
    const bodyText = document.body.innerText;
    const seen = new Set();
    const findings = []; // { type, original, placeholder, masked }

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

    // Password inputs
    document.querySelectorAll('input[type="password"]').forEach(inp => {
        const placeholder = _makePlaceholder('PASSWORD');
        const original = inp.value || '(password field)';
        _piiMap[placeholder] = original;
        findings.push({ type: 'PASSWORD', original, placeholder, masked: '********' });
    });

    // ── 2. Inject CSS ──
    _injectRedactCss();

    // ── 3. Walk text nodes and wrap PII matches in spans ──
    // We must collect nodes first (TreeWalker is live — DOM changes during walk break it)
    const textNodes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            // Skip nodes inside script/style/our own badge
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
        // A node may have been moved out of the DOM already if a previous finding
        // split its parent — skip detached nodes.
        if (!textNode.isConnected) continue;
        for (const f of findings) {
            if (f.type === 'PASSWORD') continue;
            if (textNode.textContent.includes(f.original)) {
                _wrapTextNodeMatch(textNode, f.original, f.masked);
                break; // each text node handles one finding per pass
            }
        }
    }

    // ── 4. Password inputs — blue outline + show "redacted" chip via placeholder ──
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

    // ── 5. Floating badge ──
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

    // ── 6. Return payload ──
    const counts = { ..._piiCounters };
    const original = findings.map(f => ({ field: f.type, value: f.original }));
    const sent     = findings.map(f => ({ field: f.type, value: f.placeholder }));
    return { counts, original, sent };
}

/**
 * RESTORE_PAGE — removes all wrappers, style tag, outlines and badge,
 * restoring the exact original text content.
 */
function restorePage() {
    // Process in reverse so inner ops don't conflict with outer ones
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
            // Reconstruct the original text node and remove the [before, span, after] trio.
            // The trio was inserted before op.nextSibling; find them by walking from
            // op.parent's children.
            const parent = op.parent;
            if (!parent || !parent.isConnected) continue;

            // Find the three nodes we inserted: beforeText + span.ls-redacted + afterText
            // They sit consecutively where the original textNode was.
            // The safest approach: collect the span we inserted (which has our class),
            // then grab its previousSibling (before) and nextSibling (after).
            const spans = Array.from(parent.querySelectorAll(':scope > span.ls-redacted'));
            // Use the originalText to identify the right span
            let matched = null;
            for (const sp of spans) {
                // Check that its surrounding text nodes reconstruct op.originalText
                const before = sp.previousSibling;
                const after  = sp.nextSibling;
                const reconstructed =
                    (before && before.nodeType === Node.TEXT_NODE ? before.textContent : '') +
                    op.originalText.slice(
                        (before && before.nodeType === Node.TEXT_NODE ? before.textContent.length : 0),
                        op.originalText.length - (after && after.nodeType === Node.TEXT_NODE ? after.textContent.length : 0)
                    );
                // simpler: just check the concat of before + span.textContent contains part of originalText
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
                if (before && before.nodeType === Node.TEXT_NODE && before.textContent === '') {
                    parent.removeChild(before);
                } else if (before && before.nodeType === Node.TEXT_NODE) {
                    parent.removeChild(before);
                }
                if (after && after.nodeType === Node.TEXT_NODE) {
                    parent.removeChild(after);
                }
            } else {
                // Fallback: just set innerText of parent — only if no other children
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
// SECTION 3: Original agent helpers (unchanged)
// ─────────────────────────────────────────────────────────────────────────────

function collectCandidates() {
    const selector = 'a, button, input, textarea, select, [role="button"], [role="link"]';
    const candidates = [];
    let index = 0;

    function scan(root) {
        if (!root) return;
        const nodes = root.querySelectorAll(selector);
        nodes.forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.width < 4 || rect.height < 4) return;

            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

            el.setAttribute('data-ls-id', String(index));

            const innerText = (el.innerText || el.textContent || '').trim();
            const ariaLabel = (el.getAttribute('aria-label') || '').trim();
            const placeholder = (el.getAttribute('placeholder') || '').trim();
            const title = (el.getAttribute('title') || '').trim();
            const alt = (el.getAttribute('alt') || '').trim();
            const name = (el.getAttribute('name') || '').trim();
            const rawId = (el.id || '').trim();
            const href = (el.getAttribute('href') || '').trim();

            const label = (innerText || ariaLabel || placeholder || title || alt || name || rawId).slice(0, 80);

            candidates.push({
                id: index,
                tag: el.tagName.toLowerCase(),
                type: (el.getAttribute('type') || '').toLowerCase(),
                label: label,
                x: Math.round(rect.left + rect.width / 2),
                y: Math.round(rect.top + rect.height / 2),
                bbox: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)],
                name: name,
                aria_label: ariaLabel,
                placeholder: placeholder,
                raw_id: rawId,
                href: href
            });
            index++;
        });

        const allElements = root.querySelectorAll('*');
        allElements.forEach(el => {
            if (el.shadowRoot) {
                scan(el.shadowRoot);
            }
        });
    }

    scan(document);
    // Use updated redact() — returns {elements, counts}; caller receives full result
    const result = redact(candidates);
    return result.elements !== undefined ? result.elements : result;
}

async function executeAction(actionData) {
    const { action, target, value } = actionData;
    let targetEl = null;
    if (target !== null && target !== undefined) {
        targetEl = document.querySelector(`[data-ls-id="${target}"]`);
    }

    if (action === 'click' || action === 'search') {
        if (targetEl) {
            targetEl.focus();
            targetEl.click();
        }
        if (action === 'search' && value) {
            if (targetEl) {
                targetEl.value = value;
                targetEl.dispatchEvent(new Event('input', { bubbles: true }));
                targetEl.dispatchEvent(new Event('change', { bubbles: true }));
            }
            const enterEvt = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true });
            (targetEl || document.activeElement).dispatchEvent(enterEvt);
        }
    } else if (action === 'type') {
        if (targetEl) {
            targetEl.focus();
            targetEl.value = value || '';
            targetEl.dispatchEvent(new Event('input', { bubbles: true }));
            targetEl.dispatchEvent(new Event('change', { bubbles: true }));
        }
    } else if (action === 'press') {
        const keyName = value || 'Enter';
        const keyEvt = new KeyboardEvent('keydown', { key: keyName, code: keyName, bubbles: true });
        (document.activeElement || document.body).dispatchEvent(keyEvt);
    } else if (action === 'scroll') {
        window.scrollBy(0, 500);
    }

    await new Promise(r => setTimeout(r, 1000));
    return { success: true, url: window.location.href };
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION 4: Message listener (agent + demo messages)
// ─────────────────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'OBSERVE') {
        const elements = collectCandidates();
        sendResponse({ elements: elements, url: window.location.href });

    } else if (msg.type === 'EXECUTE_ACTION') {
        executeAction(msg.actionData).then(res => sendResponse(res));
        return true; // async response

    } else if (msg.type === 'PREVIEW_REDACTION') {
        // Demo only — must not be called during an agent run
        try {
            const result = previewRedaction();
            sendResponse(result);
        } catch (err) {
            console.error('[LiteSight] PREVIEW_REDACTION error:', err);
            sendResponse({ counts: {}, original: [], sent: [], error: String(err) });
        }

    } else if (msg.type === 'RESTORE_PAGE') {
        restorePage();
        sendResponse({ restored: true });

    } else if (msg.type === 'PING') {
        sendResponse({ pong: true });

    } else if (msg.type === 'CLEAR_IDS') {
        document.querySelectorAll('[data-ls-id]').forEach(el => el.removeAttribute('data-ls-id'));
        sendResponse({ cleared: true });

    } else if (msg.type === 'VERIFY_TYPED_VALUE') {
        const el = document.querySelector(`[data-ls-id="${msg.targetId}"]`);
        const matches = el ? (el.value === msg.expected) : false;
        sendResponse({ matches });
    }
});
