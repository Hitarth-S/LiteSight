# LiteSight Technical Roadmap

This roadmap outlines the strategic optimization path for LiteSight, heavily inspired by cutting-edge academic research on on-device LLMs, adaptive context management, and edge-cloud synergy.

## Phase 1: Adaptive Context Management
*Objective: Eliminate context bloat and O(n) memory growth during continuous browser execution.*

- [x] **Mathematical Foveation**: PyTorch-based vision splitting to avoid full-frame token explosion.
- [x] **Just-In-Time (JIT) Schema Passing**: Instead of loading the full API schema of all tools, the agent receives a concise "Tool Bank". Full schemas are only injected *after* the agent selects a tool.
- [x] **Context State Objects (CSO)**: Implement a secondary distillation process that compresses raw, verbose DOM history into a dense, append-only Key-Value checklist (e.g., `user_goal: login, status: waiting_for_auth`).
- [x] **KV Cache Pruning**: Separate context into `Permanent` (CSO) and `Ephemeral` (verbose HTML). Evict ephemeral tokens from the KV cache after every turn to maintain a flat memory footprint.

## Phase 2: On-Device Personalization & Autonomy
*Objective: Enable the agent to learn user habits securely on-device without cloud reliance.*

- [x] **Retrieval-Augmented Personalization (RAP)**: Build a lightweight local Vector Database (e.g., FAISS/Chroma) to store user preferences and browser habits, retrieving them dynamically during execution.
- [x] **Nightly LoRA Fine-Tuning**: Implement a local scheduler to perform parameter-efficient fine-tuning (LoRA) on the edge model during off-peak hours using the day's successful trajectories.

## Phase 3: Hardware Acceleration
*Objective: Maximize computational throughput on strictly constrained edge devices (e.g., 7th-Gen Intel i5, 12GB RAM).*

- [x] **4-bit AWQ / GPTQ Quantization**: Compress the SmolVLM-256M weights from `fp32` to 4-bit, dropping RAM usage from ~1GB to ~300MB while preserving reasoning capabilities via activation-aware quantization.
- [x] **Collaborative Sharding**: Implement dynamic routing to split inference chunks between the local edge model and the cloud planner for tasks of intermediate complexity.

## Phase 4: Future Outlook (LiteSight 2.0)
*Objective: Push the boundaries of on-device autonomy, privacy, and architectural resilience.*

- [ ] **Pure Visual Inference (Zero-DOM Dependency)**: Transitioning from a Hybrid (DOM+Vision) approach to 100% pixel-to-coordinate mapping (similar to OmniParser). This eliminates reliance on the DOM entirely, making the agent immune to anti-bot obfuscation, dynamic React virtual DOMs, and opaque `<canvas>` elements.
- [ ] **Privacy-Preserving Federated Learning**: While the current Nightly LoRA scheduler learns locally, the next step is securely sharing these learned workflow "weights" across thousands of LiteSight devices using Differential Privacy. This creates a globally smarter agent without ever transmitting a single pixel of personal user data.
- [ ] **Local Multi-Agent Swarms**: Deconstructing the monolithic edge model into a local network of specialized "Micro-Agents" (e.g., a 100M parameter model strictly for CAPTCHA solving, another for tabular data extraction). These micro-agents will communicate via a local message bus, significantly reducing power consumption and inference time compared to generalized models.
