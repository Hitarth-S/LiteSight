// src/privacy/sanitizer.js
/**
 * Combined WebGPU & Synthetic Masking Privacy Pipeline.
 * Orchestrates detector.js and canvas_masker.js within browser context.
 */

(function () {
    class PrivacyPipeline {
        constructor() {
            this.detector = window.LiteSightPIIDetector || null;
            this.masker = window.LiteSightCanvasMasker || null;
        }

        async sanitizeCurrentView() {
            if (!this.detector) this.detector = window.LiteSightPIIDetector;
            if (!this.masker) this.masker = window.LiteSightCanvasMasker;

            // 1. Detect all visual and DOM PII bounding boxes
            const piiBoxes = await this.detector.detect(document);

            return {
                detectedCount: piiBoxes.length,
                boxes: piiBoxes,
                timestamp: Date.now()
            };
        }

        /**
         * Renders synthetic vector overlays onto a base64 or image element
         */
        async maskImage(imageElement, boxes) {
            if (!this.masker) this.masker = window.LiteSightCanvasMasker;
            const sanitizedCanvas = this.masker.mask(imageElement, boxes);
            return sanitizedCanvas.toDataURL('image/png');
        }
    }

    window.LiteSightPrivacyPipeline = new PrivacyPipeline();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { PrivacyPipeline };
    }
})();
