# LiteSight Active Engineering Roadmap (Build Tasks)

This roadmap tracks the remaining build deliverables required to transition LiteSight from a local-VLM prototype into a privacy-first, fast-path browser agent.

## Phase 1: Fast-Path DOM Indexer & Speculative Engine

Objective: Build sub-500ms DOM-based navigation to handle 90% of routine web interactions without running heavy local vision passes.

* [x] **Native JS DOM Indexing Snapshot Parser (`src/state/snapshot.js`)**:
* Built atomic snapshot engine assigning discrete integer keys to interactable DOM nodes (`[1] button`, `[2] combobox`, `[3] textbox`).
* Extracts observed node labels, current values, and ARIA attributes in a single browser call conforming to Section 7.B.1 schema.

* [x] **Decoupled Cloud Speculative Policy API (`src/orchestrator/executor.py`)**:
* Implemented single-request action resolver returning combined `Operation + Target Index` JSON payloads (`{"operation": "CLICK", "target_index": 4}`).
* Implemented speculative target filtering ensuring click/type actions only accept compatible element types.

* [x] **Client Action Execution Guard (`src/browser/engine.py`)**:
* Built pre-execution validation layer that re-checks node freshness (`StaleNodeException`), element visibility/occlusion (`ElementObscuredError`), and non-DOM targets before dispatching events.

## Phase 2: On-Device WebGPU Synthetic Privacy Kernel

Objective: Implement local visual PII detection and context-preserving synthetic masking to satisfy 40% of the SIH evaluation rubric.

* [x] **WebGPU Visual PII Detector (`src/privacy/detector.js`)**:
* Built local PII detector scanning DOM & canvas for passwords, credit card numbers, government IDs, and avatar/face regions in real-time.
* Integrated local heuristic pattern recognition and WebGPU initialization hooks.

* [x] **Context-Preserving Synthetic Masker (`src/privacy/canvas_masker.js`)**:
* Built HTML5 Canvas overlay engine that visually replaces detected PII bounding boxes with stylized synthetic vector graphics (`[SYNTHETIC_CARD]`, standard avatar glyphs, `🔒 ••••••••`).
* Guarantees sanitized frames maintain exact UI boundaries and context without opaque black boxes.

* [x] **Dual-Pane Live Sanitization Inspector UI (`src/privacy/inspector_overlay.js`)**:
* Built live in-browser HUD showing real-time metrics (RAM <480MB, sub-500ms latency) and visual proof of local PII masking.

## Phase 3: Foveated Visual Fallback Engine Integration

Objective: Connect the existing local SmolVLM-256M model strictly as a fallback engine for non-DOM elements.

* [x] **Non-DOM Target Router (`src/orchestrator/exceptions.py`, `src/browser/engine.py`)**:
* Implemented detection filter that flags `<canvas>`, WebGL, or cross-origin iframes and raises `CanvasFallbackTrigger` to divert execution to local visual fallback.

* [x] **Mathematical Foveation Adapter (`src/vision/foveation.py`)**:
* Connected PyTorch foveation module to extract high-resolution crop patches around targeted non-DOM regions while heavily downsampling surrounding context.

* [x] **Visual Coordinate Mapper (`src/orchestrator/executor.py`)**:
* Mapped local SmolVLM foveation and spatial layout grounding directly to Playwright viewport coordinates.

## Phase 4: Future Outlook (LiteSight 2.0)

Objective: Post-hackathon scaling, privacy-preserving federated learning, and multi-agent execution.

* [ ] **Pure Visual Inference (Zero-DOM Dependency)**: Transitioning from a Hybrid (DOM+Vision) approach to 100% pixel-to-coordinate mapping (similar to OmniParser).

* [ ] **Privacy-Preserving Federated Learning**: Securely sharing learned workflow LoRA weights across devices using Differential Privacy.

* [ ] **Local Multi-Agent Swarms**: Deconstructing the monolithic edge model into specialized micro-agents communicating over a local message bus.