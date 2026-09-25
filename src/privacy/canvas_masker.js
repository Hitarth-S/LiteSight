// src/privacy/canvas_masker.js
/**
 * Context-Preserving Synthetic Vector Masker.
 * Adheres strictly to ARCHITECTURE.md Section 7.A & AGENTS.md invariant #4:
 * "Never transmit raw screenshots or opaque black boxes to the cloud.
 * Sensitive visual elements must be replaced locally with synthetic, context-preserving vector overlays."
 * 
 * Input: ImageBitmap | HTMLCanvasElement | HTMLImageElement, Array<PIIBoundingBox>
 * Output: Blob (PNG/WebP Frame) | DataURL
 */

(function () {
    class CanvasMasker {
        /**
         * Renders context-preserving synthetic vector graphics over detected PII regions.
         * @param {HTMLCanvasElement|HTMLImageElement|ImageBitmap} sourceImage 
         * @param {Array<{type: string, x: number, y: number, width: number, height: number}>} boundingBoxes 
         * @returns {HTMLCanvasElement} Sanitized canvas
         */
        mask(sourceImage, boundingBoxes = []) {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');

            canvas.width = sourceImage.width || sourceImage.videoWidth || 1920;
            canvas.height = sourceImage.height || sourceImage.videoHeight || 1080;

            // Draw original source frame onto canvas
            ctx.drawImage(sourceImage, 0, 0, canvas.width, canvas.height);

            for (const box of boundingBoxes) {
                const { type, x, y, width, height } = box;
                if (width <= 0 || height <= 0) continue;

                ctx.save();

                if (type === "CREDIT_CARD") {
                    this._drawSyntheticCard(ctx, x, y, width, height);
                } else if (type === "FACE") {
                    this._drawSyntheticAvatar(ctx, x, y, width, height);
                } else if (type === "PASSWORD") {
                    this._drawSyntheticPassword(ctx, x, y, width, height);
                } else if (type === "GOVERNMENT_ID") {
                    this._drawSyntheticID(ctx, x, y, width, height);
                } else {
                    this._drawGenericSyntheticMask(ctx, x, y, width, height, type);
                }

                ctx.restore();
            }

            return canvas;
        }

        _drawSyntheticCard(ctx, x, y, w, h) {
            // Draw stylized card background with rounded corners and gradient
            ctx.beginPath();
            const r = Math.min(8, w / 4, h / 4);
            ctx.roundRect(x, y, w, h, r);
            const grad = ctx.createLinearGradient(x, y, x + w, y + h);
            grad.addColorStop(0, '#1e293b');
            grad.addColorStop(1, '#0f172a');
            ctx.fillStyle = grad;
            ctx.fill();
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Gold microchip glyph
            const chipW = Math.max(12, Math.min(24, w * 0.2));
            const chipH = Math.max(8, Math.min(18, h * 0.3));
            ctx.fillStyle = '#fbbf24';
            ctx.fillRect(x + 6, y + (h - chipH) / 2, chipW, chipH);

            // Vector badge label
            ctx.fillStyle = '#e2e8f0';
            ctx.font = `bold ${Math.max(9, Math.min(13, Math.round(h * 0.35)))}px monospace`;
            ctx.fillText("[SYNTHETIC_CARD]", x + chipW + 10, y + h / 2 + 4);
        }

        _drawSyntheticAvatar(ctx, x, y, w, h) {
            // Neutral circle avatar with user silhouette
            ctx.beginPath();
            const cx = x + w / 2;
            const cy = y + h / 2;
            const radius = Math.min(w, h) / 2;
            ctx.arc(cx, cy, radius, 0, Math.PI * 2);
            ctx.fillStyle = '#334155';
            ctx.fill();
            ctx.strokeStyle = '#64748b';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Head silhouette
            ctx.beginPath();
            ctx.arc(cx, cy - radius * 0.2, radius * 0.35, 0, Math.PI * 2);
            ctx.fillStyle = '#94a3b8';
            ctx.fill();

            // Shoulders silhouette
            ctx.beginPath();
            ctx.arc(cx, cy + radius * 0.7, radius * 0.65, Math.PI, 0);
            ctx.fill();
        }

        _drawSyntheticPassword(ctx, x, y, w, h) {
            // Clean input overlay with dot pattern
            ctx.fillStyle = '#1e293b';
            ctx.fillRect(x, y, w, h);
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 1;
            ctx.strokeRect(x, y, w, h);

            // Lock icon & security bullets
            ctx.fillStyle = '#94a3b8';
            ctx.font = `${Math.max(10, Math.min(14, Math.round(h * 0.6)))}px sans-serif`;
            ctx.fillText("🔒 ••••••••", x + 6, y + h * 0.7);
        }

        _drawSyntheticID(ctx, x, y, w, h) {
            ctx.beginPath();
            ctx.roundRect(x, y, w, h, 4);
            ctx.fillStyle = '#0f766e';
            ctx.fill();
            ctx.strokeStyle = '#2dd4bf';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${Math.max(9, Math.min(12, Math.round(h * 0.4)))}px sans-serif`;
            ctx.fillText("🛡️ [SYNTHETIC_ID]", x + 6, y + h * 0.65);
        }

        _drawGenericSyntheticMask(ctx, x, y, w, h, type) {
            ctx.fillStyle = '#1e1e2e';
            ctx.fillRect(x, y, w, h);
            ctx.strokeStyle = '#a6adc8';
            ctx.lineWidth = 1;
            ctx.strokeRect(x, y, w, h);

            ctx.fillStyle = '#cdd6f4';
            ctx.font = `10px monospace`;
            ctx.fillText(`[REDACTED_${type}]`, x + 4, y + h * 0.65);
        }

        /**
         * Returns data URL of sanitized frame.
         */
        toDataURL(canvas, format = 'image/png') {
            return canvas.toDataURL(format);
        }

        /**
         * Returns Promise<Blob> of sanitized frame.
         */
        toBlob(canvas, format = 'image/png') {
            return new Promise((resolve, reject) => {
                canvas.toBlob((blob) => {
                    if (blob) resolve(blob);
                    else reject(new Error("Canvas toBlob failed"));
                }, format);
            });
        }
    }

    window.LiteSightCanvasMasker = new CanvasMasker();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { CanvasMasker };
    }
})();
