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

LiteSight uses a dual-process architecture (Fast Executor and Slow Planner). To start the agent and view the execution flow, run the main entry point:

```bash
python main.py
```

## Architecture Progress

- **Vision (Implemented)**: PyTorch-based foveated tokenization (`src/vision/foveation.py`) successfully extracts high-res center patches and downsampled irregular grids, preventing token explosion.
- **State (Implemented)**: Asynchronous `MutationObserver` (`src/state/observer.js`) tracks DOM changes and pushes them directly to the Python backend via Playwright-style function exposure.
- **Browser (Implemented)**: Headless engine wrapper (`src/browser/engine.py`) using `lightpanda`, binding the JS context for zero-polling state diffing.
- **Orchestration (WIP)**: The heavy LLM (Slow Planner) and lightweight edge model (Fast Executor) loops are structurally complete in `src/orchestrator/executor.py`, awaiting the final model integrations.
