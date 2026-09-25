1. Dual-Process Orchestration (Thinking Fast & Slow)

The system must be split into a High-Level Planner (Heavy LLM) and a Reactive Executor (Lightweight Edge Model).

    The Slow Planner: When a new domain is accessed, the heavy LLM generates a structured JSON array of sub-goals (e.g., ["locate_login", "enter_credentials", "verify_2fa"]).

    The Fast Executor: The lightweight edge model operates in a closed loop, executing the current sub-goal using muscle memory and returning a complete or failed status.

    The Handoff: The Planner remains dormant to save compute, waking only when the Fast Executor returns a failed state indicating an unexpected layout or an empty DOM.

2. The Vision Layer: Foveated Tokenization

To eliminate token explosion, the visual module must abandon uniform grid patching and implement foveated tokenization, operating on the principle that a coarse view guides where to look, while selectively acquired high-resolution evidence refines what to think.

    Irregular Grid Processing: The module extracts high-resolution patches centered strictly on the active interaction point and progressively downsamples surrounding patches on an irregular grid.

    Bandwidth Optimization: This approach preserves visual context while reducing the overall pixel and token count by roughly 24x compared to traditional uniform inputs.

    API Contract: The Fast Executor must pass a specific (x, y) coordinate (the foveation center) to the Vision API, which will return the compressed foveated token array rather than a standard 1080p image tensor.

3. The State Layer: MutationObserver Diffing & Lightpanda Engine

The agent must never capture back-to-back full-page DOM snapshots. The State Layer relies on the lightweight `lightpanda.AsyncBrowser()` to inject our native MutationObserver into the page context, monitoring changes in a non-blocking manner.

    Configuration: The observer must be configured to track childList (for added/removed nodes), attributes (for state changes like disabled or hidden), and characterData (for text modifications).

    Batch Processing: Instead of polling the DOM for changes, the agent must passively listen for the callback function, which will receive an array of MutationRecord objects detailing only what changed since the last action.

    Reconciliation: The execution loop updates a local, lightweight state tree using these mutation records, ensuring the agent always acts on the current UI state with zero redundant parsing overhead.

    ## 7. AI Agent Implementation Contracts & Machine Specs

> **Note for AI Coding Agents:** When implementing or refactoring modules in this repository, you MUST adhere strictly to the file paths, JSON schemas, and exception classes defined below. Do not create unmapped helper files or change payload key names.

### A. Code Base File Structure & Responsibility Map

| Module Path | Primary Responsibility | Input Type | Output Type |
| :--- | :--- | :--- | :--- |
| `src/privacy/detector.js` | WebGPU YOLOv8 + Wasm OCR execution | `HTMLVideoElement` / `ImageBitmap` | `Array<PIIBoundingBox>` |
| `src/privacy/canvas_masker.js` | Canvas synthetic SVG vector overlay | `ImageBitmap`, `Array<PIIBoundingBox>` | `Blob` (PNG/WebP Frame) |
| `src/state/snapshot.js` | Fast-path indexed DOM tree extractor | `Document` / `DOM Node` | `IndexedDOMState` (JSON) |
| `src/state/observer.js` | Asynchronous MutationObserver listener | DOM Mutation Events | `MutationRecord` stream |
| `src/vision/foveation.py` | PyTorch irregular grid foveation crop | `Tensor` (Full Image), `TargetCoord` | `Tensor` (Compressed Tokens) |
| `src/orchestrator/executor.py` | Fast/Slow process action loop & guard | `IndexedDOMState`, `GoalString` | `ActionPayload` |

---

### B. Machine Schemas & Type Contracts

#### 1. Fast-Path Indexed DOM State Schema (`src/state/snapshot.js`)
AI agents generating snapshot code must emit JSON strictly matching this schema:
```json
{
  "$schema": "[http://json-schema.org/draft-07/schema#](http://json-schema.org/draft-07/schema#)",
  "type": "object",
  "properties": {
    "timestamp": { "type": "number" },
    "url": { "type": "string" },
    "elements": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "index": { "type": "integer" },
          "tag": { "type": "string" },
          "role": { "type": "string" },
          "label": { "type": "string" },
          "value": { "type": "string" },
          "is_visible": { "type": "boolean" },
          "bounding_box": {
            "type": "object",
            "properties": {
              "x": { "type": "number" },
              "y": { "type": "number" },
              "width": { "type": "number" },
              "height": { "type": "number" }
            },
            "required": ["x", "y", "width", "height"]
          }
        },
        "required": ["index", "tag", "is_visible", "bounding_box"]
      }
    }
  },
  "required": ["timestamp", "url", "elements"]
}

2. Server Action Response Schema (src/orchestrator/executor.py)
AI agents building server-side models must format responses strictly as:
JSON
{
 "$schema": "[http://json-schema.org/draft-07/schema#](http://json-schema.org/draft-07/schema#)",
 "type": "object",
 "properties": {
 "operation": {
 "type": "string",
 "enum": ["CLICK", "TYPE_TEXT", "SELECT", "SCROLL_UP", "SCROLL_DOWN", "WAIT", "FALLBACK_TO_VISION", "DONE"]
 },
 "target_index": { "type": ["integer", "null"] },
 "text_value": { "type": ["string", "null"] },
 "reasoning_summary": { "type": "string" }
 },
 "required": ["operation", "target_index"]
}
C. Required Exceptions & Error Handling Class Hierarchy
AI agents MUST import and raise these exact custom exception classes located in src/orchestrator/exceptions.py:
Python
class LiteSightBaseException(Exception):
 """Base exception for all LiteSight runtime errors."""
 pass
class StaleNodeException(LiteSightBaseException):
 """Raised when target_index is no longer present in current DOM tree."""
 pass
class ElementObscuredError(LiteSightBaseException):
 """Raised when target element is covered by overlay/modal or zero-width."""
 pass
class CanvasFallbackTrigger(LiteSightBaseException):
 """Raised when action target resides within non-indexed <canvas> or WebGL context."""
 pass
class PIIRedactionFailure(LiteSightBaseException):
 """Raised if WebGPU privacy kernel fails frame sanitization prior to egress."""
 pass