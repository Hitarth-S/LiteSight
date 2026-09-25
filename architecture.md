# LiteSight — Architecture Specification

## 1. Dual-Process Orchestration (Thinking Fast & Slow)

The system is split into a **High-Level Planner** (Heavy LLM) and a **Reactive Executor** (Lightweight Edge Model).

- **The Slow Planner**: When a new domain is accessed, the heavy LLM (Groq Qwen 3.8-27b via LPU) generates a structured JSON array of sub-goals (e.g., `["locate_login", "enter_credentials", "verify_2fa"]`). It also injects Retrieval-Augmented Personalization (RAP) context from the local preference store.

- **The Fast Executor**: The lightweight edge model operates in a closed loop, executing the current sub-goal using indexed DOM muscle memory and returning a `complete` or `failed` status within sub-500ms.

- **The Handoff**: The Planner remains dormant to save compute, waking only when the Fast Executor returns a `failed` state indicating an unexpected layout, an empty DOM, or a `CanvasFallbackTrigger`.

- **Context State Object (CSO)**: A rolling compressed session-memory is maintained by `src/state/cso_tracker.py`. On each Slow Planner call, only the minimal distilled context window (not the raw DOM) is injected, preventing token explosion across long-horizon tasks.

---

## 2. The Vision Layer: Foveated Tokenization

To eliminate token explosion, the visual module abandons uniform grid patching and implements **foveated tokenization**, operating on the principle that a coarse view guides where to look, while selectively acquired high-resolution evidence refines what to think.

- **Irregular Grid Processing**: The module extracts high-resolution patches centered strictly on the active interaction point and progressively downsamples surrounding patches on an irregular grid.

- **Bandwidth Optimization**: This approach preserves visual context while reducing the overall pixel and token count by roughly **24x** compared to traditional uniform inputs.

- **API Contract**: The Fast Executor passes a specific `(x, y)` coordinate (the foveation center) to the Vision API (`src/vision/foveation.py`), which returns the compressed foveated token array rather than a standard 1080p image tensor.

- **OmniVisualParser Fallback** (`src/vision/omni_parser.py`): When even the foveated VLM is unavailable, a pure NumPy/SciPy morphological edge detector with Non-Maximum Suppression (NMS) extracts discrete `[V1] button`, `[V2] textbox` indices directly from pixel buffers — zero DOM dependency, zero raw frame egress.

---

## 3. The State Layer: MutationObserver Diffing

The agent never captures back-to-back full-page DOM snapshots. The State Layer injects a native `MutationObserver` into the page context via Playwright, monitoring changes in a non-blocking manner.

- **Configuration**: The observer tracks `childList` (for added/removed nodes), `attributes` (for state changes like `disabled` or `hidden`), and `characterData` (for text modifications).

- **Batch Processing**: Instead of polling the DOM for changes, the agent passively listens for the callback function, which receives an array of `MutationRecord` objects detailing only what changed since the last action.

- **Reconciliation**: The execution loop updates a local, lightweight state tree using these mutation records, ensuring the agent always acts on the current UI state with zero redundant parsing overhead.

---

## 4. The Privacy Layer: WebGPU Synthetic Privacy Pipeline

All visual frame egress passes through a mandatory local privacy pipeline **before** any data is sent to a cloud model.

- **PII Detection** (`src/privacy/detector.js`): A WebGPU-accelerated kernel scans DOM and canvas frames for passwords, credit card numbers, government IDs, and face/avatar regions using local heuristic pattern recognition.

- **Context-Preserving Synthetic Masking** (`src/privacy/canvas_masker.js`): Detected PII bounding boxes are replaced with stylized synthetic vector graphics — `[SYNTHETIC_CARD]`, standard avatar silhouettes, `🔒 ••••••••` — maintaining exact UI boundaries without opaque black boxes.

- **Pipeline Orchestration** (`src/privacy/sanitizer.js`): The sanitizer composes detector → masker into a single atomic unit, guaranteeing no raw frame can bypass redaction.

- **Zero-Trust Inspector** (`src/privacy/inspector_overlay.js`): A live in-browser HUD overlays real-time PII masking counts, DOM execution latency, and client RAM usage for transparent client-side attestation.

---

## 5. The Federation Layer: Differential Privacy & Nightly LoRA

- **Differential Privacy Engine** (`src/federation/differential_privacy.py`): Applies analytic Gaussian noise with configurable L2 clipping norm. Tracks cumulative privacy budget (ε, δ) per client session.

- **Federated Client** (`src/federation/client.py`): Transforms verified daily trajectories into differentially private LoRA weight deltas. Uses deterministic SHA-256 hashing so no raw goal text or URL leaves the device.

- **Nightly Scheduler** (`src/orchestrator/scheduler.py`): `NightlyLoRAScheduler` accumulates successful trajectories throughout the day and runs `FederatedClient.generate_privatized_update()` during off-peak hours to update edge model muscle memory.

---

## 6. The Multi-Agent Layer: Local Swarm Bus

- **LocalMessageBus** (`src/orchestrator/bus.py`): Async in-memory pub/sub + request/response bus. Uses correlation IDs and `asyncio.Future` resolution — **no polling**, no network overhead, sub-millisecond latency.

- **SwarmCoordinator** (`src/agents/swarm.py`): Orchestrates four specialized micro-agents:
  - `DOMSensorAgent` — Maintains indexed element cache from MutationObserver streams.
  - `PrivacySentinelAgent` — Pre-egress PII gatekeeper; raises `PIIRedactionFailure` on violation.
  - `SpeculativeActionAgent` — Sub-500ms fast-path DOM action resolver using ARIA scoring.
  - `VisualGroundingAgent` — OmniParser + foveation fallback for non-DOM targets.

---

## 7. AI Agent Implementation Contracts & Machine Specs

> **Note for AI Coding Agents:** When implementing or refactoring modules in this repository, you MUST adhere strictly to the file paths, JSON schemas, and exception classes defined below. Do not create unmapped helper files or change payload key names.

### A. Code Base File Structure & Responsibility Map

| Module Path | Primary Responsibility | Input Type | Output Type |
| :--- | :--- | :--- | :--- |
| `src/privacy/detector.js` | WebGPU YOLOv8 + Wasm OCR execution | `HTMLVideoElement` / `ImageBitmap` | `Array<PIIBoundingBox>` |
| `src/privacy/canvas_masker.js` | Canvas synthetic SVG vector overlay | `ImageBitmap`, `Array<PIIBoundingBox>` | `Blob` (PNG/WebP Frame) |
| `src/privacy/sanitizer.js` | End-to-end frame sanitization pipeline | Raw frame | Sanitized `Blob` |
| `src/state/snapshot.js` | Fast-path indexed DOM tree extractor | `Document` / `DOM Node` | `IndexedDOMState` (JSON) |
| `src/state/observer.js` | Asynchronous MutationObserver listener | DOM Mutation Events | `MutationRecord` stream |
| `src/state/cso_tracker.py` | Rolling compressed session memory | Session events | Distilled context JSON |
| `src/state/personalization.py` | Local preference retrieval (RAP) | User profile store | Context injection dict |
| `src/vision/foveation.py` | PyTorch irregular grid foveation crop | `Tensor` (Full Image), `TargetCoord` | `Tensor` (Compressed Tokens) |
| `src/vision/omni_parser.py` | Pure visual UI component detection | `np.ndarray` / `Tensor` | `List[VisualElement]` |
| `src/orchestrator/executor.py` | Fast/Slow process action loop & guard | `IndexedDOMState`, `GoalString` | `ActionPayload` |
| `src/orchestrator/bus.py` | In-memory async multi-agent message bus | Topic + payload | Correlated response |
| `src/orchestrator/scheduler.py` | Nightly LoRA fine-tuning scheduler | Trajectory buffer | `FederatedWeightPayload` |
| `src/agents/swarm.py` | Four-agent swarm coordinator | `DOMSnapshot`, `PrivacyReport` | `ActionDecision` |
| `src/federation/differential_privacy.py` | Gaussian noise DP engine | Raw weight delta | Privatized delta + budget |
| `src/federation/client.py` | Federated LoRA update generator | Trajectory list | `FederatedWeightPayload` |
| `src/browser/engine.py` | Playwright browser controller + guards | `ActionPayload` | Execution result |

---

### B. Machine Schemas & Type Contracts

#### 1. Fast-Path Indexed DOM State Schema (`src/state/snapshot.js`)
AI agents generating snapshot code must emit JSON strictly matching this schema:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
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
```

#### 2. Server Action Response Schema (`src/orchestrator/executor.py`)
AI agents building server-side models must format responses strictly as:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
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
```

---

### C. Required Exceptions & Error Handling Class Hierarchy
AI agents MUST import and raise these exact custom exception classes located in `src/orchestrator/exceptions.py`:
```python
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
```