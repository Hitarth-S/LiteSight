# LiteSight: Developer & Agent Guidelines

This document contains rules and boundaries for engineers and AI agents working on the LiteSight codebase.

---

## 1. Primary Objectives

LiteSight is a privacy-first browser agent for the Smart India Hackathon (SIH). The system must maintain:
1. **Zero Raw Data Egress**: Passwords, credit cards, emails, and sensitive identifiers must never leave the client machine in unredacted form.
2. **Sub-500ms Edge Execution**: Standard web actions (`CLICK`, `TYPE_TEXT`, `SELECT`) must execute in under 500ms using the indexed DOM fast path.
3. **Low Client Resource Utilization**: The client runs in consumer browsers. Do not use polling loops. Do not run heavy machine learning models on the browser UI thread.

---

## 2. Mandatory Rules & Invariants

- **No Polling**: Do not use `while True` sleep loops for DOM state changes. Use `MutationObserver` callbacks ([`src/state/observer.js`](src/state/observer.js)) or message bus events ([`src/orchestrator/bus.py`](src/orchestrator/bus.py)).
- **Indexed DOM First**: Standard HTML controls (buttons, inputs, dropdowns) must use integer indices (`[0]`, `[1]`). Do not invoke multimodal models for standard DOM elements.
- **Client-Side Redaction**: All data sent to `server.py` must pass through [`sanitizer.js`](src/privacy/sanitizer.js) or [`sanitizer.py`](src/state/sanitizer.py).
- **No Synchronous Reflows**: Use `el.textContent` instead of `el.innerText` when scanning DOM collections. `innerText` triggers synchronous layout calculations.
- **Escape DOM Queries**: When querying elements by index or attribute, always wrap values with `CSS.escape()`.
- **Catch Specific Exceptions**: Do not use bare `except Exception:` blocks. Raise and catch defined exceptions from [`src/orchestrator/exceptions.py`](src/orchestrator/exceptions.py).
- **Retain Async Tasks**: When creating background tasks with `asyncio.create_task()`, store the task in a set to prevent premature garbage collection.
- **URL Validation**: Verify URL schemes using case-insensitive checks (`url.lower().startswith(("http://", "https://"))`).
- **No Git Commits / Pushes**: Keep local changes uncommitted on branch `development` unless explicitly asked by the user.

---

## 3. Directory Map

| Directory | Purpose |
| :--- | :--- |
| `extension/` | Manifest V3 browser extension (Client UI, WebGPU detector, DOM bridge) |
| `scripts/` | `train_ui_patterns.py` (cross-site UI pattern learner) and domain corpus |
| `server.py` | Centralized reasoning server (`/api/step`, `/api/settings`, `/health`) |
| `src/browser/` | Playwright browser engine, action executor, and tab manager |
| `src/privacy/` | PII detector, canvas masker, and visual indicator overlays |
| `src/orchestrator/` | Reactive executor, planner, exceptions, and local message bus |
| `src/knowledge/` | `ui_patterns.json` (learned statistical weights and keywords) |
| `src/state/` | `snapshot.js` (DOM indexer), `observer.js`, `sanitizer.py`, `cso_tracker.py` |
| `src/vision/` | `foveation.py` and `omni_parser.py` (visual fallback engine) |
| `src/agents/` | `swarm.py` (multi-agent edge swarm architecture) |
| `src/federation/` | `differential_privacy.py` and `client.py` |
| `tests/` | Unit and integration tests (32 tests passing) |

---

## 4. Test Verification Command

Run the complete test suite before submitting changes:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/ -v
```