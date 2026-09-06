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

## Architecture Progress

- **Vision (WIP)**: Migrating from random noise tensors to a real, small-scale Multimodal Edge Model (like Moondream2) capable of true spatial coordinate inference.
- **State (Implemented)**: An asynchronous `MutationObserver` (`src/state/observer.js`) tracks DOM changes and pushes absolute spatial coordinates directly to the Python backend via Playwright-style function exposure.
- **Browser (WIP)**: Migrating the headless wrapper (`src/browser/engine.py`) from Lightpanda stubs to a true Playwright-headed browser instance so actions can be visualized.
- **Privacy (Implemented)**: The `StateSanitizer` module scrubs all Personally Identifiable Information (PII) from the local state tree before transmitting context to the cloud.
- **Orchestration (Implemented)**: The dual-process loop (`src/orchestrator/executor.py`) is fully functional. The Slow Planner connects to Groq's high-speed API (Qwen 3.8-27b) for strategic planning, while the Fast Executor relies on local HuggingFace `transformers` models for spatial grounding and muscle-memory execution.
