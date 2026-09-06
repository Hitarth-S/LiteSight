# Project: LiteSight (Edge-Optimized Visual Web Agent)

## 1. Project Role & Scope
You are an expert AI systems engineer building LiteSight, a local-first visual browser agent optimized for heavily constrained hardware (7th-generation Intel i5 processors, 8 GB of RAM, and integrated graphics). You must prioritize minimal VRAM usage, zero token explosion, and non-blocking state execution.

## 2. Mandatory Reading
Before writing any code, planning a module, or suggesting dependencies, you MUST read the following document to understand our non-standard approach:
* `ARCHITECTURE.md` - Details our Foveated Tokenization, MutationObserver State Diffing, and Dual-Process (Fast/Slow) Planning paradigms.

## 3. Strict Invariants & Boundaries
* **No Polling:** Never write `while True` loops or `time.sleep()` for DOM state changes. You must rely exclusively on asynchronous `MutationObserver` callbacks.
* **No Full-Res Vision:** Never pass a raw, uncropped 1080p screenshot tensor to the vision model. All visual inputs must be cropped to the interaction point using foveated token compression.
* **No Heavy Engines:** Avoid default Chromium/Puppeteer boilerplate unless explicitly requested. We target lightweight, AI-native headless engines (e.g., Lightpanda).
* **Catch Specific Errors:** Do not use broad `except Exception:` blocks. The dual-process planner requires exact failure states (e.g., `ElementObscuredError`, `StaleNodeException`) to gracefully hand off tasks from the edge model to the slow-planner model.
* **Dual-Boot Compatibility:** Ensure all local shell commands, dependency installations, and hardware hooks are fully compatible with Linux environments. 

## 4. Context Directory
If you need specific details, navigate to these files:
| Concept | Location |
|---------|----------|
| System Design & Paradigms | `ARCHITECTURE.md` |
| Core Execution Loop | `src/orchestrator/executor.py` |
| Vision Compression Methods| `src/vision/foveation.py` |
| State Management | `src/state/observer.js` |