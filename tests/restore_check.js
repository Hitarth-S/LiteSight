/**
 * restore_check.js — Verifies that after RESTORE_PAGE the page text content
 * is byte-identical to the pre-preview original.
 *
 * Simulates the _wrapTextNodeMatch + restorePage cycle using jsdom,
 * without needing a real browser.
 *
 * Run with: node tests/restore_check.js
 */
'use strict';

const { JSDOM } = require('jsdom');
const fs   = require('fs');
const path = require('path');

// ─── Load pii_page.html ──────────────────────────────────────────────────────
const html = fs.readFileSync(path.join(__dirname, 'pii_page.html'), 'utf8');
const dom  = new JSDOM(html);
const { document, NodeFilter, Node } = dom.window;

// ─── Capture original text snapshot ─────────────────────────────────────────
const originalText = document.body.textContent;

// ─── Reproduce _wrapTextNodeMatch logic ─────────────────────────────────────
let restoreOps = [];

function wrapTextNodeMatch(textNode, original, masked) {
    const txt = textNode.textContent;
    const idx = txt.indexOf(original);
    if (idx === -1) return false;
    const parent = textNode.parentNode;
    if (!parent) return false;
    if (parent.classList && parent.classList.contains('ls-redacted')) return false;

    const before = txt.slice(0, idx);
    const after  = txt.slice(idx + original.length);

    restoreOps.push({
        type: 'text',
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

// ─── Simulate preview — wrap the known PII values ────────────────────────────
const testFindings = [
    { original: '2345 6789 0124', masked: '**** **** 0124' },
    { original: 'ABCDE1234F',     masked: 'ABC**1234*'     },
    { original: '+91 98765 43210',masked: '+91 98*** ***10'},
    { original: 'test.user@example.com', masked: 't*******************@example.com' },
];

// Collect text nodes first (same pattern as content.js)
const textNodes = [];
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
        const p = node.parentElement;
        if (!p) return NodeFilter.FILTER_REJECT;
        const tag = p.tagName && p.tagName.toLowerCase();
        if (tag === 'script' || tag === 'style') return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
    }
});
let n;
while ((n = walker.nextNode())) textNodes.push(n);

for (const textNode of textNodes) {
    if (!textNode.isConnected) continue;
    for (const f of testFindings) {
        if (textNode.textContent.includes(f.original)) {
            wrapTextNodeMatch(textNode, f.original, f.masked);
            break;
        }
    }
}

const maskedText = document.body.textContent;
console.log('\n─── Preview active ─────────────────────────────────────────────');
console.log('  Original PII values should NOT appear in masked text:');
let previewOk = true;
for (const f of testFindings) {
    const present = maskedText.includes(f.original);
    if (present) previewOk = false;
    console.log(`  "${f.original}" present: ${present}  ${!present ? '✓' : '✗ FAIL'}`);
}

// ─── Simulate RESTORE_PAGE ───────────────────────────────────────────────────
for (let i = restoreOps.length - 1; i >= 0; i--) {
    const op = restoreOps[i];
    if (op.type !== 'text') continue;

    const parent = op.parent;
    if (!parent || !parent.isConnected) continue;

    const spans = Array.from(parent.querySelectorAll(':scope > span.ls-redacted'));
    let matched = null;
    for (const sp of spans) {
        const bef = sp.previousSibling;
        const aft = sp.nextSibling;
        const befTxt = (bef && bef.nodeType === Node.TEXT_NODE) ? bef.textContent : '';
        const aftTxt = (aft && aft.nodeType === Node.TEXT_NODE) ? aft.textContent : '';
        if (op.originalText.startsWith(befTxt) && op.originalText.endsWith(aftTxt)) {
            matched = sp;
            break;
        }
    }

    if (matched) {
        const bef = matched.previousSibling;
        const aft = matched.nextSibling;
        const restored = document.createTextNode(op.originalText);
        parent.insertBefore(restored, matched);
        parent.removeChild(matched);
        if (bef && bef.nodeType === Node.TEXT_NODE) parent.removeChild(bef);
        if (aft && aft.nodeType === Node.TEXT_NODE) parent.removeChild(aft);
    } else {
        if (parent.childNodes.length <= 3) parent.textContent = op.originalText;
    }
}

const restoredText = document.body.textContent;

// ─── Final check: restored === original ─────────────────────────────────────
console.log('\n─── Restore check ──────────────────────────────────────────────');
const identical = restoredText === originalText;
console.log(`  body.textContent identical to original: ${identical}  ${identical ? '✓ PASS' : '✗ FAIL'}`);

if (!identical) {
    // Show first differing character
    for (let i = 0; i < Math.max(originalText.length, restoredText.length); i++) {
        if (originalText[i] !== restoredText[i]) {
            console.log(`  First diff at index ${i}: original="${originalText.slice(i, i+20)}" restored="${restoredText.slice(i, i+20)}"`);
            break;
        }
    }
}

const allOk = previewOk && identical;
console.log('\n═══════════════════════════════════════════════════════');
console.log(`  Result: ${allOk ? '✓ ALL CHECKS PASSED' : '✗ SOME CHECKS FAILED'}`);
console.log('═══════════════════════════════════════════════════════\n');
process.exit(allOk ? 0 : 1);
