1. Dual-Process Orchestration (Thinking Fast & Slow)

The system must be split into a High-Level Planner (Heavy LLM) and a Reactive Executor (Lightweight Edge Model).

    The Slow Planner: When a new domain is accessed, the heavy LLM generates a structured JSON array of sub-goals (e.g., ["locate_login", "enter_credentials", "verify_2fa"]).

    The Fast Executor: The lightweight edge model operates in a closed loop, executing the current sub-goal using muscle memory and returning a complete or failed status.

    The Handoff: The Planner remains dormant to save compute, waking only when the Fast Executor returns a failed state indicating an unexpected layout or an empty DOM.

2. The Vision Layer: Foveated Tokenization

To eliminate token explosion, the visual module must abandon uniform grid patching and implement foveated tokenization, operating on the principle that a coarse view guides where to look, while selectively acquired high-resolution evidence refines what to think.

    Irregular Grid Processing: The module extracts high-resolution patches centered strictly on the active interaction point and progressively downsamples surrounding patches on an irregular grid.

    Bandwidth Optimization: This approach preserves visual context while reducing the overall pixel and token count by roughly 24x compared to traditional uniform inputs.

    API Contract: The Fast Executor must pass a specific (x, y) coordinate (the foveation center) to the Vision API, which will return the compressed foveated token array rather than a standard 1080p image tensor.

3. The State Layer: MutationObserver Diffing

The agent must never capture back-to-back full-page DOM snapshots. The State Layer must rely exclusively on the browser's native MutationObserver Web API to monitor changes in a non-blocking manner.

    Configuration: The observer must be configured to track childList (for added/removed nodes), attributes (for state changes like disabled or hidden), and characterData (for text modifications).

    Batch Processing: Instead of polling the DOM for changes, the agent must passively listen for the callback function, which will receive an array of MutationRecord objects detailing only what changed since the last action.

    Reconciliation: The execution loop updates a local, lightweight state tree using these mutation records, ensuring the agent always acts on the current UI state with zero redundant parsing overhead.