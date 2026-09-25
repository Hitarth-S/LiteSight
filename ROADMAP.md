# LiteSight Active Engineering Roadmap (Build Tasks)

This roadmap tracks the remaining build deliverables required to transition LiteSight from a local-VLM prototype into a privacy-first, fast-path browser agent.

## Phase 1: Fast-Path DOM Indexer & Speculative Engine

Objective: Build sub-500ms DOM-based navigation to handle 90% of routine web interactions without running heavy local vision passes.

* [ ] **Native JS DOM Indexing Snapshot Parser (`src/state/snapshot.js`)**:
* Build atomic snapshot engine that assigns discrete integer keys to interactable DOM nodes (`[1] button`, `[2] combobox`, `[3] textbox`).

* Extract observed node labels, current values, and ARIA attributes in a single browser protocol call.

* [ ] **Decoupled Cloud Speculative Policy API**:
* Implement single-request action resolver on the server returning combined `Operation + Target Index` JSON payloads (`{"op": "CLICK", "target": 4}`).

* Implement speculative target filtering to ensure click actions only accept compatible element types.

* [ ] **Client Action Execution Guard**:
* Build pre-execution validation layer that re-checks node freshness, element visibility, and click occlusion before dispatching events.

## Phase 2: On-Device WebGPU Synthetic Privacy Kernel

Objective: Implement local visual PII detection and context-preserving synthetic masking to satisfy 40% of the SIH evaluation rubric.

* [ ] **WebGPU Visual PII Detector (`src/privacy/detector.js`)**:
* Port and run an INT8 quantized YOLOv8-Nano object detection model on WebGPU to detect faces, credit cards, and government IDs in real-time.

* Integrate a WebAssembly OCR engine (Tesseract.js / PaddleOCR Wasm) to parse text-based PII across non-DOM/Canvas regions.

* [ ] **Context-Preserving Synthetic Masker (`src/privacy/canvas_masker.js`)**:
* Build HTML5 Canvas overlay engine that visually replaces detected PII bounding boxes with stylized synthetic vector graphics (`[SYNTHETIC_CARD]`, standard avatar glyphs).

* Ensure sanitized frames maintain exact UI element boundaries and context before transmitting images to the cloud VLM.

* [ ] **Dual-Pane Live Sanitization Inspector UI**:
* Build a browser extension side-by-side overlay showing the live raw webpage on the left and the sanitized frame + indexed DOM JSON received by the server on the right.

## Phase 3: Foveated Visual Fallback Engine Integration

Objective: Connect the existing local SmolVLM-256M model strictly as a fallback engine for non-DOM elements.

* [ ] **Non-DOM Target Router**:
* Implement detection filter that flags `<canvas>`, WebGL, SVG charts, or cross-origin iframes and diverts execution from the fast-path indexer to the local visual fallback.

* [ ] **Mathematical Foveation Adapter (`src/vision/foveation.py`)**:
* Connect PyTorch foveation module to extract high-resolution crop patches around targeted non-DOM regions while heavily downsampling surrounding context.

* [ ] **Visual Coordinate Mapper**:
* Map local SmolVLM bounding-box predictions directly to absolute Playwright viewport click coordinates.

## Phase 4: Future Outlook (LiteSight 2.0)

Objective: Post-hackathon scaling, privacy-preserving federated learning, and multi-agent execution.

* [ ] **Pure Visual Inference (Zero-DOM Dependency)**: Transitioning from a Hybrid (DOM+Vision) approach to 100% pixel-to-coordinate mapping (similar to OmniParser).

* [ ] **Privacy-Preserving Federated Learning**: Securely sharing learned workflow LoRA weights across devices using Differential Privacy.

* [ ] **Local Multi-Agent Swarms**: Deconstructing the monolithic edge model into specialized micro-agents communicating over a local message bus.