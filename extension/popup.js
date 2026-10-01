// popup.js - LiteSight Extension Popup Agent Loop

const logEl     = document.getElementById('log');
const goalInput = document.getElementById('goalInput');
const runBtn    = document.getElementById('runBtn');
const stopBtn   = document.getElementById('stopBtn');
const previewBtn= document.getElementById('previewBtn');
const statusDot = document.getElementById('statusDot');

// Redaction panel elements
const redactPanel = document.getElementById('redactPanel');
const countsLine  = document.getElementById('countsLine');
const originalCol = document.getElementById('originalCol');
const sentCol     = document.getElementById('sentCol');

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

function log(msg, type = 'info') {
    const div = document.createElement('div');
    div.className = `log-${type}`;
    div.textContent = msg;   // never innerHTML — prevents XSS with page-derived text
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
}

async function getActiveTab() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0] || null;
}

function setRunning(active) {
    runBtn.disabled  = active;
    stopBtn.disabled = !active;
    statusDot.className = 'header-status' + (active ? '' : ' idle');
}

// ─────────────────────────────────────────────────────────────────────────────
// Original agent loop — unchanged behaviour
// ─────────────────────────────────────────────────────────────────────────────

let _agentAbort = false;

async function runAgentLoop() {
    const goal = goalInput.value.trim();
    if (!goal) { log('Please enter a goal first.', 'fail'); return; }

    // Clear log, close redact panel if open
    logEl.textContent = '';
    hideRedactPanel();
    log(`Starting agent loop for: "${goal}"`, 'info');
    setRunning(true);
    _agentAbort = false;

    const tab = await getActiveTab();
    if (!tab) { log('No active tab found.', 'fail'); setRunning(false); return; }
    const tabId = tab.id;

    const history = [];
    const MAX_STEPS = 8;

    try {
        for (let step = 1; step <= MAX_STEPS; step++) {
            if (_agentAbort) { log('Run stopped by user.', 'warn'); break; }

            log(`--- Step ${step}/${MAX_STEPS} ---`, 'info');

            // 1. Observe
            let obs = null;
            try {
                obs = await chrome.tabs.sendMessage(tabId, { type: 'OBSERVE' });
            } catch (e) {
                log(`Observation error (reload page?): ${e.message}`, 'fail');
                break;
            }
            if (!obs || !obs.elements) { log('Failed to observe page.', 'fail'); break; }
            log(`Observed ${obs.elements.length} candidates on ${obs.url}`, 'info');

            // 2. /act via background
            log('Sending to server /act…', 'info');
            const serverRes = await chrome.runtime.sendMessage({
                type: 'CALL_ACT',
                payload: { goal, url: obs.url, elements: obs.elements, history }
            });

            if (!serverRes || !serverRes.success) {
                log(`Server error: ${serverRes ? serverRes.error : 'no response'}`, 'fail');
                break;
            }

            const decision = serverRes.data;
            log(`Decision: action='${decision.action}', target=${decision.target} — ${decision.reason || ''}`, 'info');

            if (decision.action === 'done') { log('SUCCESS: goal completed!', 'success'); break; }
            if (decision.action === 'fail') { log(`FAIL: ${decision.reason || 'no element matches'}`, 'fail'); break; }

            // 3. Execute
            log(`Executing '${decision.action}' on target ${decision.target}…`, 'info');
            const execRes = await chrome.tabs.sendMessage(tabId, {
                type: 'EXECUTE_ACTION',
                actionData: decision
            });

            if (execRes && execRes.success) {
                log(`Done. URL: ${execRes.url}`, 'success');
                history.push({ step, decision, url: execRes.url });
            } else {
                log('Action execution failed.', 'fail');
                break;
            }

            await new Promise(r => setTimeout(r, 1500));
        }
    } finally {
        setRunning(false);
    }
}

function stopAgent() {
    _agentAbort = true;
    stopBtn.disabled = true;
}

runBtn.addEventListener('click', runAgentLoop);
stopBtn.addEventListener('click', stopAgent);

// ─────────────────────────────────────────────────────────────────────────────
// Preview Redaction — demo feature, separate from agent run
// ─────────────────────────────────────────────────────────────────────────────

let _previewOn = false;

async function togglePreview() {
    const tab = await getActiveTab();
    if (!tab) { log('No active tab for preview.', 'fail'); return; }
    const tabId = tab.id;

    if (_previewOn) {
        // Restore page
        await chrome.tabs.sendMessage(tabId, { type: 'RESTORE_PAGE' });
        _previewOn = false;
        previewBtn.classList.remove('active');
        previewBtn.textContent = '🔒 Preview';
        hideRedactPanel();
        log('Page restored.', 'info');
        return;
    }

    // Ask content script to preview
    let result;
    try {
        result = await chrome.tabs.sendMessage(tabId, { type: 'PREVIEW_REDACTION' });
    } catch (e) {
        log(`Preview error: ${e.message}`, 'fail');
        return;
    }

    if (result.error) { log(`Preview error: ${result.error}`, 'fail'); return; }

    _previewOn = true;
    previewBtn.classList.add('active');
    previewBtn.textContent = '↩ Restore page';

    const total = Object.values(result.counts).reduce((a, b) => a + b, 0);
    log(`Redaction preview active — ${total} PII items masked.`, 'warn');

    showRedactPanel(result);
}

function hideRedactPanel() {
    redactPanel.classList.remove('visible');
    originalCol.textContent = '';
    sentCol.textContent = '';
    countsLine.textContent = '—';
}

/**
 * Returns the asterisk-mask display string for a given PII type.
 * Mirrors the masks injected on the page by content.js _maskForDisplay().
 */
function _maskDisplay(type, value) {
    if (type === 'AADHAAR') {
        const digits = value.replace(/[\s-]/g, '');
        return '**** **** ' + digits.slice(8);
    }
    if (type === 'PAN') {
        return value.slice(0, 3) + '**' + value.slice(5, 9) + '*';
    }
    if (type === 'PHONE') {
        // +91 98*** ***10
        return '+91 98*** ***' + value.replace(/[\s-]/g, '').slice(-2);
    }
    if (type === 'EMAIL') {
        const atIdx = value.indexOf('@');
        const local = value.slice(0, atIdx);
        const domain = value.slice(atIdx + 1);
        return local[0] + '*'.repeat(local.length - 1) + '@' + domain;
    }
    if (type === 'PASSWORD') {
        return '********';
    }
    return '***';
}

function showRedactPanel(result) {
    // Counts line — total items count with subtle highlight already in CSS
    const total = Object.values(result.counts).reduce((a, b) => a + b, 0);
    const parts = Object.entries(result.counts).map(([k, v]) => `${k} ${v}`);
    countsLine.textContent = `${total} item${total !== 1 ? 's' : ''} — ${parts.join(' · ')}`;

    // Clear columns
    originalCol.textContent = '';
    sentCol.textContent = '';

    // Populate "On page" column using textContent only (no innerHTML with page data)
    (result.original || []).forEach((item) => {
        const row = document.createElement('div');
        row.className = 'pii-row';

        const lbl = document.createElement('div');
        lbl.className = 'pii-label';
        lbl.textContent = item.field;   // safe: comes from our own rules enum

        const val = document.createElement('div');
        val.className = 'pii-value original';
        val.textContent = item.value;   // page-derived — textContent only

        row.appendChild(lbl);
        row.appendChild(val);
        originalCol.appendChild(row);
    });

    // Populate "Sent to server" column — show asterisk masks with blue highlight box
    (result.original || []).forEach((item) => {
        const row = document.createElement('div');
        row.className = 'pii-row';

        const lbl = document.createElement('div');
        lbl.className = 'pii-label';
        lbl.textContent = item.field;

        // For PASSWORD, append a small "redacted" chip label
        const val = document.createElement('div');
        val.className = 'pii-value redacted';  // CSS applies blue box

        if (item.field === 'PASSWORD') {
            val.textContent = '********';

            // Small "redacted" chip
            const chip = document.createElement('span');
            chip.textContent = ' redacted';
            chip.style.cssText = [
                'font-size:8px',
                'font-family:system-ui,sans-serif',
                'font-weight:700',
                'letter-spacing:.4px',
                'text-transform:uppercase',
                'color:#6366f1',
                'background:rgba(99,102,241,.12)',
                'border-radius:3px',
                'padding:0 3px',
                'margin-left:4px',
                'vertical-align:middle'
            ].join(';');
            val.appendChild(chip);
        } else {
            val.textContent = _maskDisplay(item.field, item.value);
        }

        row.appendChild(lbl);
        row.appendChild(val);
        sentCol.appendChild(row);
    });

    redactPanel.classList.add('visible');
}

previewBtn.addEventListener('click', togglePreview);
