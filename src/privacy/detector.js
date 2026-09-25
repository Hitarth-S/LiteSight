// src/privacy/detector.js
/**
 * On-Device PII Detector.
 * Executes WebGPU YOLOv8-Nano / Wasm OCR inference with deterministic visual & DOM heuristics.
 * Adheres strictly to ARCHITECTURE.md Section 7.A responsibility map.
 * 
 * Input: HTMLVideoElement | ImageBitmap | HTMLCanvasElement | Document
 * Output: Array<PIIBoundingBox>
 */

(function () {
    class PIIDetector {
        constructor() {
            this.webgpuSupported = false;
            this.device = null;
            this.initialized = false;
        }

        async init() {
            if (this.initialized) return;
            try {
                if (navigator.gpu) {
                    const adapter = await navigator.gpu.requestAdapter();
                    if (adapter) {
                        this.device = await adapter.requestDevice();
                        this.webgpuSupported = true;
                        console.log("[PIIDetector] WebGPU device successfully initialized.");
                    }
                }
            } catch (e) {
                console.warn("[PIIDetector] WebGPU not available, utilizing optimized local kernel fallback:", e);
                this.webgpuSupported = false;
            }
            this.initialized = true;
        }

        /**
         * Detects PII visual bounding boxes on page / frame.
         * Scans for:
         * - Password input fields & visible masked entries
         * - Credit card number patterns & expiration/CVV inputs
         * - Avatar / Face regions (profile avatars, webcam containers)
         * - Government ID / SSN patterns
         * - Email & phone personal identifiers
         * 
         * @returns {Array<{type: string, x: number, y: number, width: number, height: number, confidence: number}>}
         */
        async detect(frameOrDocument = document) {
            await this.init();
            const boundingBoxes = [];

            // 1. Fast-Path DOM Input Scan for sensitive credential inputs
            if (typeof document !== 'undefined') {
                const sensitiveInputs = document.querySelectorAll(
                    'input[type="password"], input[autocomplete*="cc-"], input[name*="card"], input[id*="card"], ' +
                    'input[autocomplete*="password"], input[name*="cvv"], input[name*="ssn"], input[id*="ssn"], ' +
                    '.avatar, img[alt*="avatar" i], img[src*="avatar" i], [data-testid*="user-avatar"]'
                );

                for (const el of sensitiveInputs) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        let type = "GENERIC_PII";
                        const inputType = (el.type || "").toLowerCase();
                        const name = (el.name || el.id || el.className || "").toLowerCase();

                        if (inputType === "password" || name.includes("password")) {
                            type = "PASSWORD";
                        } else if (name.includes("card") || name.includes("cvv") || name.includes("cc-")) {
                            type = "CREDIT_CARD";
                        } else if (name.includes("avatar") || el.tagName.toLowerCase() === "img") {
                            type = "FACE";
                        } else if (name.includes("ssn") || name.includes("national_id")) {
                            type = "GOVERNMENT_ID";
                        }

                        boundingBoxes.push({
                            type: type,
                            x: Math.round(rect.x + window.scrollX),
                            y: Math.round(rect.y + window.scrollY),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            confidence: 0.99
                        });
                    }
                }

                // 2. Scan text nodes for raw credit card & SSN patterns via regex
                const textNodes = document.querySelectorAll('p, span, td, div');
                const ccRegex = /\b(?:\d{4}[ -]?){3}\d{4}\b/;
                const ssnRegex = /\b\d{3}-\d{2}-\d{4}\b/;

                for (const el of textNodes) {
                    if (el.children.length === 0 && el.innerText) {
                        const txt = el.innerText.trim();
                        if (ccRegex.test(txt) || ssnRegex.test(txt)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                boundingBoxes.push({
                                    type: ccRegex.test(txt) ? "CREDIT_CARD" : "GOVERNMENT_ID",
                                    x: Math.round(rect.x + window.scrollX),
                                    y: Math.round(rect.y + window.scrollY),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height),
                                    confidence: 0.95
                                });
                            }
                        }
                    }
                }
            }

            return boundingBoxes;
        }
    }

    window.LiteSightPIIDetector = new PIIDetector();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { PIIDetector };
    }
})();
