// background.js - Service Worker for LiteSight Browser Extension

const SERVER_BASE = 'http://localhost:8000';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'CALL_ACT') {
        fetch(`${SERVER_BASE}/act`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(msg.payload)
        })
        .then(res => res.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(err => sendResponse({ success: false, error: err.toString() }));
        return true; // Keeps async response port open
    } else if (msg.type === 'CALL_PLAN') {
        fetch(`${SERVER_BASE}/plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(msg.payload)
        })
        .then(res => res.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(err => sendResponse({ success: false, error: err.toString() }));
        return true;
    }
});
