# Smart Erasing Duster Digital Twin (V2.1)

A cyber-physical software-only Digital Twin trail prototype for the **Smart Erasing Duster**, engineered directly inside `ECS_V2/V2.1`.

---

## 1. System Architecture & Invariants

```
+-----------------------------------------------------------------------------------+
|                                  REACT DASHBOARD                                  |
|  - Interactive Simulation Canvas (SVG Overlays, Dynamic Duster Bounding Box)      |
|  - 11-Channel Perception Debugger & Object Inspector                              |
|  - Strictly Clean Vector SVGs (zero emojis or raw unicode symbols)                |
+--------------------------+---------------------------------+----------------------+
                           |                                 ^
         WebSocket Events  |                                 | RTP Video Stream
         (JSON Telemetry)  v                                 | (H.264 / JPEG @ 30fps)
+------------------------------------------------------------+----------------------+
|                           FASTAPI DUAL-CHANNEL BACKEND                            |
|                                                                                   |
|  +---------------------------------+    +--------------------------------------+  |
|  |       PHYSICAL TWIN STORE       |    |        EXECUTION ACTION STORE        |  |
|  |  (Authoritative board state)    |    |  (Robot dispatch & telemetry)        |  |
|  |  UNKNOWN, NEW_INK, STABLE_INK,  |    |  IDLE, PLANNING, CLEANING_ACTIVE,    |  |
|  |  OCCLUDED, PARTIALLY_CLEANED,   |    |  VERIFYING, RECLEAN_PENDING, STOPPED |  |
|  |  CLEANED, PERMANENT_DEFECT      |    |  *RESIDUAL_DETECTED is a trigger flag|  |
|  +---------------------------------+    +--------------------------------------+  |
|                                  ^        ^                                       |
|                                  |        |                                       |
|               +------------------+--------+------------------+                    |
|               |        EVENT-SOURCED PURE REDUCER            |                    |
|               |       (21-Row Commit Truth Table)            |                    |
|               +----------------------------------------------+                    |
|                                      ^                                            |
|                                      |                                            |
|     +--------------------------------+-----------------------------------+        |
|     | MULTI-SIGNAL PERCEPTION ENGINE |  BOUSTROPHEDON COVERAGE PLANNER   |        |
|     | - 4-corner Homography Warping  |  - Configurable Overlap (28%)     |        |
|     | - Multi-Space Diff (RGB/HSV/Lab)| - Continuous Mission Trajectory   |        |
|     | - Shadow Chrominance Filtering |  - Dynamic Home Dock (w/2, H-h/2) |        |
|     | - Non-MOG2 Temporal Occlusion  |  - Exterior Rounded U-Turns       |        |
|     | - Mode A Projector Likelihood  |  - Safety Caps (3 recleans max)   |        |
|     +--------------------------------+-----------------------------------+        |
+-----------------------------------------------------------------------------------+
```

### Key Architectural Invariants
1. **Separation of Physical Twin vs Execution Action Store**:
   - `Physical Twin Store` (`board_twin.py`) models physical reality on the whiteboard surface.
   - `Execution Store` (`execution_state.py`) models robot status, paths, and dispatch queues.
   - `RESIDUAL_DETECTED` is an ephemeral trigger / measurement flag, **never** a persistent physical twin state.
2. **21-Row Commit Truth Table (`reconciler.py`)**:
   - Implemented as a pure reducer: `reconcile(twin, exec, event) -> (next_twin, next_exec, actions)`.
   - Eliminates race conditions between sensor noise, digital projector interference, manual wiping, and robot motion.
3. **Fully Configurable Dynamic Geometry (`config.yaml`)**:
   - Duster dimensions ($162 \times 58 \times 42\text{ mm}$) and Board dimensions ($1000 \times 700\text{ mm}$) are dynamically loaded from config.
   - Actuator home dock is dynamically calculated at $(w_{\text{duster}}/2, H_{\text{board}} - h_{\text{duster}}/2)$.
4. **Multi-Signal Perception (NO MOG2)**:
   - Preserves occluded ink in the twin when an actor/hand blocks the camera.
   - Reject shadows via chrominance ratios without misclassifying them as ink.
   - Projector Mode A computes continuous likelihood $[0.0, 1.0]$; ambiguous regions transition to `UNKNOWN` and never automatically create ink.
5. **Safety Caps & Residual Tiers**:
   - $\le 1\% \to$ `CLEANED`.
   - $1\% \text{ to } 5\% \to$ `TIER_2_FINE_RESIDUAL` (targeted fine re-clean).
   - $\ge 5\% \to$ `TIER_3_MAJOR_RESIDUAL` (full Boustrophedon sweep).
   - Re-cleans exceeding `MAX_RECLEAN_ATTEMPTS=3` cleanly promote ink to `PERMANENT_DEFECT` preventing infinite loops.
6. **Strict Vector SVG UI Iconography**:
   - Zero emojis or raw unicode symbols anywhere in the web UI.
   - Clean vector SVGs with dynamic `currentColor` and consistent stroke width.

---

## 2. Master Configuration (`config.yaml`)

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
  corner_ids: [0, 1, 2, 3]

baseline:
  frames_to_accumulate: 20
  dirty_board_threshold: 0.04
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
  min_area_fraction: 0.045
  min_displacement_px: 12
  confirmation_frames: 3

cleaning:
  duster_width_mm: 162.0    # 16.2 cm (configurable)
  duster_height_mm: 58.0    # 5.8 cm (configurable)
  duster_thickness_mm: 42.0 # 4.2 cm (configurable)
  lane_overlap: 0.28        # 28% lane overlap
  nominal_efficiency: 0.85
  clean_threshold: 0.01     # <= 1% is CLEANED
  residual_major_threshold: 0.05 # >= 5% is PARTIALLY_CLEANED (major sweep)
  max_reclean_attempts: 3   # Promotion to PERMANENT_DEFECT
  max_mission_duration_sec: 180.0
  residual_trigger_timeout_sec: 5.0
```

---

## 3. Running Automated Tests

Run the complete test suite using the project virtual environment:

```powershell
& "C:\Users\vkmuk\OneDrive\Documents\Project\.venv\Scripts\python.exe" -m pytest -v
```

All 128 tests pass:
- `tests/test_reconciler_truth_table.py` (all 21 rows)
- `tests/test_reclean_caps.py` (safety cap promotion to PERMANENT_DEFECT)
- `tests/test_planner.py` (Boustrophedon sweep, U-turns, dynamic home dock)
- `tests/test_homography.py` (4-corner calibration and reprojection)
- `tests/test_temporal_occlusion.py` (non-MOG2 occlusion detection & ink preservation)
- `tests/test_shadow_rejection.py` (shadow vs ink discrimination)
- `tests/test_projector_decoupling.py` (Mode A likelihood & UNKNOWN fallback)
- `tests/test_baseline_epochs.py` (epoch roll & dirty board abort)
- `tests/test_closed_loop.py` (complete cyber-physical E2E loop)

---

## 4. Starting the Application

### 4.1 Backend (FastAPI + RTP + WebSockets)
```powershell
cd backend
& "C:\Users\vkmuk\OneDrive\Documents\Project\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- REST API & WebSockets: `http://127.0.0.1:8000`
- RTP Video Stream: `udp://127.0.0.1:5004`
- API Health: `http://127.0.0.1:8000/health`
- Dynamic Config: `http://127.0.0.1:8000/api/config`

### 4.2 Frontend (React + Vite Dashboard)
```powershell
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser.
Production build verification:
```powershell
cd frontend
npm run build
```
Builds cleanly with zero TypeScript errors.
