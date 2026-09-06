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

3. Install the dependencies (ensure you have a lightweight headless engine like Lightpanda installed):
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: Add your specific dependencies to `requirements.txt` as they are finalized).*

## Usage

LiteSight uses a dual-process architecture (Fast Executor and Slow Planner). To start the agent, run the orchestrator:

```bash
python -m src.orchestrator.executor
```

*(Note: Provide the target URL or domain context as an argument if supported by your entry point).*

## Architecture Highlights

- **Vision**: Uses foveated tokenization (`src/vision/foveation.py`) to extract high-res patches at interaction points while down-sampling the rest, preventing token explosion.
- **State**: Uses a passive `MutationObserver` (`src/state/observer.js`) for non-blocking UI state diffing instead of polling full-page snapshots.
- **Orchestration**: Splits tasks between a heavy LLM (Slow Planner) and a lightweight edge model (Fast Executor) inside `src/orchestrator/executor.py`.
