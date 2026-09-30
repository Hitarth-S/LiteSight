// extension/background.js
/**
 * LiteSight Background Service Worker
 * Handles communication between popup, content script, and server endpoint.
 */

chrome.runtime.onInstalled.addListener(() => {
    console.log("[LiteSight] Background service worker initialized.");
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "SEND_TO_SERVER") {
        const { serverUrl, payload } = request;
        
        fetch(`${serverUrl}/api/step`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => sendResponse({ success: true, action: data }))
        .catch(err => {
            console.error("[LiteSight Background] Server connection error:", err);
            sendResponse({ success: false, error: err.message });
        });

        return true; // Keep channel open for async response
    }
});
