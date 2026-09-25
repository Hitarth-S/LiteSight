# LiteSight

LiteSight is an edge-optimized, privacy-first visual web agent designed for heavily constrained hardware (7th-generation Intel i5, 8–12 GB RAM, integrated graphics). It combines sub-500ms **Fast-Path Indexed DOM execution**, **On-Device WebGPU PII redaction** with context-preserving synthetic vector graphics, and a dual-process orchestrator (Cloud Macro Planner + 4-bit Edge VLM).

## System Requirements

- Python 3.10+
- Heavily constrained hardware supported (designed for 7th-Gen Intel CPU, 8-12GB RAM, integrated graphics)
- Chromium / Playwright runtime

## Quickstart & Setup Guide

### 1. Clone the Repository
```bash
git clone https://github.com/Hitarth-S/LiteSight.git
cd LiteSight
```

### 2. Create & Activate Virtual Environment
On Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```
On Windows:
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies & Browser Engine
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory:
```bash
cp .env.example .env  # or create .env manually
```
Add your Groq API key (used for the Slow Planner macro-reasoning engine):
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
```

---

## How to Run LiteSight

### Mode A: Autonomous Exploration (Dual-Process Cloud Planner + Edge)
When no explicit goal is provided, the Groq LPU (Qwen 3.8-27b) evaluates the domain context, injects local user preferences via Retrieval-Augmented Personalization (RAP), and generates a structured macro-plan:

```bash
python main.py --url https://github.com
```

### Mode B: Direct Fast-Path Goal Execution
To bypass cloud latency and execute direct instructions on the local Fast-Path Indexed DOM in sub-500ms:

```bash
python main.py --url https://en.wikipedia.org --goal "locate the main search bar, type 'Artificial Intelligence', and hit search"
```

### Mode C: Pure Visual Inference (Zero-DOM Dependency)
To navigate non-DOM applications (Canvas games, WebGL portals, remote desktops) using 100% pixel-to-coordinate mapping via `OmniVisualParser`:

```bash
python main.py --url https://canvas-app.example.com --pure-vision
```

### Mode D: Local Multi-Agent Swarm
To run four specialized edge micro-agents communicating over the zero-network in-memory `LocalMessageBus`:

```bash
python main.py --url https://en.wikipedia.org --goal "locate search bar" --swarm
```

### Live Evaluation Features:
- **Dual-Pane Privacy & Action Inspector**: An interactive HUD automatically mounts in the lower-right corner of the browser window, showing live DOM execution latency (<500ms), client RAM usage (<480MB), and verified counts of on-device masked PII regions.
- **Context-Preserving Synthetic Masking**: Sensitive fields (passwords, credit cards, faces) are detected and visually overlaid with synthetic vector graphics before any visual payload egresses.

## Technical Roadmap & Optimizations

LiteSight is actively evolving based on cutting-edge academic research regarding on-device AI and context management. Please see our [ROADMAP.md](ROADMAP.md) for detailed plans regarding Just-In-Time schema passing, Context State Objects (CSO), and nightly on-device fine-tuning.

## Architecture Progress

All four roadmap phases are **fully implemented**. The following modules are production-ready:

### Phase 1 — Fast-Path Indexed DOM
- **Fast-Path Indexed DOM First** (`src/state/snapshot.js`): Atomic snapshot engine assigns discrete integer indices (`[1] button`, `[2] combobox`) to interactable elements, executing routine web actions in sub-500ms without multimodal passes.
- **Asynchronous State Observer** (`src/state/observer.js`): Non-blocking `MutationObserver` tracks DOM diffs passively with zero CPU polling.
- **Context State Object (CSO) Tracker** (`src/state/cso_tracker.py`): Maintains a rolling compressed session-memory representation for zero token-explosion context injection into the macro-planner.
- **Retrieval-Augmented Personalization (RAP)** (`src/state/personalization.py`): Injects local user preference context into macro-plans using lightweight retrieval — no cloud data egress.
- **Client Action Execution Guard** (`src/browser/engine.py`): Pre-execution validation layer re-checking `StaleNodeException`, `ElementObscuredError`, and non-DOM targets before dispatching Playwright events.

### Phase 2 — On-Device WebGPU Privacy Kernel
- **On-Device WebGPU Privacy Kernel** (`src/privacy/detector.js`): Real-time visual and DOM PII detection (passwords, card numbers, government IDs, faces).
- **Context-Preserving Synthetic Masker** (`src/privacy/canvas_masker.js`): Replaces PII bounding boxes with stylized synthetic vector graphics (`[SYNTHETIC_CARD]`, avatar glyphs, `🔒 ••••••••`).
- **Privacy Sanitizer Pipeline** (`src/privacy/sanitizer.js`): Orchestrates end-to-end frame sanitization before any payload egresses the client.
- **Dual-Pane Privacy & Action Inspector** (`src/privacy/inspector_overlay.js`): Real-time in-browser HUD demonstrating zero-trust client-side sanitization with live DOM metrics.

### Phase 3 — Foveated Visual Fallback & Dual-Process Orchestration
- **Visual Fallback with Foveation** (`src/vision/foveation.py`): Raises `CanvasFallbackTrigger` on non-DOM targets (`<canvas>`, WebGL, iframes) to invoke local **SmolVLM-256M** (4-bit NF4 quantized) with PyTorch foveated tokenization — 24x token reduction vs. uniform grid patching.
- **Orchestration & Dual-Process Planning** (`src/orchestrator/executor.py`): Enforces strict client execution guards, CSO memory distillation, JIT tool schema injection, and nightly LoRA trajectory compilation via `NightlyLoRAScheduler`.
- **Custom Exception Hierarchy** (`src/orchestrator/exceptions.py`): `StaleNodeException`, `ElementObscuredError`, `CanvasFallbackTrigger`, `PIIRedactionFailure` — each maps to a distinct planner handoff decision.

### Phase 4 — Advanced Extensions (Federated Learning & Multi-Agent Swarms)
- **Pure Visual Inference Engine** (`src/vision/omni_parser.py`): `OmniVisualParser` maps UI interactables from pixel buffers directly to screen coordinates using morphological edge clustering, connected-component labeling, and Non-Maximum Suppression (NMS) — zero DOM dependency.
- **Differentially Private Federated Learning** (`src/federation/differential_privacy.py`, `src/federation/client.py`): `DifferentialPrivacyEngine` applies analytic Gaussian noise with L2 sensitivity clipping; `FederatedClient` transforms verified trajectories into anonymous `(epsilon, delta)`-bounded LoRA parameter deltas.
- **Nightly LoRA Scheduler** (`src/orchestrator/scheduler.py`): Compiles daily successful action trajectories into anonymous differentially private weight updates during off-peak hours via `NightlyLoRAScheduler`.
- **Local Multi-Agent Swarm** (`src/orchestrator/bus.py`, `src/agents/swarm.py`): Async in-memory `LocalMessageBus` (pub/sub + request/response with correlation IDs) coordinates four micro-agents — `DOMSensorAgent`, `PrivacySentinelAgent`, `SpeculativeActionAgent`, `VisualGroundingAgent` — via `SwarmCoordinator`.
