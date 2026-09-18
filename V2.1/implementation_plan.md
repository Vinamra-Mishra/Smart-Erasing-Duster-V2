# Smart Erasing Duster: Software-Only Digital Twin Trail (V2.1) — Unified Execution Plan

## Executive Summary

This plan provides a **single unified execution blueprint** to build the complete **Smart Erasing Duster** digital twin prototype directly inside `ECS_V2/V2.1`. All components across backend, digital twin, perception, planner, simulation, and frontend will be constructed in one cohesive, end-to-end implementation with zero phased deferrals.

---

## 1. Decision Log (Brainstorming & Architecture Invariants)

| Decision ID | Decision Made | Alternatives Considered | Rationale |
| :--- | :--- | :--- | :--- |
| **DEC-01** | **Unified Plan (No Staggered Phases)** | Phased rollout (Phase 1 Perception, Phase 2 Twin, etc.) | Prevents architectural drift and technical debt; validates all closed-loop invariants together from day one. |
| **DEC-02** | **Physical Twin Store vs. Execution Action Store Separation** | Single monolithic twin state | `CLEANING` and `RECLEAN_PENDING` are robot actions, not board physical properties. Separating them prevents phantom state bugs. |
| **DEC-03** | **Event-Sourced Pure Reducer Reconciler** | Polling game loop with state diffing; Reactive streams (RxPy) | Pure reducer function `reduce(state, event) -> next_state` makes all 21 rows of the Truth Table 100% deterministic and unit-testable. |
| **DEC-04** | **Dual-Channel Transport (RTP + WebSockets)** | Monolithic WebSocket (sending MJPEG + events); HTTP polling | RTP handles high-fps low-latency video streaming without blocking the event loop; WebSockets provide reliable bidirectional JSON event bus. |
| **DEC-05** | **Fully Configurable Actuator & Board Dimensions** | Hardcoded standard dimensions | Duster ($162 \times 58 \times 42\text{ mm}$ default) and Board ($1000 \times 700\text{ mm}$ default) are dynamic config inputs. Actuator home dock is computed dynamically at $(w/2, H - h/2)$. |
| **DEC-06** | **21-Row Exhaustive Commit Truth Table** | Heuristic ad-hoc state checks | Eliminates race conditions between camera, digital projector overlays, manual human actions, and robotic wiping. |
| **DEC-07** | **Multi-Tier Residual Architecture with Hard Caps** | Binary Clean/Dirty threshold | Distinguishes fine residuals ($1\% \le r < 5\%$) from major misses ($r \ge 5\%$). `MAX_RECLEAN_ATTEMPTS=3` promotes stubborn ink to `PERMANENT_DEFECT`. |
| **DEC-08** | **Illumination Normalization over Baseline Drift** | Continuous background model adaptation (e.g., MOG2) | Prevents slow-moving occluders or erased ink from bleeding into the reference baseline. Baseline epochs only roll after verified clean. |

---

## 2. Architectural Invariants & Key Specifications

### 2.1 Separation of Concerns: Physical World State vs. Execution State
- **Physical Twin Store (`board_twin.py`)**: Authoritative model of physical marks on the board surface.
  - Physical States: `UNKNOWN`, `NEW_INK`, `STABLE_INK`, `OCCLUDED`, `PARTIALLY_CLEANED`, `CLEANED`, `PERMANENT_DEFECT`.
  - **`RESIDUAL_DETECTED` is NOT a Physical Twin state**: It is an ephemeral measurement / transition trigger stored in the Execution Action Store as a derived flag (`residual_tier: TIER_1_CLEANED | TIER_2_FINE_RESIDUAL | TIER_3_MAJOR_RESIDUAL`).
- **Execution / Action Store (`execution_state.py`)**: Models the robot/duster activity and planner dispatch.
  - Execution States: `IDLE`, `PLANNING`, `CLEANING_ACTIVE`, `VERIFYING`, `RECLEAN_PENDING`, `STOPPED`, `SAFETY_LOCK`.

### 2.2 Reconciler Implementation: Event-Sourced Pure Reducer
The Reconciler (`reconciler.py`) operates as a pure reducer:
$$\text{Reconciler}(\text{CurrentPhysicalState}, \text{CurrentExecutionState}, \text{Event}) \to (\text{NextPhysicalState}, \text{NextExecutionState}, \text{Actions})$$
- Events ingested via the WebSocket event bus:
  - `OBSERVATION_FRAME_EVALUATED`: Processed frame evidence vector per detected region.
  - `DUSTER_MOVED`: Tool trajectory update in `FRAME_BOARD`.
  - `WIPE_SWEEP_EXECUTED`: Duster footprint swept over target polygon.
  - `VERIFICATION_WINDOW_ELAPSED`: Multi-frame post-wipe settle timer completed.
  - `PROJECTOR_STATE_TOGGLED`: Mode A/B switch or reference calibration signal.
- The state transition logic follows the **21-Row Commit Truth Table** deterministically.

### 2.3 Dual-Channel Transport Architecture (RTP + WebSockets)
Communication between the Python backend and React frontend is decoupled into two dedicated pipelines:

1. **High-Framerate Video Stream (RTP Pipeline)**:
   - **Backend Source**: OpenCV pipeline captures camera or virtual board canvas, rectifies perspective to $1000 \times 700$ `FRAME_BOARD`, composites HUD debug overlays (contours, duster footprint, coordinate axes), and packetizes video via RTP / GStreamer / WebRTC.
   - **Frontend Sink**: HTML5 `<video>` / WebRTC receiver rendering seamless 30 fps stream without serializing base64 across JSON websockets.
2. **Bidirectional Event & Telemetry Bus (WebSocket Pipeline)**:
   - Endpoint: `/ws/events` and `/ws/telemetry`.
   - **Frontend ➔ Backend**: Interactive canvas draw strokes, duster manual drag, scenario triggers, baseline capture commands, planner dispatch.
   - **Backend ➔ Frontend**: Reconciled Physical Twin delta, Execution Action state, operational metrics (IoU, precision, recall, FPR), audit logs.

### 2.4 Coordinate System Standards & Config-Driven Duster Geometry
- **Board Coordinate Space**: Normalized $W_{\text{board}} \times H_{\text{board}}$ px representing a physical whiteboard ($1\text{ px} = 1\text{ mm}$), loaded directly from `config.yaml` (`board_width_mm: 1000`, `board_height_mm: 700`).
  - Origin $(0, 0)$: Top-Left corner.
  - Board bounds: $[0, W_{\text{board}}]\text{ mm} \times [0, H_{\text{board}}]\text{ mm}$.
- **Fully Configurable Duster Physical Dimensions (`config.yaml`)**:
  - Duster length, width, and thickness are **NEVER hardcoded** in Python or TypeScript:
    ```yaml
    cleaning:
      duster_width_mm: 162.0    # 16.2 cm (configurable)
      duster_height_mm: 58.0    # 5.8 cm (configurable)
      duster_thickness_mm: 42.0 # 4.2 cm (configurable)
    ```
- **Dynamic Duster Home Dock Invariant**:
  - The duster home dock is dynamically calculated from configured board and duster dimensions:
    $$x_{\text{home}} = \frac{w_{\text{duster}}}{2}, \quad y_{\text{home}} = H_{\text{board}} - \frac{h_{\text{duster}}}{2}, \quad \theta_{\text{home}} = 0^{\circ}$$
    (e.g., for default $1000 \times 700\text{ mm}$ and $162 \times 58\text{ mm}$, $(x_{\text{home}}, y_{\text{home}}) = (81.0, 671.0)\text{ mm}$, updating automatically if configuration changes).
  - Every cleaning mission plans a continuous transit trajectory:
    $$\text{Home}(x_{\text{home}}, y_{\text{home}}) \to \text{Target Entry} \to \text{Boustrophedon Sweep} \to \text{Return Home}$$
- **Explicit Frame Enumeration**: Every polygon, contour, bounding box, and trajectory is tagged with its coordinate frame:
  - `FRAME_CAMERA`: Raw camera sensor pixels $(u, v) \in [0, W_{\text{cam}}] \times [0, H_{\text{cam}}]$.
  - `FRAME_BOARD`: Homography-rectified physical board coordinates $(x, y) \in [0, W_{\text{board}}] \times [0, H_{\text{board}}]$ in mm.
  - `FRAME_DUSTER`: Actuator body-fixed local coordinates $(\Delta x, \Delta y) \in [-w/2, w/2] \times [-h/2, h/2]\text{ mm}$ centered at the tool midpoint.
  - `FRAME_PATH`: Ordered waypoint sequence $[(x_i, y_i, \theta_i, v_i)]$ in `FRAME_BOARD`.

### 2.5 Spatial Matching Criteria
For associating an observation with an existing ink object:
- Match exists if and only if:
  $$\text{IoU}(\text{geom}_{\text{obs}}, \text{geom}_{\text{twin}}) \ge \text{matching\_iou\_threshold} \quad \mathbf{AND} \quad \|\text{centroid}_{\text{obs}} - \text{centroid}_{\text{twin}}\|_2 \le \text{matching\_centroid\_dist\_mm}$$
  (both thresholds loaded from `config.yaml`).
- If neither condition or only one condition is met: the observation is evaluated as a separate candidate object.

### 2.6 Exhaustive Commit Truth Table (The Reconciler Contract)
The Reconciler mediates between the **Observation Evidence** and the **Physical Twin State**.
Observation states:
- `OBS_ABSENT`: No difference detected from baseline.
- `OBS_INK`: Stroke confirmed through evidence fusion.
- `OBS_OCCLUDED`: Multi-signal coherent motion / broad occluder detected.
- `OBS_SHADOW`: Low-frequency illumination drop with invariant chrominance.
- `OBS_PROJECTOR`: Additive digital overlay detected.
- `OBS_UNCERTAIN`: Specular glare, high noise, or ambiguous projector region.

| Row | Current Twin State | Observation Evidence | Spatial Match? | Reconciler Action / Next Physical State | Invariant Rationale |
| :---: | :--- | :--- | :---: | :--- | :--- |
| **1** | **None** | `OBS_ABSENT` / `OBS_SHADOW` | N/A | Do nothing (remain clean) | Baseline noise & shadows rejected |
| **2** | **None** | `OBS_INK` (persistence $\ge K$) | N/A | Create `NEW_INK` $\to$ `STABLE_INK` | Confirmed physical ink appearance |
| **3** | **None** | `OBS_OCCLUDED` | N/A | Set `board_occlusion_mask`, Twin = None | Occluder is not ink |
| **4** | **None** | `OBS_PROJECTOR` / `OBS_UNCERTAIN` | N/A | Add to `uncertainty_mask`, Twin = `UNKNOWN` | Never assume ink from projector or glare |
| **5** | **UNKNOWN** | `OBS_INK` | Yes | Resolve $\to$ `NEW_INK` $\to$ `STABLE_INK` | Ambiguity resolved: ink confirmed |
| **6** | **UNKNOWN** | `OBS_ABSENT` | N/A | Resolve $\to$ `CLEANED` / remove | Ambiguity resolved: board is clean |
| **7** | **UNKNOWN** | `OBS_OCCLUDED` / `OBS_UNCERTAIN` | N/A | Retain `UNKNOWN` | Ambiguity persists |
| **8** | **STABLE_INK** | `OBS_INK` | Yes | Update `last_seen`, retain `STABLE_INK` | Normal steady-state observation |
| **9** | **STABLE_INK** | `OBS_INK` | No | Retain existing, create separate `NEW_INK` | Spatially separate writing |
| **10**| **STABLE_INK** | `OBS_OCCLUDED` | Yes | Transition $\to$ `OCCLUDED` | **NEVER DELETE INK**; actor blocks view |
| **11**| **STABLE_INK** | `OBS_ABSENT` (no clean action) | N/A | Decrement confidence; if $0 \to$ `UNKNOWN` | Do not immediately erase; suspect wipe |
| **12**| **OCCLUDED** | `OBS_OCCLUDED` | N/A | Retain `OCCLUDED` | Occlusion remains active |
| **13**| **OCCLUDED** | `OBS_INK` (actor departed) | Yes | Reconcile geometry $\to$ `STABLE_INK` | Ink confirmed present after occlusion |
| **14**| **OCCLUDED** | `OBS_ABSENT` (actor departed) | N/A | Log `EXTERNAL_ERASURE_SUSPECTED` $\to$ `UNKNOWN` | Manual erasure suspected while occluded |
| **15**| **PARTIALLY_CLEANED** | `OBS_INK` (residual present) | Yes | Retain `PARTIALLY_CLEANED` | Residual ink still physically present |
| **16**| **PARTIALLY_CLEANED** | `OBS_ABSENT` (after re-clean) | N/A | Transition $\to$ `CLEANED` | Closed-loop verification confirmed clean |
| **17**| **CLEANED** | `OBS_INK` | N/A | Create `NEW_INK` | New ink written over previously cleaned area |
| **18**| **CLEANED** | `OBS_ABSENT` | N/A | Retain `CLEANED` (garbage collect at epoch) | Verified clean state |
| **19**| **PERMANENT_DEFECT** | `OBS_INK` / `OBS_ABSENT` | Yes | Retain `PERMANENT_DEFECT` (informational) | Known permanent defect; ignore in re-clean |
| **20**| **PERMANENT_DEFECT** | `OBS_OCCLUDED` | Yes | Retain `PERMANENT_DEFECT`, mark occluded | Defect temporarily hidden |
| **21**| **Any State** | Re-cleans $> \text{MAX\_RECLEAN\_ATTEMPTS}$ | N/A | Force $\to$ `PERMANENT_DEFECT`, log `RECLEAN_CAP_HIT` | Prevents infinite loop on stubborn marks |

### 2.7 Residual Execution Tiers & Safety Loop Caps
- **Residual Tiers (Execution Action Store)**:
  - $\text{residual} \le \text{clean\_threshold}$: Physical state $\to$ `CLEANED`.
  - $\text{clean\_threshold} < \text{residual} < \text{residual\_major\_threshold}$: Physical state remains `PARTIALLY_CLEANED`, execution flag set to `TIER_2_FINE_RESIDUAL` $\to$ triggers targeted fine re-clean.
  - $\text{residual} \ge \text{residual\_major\_threshold}$: Physical state remains `PARTIALLY_CLEANED`, execution flag set to `TIER_3_MAJOR_RESIDUAL` $\to$ triggers broad Boustrophedon sweep.
- **Safety Caps & Timeouts**:
  - `MAX_RECLEAN_ATTEMPTS` (default 3): Per-object hard cap from `config.yaml`.
  - `MAX_MISSION_DURATION_SEC` (default 180.0): Mission-level wall-clock safety cap from `config.yaml`.
  - `RESIDUAL_TRIGGER_TIMEOUT_SEC` (default 5.0): Timeout for transient re-plan triggers.

### 2.8 Baseline Capture Validation & Epoch Roll Fallback
- **Baseline Capture Validation**:
  - Edge/contrast scan across the board. If edge density $> \text{dirty\_board\_threshold}$ (configurable, default 0.04), abort capture and alert user.
- **Epoch Roll Fallback**:
  - Baseline Epoch roll occurs when the board is **verified clean within the configured detection tolerance** ($\text{residual} \le \text{clean\_threshold}$).
  - `PERMANENT_DEFECT` objects are masked out of the residual calculation, allowing epoch roll while embedding defect locations into `permanent_defect_mask`.

### 2.9 Projector Decoupling: Mode A as Likelihood
- **Mode A (Camera-Only)**: Produces a continuous $\text{PROJECTOR\_LIKELIHOOD} \in [0.0, 1.0]$. It is explicitly a heuristic, NOT projector ground truth.
- **Invariant**:
  - High confidence projector $\to$ suppress candidate from ink.
  - Insufficient confidence projector $\to$ classify region as `UNKNOWN` (add to `uncertainty_mask`).
  - **NEVER**: Projector detection deletes known Twin ink; **NEVER**: `UNKNOWN` creates new ink.

### 2.10 Exact Operational Metric Formulas
- $\text{Precision} = \frac{TP}{TP + FP} = \frac{\text{Area}(\text{Detected Ink} \cap \text{Ground Truth Ink})}{\text{Area}(\text{Detected Ink})}$
- $\text{Recall} = \frac{TP}{TP + FN} = \frac{\text{Area}(\text{Detected Ink} \cap \text{Ground Truth Ink})}{\text{Area}(\text{Ground Truth Ink})}$
- $\text{IoU} = \frac{TP}{TP + FP + FN} = \frac{\text{Area}(\text{Detected Ink} \cap \text{Ground Truth Ink})}{\text{Area}(\text{Detected Ink} \cup \text{Ground Truth Ink})}$
- $\text{False Positive Rate (FPR)} = \frac{FP}{FP + TN} = \frac{\text{Area}(\text{Detected Ink} \setminus \text{Ground Truth Ink})}{\text{Area}(\text{Clean Board Ground Truth})}$
- $\text{Residual Fraction} = \frac{\text{Area}(\text{Residual Ink Post-Clean})}{\text{Area}(\text{Original Target Ink Pre-Clean})}$
- $\text{Cleaning Coverage} = \frac{\text{Area}(\text{Duster Swept Footprint} \cap \text{Target Geometry})}{\text{Area}(\text{Target Geometry})}$
- $\text{Tracking Stability} = 1.0 - \frac{\text{Count}(\text{Unplanned ID Switches})}{\text{Total Object Lifetime Frames}}$

---

## 3. Directory Structure (`ECS_V2/V2.1`)

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

---

## 4. Master Configuration Contract (`config.yaml`)

```yaml
system:
  board_width_mm: 1000.0
  board_height_mm: 700.0
  camera_index: 0
  fps: 30
  transport:
    rtp_host: "127.0.0.1"
    rtp_port: 5004
    ws_port: 8000

calibration:
  aruco_dict: "DICT_4X4_50"
  corner_ids: [0, 1, 2, 3] # TL, TR, BR, BL

baseline:
  frames_to_accumulate: 20
  dirty_board_threshold: 0.04 # Reject baseline if edge density > 4%
  allow_dirty_board_override: false

perception:
  evidence_weights:
    w_rgb: 0.25
    w_hsv: 0.20
    w_lab: 0.20
    w_edge: 0.20
    w_contrast: 0.15
  disturbance_penalties:
    w_shadow: 0.40
    w_glare: 0.50
    w_occlusion: 0.80
    w_projector: 0.60
  stroke_min_area: 15
  stroke_max_expected_thickness_mm: 12.0
  matching_iou_threshold: 0.40
  matching_centroid_dist_mm: 30.0

occlusion:
  min_area_fraction: 0.045 # 4.5% of board area
  min_displacement_px: 12
  confirmation_frames: 3

cleaning:
  duster_width_mm: 162.0    # 16.2 cm (configurable)
  duster_height_mm: 58.0    # 5.8 cm (configurable)
  duster_thickness_mm: 42.0 # 4.2 cm (configurable)
  lane_overlap: 0.28        # 28% lane overlap (configurable)
  nominal_efficiency: 0.85
  clean_threshold: 0.01     # <= 1% is CLEANED
  residual_major_threshold: 0.05 # >= 5% is PARTIALLY_CLEANED (major sweep)
  max_reclean_attempts: 3   # Promotion to PERMANENT_DEFECT
  max_mission_duration_sec: 180.0 # Wall-clock safety cap
  residual_trigger_timeout_sec: 5.0
```

---

## 5. UI/UX & Design Guidelines

- **Zero Emojis / Unicode Symbols Rule**: All icons in navigation, buttons, indicators, and status badges must strictly be clean, vector SVGs with dynamic `currentColor` styling.
- **Split-Pane Layout**:
  - **Left Pane (Video/Twin Stream)**: Interactive Canvas displaying the low-latency RTP/video feed overlaid with SVG coordinate axes, duster position, target polygon hulls, and brush drawing tools.
  - **Right Pane (Control & Telemetry)**: Real-time Perception Debugger (11 diff channels), Ink Object Inspector, Planner Dispatch controls, Residual Tier indicators, and Scenario bar.

---

## 6. Verification Plan

### Automated Tests
1. Run complete pytest test suite in the virtual environment:
   ```powershell
   & "C:\Users\vkmuk\OneDrive\Documents\Project\.venv\Scripts\python.exe" -m pytest tests/ -v
   ```
2. Build React frontend without lint/type errors:
   ```powershell
   npm --prefix frontend run build
   ```

### Manual Verification
1. **Dynamic Geometry Verification**: Modify `duster_width_mm`, `duster_height_mm`, and `board_width_mm` in `config.yaml` $\to$ verify backend and frontend dynamically calculate the home dock $(w/2, H - h/2)$ and update the visualizer without code changes.
2. **Dual-Channel Stream**: Verify video feeds via RTP and events/state updates via WebSocket simultaneously without frame drops.
3. **Truth Table & Reconciler**: Verify all 21 rows in automated tests and interactively in the simulation canvas.
4. **Safety Caps**: Verify 3 consecutive failed clean attempts cleanly transition ink to `PERMANENT_DEFECT`.
