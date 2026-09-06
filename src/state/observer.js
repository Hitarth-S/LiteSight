// src/state/observer.js
// State Layer: MutationObserver Diffing

class DOMObserver {
    constructor(callback) {
        this.callback = callback;
        // Configuration: childList, attributes, characterData
        this.config = {
            childList: true,
            attributes: true,
            characterData: true,
            subtree: true
        };
        this.observer = new MutationObserver(this.handleMutations.bind(this));
    }

    start(targetNode = document.body) {
        this.observer.observe(targetNode, this.config);
    }

    stop() {
        this.observer.disconnect();
    }

    handleMutations(mutationsList, observer) {
        // Batch Processing: array of MutationRecord objects
        const changes = [];
        for (const mutation of mutationsList) {
            changes.push({
                type: mutation.type,
                targetId: mutation.target.id || "unnamed_node",
                addedNodes: Array.from(mutation.addedNodes).map(node => {
                    if (node.nodeType === 1 && node.getBoundingClientRect) { // Element node
                        const rect = node.getBoundingClientRect();
                        return {
                            tag: node.tagName,
                            text: node.innerText?.trim().substring(0, 50) || "",
                            x: rect.x + (rect.width / 2),
                            y: rect.y + (rect.height / 2)
                        };
                    }
                    return null;
                }).filter(n => n !== null),
                removedNodes: Array.from(mutation.removedNodes).length,
                attributeName: mutation.attributeName,
                oldValue: mutation.oldValue
            });
        }
        // Reconciliation: Send batch to python backend
        if (this.callback) {
            this.callback(changes);
        }
    }
}

// Example usage to bind to Python backend via browser's exposed functions
window.LiteSightObserver = new DOMObserver((changes) => {
    if (window._liteSightStateUpdate) {
        window._liteSightStateUpdate(changes);
    }
});
window.LiteSightObserver.start();
