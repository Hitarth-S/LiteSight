// extension/background.js
/**
 * LiteSight Background Service Worker
 * Handles communication between popup, content script, and server endpoint.
 */

const DEFAULT_SERVER_BASE = 'http://localhost:8000';

chrome.runtime.onInstalled.addListener(() => {
    console.log("[LiteSight] Background service worker initialized.");
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // 1. Direct step API endpoint
    if (request.action === "SEND_TO_SERVER") {
        const serverUrl = request.serverUrl || DEFAULT_SERVER_BASE;
        
        fetch(`${serverUrl}/api/step`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request.payload)
        })
        .then(res => res.json())
        .then(data => sendResponse({ success: true, action: data }))
        .catch(err => {
            console.error("[LiteSight Background] Server connection error:", err);
            sendResponse({ success: false, error: err.message });
        });

        return true;
    }
    
    // 2. High-level agent /act endpoint
    if (request.type === 'CALL_ACT') {
        const serverUrl = request.serverUrl || DEFAULT_SERVER_BASE;
        fetch(`${serverUrl}/act`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request.payload)
        })
        .then(res => res.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(err => {
            console.error("[LiteSight Background] /act error:", err);
            sendResponse({ success: false, error: err.toString() });
        });
        return true;
    }

    // 3. Subgoal planner /plan endpoint
    if (request.type === 'CALL_PLAN') {
        const serverUrl = request.serverUrl || DEFAULT_SERVER_BASE;
        fetch(`${serverUrl}/plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request.payload)
        })
        .then(res => res.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(err => {
            console.error("[LiteSight Background] /plan error:", err);
            sendResponse({ success: false, error: err.toString() });
        });
        return true;
    }
});
