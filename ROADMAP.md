# LiteSight Technical Roadmap

This roadmap outlines the strategic optimization path for LiteSight, heavily inspired by cutting-edge academic research on on-device LLMs, adaptive context management, and edge-cloud synergy.

## Phase 1: Adaptive Context Management
*Objective: Eliminate context bloat and O(n) memory growth during continuous browser execution.*

- [x] **Mathematical Foveation**: PyTorch-based vision splitting to avoid full-frame token explosion.
- [ ] **Just-In-Time (JIT) Schema Passing**: Instead of loading the full API schema of all tools, the agent receives a concise "Tool Bank". Full schemas are only injected *after* the agent selects a tool.
- [ ] **Context State Objects (CSO)**: Implement a secondary distillation process that compresses raw, verbose DOM history into a dense, append-only Key-Value checklist (e.g., `user_goal: login, status: waiting_for_auth`).
- [ ] **KV Cache Pruning**: Separate context into `Permanent` (CSO) and `Ephemeral` (verbose HTML). Evict ephemeral tokens from the KV cache after every turn to maintain a flat memory footprint.

## Phase 2: On-Device Personalization & Autonomy
*Objective: Enable the agent to learn user habits securely on-device without cloud reliance.*

- [ ] **Retrieval-Augmented Personalization (RAP)**: Build a lightweight local Vector Database (e.g., FAISS/Chroma) to store user preferences and browser habits, retrieving them dynamically during execution.
- [ ] **Nightly LoRA Fine-Tuning**: Implement a local scheduler to perform parameter-efficient fine-tuning (LoRA) on the edge model during off-peak hours using the day's successful trajectories.

## Phase 3: Hardware Acceleration
*Objective: Maximize computational throughput on strictly constrained edge devices (e.g., 7th-Gen Intel i5, 12GB RAM).*

- [ ] **4-bit AWQ / GPTQ Quantization**: Compress the SmolVLM-256M weights from `fp32` to 4-bit, dropping RAM usage from ~1GB to ~300MB while preserving reasoning capabilities via activation-aware quantization.
- [ ] **Collaborative Sharding**: Implement dynamic routing to split inference chunks between the local edge model and the cloud planner for tasks of intermediate complexity.
