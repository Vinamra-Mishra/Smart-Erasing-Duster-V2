# Original User Request

## Initial Request — 2026-09-17T13:34:15Z

Build the software-only Digital Twin prototype for the Smart Erasing Duster (V2.1) in `ECS_V2/V2.1`, featuring an event-sourced pure reducer reconciler, dual-channel transport (RTP video streaming + WebSocket telemetry/event bus), config-driven dynamic duster/board dimensions, multi-tier residual handling, baseline epoch validation, and an interactive React simulation dashboard adhering strictly to clean vector SVG iconography.

Working directory: `c:\Users\vkmuk\OneDrive\Documents\Project\ECS_V2\V2.1`
Integrity mode: development
Python Virtual Environment: `C:\Users\vkmuk\OneDrive\Documents\Project\.venv`

## Skill Directives (`.agents` Skills Integration)
- **`fastapi-pro` & `async-python-patterns`**: Architect high-performance async endpoints, lifespan handlers, and non-blocking background workers.
- **`computer-vision-expert`**: Implement homography registration in `FRAME_BOARD`, multi-space diffs (RGB, HSV, Lab), shadow chrominance ratio filtering, and multi-signal temporal occlusion without MOG2.
- **`react-patterns` & `zustand-store-ts`**: Build modular React components with strictly typed Zustand stores for physical twin mirroring and event dispatching.
- **`ui-ux-pro-max` & User Global Rules**: Zero emojis or raw unicode symbols anywhere in the web UI. Strictly use clean vector SVGs with `currentColor` and consistent stroke width.
- **`pytest-skill`**: Construct comprehensive, parameterized pytest suites covering all 21 rows of the Truth Table, safety caps, and homography accuracy.
- **`clean-code-guard`**: Enforce strict separation of concerns (Physical Twin vs Execution Action Store), DRY principles, and no dead code.

## Requirements

### R1. Authoritative Physical Twin & Event-Sourced Reconciler
Implement decoupled Physical Twin Store (`board_twin.py`) and Execution Store (`execution_state.py`). Implement the reconciler as a pure reducer executing the exhaustive 21-row Commit Truth Table deterministically:
$$\text{Reconciler}(\text{CurrentPhysicalState}, \text{CurrentExecutionState}, \text{Event}) \to (\text{NextPhysicalState}, \text{NextExecutionState}, \text{Actions})$$
Maintain `RESIDUAL_DETECTED` strictly as an execution trigger flag, never a physical state. Enforce per-object re-clean safety cap (`MAX_RECLEAN_ATTEMPTS=3` promoting stubborn residual to `PERMANENT_DEFECT`).

### R2. Dual-Channel Transport Backend (FastAPI + RTP + WebSockets)
Build high-performance async backend using FastAPI and modern async patterns. Decouple high-framerate video streaming with HUD overlays via RTP (`127.0.0.1:5004`) from bidirectional JSON event/telemetry communication over WebSockets (`/ws/events`, `/ws/telemetry`). All duster ($162 \times 58 \times 42\text{ mm}$) and board ($1000 \times 700\text{ mm}$) dimensions must be dynamically loaded from `config.yaml`, with home dock dynamically computed at $(w/2, H - h/2)$.

### R3. Multi-Signal Perception & Baseline Epoch Engine
Implement 4-corner homography registration to normalized `FRAME_BOARD`, multi-space difference maps (RGB, HSV, Lab, edge, local contrast), shadow rejection via chrominance ratios, projector decoupling (Mode A continuous likelihood $[0.0, 1.0]$, ambiguous regions set to `UNKNOWN`), and multi-signal temporal occlusion detection (coherent motion, area fraction $\ge 4.5\%$, temporal persistence — NO MOG2) that preserves occluded ink in the twin. Validate baseline captures against dirty boards and roll epochs only when residual $\le \text{clean\_threshold}$ (ignoring known `PERMANENT_DEFECT`s).

### R4. Config-Driven Coverage Path Planner
Implement Boustrophedon sweep coverage planner in `FRAME_BOARD` with configurable overlap (default 28%), smooth U-turns outside ink hulls, and full continuous trajectory planning starting from the dynamically computed Home Dock $(w/2, H - h/2)$ to target entry and returning home.

### R5. Interactive React Simulation Dashboard (SVG Only)
Construct a modern React/Vite + Zustand split-pane dashboard. Left pane: live RTP video / virtual canvas with SVG overlays (coordinate axes, duster position, target hulls) and interactive drawing brush. Right pane: 11-channel perception debugger, object inspector, residual tier indicators, and planner dispatch controls. Strictly zero emojis or raw Unicode symbols: use clean vector SVGs with `currentColor` styling.

## Acceptance Criteria

### Truth Table & State Reconciliation
- [ ] Automated pytest suite validates all 21 rows of the Commit Truth Table in `test_reconciler_truth_table.py`.
- [ ] `RESIDUAL_DETECTED` is verified to never exist as a state in the Physical Twin Store.
- [ ] 3 consecutive failed clean attempts cleanly transition ink to `PERMANENT_DEFECT` without infinite loops.

### Actuator Geometry & Configuration
- [ ] Changing `duster_width_mm` and `duster_height_mm` in `config.yaml` automatically updates home dock coordinates and visualizer bounding boxes without code changes.
- [ ] Coordinate frames are explicitly tagged (`FRAME_CAMERA`, `FRAME_BOARD`, `FRAME_DUSTER`, `FRAME_PATH`).

### Perception & Occlusion
- [ ] Temporary human/hand occlusions mark overlapping twin ink as `OCCLUDED` and preserve it without deletion.
- [ ] Baseline capture aborts with an error alert if board edge density exceeds `dirty_board_threshold`.
- [ ] Ambiguous projected regions are assigned to `UNKNOWN` and never automatically converted to ink.

### Transport & Performance
- [ ] Video frames stream via RTP while WebSocket events sync bidirectionally without blocking.
- [ ] Exact operational formulas (Precision, Recall, IoU, FPR, Residual Fraction) compute live and match ground truth.

### UI & Code Quality
- [ ] Zero emojis or unicode symbols present in the UI; all icons are vector SVGs.
- [ ] Frontend builds cleanly with `npm run build` without TypeScript or lint errors.
- [ ] Python tests pass via `& "C:\Users\vkmuk\OneDrive\Documents\Project\.venv\Scripts\python.exe" -m pytest tests/ -v`.

## Follow-up — 2026-09-17T13:39:10Z

IMPORTANT ARCHITECTURAL DIRECTIVE & SKILLS DISTRIBUTION:

1. Unified Implementation Plan:
   The authoritative implementation plan has been written directly to your workspace root:
   `c:\Users\vkmuk\OneDrive\Documents\Project\ECS_V2\V2.1\implementation_plan.md`
   Every subagent must review and strictly align with this specification (including the 21-row Truth Table, decoupled Physical Twin vs Execution Action Store, RTP on port 5004 + WebSockets on port 8000, dynamic duster geometry at `[w/2, H - h/2]`, and residual tiers).

2. Specialized Skills Distribution (`.agents/skills`):
   The skills are installed in `c:\Users\vkmuk\OneDrive\Documents\Project\ECS_V2\V2.1\.agents\skills`. Please distribute and require the relevant subagents to consult and adhere to their respective SKILL.md directives:
   - Backend, Streaming & Transports (M2, M6):
     * `fastapi-pro`: Async APIs, Pydantic v2 schemas, WebSocket endpoints.
     * `async-python-patterns`: Non-blocking loops, background workers, RTP packetization.
   - Perception, Homography & Vision (M3):
     * `computer-vision-expert`: Real-time spatial analysis, homography in FRAME_BOARD, multi-space difference maps, shadow chrominance ratio filtering, temporal occlusion detection without MOG2.
   - Frontend & Interactive Canvas (M5):
     * `react-patterns` & `zustand-store-ts`: Modern typed React, decoupled event bus, Zustand stores.
     * `ui-ux-pro-max` + User Global Rules: Strictly zero emojis or Unicode character symbols; use clean vector SVGs with `currentColor` and consistent stroke width.
   - Reconciler, Architecture & Verification (M1, M4, M7):
     * `clean-code-guard`: Strict separation of physical vs execution state, pure reducer design.
     * `pytest-skill`: Production-grade pytest suites with parameterized tests for all 21 rows of the Truth Table, safety caps, and homography.

Please ensure the Project Orchestrator propagates these skills and the implementation plan to all assigned subagents immediately.
