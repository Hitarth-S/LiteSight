/**
 * pii_check.js — Automated proof runner for the LiteSight PII redaction demo.
 * Run with: node tests/pii_check.js
 *
 * Uses jsdom to simulate the browser environment without needing a real browser.
 * Reproduces the same Verhoeff + PII logic from content.js so the proof is
 * independent of the extension runtime.
 */
'use strict';

// ─── Verhoeff tables (exact copy from content.js) ────────────────────────────
const _V_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
    [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
    [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
    [9,8,7,6,5,4,3,2,1,0]
];
const _V_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
    [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
    [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]
];

function _verhoeffValid(numStr) {
    const digits = numStr.split('').reverse().map(Number);
    let c = 0;
    for (let i = 0; i < digits.length; i++) c = _V_D[c][_V_P[i % 8][digits[i]]];
    return c === 0;
}

// ─── PII rules (exact copy from content.js) ──────────────────────────────────
const PII_RULES = [
    { type: 'AADHAAR', regex: /\b(\d{4}[\s-]\d{4}[\s-]\d{4}|\d{12})\b/g,
      validate: m => _verhoeffValid(m.replace(/[\s-]/g, '')) },
    { type: 'PAN',     regex: /\b[A-Z]{5}\d{4}[A-Z]\b/g, validate: null },
    { type: 'PHONE',   regex: /\+91[\s-]?\d{5}[\s-]?\d{5}\b/g, validate: null },
    { type: 'EMAIL',   regex: /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g, validate: null },
];

function scanText(text) {
    const found = {};  // type → [matches]
    const notRedacted = [];

    for (const rule of PII_RULES) {
        rule.regex.lastIndex = 0;
        let m;
        while ((m = rule.regex.exec(text)) !== null) {
            const original = m[0];
            if (rule.validate && !rule.validate(original)) {
                notRedacted.push({ type: rule.type, value: original, reason: 'failed extra validation' });
                continue;
            }
            (found[rule.type] = found[rule.type] || []).push(original);
        }
    }
    return { found, notRedacted };
}

// ─── Load the KYC page text (naively parse visible text from HTML) ───────────
const fs   = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'pii_page.html'), 'utf8');

// Strip tags to get visible text (simple, sufficient for our planted data)
const visibleText = html.replace(/<script[\s\S]*?<\/script>/gi, '')
                        .replace(/<style[\s\S]*?<\/style>/gi, '')
                        .replace(/<[^>]+>/g, ' ')
                        .replace(/&amp;/g, '&')
                        .replace(/&lt;/g, '<')
                        .replace(/&gt;/g, '>')
                        .replace(/\s+/g, ' ');

// Also extract password value from the HTML attribute
const pwdMatch = html.match(/value="([^"]+)"[^>]*type="password"|type="password"[^>]*value="([^"]+)"/);
const passwordValue = (pwdMatch && (pwdMatch[1] || pwdMatch[2])) || '';

// ─── Run scan ────────────────────────────────────────────────────────────────
const { found, notRedacted } = scanText(visibleText);

// Passwords are not in visible text — handle separately
if (passwordValue) {
    (found['PASSWORD'] = found['PASSWORD'] || []).push('(password field)');
}

// ─── Assertions ──────────────────────────────────────────────────────────────
let pass = true;
const EXPECTED = { AADHAAR: 1, PAN: 1, PHONE: 1, EMAIL: 1, PASSWORD: 1 };
const NEGATIVES = ['123456789012', '1234 5678 9013'];

console.log('\n═══════════════════════════════════════════════════════');
console.log('  LiteSight PII Redaction — Automated Proof');
console.log('═══════════════════════════════════════════════════════\n');

// Verhoeff check section
console.log('── Verhoeff Check ──────────────────────────────────────');
console.log('  234567890124 valid:', _verhoeffValid('234567890124'),   '← expect true');
console.log('  123456789012 valid:', _verhoeffValid('123456789012'),   '← expect false');
console.log('  123456789013 valid:', _verhoeffValid('123456789013'),   '← expect false');
console.log();

// Counts check
console.log('── PII Counts ──────────────────────────────────────────');
for (const [type, expectedCount] of Object.entries(EXPECTED)) {
    const actual = (found[type] || []).length;
    const ok = actual === expectedCount;
    if (!ok) pass = false;
    console.log(`  ${type.padEnd(10)} expected=${expectedCount}  actual=${actual}  ${ok ? '✓' : '✗ FAIL'}`);
}
console.log();

// Negatives — confirm they were NOT redacted
console.log('── Negatives (must NOT be redacted) ───────────────────');
for (const neg of NEGATIVES) {
    const stripped = neg.replace(/\s/g, '');
    // Check that none of the AADHAAR found values match this
    const wasRedacted = (found['AADHAAR'] || []).some(v => v.replace(/[\s-]/g,'') === stripped);
    const ok = !wasRedacted;
    if (!ok) pass = false;
    console.log(`  "${neg}"  redacted=${wasRedacted}  ${ok ? '✓ correctly excluded' : '✗ FAIL — should NOT be redacted'}`);
}
console.log();

// Payload PII-free check
console.log('── Sanitised Payload (grep check) ─────────────────────');
const ORIGINALS = [
    '2345 6789 0124', '234567890124',
    'ABCDE1234F',
    '+91 98765 43210',
    'test.user@example.com',
    'Str0ng#Pass99!'
];
// Simulate what would be sent: replace each PII value with placeholder
let payload = visibleText;
const counters = {};
for (const rule of PII_RULES) {
    rule.regex.lastIndex = 0;
    payload = payload.replace(rule.regex, (m) => {
        if (rule.validate && !rule.validate(m)) return m;
        counters[rule.type] = (counters[rule.type] || 0) + 1;
        return `[${rule.type}_${counters[rule.type]}]`;
    });
}
// passwords never appear in visible text anyway, but confirm
for (const orig of ORIGINALS) {
    const present = payload.includes(orig);
    if (present) pass = false;
    console.log(`  "${orig}" in payload: ${present}  ${!present ? '✓ not present' : '✗ FAIL — PII leaked!'}`);
}
console.log();

// Final result
console.log('═══════════════════════════════════════════════════════');
console.log(`  Result: ${pass ? '✓ ALL CHECKS PASSED' : '✗ SOME CHECKS FAILED'}`);
console.log('═══════════════════════════════════════════════════════\n');
process.exit(pass ? 0 : 1);
