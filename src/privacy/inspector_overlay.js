// src/privacy/inspector_overlay.js
/**
 * Dual-Pane Visual Privacy & Action Inspector + Real-Time In-Page Privacy Indicators.
 * Fulfills Feature 2 of SIH MVP & User Request:
 * 1. Displays real-time side-by-side view of live webpage vs on-device sanitized egress frame.
 * 2. Renders subtle in-page visual overlays & badges indicating:
 *    - MONITORED AREAS: Active sensitive fields guarded by LiteSight
 *    - REDACTED AREAS: Elements/text masked locally with context-preserving vectors
 */

(function () {
    class PrivacyInspector {
        constructor() {
            this.container = null;
            this.indicatorsContainer = null;
            this.visible = false;
            this.indicatorsEnabled = true;
            this._injectStyles();
        }

        _injectStyles() {
            if (document.getElementById('litesight-privacy-styles')) return;
            const style = document.createElement('style');
            style.id = 'litesight-privacy-styles';
            style.textContent = `
                /* In-Page Visual Highlights for Monitored and Redacted Elements */
                [data-litesight-privacy="monitored"] {
                    outline: 2px dashed rgba(56, 189, 248, 0.75) !important;
                    outline-offset: 2px !important;
                    box-shadow: 0 0 10px rgba(56, 189, 248, 0.22) !important;
                    transition: outline 0.2s ease, box-shadow 0.2s ease !important;
                }
                [data-litesight-privacy="redacted"] {
                    outline: 2px solid rgba(34, 197, 94, 0.85) !important;
                    outline-offset: 2px !important;
                    background-color: rgba(34, 197, 94, 0.08) !important;
                    box-shadow: 0 0 14px rgba(34, 197, 94, 0.32) !important;
                    transition: outline 0.2s ease, box-shadow 0.2s ease !important;
                }

                @keyframes lsPulseGlow {
                    0% { opacity: 0.88; transform: translateY(0); }
                    50% { opacity: 1; transform: translateY(-1px); }
                    100% { opacity: 0.88; transform: translateY(0); }
                }

                .ls-privacy-badge {
                    position: absolute;
                    pointer-events: auto;
                    cursor: default;
                    z-index: 2147483640;
                    display: inline-flex;
                    align-items: center;
                    gap: 5px;
                    padding: 3px 7px;
                    border-radius: 4px;
                    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 0.3px;
                    backdrop-filter: blur(6px);
                    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.45);
                    animation: lsPulseGlow 3s infinite ease-in-out;
                    user-select: none;
                }
                .ls-badge-redacted {
                    background: rgba(15, 23, 42, 0.92);
                    color: #22c55e;
                    border: 1px solid #22c55e;
                }
                .ls-badge-monitored {
                    background: rgba(15, 23, 42, 0.92);
                    color: #38bdf8;
                    border: 1px solid #38bdf8;
                }
                .ls-privacy-box {
                    position: absolute;
                    pointer-events: none;
                    z-index: 2147483639;
                    box-sizing: border-box;
                    border-radius: 4px;
                    transition: all 0.2s ease-out;
                }
                .ls-box-redacted {
                    border: 1.5px solid rgba(34, 197, 94, 0.7);
                    background: rgba(34, 197, 94, 0.08);
                }
                .ls-box-monitored {
                    border: 1.5px dashed rgba(56, 189, 248, 0.6);
                    background: rgba(56, 189, 248, 0.05);
                }
            `;
            const head = document.head || document.documentElement;
            if (head) head.appendChild(style);
        }

        mount() {
            // Disabled: Bottom-right dual pane window removed per user configuration
            const existing = document.getElementById('litesight-inspector-root');
            if (existing) existing.remove();
            this.container = null;
        }

        updateAction(actionStr, latencyMs = 0) {
            // Dual-pane HUD disabled
        }

        updateSanitizedStats(detectedCount = 0, monitoredCount = 0, redactedCount = 0, sensitivity = "BALANCED") {
            // Dual-pane HUD disabled
        }

        /**
         * Renders subtle in-page visual overlays and badges on monitored & redacted webpage regions.
         * Fulfills user requirement for real-time visual feedback on PII operations.
         */
        renderVisualIndicators(boxes = [], config = {}) {
            this._injectStyles();
            if (config && typeof config.visual_indicators === 'boolean') {
                this.indicatorsEnabled = config.visual_indicators;
            }

            if (!this.indicatorsEnabled) {
                this.clearVisualIndicators();
                return;
            }

            // Ensure overlay container exists
            let container = document.getElementById('litesight-visual-overlays-container');
            if (!container) {
                container = document.createElement('div');
                container.id = 'litesight-visual-overlays-container';
                container.style.cssText = `
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    pointer-events: none;
                    z-index: 2147483638;
                    overflow: visible;
                `;
                const targetParent = document.body || document.documentElement;
                if (targetParent) targetParent.appendChild(container);
            }
            this.indicatorsContainer = container;

            // Clear previous overlays inside container
            container.innerHTML = '';

            let monitoredCount = 0;
            let redactedCount = 0;

            for (const box of boxes) {
                const { type, status, category, x, y, width, height } = box;
                if (width <= 0 || height <= 0) continue;

                const isRedacted = (status === "REDACTED");
                if (isRedacted) redactedCount++;
                else monitoredCount++;

                // 1. Subtle Bounding Highlight Box
                const boxDiv = document.createElement('div');
                boxDiv.className = `ls-privacy-box ${isRedacted ? 'ls-box-redacted' : 'ls-box-monitored'}`;
                boxDiv.style.left = `${x}px`;
                boxDiv.style.top = `${y}px`;
                boxDiv.style.width = `${width}px`;
                boxDiv.style.height = `${height}px`;
                container.appendChild(boxDiv);

                // 2. Real-Time Status Badge
                const badge = document.createElement('div');
                badge.className = `ls-privacy-badge ${isRedacted ? 'ls-badge-redacted' : 'ls-badge-monitored'}`;
                const badgeY = Math.max(0, y - 22);
                badge.style.left = `${x}px`;
                badge.style.top = `${badgeY}px`;
                badge.title = `LiteSight On-Device Privacy Sentinel: ${isRedacted ? 'Locally redacted from cloud reasoning' : 'Actively monitoring sensitive input'}`;

                const icon = isRedacted ? '🛡️' : '👁️';
                const label = isRedacted ? 'REDACTED' : 'MONITORED';
                const catText = category || type;

                badge.innerHTML = `
                    <span>${icon}</span>
                    <span>${label}:</span>
                    <span style="color: #e2e8f0; font-weight: normal;" class="ls-cat-text"></span>
                `;
                badge.querySelector('.ls-cat-text').textContent = catText;
                container.appendChild(badge);
            }

            // Also update HUD stats
            const sens = config && config.sensitivity ? config.sensitivity : "BALANCED";
            this.updateSanitizedStats(boxes.length, monitoredCount, redactedCount, sens);
        }

        clearVisualIndicators() {
            const container = document.getElementById('litesight-visual-overlays-container');
            if (container) {
                container.innerHTML = '';
            }
            const stamped = document.querySelectorAll('[data-litesight-privacy]');
            for (const el of stamped) {
                el.removeAttribute('data-litesight-privacy');
                el.removeAttribute('data-litesight-category');
            }
        }

        toggleVisualIndicators(enabled) {
            this.indicatorsEnabled = (typeof enabled === 'boolean') ? enabled : !this.indicatorsEnabled;
            if (!this.indicatorsEnabled) {
                this.clearVisualIndicators();
            } else if (window.LiteSightPIIDetector) {
                window.LiteSightPIIDetector.detect(document).then(boxes => {
                    this.renderVisualIndicators(boxes, window.LiteSightPIIDetector.getConfig());
                });
            }
        }
    }

    window.LiteSightInspector = new PrivacyInspector();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { PrivacyInspector };
    }
})();
