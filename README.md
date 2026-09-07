# LiteSight

> **Branch: `main` (Active Development)**
> This branch is currently undergoing migration to integrate a headed Playwright browser (replacing the Lightpanda stub) and a real, lightweight Multimodal Edge Model (e.g., Qwen-VL or Moondream2) to execute real DOM interactions visually on-device. If you want the purely architectural structural code (stubbed), see the `skeleton` branch.

LiteSight is a local-first visual browser agent designed for constrained hardware. It minimizes VRAM usage and avoids token explosion by using foveated tokenization and relying on non-blocking DOM mutation tracking.

## Requirements

- Python 3.10+
- Heavily constrained hardware (designed for 7th-Gen Intel CPU, 12GB RAM, integrated graphics)

## Architecture Overview

1. **Slow, Heavy Logic Planner**: Cloud-based (using Groq) reasoning model that runs occasionally to plot macro-goals and sub-tasks based on compressed context.
2. **Fast, Reactive Executor**: Extremely small, on-device Edge model (CPU/RAM bound) running in a fast `while(true)` loop to handle muscle-memory UI interactions (scrolling, clicking).
3. **Foveated Tokenization**: Instead of sending full 1080p frame sequences to the LLMs (which causes token explosion), the agent splits vision into a high-res center patch (fovea) and a massively down-sampled contextual grid.

## Usage

LiteSight uses a dual-process architecture (Fast Executor and Slow Planner). It operates as a Command Line Interface (CLI). To run the agent, specify a target URL:

```bash
python main.py --url https://github.com
```

If you wish to bypass the cloud-based Slow Planner and test the local Edge Model immediately, you can provide an explicit goal:

```bash
python main.py --url https://github.com --goal "click_login_button"
```

## Technical Roadmap & Optimizations

LiteSight is actively evolving based on cutting-edge academic research regarding on-device AI and context management. Please see our [ROADMAP.md](ROADMAP.md) for detailed plans regarding Just-In-Time schema passing, Context State Objects (CSO), and nightly on-device fine-tuning.

## Architecture Progress

- **Vision (Implemented)**: Successfully migrated to **SmolVLM-256M-Instruct**, running locally in **4-bit NF4 Quantization** via `bitsandbytes`, keeping RAM usage strictly under 500MB on edge devices.
- **State (Implemented)**: An asynchronous `MutationObserver` (`src/state/observer.js`) tracks DOM changes and pushes absolute spatial coordinates directly to the Python backend via Playwright-style function exposure.
- **Browser (Implemented)**: Migrated to a true **Playwright headed browser instance**, allowing full visual observation of the agent's actions on real web pages.
- **Privacy & Personalization (Implemented)**: 
  - **StateSanitizer**: Scrubs all Personally Identifiable Information (PII) before cloud transmission.
  - **Retrieval-Augmented Personalization (RAP)**: Injects local user preferences (e.g., dark mode, cookie rejection) into context dynamically without uploading data.
- **Orchestration (Implemented)**: The dual-process loop (`src/orchestrator/executor.py`) is fully functional with advanced memory management:
  - **Cloud Planner**: Qwen 3.8-27b (via Groq API) for high-level logic.
  - **Edge Executor**: Local SmolVLM for spatial grounding and muscle-memory UI execution.
  - **Context State Objects (CSO)**: Compresses raw DOM history into dense key-value checklists to prevent memory bloat.
  - **Just-In-Time (JIT) Tooling**: Dynamically injects function schemas only when needed to optimize prompt size and inference latency.
  - **Nightly LoRA Scheduler**: Logs successful trajectories daily and queues them for off-peak parameter-efficient fine-tuning on the local device.
