# Project: LiteSight (Edge-Optimized Privacy-First Web Agent)
# Language: STE (Simplified Technical English)

## 1. Project Role & Scope
You are an expert AI systems engineer building LiteSight, a privacy-first, local-first browser agent optimized for heavily constrained hardware (7th-generation Intel i5 processors, 8–12 GB RAM, integrated graphics). You must prioritize zero-trust local visual PII redaction, sub-500ms execution latency via Jev-style DOM indexing, zero token explosion, and non-blocking asynchronous state processing.

## 2. Mandatory Reading
Before writing any code, planning a module, or adding dependencies, you MUST read the following architecture specifications:
* `architecture.md` — Details our Fast-Path DOM Indexing, WebGPU Synthetic Privacy Pipeline, Mathematical Foveation Fallback, Dual-Process (Fast/Slow) Planning, Federated Learning, and Multi-Agent Swarm paradigms.

## 3. Strict Invariants & Boundaries
* **No Polling:** Never write `while True` loops or `time.sleep()` for DOM state changes. You must rely strictly on asynchronous `MutationObserver` callbacks (`src/state/observer.js`) or `LocalMessageBus` async subscriptions (`src/orchestrator/bus.py`).
* **Fast-Path DOM First:** Standard HTML element interactions (buttons, textboxes, dropdowns) must use integer-indexed DOM snapshots (`[1] button`, `[2] combobox`). Never execute a multimodal forward pass for standard DOM controls.
* **On-Device WebGPU Privacy Kernel:** All visual frame egress MUST pass through the local WebGPU PII detection + synthetic masking pipeline (`src/privacy/sanitizer.js`) before network transmission.
* **Context-Preserving Synthetic Masking:** Never transmit raw screenshots or opaque black boxes to the cloud. Sensitive visual elements (faces, passwords, card numbers) must be replaced locally with synthetic, context-preserving vector overlays.
* **No Raw 1080p Screenshots:** Never pass uncropped, full-resolution image tensors to either local or cloud VLMs. Non-DOM elements (Canvas, WebGL, cross-origin iframes) must be cropped using mathematical foveation centered on the interaction point (`src/vision/foveation.py`).
* **Strict Secrets Management:** Never hardcode credentials or API keys. All environment variables (`GROQ_API_KEY`, `OPENROUTER_API_KEY`) MUST be loaded exclusively from the `.env` file via `python-dotenv`.
* **Catch Specific Errors:** Do not use broad `except Exception:` blocks. The dual-process planner requires exact failure states (`ElementObscuredError`, `StaleNodeException`, `CanvasFallbackTrigger`, `PIIRedactionFailure`) defined in `src/orchestrator/exceptions.py` to hand off execution between the indexed DOM parser, local edge VLM, and cloud planner.
* **Dual-Boot Compatibility:** Ensure all local shell commands, browser harness tools, and WebGPU hooks operate natively across Linux and Windows environments.
* **Zero Raw Data Egress in Federation:** The `FederatedClient` (`src/federation/client.py`) must NEVER transmit raw goal strings, URLs, or user tokens. All trajectory data must be converted to anonymous parameter deltas before leaving the device.

## 4. Implementation Status
All four roadmap phases are fully implemented and tested:

| Phase | Status | Key Deliverables |
|-------|--------|-----------------|
| Phase 1: Fast-Path DOM | ✅ Complete | `snapshot.js`, `observer.js`, `cso_tracker.py`, `personalization.py`, `engine.py` |
| Phase 2: WebGPU Privacy | ✅ Complete | `detector.js`, `canvas_masker.js`, `sanitizer.js`, `inspector_overlay.js` |
| Phase 3: Foveated Fallback | ✅ Complete | `foveation.py`, `executor.py`, `exceptions.py` |
| Phase 4: Federation & Swarms | ✅ Complete | `omni_parser.py`, `differential_privacy.py`, `client.py`, `scheduler.py`, `bus.py`, `swarm.py` |

## 5. Context Directory
If you need specific module details, navigate to these files:

| Concept | Location |
|---------|----------|
| System Design & Paradigms | `architecture.md` |
| Dual-Process Orchestrator | `src/orchestrator/executor.py` |
| Custom Exception Hierarchy | `src/orchestrator/exceptions.py` |
| In-Memory Multi-Agent Bus | `src/orchestrator/bus.py` |
| Nightly LoRA Scheduler | `src/orchestrator/scheduler.py` |
| WebGPU Privacy & Synthetic Masking | `src/privacy/sanitizer.js` |
| PII Detector | `src/privacy/detector.js` |
| Canvas Masker | `src/privacy/canvas_masker.js` |
| Live Privacy Inspector HUD | `src/privacy/inspector_overlay.js` |
| Fast-Path DOM Indexer & Observer | `src/state/observer.js` |
| DOM Snapshot Schema | `src/state/snapshot.js` |
| CSO Session Memory | `src/state/cso_tracker.py` |
| RAP Personalization | `src/state/personalization.py` |
| Visual Foveation Fallback | `src/vision/foveation.py` |
| Pure Visual Inference (Zero-DOM) | `src/vision/omni_parser.py` |
| Multi-Agent Swarm Coordinator | `src/agents/swarm.py` |
| Differential Privacy Engine | `src/federation/differential_privacy.py` |
| Federated Learning Client | `src/federation/client.py` |
| Browser Engine & Action Guard | `src/browser/engine.py` |
| Agent Entry Point | `main.py` |