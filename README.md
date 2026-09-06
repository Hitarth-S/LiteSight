# LiteSight

LiteSight is a local-first visual browser agent designed for constrained hardware. It minimizes VRAM usage and avoids token explosion by using foveated tokenization and relying on non-blocking DOM mutation tracking.

## Requirements

- Python 3.10+
- Linux environment
- Node.js (for testing the JS observer script, optional)

## Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone <repository_url>
   cd LiteSight
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. Install the dependencies. To prevent disk quota issues and respect the hardware constraints (no GPU needed), we install the CPU-only version of PyTorch:
   ```bash
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements.txt
   ```

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

- **Vision (Implemented)**: PyTorch-based foveated tokenization (`src/vision/foveation.py`) extracts high-resolution center patches and down-sampled irregular grids, thereby preventing token explosion on constrained hardware.
- **State (Implemented)**: An asynchronous `MutationObserver` (`src/state/observer.js`) tracks DOM changes and pushes absolute spatial coordinates directly to the Python backend via Playwright-style function exposure.
- **Browser (Implemented)**: A headless engine wrapper (`src/browser/engine.py`) uses `lightpanda` to bind the JavaScript context, enabling zero-polling state diffing.
- **Privacy (Implemented)**: The `StateSanitizer` module scrubs all Personally Identifiable Information (PII) from the local state tree before transmitting context to the cloud.
- **Orchestration (Implemented)**: The dual-process loop (`src/orchestrator/executor.py`) is fully functional. The Slow Planner connects to Groq's high-speed API (Llama-3 70B) for strategic planning, while the Fast Executor relies on local HuggingFace `transformers` models for spatial grounding and muscle-memory execution.
