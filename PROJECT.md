# Project: Smart Erasing Duster V2.1 Digital Twin

## Architecture
The Smart Erasing Duster (V2.1) is an event-sourced digital twin system designed to model, track, plan, and verify whiteboard cleaning in real time. It consists of:
1. **Authoritative Digital Twin**: Strict decoupling of the physical reality of marker ink (`BoardTwinStore` in `board_twin.py`) from robotic erasing actions (`ExecutionStore` in `execution_state.py`), mediated by an event-sourced pure reducer reconciler executing the exhaustive 21-row Commit Truth Table.
2. **Dual-Channel Transport Backend**: FastAPI application decoupled into high-framerate video streaming over RTP UDP port 5004 (with HTTP MJPEG bridge for browsers) and bidirectional telemetry/events over WebSockets (`/ws/events`, `/ws/telemetry`).
3. **Multi-Signal Perception Engine**: 4-corner homography to metric `FRAME_BOARD` ($1000 \times 700$ mm), 11-channel difference engine (RGB, HSV, Lab, edge, local contrast), chrominance ratio shadow rejection, Mode A continuous projector likelihood with `UNKNOWN` fallback, and 3-signal temporal occlusion detection (strictly no MOG2) preserving occluded ink.
4. **Config-Driven Coverage Path Planner**: Boustrophedon sweep coverage planner with configurable 28% lane overlap, smooth exterior U-turns outside ink hulls, and continuous trajectory generation starting from dynamic Home Dock $(w/2, H - h/2)$ to target entry and returning home.
5. **Interactive React Simulation Dashboard**: Vite + React + Zustand split-pane dashboard with interactive drawing canvas, SVG overlays, 11-channel perception debugger, object inspector, and planner controls adhering strictly to zero-emoji / vector SVG standards.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Decoupled Physical Twin Store | `board_twin.py` modeling physical ink states (`UNKNOWN`, `NEW_INK`, `STABLE_INK`, `OCCLUDED`, `PARTIALLY_CLEANED`, `CLEANED`, `PERMANENT_DEFECT`) | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Decoupled Execution Action Store | `execution_state.py` modeling robot actions and ephemeral `residual_detected_flag` with 3 tiers | M1 | ORIGINAL_REQUEST §R1 |
| 3 | 21-Row Commit Truth Table Reconciler | Pure reducer executing all 21 rows deterministically: `reconcile(P_t, E_t, event) -> (P_{t+1}, E_{t+1}, actions)` | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Safety Loop Cap & Defect Promotion | Per-object `MAX_RECLEAN_ATTEMPTS=3` cleanly promoting stubborn residual to `PERMANENT_DEFECT` (Row 21) | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Master Configuration Contract | `config.yaml` with dynamic duster ($162 \times 58 \times 42$ mm) and board ($1000 \times 700$ mm) dimensions | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Dynamic Home Dock Calculation | Actuator home dynamically computed at $(w/2, H - h/2) = (81.0, 671.0)$ mm | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Explicit Coordinate Frame Tagging | Strict tagging across `FRAME_CAMERA`, `FRAME_BOARD`, `FRAME_DUSTER`, `FRAME_PATH` | M2 | ORIGINAL_REQUEST §R2 |
| 8 | RTP Video Streaming on Port 5004 | Pure Python UDP RTP packetizer (RFC 3550 + RFC 2435 MJPEG) streaming video on `127.0.0.1:5004` | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Dual WebSocket Event Bus | Non-blocking broadcast over `/ws/events` and `/ws/telemetry` | M2 | ORIGINAL_REQUEST §R2 |
| 10 | 4-Corner Homography Registration | ArUco marker and interactive corner calibration warping camera view to metric `FRAME_BOARD` | M3 | ORIGINAL_REQUEST §R3 |
| 11 | 11-Channel Difference Engine | Multi-space diff maps (RGB, HSV, Lab, edge, local contrast) fused into normalized evidence | M3 | ORIGINAL_REQUEST §R3 |
| 12 | Chrominance Ratio Shadow Rejection | Discriminating shadows via invariant chrominance ratios and brightness drops (`OBS_SHADOW`) | M3 | ORIGINAL_REQUEST §R3 |
| 13 | Mode A Projector Decoupling | Continuous projector likelihood $[0.0, 1.0]$; ambiguous regions classified as `UNKNOWN` without deleting ink | M3 | ORIGINAL_REQUEST §R3 |
| 14 | Temporal Occlusion Detection (No MOG2) | Coherent motion, area fraction $\ge 4.5\%$, persistence $\ge 3$ frames marking ink `OCCLUDED` and preserving it | M3 | ORIGINAL_REQUEST §R3 |
| 15 | Baseline Capture Validation & Epoch Roll | Aborting baseline capture if edge density > `dirty_board_threshold` (0.04); rolling epoch only when residual $\le 0.01$ with defect masking | M3 | ORIGINAL_REQUEST §R3 |
| 16 | Boustrophedon Sweep Coverage Planner | Axis-aligned sweep with configurable 28% lane overlap and smooth exterior U-turns outside ink hulls | M4 | ORIGINAL_REQUEST §R4 |
| 17 | Continuous Transit Trajectory Planning | Continuous path from Home Dock $(w/2, H - h/2)$ to target entry and returning home | M4 | ORIGINAL_REQUEST §R4 |
| 18 | Exact Operational Metric Formulas | Computing Precision, Recall, IoU, FPR, Residual Fraction, Coverage, Stability in physical coordinates | M4 | ORIGINAL_REQUEST §R4 |
| 19 | Simulation Engine & Deterministic Scenarios | Virtual board, dynamic duster model, imperfect erasing, and Scenarios 1..6 presets | M4 | ORIGINAL_REQUEST §R4 |
| 20 | Split-Pane React Dashboard | Left pane live RTP/virtual canvas with SVG overlays; right pane 11-channel debugger, inspector, controls | M5 | ORIGINAL_REQUEST §R5 |
| 21 | Strict Zero-Emoji Vector SVG Iconography | Complete absence of emojis or unicode symbols; clean vector SVGs with `currentColor` styling | M5 | ORIGINAL_REQUEST §R5 |
| 22 | Full Closed-Loop E2E Integration | 100% pass of E2E test suite (Tiers 1-4) across write, observe, plan, clean, residual, re-clean | M6 | ORIGINAL_REQUEST Acceptance |
| 23 | Adversarial Coverage Hardening | Tier 5 adversarial stress tests, edge cases, and robustness verification | M7 | Project Pattern §Phase 2 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Physical Twin Store & Reconciler | `board_twin.py`, `execution_state.py`, `reconciler.py`, `state_machine.py`, `test_reconciler_truth_table.py` | none | DONE |
| M2 | Config & Dual Transport Backend | `config.yaml`, FastAPI backend, RTP 5004 streaming, `/ws/events`, `/ws/telemetry`, dynamic Home Dock | none | DONE |
| M3 | Perception & Baseline Epoch Engine | Homography in `FRAME_BOARD`, 11-channel diffs, shadow rejection, projector decoupling, non-MOG2 occlusion, baseline validation | M1, M2 | DONE |
| M4 | Coverage Planner & Simulation | Boustrophedon sweep (28% overlap), smooth exterior U-turns, Home trajectory, operational formulas, Scenarios 1..6 | M1, M2 | DONE |
| M5 | Interactive React SVG Dashboard | Vite + React + Zustand split-pane dashboard, canvas + SVG overlays, 11-channel debugger, zero emojis | M2, M3, M4 | DONE |
| M6 | Full E2E Integration & Verification | 100% pass of E2E test suite (Tiers 1-4) published by E2E Testing Track | M1, M2, M3, M4, M5 | DONE |
| M7 | Adversarial Coverage Hardening | Tier 5 coverage analysis, boundary tests in test_reconciler_truth_table, test_planner, test_scenarios_1_to_6 | M6 | DONE |

## Interface Contracts
### `reconciler.py` ↔ Digital Twin & Execution Stores
- Signature: `reconcile(twin_state: BoardTwinState, exec_state: ExecutionState, event: ReconcilerEvent) -> Tuple[BoardTwinState, ExecutionState, List[ReconcilerAction]]`
- Invariant: Pure reducer, no side-effects, deterministic execution of 21-row Truth Table.
- `RESIDUAL_DETECTED` is strictly an event/execution flag, never stored in `BoardTwinState`.

### `config.py` ↔ System Components
- Contract: `Config.get_home_dock() -> Tuple[float, float, float]` returning $(w_{\text{duster}}/2, H_{\text{board}} - h_{\text{duster}}/2, 0.0)$ in mm.
- Invariant: Loaded from `config.yaml`, dynamically propagated to planner, twin, visualizer, and frontend.

### Backend ↔ Frontend Transport Contracts
- RTP Video: `udp://127.0.0.1:5004` (RFC 3550 / RFC 2435 MJPEG) + HTTP MJPEG bridge `/api/camera/stream`
- WebSocket `/ws/events`: Bidirectional JSON messages:
  - Inbound: `DRAW_STROKE`, `ERASE_STROKE`, `SET_DUSTER_POSE`, `DISPATCH_CLEAN`, `SET_SCENARIO`, `CAPTURE_BASELINE`
  - Outbound: `TWIN_DELTA`, `EXECUTION_UPDATE`, `ACTION_LOG`, `ALERT`
- WebSocket `/ws/telemetry`: 10-30 Hz telemetry broadcast (`duster_pose`, `metrics`, `residual_tier`, `fps`).

### Perception ↔ Reconciler Contract
- Perception emits `OBSERVATION_FRAME_EVALUATED` event containing list of `ObservationRegion`:
  - `geometry`: Polygon in `FRAME_BOARD`
  - `evidence_state`: `OBS_ABSENT`, `OBS_INK`, `OBS_OCCLUDED`, `OBS_SHADOW`, `OBS_PROJECTOR`, `OBS_UNCERTAIN`
  - `evidence_score`: Float $\in [0.0, 1.0]$

## Code Layout
```
ECS_V2/V2.1/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI application, RTP streaming & WebSocket routers
│   │   ├── core/
│   │   │   ├── config.py               # Pydantic v2 configuration (loads config.yaml)
│   │   │   ├── state.py                # Runtime state coordinator
│   │   │   └── events.py               # Event dispatch & immutable audit log bus
│   │   ├── api/
│   │   │   ├── camera.py               # Webcam, RTSP/RTP & virtual canvas feeder
│   │   │   ├── stream.py               # RTP video packetizer / MJPEG-WebRTC bridge
│   │   │   ├── ws.py                   # Bidirectional WebSocket (/ws/events, /ws/telemetry)
│   │   │   ├── calibration.py          # ArUco marker & manual corner calibration
│   │   │   ├── reference.py            # Baseline epoch capture, validation & history
│   │   │   ├── perception.py           # Perception control & debug map streaming
│   │   │   ├── twin.py                 # Physical twin & execution store queries
│   │   │   ├── planner.py              # Coverage path planning & dispatch
│   │   │   ├── simulator.py            # Scenario injection & interactive canvas
│   │   │   └── replay.py               # Session recorder & player
│   │   ├── perception/
│   │   │   ├── frames.py               # Coordinate frame tagging (CAMERA, BOARD, DUSTER, PATH)
│   │   │   ├── registration.py         # 4-corner homography warp to board space (from config)
│   │   │   ├── reference.py            # Baseline validation, multi-frame accumulation & stats
│   │   │   ├── difference.py           # Multi-space diffs (RGB, HSV, Lab, gradient, ratio)
│   │   │   ├── illumination.py         # Illumination normalization & local contrast
│   │   │   ├── shadow.py               # Shadow rejection filter (chrominance ratio)
│   │   │   ├── glare.py                # Glare / specular saturation filter
│   │   │   ├── projector.py            # Projector decoupling (Mode A likelihood, Mode B ref)
│   │   │   ├── occlusion.py            # Multi-signal temporal occlusion detector (NO MOG2)
│   │   │   ├── strokes.py              # Stroke geometry, contours, skeletons, thickness
│   │   │   ├── temporal.py             # Multi-frame persistence & growth tracker
│   │   │   ├── fusion.py               # Weighted evidence scoring pipeline
│   │   │   └── tracker.py              # Matching via config thresholds (IoU, distance)
│   │   ├── digital_twin/
│   │   │   ├── board_twin.py           # Authoritative PHYSICAL TWIN STORE (Ink, Defects)
│   │   │   ├── execution_state.py      # Authoritative EXECUTION STORE (Duster, Planner)
│   │   │   ├── reconciler.py           # Event-Sourced Pure Reducer (21-row Truth Table)
│   │   │   ├── state_machine.py        # Physical state transitions with loop cap checks
│   │   │   └── history.py              # SQLite event & twin state persistence
│   │   ├── planning/
│   │   │   ├── geometry.py             # Shapely polygon union & inflation in FRAME_BOARD
│   │   │   ├── coverage.py             # Axis-aligned Boustrophedon sweep (config-driven overlap)
│   │   │   ├── transit.py              # Transit path from dynamically calculated Home to Target
│   │   │   ├── ordering.py             # Path segment sequence optimizer
│   │   │   └── smoothing.py            # Rounded U-turn loops outside target boundary
│   │   ├── simulation/
│   │   │   ├── board.py                # Virtual board renderer with layers
│   │   │   ├── duster.py               # Dynamic virtual duster model (dimensions from config)
│   │   │   ├── cleaning.py             # Imperfect eraser with residual & defect simulation
│   │   │   ├── metrics.py              # Exact operational metric formulas (IoU, precision, recall)
│   │   │   └── scenarios.py            # Scenarios 1..6 deterministic presets
│   │   ├── replay/
│   │   │   ├── recorder.py             # Disk stream recorder (JSONL + frames)
│   │   │   └── player.py               # Variable speed playback controller
│   │   └── schemas/
│   │       ├── calibration.py          # Corners & homography schemas
│   │       ├── ink.py                  # InkObject schemas with frame tags & states
│   │       ├── perception.py           # Evidence metrics & debug maps
│   │       ├── events.py               # Reconciler event schemas
│   │       └── planner.py              # Path trajectories & duster state
│   ├── config.yaml                     # Master configuration file (dimensions, thresholds, caps)
│   └── requirements.txt                # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── api/                        # Axios & REST client
│   │   ├── hooks/                      # useRtpStream, useWebSocket, useDigitalTwin, useCanvas
│   │   ├── components/
│   │   │   ├── Navbar.tsx              # Navigation & System Status bar (SVG icons only)
│   │   │   ├── VideoOverlayCanvas.tsx  # Board view with RTP video + SVG overlays + drawing
│   │   │   ├── InkObjectInspector.tsx  # Selected ink object details & re-clean counters
│   │   │   ├── PerceptionDebugger.tsx  # 11-channel diff map grid & metrics
│   │   │   ├── PlannerControls.tsx     # Coverage generation & stepping controls
│   │   │   ├── VirtualDusterView.tsx   # Actuator animation & trajectory view (dynamic size)
│   │   │   ├── BaselineEpochView.tsx   # Baseline epoch history, validation & defects
│   │   │   ├── CalibrationModal.tsx    # Corner dragging & ArUco detection view
│   │   │   └── ScenarioBar.tsx         # Quick scenario triggers & canvas tools
│   │   ├── pages/
│   │   │   └── MissionControlPage.tsx  # Unified Split-Pane Dashboard
│   │   ├── store/                      # Zustand store for client state & event bus
│   │   ├── types/                      # TypeScript definitions matching backend
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── tests/
│   ├── test_homography.py              # ArUco & homography verification in FRAME_BOARD
│   ├── test_difference_maps.py         # Multi-space diff validation
│   ├── test_shadow_rejection.py        # Shadow vs ink discrimination
│   ├── test_projector_decoupling.py    # Mode A likelihood, Mode B ref, UNKNOWN fallback
│   ├── test_temporal_occlusion.py      # Multi-signal occlusion & ink preservation (NO MOG2)
│   ├── test_reconciler_truth_table.py  # Exhaustive 21-row Commit Truth Table test (Event Reducer)
│   ├── test_baseline_epochs.py         # Epoch creation within tolerance & defect fallback
│   ├── test_reclean_caps.py            # MAX_RECLEAN_ATTEMPTS = 3 -> PERMANENT_DEFECT
│   ├── test_planner.py                 # Boustrophedon coverage path planning from dynamic Home
│   └── test_closed_loop.py             # Write -> Clean -> Residual -> Re-Clean -> Verified Clean
└── README.md                           # Complete documentation & architecture guide
```
