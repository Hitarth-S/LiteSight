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

### Live Evaluation Features:
- **Dual-Pane Privacy & Action Inspector**: An interactive HUD automatically mounts in the lower-right corner of the browser window, showing live DOM execution latency (<500ms), client RAM usage (<480MB), and verified counts of on-device masked PII regions.
- **Context-Preserving Synthetic Masking**: Sensitive fields (passwords, credit cards, faces) are detected and visually overlaid with synthetic vector graphics before any visual payload egresses.

## Technical Roadmap & Optimizations

LiteSight is actively evolving based on cutting-edge academic research regarding on-device AI and context management. Please see our [ROADMAP.md](ROADMAP.md) for detailed plans regarding Just-In-Time schema passing, Context State Objects (CSO), and nightly on-device fine-tuning.

## Architecture Progress

- **Fast-Path Indexed DOM First (Implemented)**: Atomic snapshot engine (`src/state/snapshot.js`) assigns discrete integer indices (`[1] button`, `[2] combobox`) to interactable elements, executing routine web actions in sub-500ms without multimodal passes.
- **On-Device WebGPU Privacy Kernel (Implemented)**: Real-time visual and DOM PII detection (`src/privacy/detector.js`) and context-preserving synthetic vector masking (`src/privacy/canvas_masker.js`) replacing sensitive data with stylized vectors (`[SYNTHETIC_CARD]`, standard avatar silhouettes, `🔒 ••••••••`).
- **Dual-Pane Privacy & Action Inspector (Implemented)**: Real-time in-browser HUD overlay (`src/privacy/inspector_overlay.js`) demonstrating zero-trust client-side sanitization side-by-side with live DOM metrics.
- **Visual Fallback with Foveation (Implemented)**: Automatically raises `CanvasFallbackTrigger` on non-DOM (`<canvas>`, WebGL, iframes) to invoke local **SmolVLM-256M** (4-bit NF4 quantized) with PyTorch foveated tokenization (`src/vision/foveation.py`).
- **State & Asynchronous Observer (Implemented)**: Non-blocking `MutationObserver` (`src/state/observer.js`) tracks DOM diffs passively without CPU polling.
- **Orchestration & Dual-Process Planning (Implemented)**: The dual-process loop (`src/orchestrator/executor.py`) enforces strict client execution guards (`src/orchestrator/exceptions.py`), with CSO memory distillation, JIT tool injection, and nightly LoRA trajectory compilation.
