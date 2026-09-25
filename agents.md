# Project: LiteSight (Edge-Optimized Privacy-First Web Agent)
# Language: STE (Simplified Technical English)

## 1. Project Role & Scope
You are an expert AI systems engineer building LiteSight, a privacy-first, local-first browser agent optimized for heavily constrained hardware (7th-generation Intel i5 processors, 8–12 GB RAM, integrated graphics)[cite: 1, 2, 4]. You must prioritize zero-trust local visual PII redaction, sub-500ms execution latency via Jev-style DOM indexing, zero token explosion, and non-blocking asynchronous state processing[cite: 1, 2, 3].

## 2. Mandatory Reading
Before writing any code, planning a module, or adding dependencies, you MUST read the following architecture specifications:
* `ARCHITECTURE.md` - Details our Fast-Path DOM Indexing, WebGPU Synthetic Privacy Pipeline, Mathematical Foveation Fallback, and Dual-Process (Fast/Slow) Planning paradigms[cite: 1, 2, 3].

## 3. Strict Invariants & Boundaries
* **No Polling:** Never write `while True` loops or `time.sleep()` for DOM state changes[cite: 2]. You must rely strictly on asynchronous `MutationObserver` callbacks (`src/state/observer.js`)[cite: 2, 3].
* **Fast-Path DOM First:** Standard HTML element interactions (buttons, textboxes, dropdowns) must use integer-indexed DOM snapshots (`[1] button`, `[2] combobox`)[cite: 3]. Never execute a multimodal forward pass for standard DOM controls[cite: 1, 3].
* **On-Device WebGPU Privacy Kernel:** All visual frame egress MUST pass through the local WebGPU YOLOv8-Nano / Wasm-OCR pipeline before network transmission[cite: 1, 4]. 
* **Context-Preserving Synthetic Masking:** Never transmit raw screenshots or opaque black boxes to the cloud[cite: 1, 2, 4]. Sensitive visual elements (faces, passwords, card numbers) must be replaced locally with synthetic, context-preserving vector overlays[cite: 1, 4].
* **No Raw 1080p Screenshots:** Never pass uncropped, full-resolution image tensors to either local or cloud VLMs[cite: 2]. Non-DOM elements (Canvas, WebGL, cross-origin iframes) must be cropped using mathematical foveation centered on the interaction point[cite: 1, 2, 3].
* **Strict Secrets Management:** Never hardcode credentials or API keys[cite: 2]. All environment variables (`GROQ_API_KEY`, `OPENROUTER_API_KEY`) MUST be loaded exclusively from the `.env` file via `python-dotenv`[cite: 2].
* **Catch Specific Errors:** Do not use broad `except Exception:` blocks[cite: 2]. The dual-process planner requires exact failure states (`ElementObscuredError`, `StaleNodeException`, `CanvasFallbackTrigger`) to hand off execution between the indexed DOM parser, local edge VLM, and cloud planner[cite: 2, 3].
* **Dual-Boot Compatibility:** Ensure all local shell commands, browser harness tools, and WebGPU hooks operate natively across Linux and Windows environments[cite: 2].

## 4. Context Directory
If you need specific module details, navigate to these files:
| Concept | Location |
|---------|----------|
| System Design & Paradigms | `ARCHITECTURE.md`[cite: 2] |
| Dual-Process Orchestrator | `src/orchestrator/executor.py`[cite: 2] |
| WebGPU Privacy & Synthetic Masking | `src/privacy/sanitizer.js`[cite: 2, 4] |
| Fast-Path DOM Indexer & Observer | `src/state/observer.js`[cite: 2] |
| Visual Foveation Fallback | `src/vision/foveation.py`[cite: 2] |