# Test Infrastructure Specification: Smart Erasing Duster (V2.1) Digital Twin

## 1. Architectural Overview & Test Strategy

The Smart Erasing Duster (V2.1) Digital Twin is an event-sourced cyber-physical simulation and control platform. Ensuring its deterministic reliability, physical accuracy, and safety requires an opaque-box, multi-tier test architecture.

Testing is structured into **4 Primary Tiers** (with an extended Tier 5 for adversarial hardening):
- **Tier 1: Core Feature Coverage** (>= 5 deterministic unit/component tests per core feature)
- **Tier 2: Boundary, Extreme & Corner Cases** (>= 5 boundary tests per feature, zero-division, geometric limits, timing caps)
- **Tier 3: Cross-Feature Combinations & Invariant Matrix** (Pairwise and combinatorial state transitions across perception, twin, and planner)
- **Tier 4: Real-World Application Scenarios** (Deterministic end-to-end user journeys 1 through 6)
- **Tier 5: Adversarial Stress & Chaos Hardening** (Timing jitter, stream packet loss, sensor noise, malformed payloads)

---

## 2. Tier 1: Core Feature Coverage (>= 5 Tests per Core Feature)

Every feature in the system is tested with at least 5 independent, self-contained test cases.

### Feature 1: Decoupled Physical Twin Store (`board_twin.py`)
1. `test_phys_twin_initial_state_empty`: Verifies an initialized board twin contains zero ink objects and empty masks.
2. `test_phys_twin_create_ink_object`: Verifies instantiation of `InkObject` with valid UUID, `FRAME_BOARD` coordinates, polygon geometry, and `NEW_INK` state.
3. `test_phys_twin_state_transition_valid`: Verifies valid physical state progression (`NEW_INK` -> `STABLE_INK` -> `PARTIALLY_CLEANED` -> `CLEANED`).
4. `test_phys_twin_rejects_residual_detected_state`: Asserts that `RESIDUAL_DETECTED` is NOT a member of `PhysicalState` enum and cannot be stored.
5. `test_phys_twin_garbage_collection_at_epoch`: Verifies that `CLEANED` objects are cleared upon epoch roll while `PERMANENT_DEFECT` objects are retained.

### Feature 2: Decoupled Execution Action Store (`execution_state.py`)
1. `test_exec_store_initial_idle`: Verifies execution store defaults to `IDLE` state with robot at Home Dock.
2. `test_exec_store_state_transitions`: Verifies transitions `IDLE` -> `PLANNING` -> `CLEANING_ACTIVE` -> `VERIFYING`.
3. `test_exec_store_residual_flags`: Verifies `residual_detected_flag` is set during `VERIFYING` and triggers `RECLEAN_PENDING`.
4. `test_exec_store_residual_tier_classification`: Verifies assignment of `TIER_1_CLEANED` ($r \le 1\%$), `TIER_2_FINE_RESIDUAL` ($1\% < r < 5\%$), and `TIER_3_MAJOR_RESIDUAL` ($r \ge 5\%$).
5. `test_exec_store_safety_lock_watchdog`: Verifies watchdog trigger forces transition to `SAFETY_LOCK` and terminates actuator dispatch.

### Feature 3: 21-Row Commit Truth Table Reconciler (`reconciler.py`)
1. `test_truth_table_rows_1_to_4_clean_and_noise`: Parameterized tests for Rows 1–4 (baseline rejection, ink creation, occlusion ignoring, projector uncertainty).
2. `test_truth_table_rows_5_to_7_unknown_resolution`: Parameterized tests for Rows 5–7 (resolving `UNKNOWN` to ink or clean, maintaining uncertainty).
3. `test_truth_table_rows_8_to_11_stable_ink_lifecycle`: Parameterized tests for Rows 8–11 (steady state, multi-object separation, occlusion preservation, unobserved decay).
4. `test_truth_table_rows_12_to_14_occluded_transitions`: Parameterized tests for Rows 12–14 (occlusion retention, restoration on departure, external wipe detection).
5. `test_truth_table_rows_15_to_21_cleaning_and_defects`: Parameterized tests for Rows 15–21 (residual retention, verified clean, new ink over cleaned, permanent defect preservation, safety cap hit).

### Feature 4: Safety Loop Cap & Defect Promotion (`state_machine.py`, `reconciler.py`)
1. `test_reclean_counter_increment`: Verifies `reclean_attempts` counter increments on each failed wipe attempt.
2. `test_reclean_cap_exact_threshold_3`: Verifies that attempts 1 and 2 result in `RECLEAN_PENDING`, while attempt 3 transitions object to `PERMANENT_DEFECT`.
3. `test_reclean_cap_emits_action_event`: Verifies `RECLEAN_CAP_HIT` action is emitted when cap is reached.
4. `test_reclean_cap_clears_execution_queue`: Verifies the actuator planner queue drops the capped object and returns execution to `IDLE`.
5. `test_reclean_cap_updates_permanent_mask`: Verifies object geometry is burned into `permanent_defect_mask` to prevent future cleans.

### Feature 5: Dynamic Actuator & Board Dimensions (`config.yaml`, `config.py`)
1. `test_config_load_default_dimensions`: Verifies board $1000 \times 700$ mm and duster $162 \times 58 \times 42$ mm match config.
2. `test_config_dynamic_board_dimensions`: Tests config override with $1200 \times 900$ mm board.
3. `test_config_dynamic_duster_dimensions`: Tests config override with $200 \times 80$ mm duster.
4. `test_config_validation_positive_dimensions`: Verifies negative or zero dimensions raise Pydantic `ValidationError`.
5. `test_config_lane_overlap_boundary`: Verifies lane overlap parameter is constrained between $[0.05, 0.90]$.

### Feature 6: Dynamic Home Dock Calculation (`config.py`)
1. `test_home_dock_default_coordinates`: Verifies Home Dock $(x_{\text{home}}, y_{\text{home}}) = (81.0, 671.0)$ mm for $162 \times 58$ mm duster on $1000 \times 700$ mm board.
2. `test_home_dock_updated_on_duster_resize`: Modifies duster to $200 \times 80$ mm; verifies Home Dock computes to $(100.0, 660.0)$ mm without code change.
3. `test_home_dock_updated_on_board_resize`: Modifies board to $1500 \times 1000$ mm; verifies Home Dock computes to $(81.0, 971.0)$ mm.
4. `test_home_dock_orientation_zero`: Verifies $\theta_{\text{home}} == 0.0$ radians/degrees.
5. `test_home_dock_clearance_inside_board`: Asserts duster at Home Dock is strictly within $[0, W] \times [0, H]$ bounding box.

### Feature 7: Coordinate Frame Tagging & Transforms (`frames.py`)
1. `test_frame_tag_enum_members`: Verifies `FRAME_CAMERA`, `FRAME_BOARD`, `FRAME_DUSTER`, `FRAME_PATH` exist.
2. `test_frame_duster_to_board_transform`: Transforms local duster corners to board space at pose $(x_d, y_d, \theta_d)$.
3. `test_frame_board_to_duster_inverse`: Verifies inverse transform $T^{-1}(T(p)) \approx p$.
4. `test_frame_tag_enforcement_in_ink_object`: Verifies `InkObject` requires `frame_id == FRAME_BOARD`.
5. `test_frame_mismatch_raises_exception`: Passing `FRAME_CAMERA` coordinates to board planner raises `CoordinateFrameMismatchError`.

### Feature 8: Dual-Channel Transport Backend (`stream.py`, `ws.py`)
1. `test_rtp_packetizer_header_rfc3550`: Verifies RTP packetizer builds 12-byte header with correct payload type, sequence number, and timestamp.
2. `test_rtp_packetizer_jpeg_fragmentation_rfc2435`: Verifies JPEG frames $> 1400$ bytes are fragmented according to RFC 2435.
3. `test_websocket_events_broadcast`: Connects async client to `/ws/events` and receives `TWIN_DELTA` on ink creation.
4. `test_websocket_telemetry_rate`: Connects to `/ws/telemetry` and verifies periodic pose and metric updates.
5. `test_http_mjpeg_stream_route`: Queries `/api/camera/stream` and verifies `multipart/x-mixed-replace` header and valid JPEG boundaries.

### Feature 9: 4-Corner Homography Registration (`registration.py`)
1. `test_homography_identity_mapping`: Verifies identity homography when camera corners match board corners.
2. `test_homography_perspective_warp`: Verifies known trapezoidal camera coordinates warp to orthogonal rectangle in `FRAME_BOARD`.
3. `test_homography_reprojection_error`: Asserts reprojection error of calibration points is $< 1.5$ mm.
4. `test_homography_point_warp_bijective`: Verifies forward and backward point projections round-trip within $< 0.1$ mm.
5. `test_homography_singular_matrix_handling`: Degenerate collinear points raise `CalibrationGeometryError`.

### Feature 10: Multi-Space Difference & Illumination Normalization (`difference.py`, `illumination.py`)
1. `test_diff_rgb_channel`: Verifies Euclidean distance in RGB color space highlights ink strokes.
2. `test_diff_hsv_channel`: Verifies saturation and value diffs distinguish colored markers from white background.
3. `test_diff_cielab_channel`: Verifies Delta-E in CIELAB space detects subtle low-contrast markers.
4. `test_diff_edge_gradient`: Verifies Sobel/Scharr gradient magnitude detects sharp stroke boundaries.
5. `test_diff_fusion_weighting`: Verifies 11-channel evidence fusion produces normalized score $\in [0.0, 1.0]$.

### Feature 11: Shadow Rejection via Invariant Chrominance Ratios (`shadow.py`)
1. `test_shadow_luminance_drop_with_constant_chroma`: Verifies illumination reduction without color shift is classified as `OBS_SHADOW`.
2. `test_shadow_vs_black_ink_discrimination`: Verifies dark marker ink (high contrast, edge gradient) is classified as `OBS_INK`, not shadow.
3. `test_shadow_mask_generation`: Asserts shadow mask accurately segments soft hand and actuator shadows.
4. `test_shadow_rejection_in_reconciler`: Verifies shadow observation does not create `InkObject` (Truth Table Row 1).
5. `test_shadow_boundary_gradient`: Verifies soft gradient transitions are treated as shadow penumbra rather than ink edges.

### Feature 12: Mode A Projector Decoupling (`projector.py`)
1. `test_projector_continuous_likelihood_range`: Verifies output likelihood $P_{\text{proj}} \in [0.0, 1.0]$.
2. `test_projector_high_confidence_suppression`: Score $> 0.85$ suppresses stroke candidate from physical ink.
3. `test_projector_ambiguous_region_to_unknown`: Score $0.35 \le P_{\text{proj}} \le 0.85$ maps region to `OBS_UNCERTAIN` / `UNKNOWN`.
4. `test_projector_never_creates_ink`: Asserts projector light projection never instantiates `NEW_INK`.
5. `test_projector_never_deletes_twin_ink`: Projector beam shining over `STABLE_INK` preserves the twin ink object.

### Feature 13: Non-MOG2 Temporal Occlusion Detection (`occlusion.py`)
1. `test_occlusion_area_fraction_threshold`: Verifies moving object $\ge 4.5\%$ of board area triggers occlusion.
2. `test_occlusion_area_fraction_below_threshold`: Moving small object $< 4.5\%$ does not trigger board occlusion mask.
3. `test_occlusion_temporal_persistence_3_frames`: Verifies occlusion requires $\ge 3$ consecutive frames before confirming `OBS_OCCLUDED`.
4. `test_occlusion_coherent_motion_vector`: Verifies optical flow coherence differentiates actor movement from writing.
5. `test_occlusion_preserves_ink_in_twin`: Verifies overlapping `STABLE_INK` transitions to `OCCLUDED` without deletion.

### Feature 14: Baseline Capture Validation & Discrete Epoch Roll (`reference.py`)
1. `test_baseline_capture_clean_board_success`: Accumulates 20 frames on clean board (edge density $< 0.04$) and establishes Epoch 0.
2. `test_baseline_capture_dirty_board_abort`: Edge density $= 0.058 > 0.04$ aborts capture with `BASELINE_VALIDATION_FAILED`.
3. `test_baseline_override_dirty_board`: Setting `allow_dirty_board_override: true` allows capture despite edge density.
4. `test_baseline_epoch_roll_on_verified_clean`: When post-wipe residual $\le 0.01$, baseline advances to Epoch $k+1$.
5. `test_baseline_epoch_roll_masks_permanent_defects`: Board with $0.005$ residual and $0.03$ permanent defect successfully rolls epoch.

### Feature 15: Boustrophedon Sweep Coverage Planner (`coverage.py`, `smoothing.py`)
1. `test_coverage_lane_step_overlap_28_percent`: Asserts effective lane step $\Delta y = h_{\text{duster}} \times (1 - 0.28) = 41.76$ mm.
2. `test_coverage_lanes_span_entire_target_hull`: Verifies sweep paths completely cover target bounding box.
3. `test_coverage_exterior_u_turns_outside_hull`: Verifies U-turn apex points lie strictly outside target ink hull.
4. `test_coverage_sweep_direction_alternation`: Verifies left-to-right followed by right-to-left lane passes.
5. `test_coverage_zero_target_empty_path`: Empty target polygon produces safe no-op trajectory.

### Feature 16: Continuous Transit Trajectory Planning (`transit.py`)
1. `test_transit_starts_at_home_dock`: First waypoint is $(x_{\text{home}}, y_{\text{home}}, 0.0)$.
2. `test_transit_ends_at_home_dock`: Final waypoint returns to $(x_{\text{home}}, y_{\text{home}}, 0.0)$.
3. `test_transit_velocity_limits`: Waypoint linear velocities do not exceed configured $v_{\max}$.
4. `test_transit_continuity`: Distance between consecutive trajectory waypoints does not exceed step limit.
5. `test_transit_entry_angle_alignment`: Approach vector smoothly aligns with first sweep lane orientation.

### Feature 17: Exact Physical Operational Metrics (`metrics.py`)
1. `test_metrics_precision_exact_formula`: Matches $\text{Area}(M_{\text{det}} \cap M_{\text{gt}}) / \text{Area}(M_{\text{det}})$.
2. `test_metrics_recall_exact_formula`: Matches $\text{Area}(M_{\text{det}} \cap M_{\text{gt}}) / \text{Area}(M_{\text{gt}})$.
3. `test_metrics_iou_exact_formula`: Matches $\text{Area}(M_{\text{det}} \cap M_{\text{gt}}) / \text{Area}(M_{\text{det}} \cup M_{\text{gt}})$.
4. `test_metrics_fpr_exact_formula`: Matches $\text{Area}(M_{\text{det}} \setminus M_{\text{gt}}) / \text{Area}(\text{Clean Board})$.
5. `test_metrics_residual_fraction_exact_formula`: Matches $\text{Area}(M_{\text{post}}) / \text{Area}(M_{\text{pre}})$.
6. `test_metrics_cleaning_coverage_exact_formula`: Matches $\text{Area}(M_{\text{swept}} \cap M_{\text{target}}) / \text{Area}(M_{\text{target}})$.
7. `test_metrics_tracking_stability_exact_formula`: Matches $1.0 - (N_{\text{switches}} / N_{\text{frames}})$.

### Feature 18: Multi-Layer Simulation Engine (`simulation/`)
1. `test_simulation_board_layer_compositing`: Verifies composite render of baseline + ink + defects + projector.
2. `test_simulation_duster_footprint_erasing`: Wiping over ink layer clears pixels within duster polygon.
3. `test_simulation_imperfect_cleaning_residual`: Configured efficiency $< 1.0$ leaves realistic fine residual ink.
4. `test_simulation_permanent_defect_inerasable`: Sweeping duster over `PERMANENT_DEFECT` leaves defect layer intact.
5. `test_simulation_interactive_brush_injection`: Injects stroke via brush API and verifies appearance on ink layer.

---

## 3. Tier 2: Boundary, Extreme & Corner Cases (>= 5 Tests per Core Feature)

Testing edge cases, zero-division, extreme inputs, and boundary limits.

### Boundary Group A: Operational Metrics Zero-Division & Extreme Values
1. `test_metrics_clean_board_both_empty`: $\text{Area}(M_{\text{det}})=0, \text{Area}(M_{\text{gt}})=0 \implies \text{Precision}=1.0, \text{Recall}=1.0, \text{IoU}=1.0, \text{FPR}=0.0$.
2. `test_metrics_detector_complete_miss`: $\text{Area}(M_{\text{det}})=0, \text{Area}(M_{\text{gt}})>0 \implies \text{Precision}=0.0, \text{Recall}=0.0, \text{IoU}=0.0, \text{FPR}=0.0$.
3. `test_metrics_pure_ghost_detection`: $\text{Area}(M_{\text{det}})>0, \text{Area}(M_{\text{gt}})=0 \implies \text{Precision}=0.0, \text{Recall}=1.0, \text{IoU}=0.0, \text{FPR}>0.0$.
4. `test_metrics_board_completely_covered`: $\text{Area}(M_{\text{gt}}) = W \times H \implies \text{Area}(\text{Clean Board})=0 \implies \text{FPR}=0.0$.
5. `test_metrics_zero_preclean_area`: Pre-clean target area $= 0 \implies \text{Residual Fraction} = 0.0$.

### Boundary Group B: Geometric Limits & Boundary Collisions
1. `test_geometry_ink_touching_board_boundary`: Stroke right against $(x=0, y=0)$ or $(x=1000, y=700)$ does not clip out of bounds or crash planner.
2. `test_geometry_single_pixel_micro_stroke`: Stroke with area $< \text{stroke\_min\_area}$ (15 mm²) is filtered out as noise.
3. `test_geometry_gigantic_full_board_stroke`: Stroke covering $95\%$ of board plans valid multi-pass coverage without memory exhaustion.
4. `test_geometry_duster_overlap_zero`: Setting `lane_overlap: 0.0` produces contiguous abutted lanes without gaps.
5. `test_geometry_duster_overlap_near_unity`: Setting `lane_overlap: 0.85` produces highly dense sweeps without infinite loops.

### Boundary Group C: Timing, Counters & Caps
1. `test_reclean_attempts_exact_boundary`: Exactly 3 attempts triggers defect promotion; attempt 2 does not.
2. `test_mission_duration_cap_exceeded`: Wall-clock execution exceeding 180s trips mission abort to `SAFETY_LOCK`.
3. `test_residual_trigger_timeout`: Transient perception flicker exceeding 5s resets `residual_detected_flag`.
4. `test_temporal_persistence_under_threshold`: Ink appearing for only 2 frames (threshold 3) is discarded as transient noise.
5. `test_occlusion_area_fraction_boundary_4_49_vs_4_51`: 4.49% does not trigger occlusion; 4.51% triggers occlusion.

### Boundary Group D: Perception Threshold Boundaries
1. `test_dirty_board_threshold_boundary`: Edge density $= 0.039$ passes baseline validation; $0.041$ aborts.
2. `test_clean_threshold_boundary`: Residual $= 0.009$ classified as `TIER_1_CLEANED`; $0.011$ classified as `TIER_2_FINE_RESIDUAL`.
3. `test_residual_major_threshold_boundary`: Residual $= 0.049$ classified as `TIER_2_FINE_RESIDUAL`; $0.051$ classified as `TIER_3_MAJOR_RESIDUAL`.
4. `test_spatial_matching_iou_boundary`: IoU $= 0.39$ rejects match; $0.41$ accepts match.
5. `test_spatial_matching_distance_boundary`: Centroid dist $= 30.1$ mm rejects match; $29.9$ mm accepts match.

---

## 4. Tier 3: Cross-Feature Combinations & Invariant Matrix

Verifies cross-cutting interactions between independent modules:

| Combination | Feature A | Feature B | Interaction & Invariant Under Test |
| :--- | :--- | :--- | :--- |
| **C1** | Dynamic Geometry (`config.yaml`) | Coverage Planner (`coverage.py`) | Changing duster height from $58$ to $80$ mm dynamically widens sweep lane pitch $(\Delta y = 80 \times 0.72 = 57.6\text{ mm})$. |
| **C2** | Dynamic Geometry (`config.yaml`) | Home Transit (`transit.py`) | Changing board to $1200 \times 900$ mm updates start/end transit waypoints to $(81.0, 871.0)$ mm. |
| **C3** | Homography (`registration.py`) | Physical Twin (`board_twin.py`) | Distorted camera perspective correctly warps to millimeter coordinates; Twin object centroid matches physical board location. |
| **C4** | Shadow Filter (`shadow.py`) | Reconciler (`reconciler.py`) | Duster casting dynamic shadow during sweep does not register as `RESIDUAL_INK` in verification. |
| **C5** | Occlusion (`occlusion.py`) | Reconciler (`reconciler.py`) | Human occluding ink during active clean prevents premature `CLEANED` marking; preserves `OCCLUDED` until actor vacates. |
| **C6** | Projector Decoupling (`projector.py`)| Reconciler (`reconciler.py`) | Projected slide appearing over clean whiteboard creates `UNKNOWN` region in twin; planner refuses to generate cleaning path for light. |
| **C7** | Re-clean Hard Cap | Baseline Epoch Roll | Stubborn residual promoted to `PERMANENT_DEFECT` (Row 21) is automatically masked, allowing baseline epoch to advance. |
| **C8** | Multi-Cluster Drawing | Sequential Mission Planning | 3 separate ink clusters written concurrently generate optimized TSP ordering of wiping passes. |

---

## 5. Tier 4: Real-World Application Scenarios (Scenarios 1..6)

Comprehensive, opaque-box end-to-end user workflows executed against the integrated digital twin:

### Scenario 1: Clean Board Single Stroke Closed-Loop Cleaning
- **Initial State**: Baseline established on pristine whiteboard (Epoch 0).
- **Step 1**: User draws a horizontal marker stroke ($200 \times 15$ mm) at $(300, 200)$ mm.
- **Step 2**: Camera captures frame $\to$ Homography rectifies to `FRAME_BOARD`.
- **Step 3**: Perception detects stroke with high confidence $\to$ Reconciler creates `NEW_INK` $\to$ transitions to `STABLE_INK`.
- **Step 4**: Cleaning mission dispatched $\to$ Execution transitions to `PLANNING` $\to$ Boustrophedon sweep generated from Home Dock.
- **Step 5**: Actuator sweeps across stroke footprint $\to$ Virtual duster erases ink with $85\%$ efficiency $\to$ Fine residual remaining ($15\%$).
- **Step 6**: Verification window evaluates residual ($r = 0.15 \ge 0.05 \implies \text{TIER\_3\_MAJOR\_RESIDUAL}$) $\to$ Twin marks `PARTIALLY_CLEANED` $\to$ Re-clean planned.
- **Step 7**: Secondary pass executes $\to$ Residual drops to $0.005 \le 0.01 \implies \text{TIER\_1\_CLEANED}$.
- **Step 8**: Closed loop confirms clean $\to$ Twin transitions to `CLEANED` $\to$ Duster parks at Home Dock $\to$ Epoch rolls to 1.

### Scenario 2: Multi-Cluster Writing & Sequential Mission Execution
- **Initial State**: Clean board.
- **Step 1**: User writes three separate ink clusters: Top-Left $(150, 150)$, Center $(500, 350)$, Bottom-Right $(800, 550)$.
- **Step 2**: Reconciler instantiates three distinct `InkObject`s with separate UUIDs.
- **Step 3**: Planner orders traversal minimizing total transit distance from Home Dock.
- **Step 4**: Actuator sequentially cleans Cluster 1 $\to$ Cluster 2 $\to$ Cluster 3.
- **Step 5**: All 3 clusters verified clean $\to$ Duster returns to Home Dock.

### Scenario 3: Real-Time Human Hand Occlusion & Ink Preservation
- **Initial State**: Board with `STABLE_INK` object at $(400, 300)$.
- **Step 1**: Presenter's hand/arm enters camera frame covering the ink object ($> 4.5\%$ board area, coherent motion).
- **Step 2**: Perception detects `OBS_OCCLUDED` over the object geometry.
- **Step 3**: Truth Table Row 10 fires: `STABLE_INK` transitions to `OCCLUDED`.
- **Step 4**: **CRITICAL INVARIANT VERIFIED**: The ink object is NOT deleted or marked absent.
- **Step 5**: Presenter's hand leaves the board.
- **Step 6**: Perception sees `OBS_INK` again $\to$ Truth Table Row 13 fires: State restored to `STABLE_INK`.

### Scenario 4: Digital Projector Artifact Rejection
- **Initial State**: Clean board.
- **Step 1**: A digital projector displays an interactive slide with high-luminance diagrams on the whiteboard.
- **Step 2**: Mode A continuous likelihood evaluates $P_{\text{proj}} = 0.55$ (ambiguous region).
- **Step 3**: Truth Table Row 4 fires: Region classified as `UNKNOWN`, added to `uncertainty_mask`.
- **Step 4**: **CRITICAL INVARIANT VERIFIED**: No `NEW_INK` is created in the Physical Twin Store.
- **Step 5**: Dispatch clean mission $\to$ Planner ignores `UNKNOWN` regions; duster remains stationary at Home Dock.

### Scenario 5: Stubborn Marker Residue & Re-Clean Hard Cap Defect Promotion
- **Initial State**: Marker ink written with permanent/stubborn dry-erase ink.
- **Step 1**: Cleaning pass 1 executed $\to$ Residual remains high ($r = 0.20$). `reclean_attempts` becomes 1.
- **Step 2**: Cleaning pass 2 executed $\to$ Residual remains high ($r = 0.18$). `reclean_attempts` becomes 2.
- **Step 3**: Cleaning pass 3 executed $\to$ Residual remains high ($r = 0.16$). `reclean_attempts` hits 3.
- **Step 4**: **CRITICAL INVARIANT VERIFIED (Row 21)**: Reconciler unconditionally transitions object to `PERMANENT_DEFECT`.
- **Step 5**: Event `RECLEAN_CAP_HIT` emitted $\to$ Object burned into `permanent_defect_mask`.
- **Step 6**: Planner drops object from queue $\to$ Actuator returns Home $\to$ Baseline epoch rolls with defect masked.

### Scenario 6: Dirty Board Baseline Initialization Rejection
- **Initial State**: Whiteboard with uncleaned marker writing from previous day.
- **Step 1**: User sends baseline capture request (`POST /api/reference/capture`).
- **Step 2**: Reference engine accumulates 20 frames and computes edge density $= 0.058$.
- **Step 3**: System detects edge density exceeds `dirty_board_threshold` ($0.058 > 0.040$).
- **Step 4**: **CRITICAL INVARIANT VERIFIED**: Baseline capture ABORTS immediately.
- **Step 5**: Alert `BASELINE_VALIDATION_FAILED` emitted to `/ws/events` $\to$ No epoch created $\to$ System safely refuses operation until board is wiped.

---

## 6. Test Execution & Automation Matrix

| Test Suite File | Focus Area | Command |
| :--- | :--- | :--- |
| `tests/test_reconciler_truth_table.py` | Exhaustive 21-Row Commit Truth Table | `pytest tests/test_reconciler_truth_table.py -v` |
| `tests/test_reclean_caps.py` | Safety Cap at 3 Re-cleans & Defect Promotion | `pytest tests/test_reclean_caps.py -v` |
| `tests/test_homography.py` | 4-Corner Homography Registration in `FRAME_BOARD` | `pytest tests/test_homography.py -v` |
| `tests/test_difference_maps.py` | 11-Channel Diff & Illumination Normalization | `pytest tests/test_difference_maps.py -v` |
| `tests/test_shadow_rejection.py` | Shadow vs Ink Chrominance Discrimination | `pytest tests/test_shadow_rejection.py -v` |
| `tests/test_projector_decoupling.py` | Mode A Likelihood & `UNKNOWN` Handling | `pytest tests/test_projector_decoupling.py -v` |
| `tests/test_temporal_occlusion.py` | Multi-Signal Occlusion & Ink Retention (No MOG2) | `pytest tests/test_temporal_occlusion.py -v` |
| `tests/test_baseline_epochs.py` | Baseline Validation (>0.04 abort) & Epoch Roll | `pytest tests/test_baseline_epochs.py -v` |
| `tests/test_planner.py` | Boustrophedon Sweep, 28% Overlap, U-turns, Transit | `pytest tests/test_planner.py -v` |
| `tests/test_closed_loop.py` | Full Closed-Loop Workflows (Write -> Clean -> Verify) | `pytest tests/test_closed_loop.py -v` |
| `tests/e2e/test_dynamic_geometry.py` | Dynamic Geometry Updates Without Code Edits | `pytest tests/e2e/test_dynamic_geometry.py -v` |
| `tests/e2e/test_occlusion_handling.py` | E2E Human Hand Occlusion & Ink State Retention | `pytest tests/e2e/test_occlusion_handling.py -v` |
| `tests/e2e/test_dirty_baseline_rejection.py` | E2E Dirty Board Rejection (Edge Density > 0.04) | `pytest tests/e2e/test_dirty_baseline_rejection.py -v` |
| `tests/e2e/test_projector_mode_a.py` | E2E Mode A Likelihood & UNKNOWN Preservation | `pytest tests/e2e/test_projector_mode_a.py -v` |
| `tests/e2e/test_scenarios_1_to_6.py` | Deterministic Presets for Scenarios 1 through 6 | `pytest tests/e2e/test_scenarios_1_to_6.py -v` |

### Full Test Suite Runner Command
```powershell
& "C:\Users\vkmuk\OneDrive\Documents\Project\.venv\Scripts\python.exe" -m pytest tests/ -v --tb=short
```
