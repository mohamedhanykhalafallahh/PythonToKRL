# PythonToKRL: project notes for Claude

Tkinter tool that generates KUKA KRL programs offline. You design a path in the GUI and export a `.src` file. The file goes to the robot (KRC) on a USB stick, so no teaching on the smartPAD is needed. The use case is robotic extrusion / 3D printing of rounded-cuboid walls: several concentric loops ("turns") stacked in Z ("layers").

**Start the program with `KRL_Generator.py`** (the all-in-one app; since step 5d it replaces the old selector). Run the tests with `python tests/regression.py`. Build the stand-alone exe with `python build_exe.py` (output: `dist/KRL_Generator.exe` + `dist/export_profiles.json`).

The owner works on two PCs (office and home) and keeps them in sync through git. Keep this file up to date with decisions and progress, because it is the shared memory between machines.

Working style the owner asked for: go step by step and slowly, plan before coding, and verify each change. Don't rush big rewrites.

## Hardware and process (from the owner, 2026-11-03)
- **Robot:** KUKA KR 6 R900 sixx (art. 10015565, s/n 502323, 07/2014), 6 kg payload, 901 mm reach, floor mounted. `$TRAFONAME` = `KR6R900 C4SR FLR`, MADA `KRC4_SR\KR_6_R900_sixx\FLOOR`, so the controller is a KR C4 smallsize. KSS version and installed options (EKI/RSI) are not known yet.
- **Process:** continuous glass-fiber roving (about 3 mm wide), impregnated with resin and cured by UV. The fiber is never cut, so the whole print is one continuous path, which is why every turn and layer is joined by a transition move.
- **Head ("NouvTete", the new head):** a PETG 3D-printed head. Fiber spool on top, resin funnel, orange resin tube, a spring-loaded roller pressing the fiber onto the bed, and the UV lamp tilted and trailing behind the roller. A follows the travel direction so the lamp always trails. The tilt (B) depends on the roller/nozzle geometry. A more compact head is in progress.
- **TCP:** measured by the 4-point method on a small metal cylinder, accuracy unsure. `TOOL_DATA[3] = {X 10, Y 0, Z 205, A 180}` was only in the variants `Copie (2)` / `large curve`. The main file kept the old MHK head value `{X -5.711, Y 128.569, Z 204.993}` until 2026-11-04, when it was switched to the NouvTete value. That value is an ASSUMPTION: it is not yet confirmed against `NouvTete15.src` or the controller's tool data. The owner will verify it.
- **Base:** `BASE_DATA[1] = {Z 200}` is an estimate; the bed is not calibrated. The owner overrides TOOL/BASE in the `.src` because the controller-side settings caused errors (which error is still unknown).
- **Fiber tension:** currently applied by hand or tape; to be automated later. UV and resin are switched manually for now.
- **Intended values:** layer height about 1 mm, speed about 10 mm/s. Note that `BAS(#VEL_CP, 2)` means 2 **m/s**; the real speed so far came from the smartPAD override.
- **Shape goal:** rounded rectangles now (see the sketches: uniform corner radius, tangent to the edges). Later: rounded cuboids, circles, ovals, infinity shapes and free-form.

## Decisions (2026-11-03)
- C_DIS approximation: yes, to be added.
- Speed: target about 1 cm/s. Set `$VEL.CP` properly instead of relying on the override.
- Turns/layers: keep the N+1 behaviour for now (the owner had loop problems with N).
- TOOL/BASE written in the `.src`: keep for now until the controller-side errors are understood.
- Deferred: E/W label meaning, final closing CIRC, generic turn offsets.

## Files
| File | Role |
|---|---|
| `KRL_Generator.py` | **START HERE: the main program** (see the next row). |
| `KRL_Generator.py` | **The all-in-one main app and the entry point** (class `MainApp`; steps 5b–5d). Shape selector (Cuboid / Cylinder) with per-shape fields (each shape keeps its own values), common Path (E, layer height, turns, layers: exact N) and Orientation (A, B/Tilt used as typed, C, auto-orient), options (C_DIS; Helix for the cylinder only), Generate / 3D View / Export (.src or .txt) / Clear / Undo / Redo / Add Comment / Add Approach (inserted at the text cursor), a top view with zoom/pan/fit, an info line (moves, length, X/Y/Z range, max A vs travel), and an output text with its own typing undo. Menus: File (Open/Save Project, Export), Edit, Tools (3D View, Fit, Export Settings, Manual 11-point editor = App6, Free-form editor = App5; both started with `--from-main`), Help. Projects use `"app": "main"` with keys `shape`, `inputs` {common, cuboid, cylinder}, `options`, `output`. Testable methods: `set_shape`, `generate`, `export_to`, `save_project_to`, `open_project_from`, `state`/`set_state`. |
| `build_exe.py` | Builds `dist/KRL_Generator.exe` (one file, windowed) with PyInstaller 5.13.2 in a private `.venv`, copies `export_profiles.json` next to it, and runs the exe's `--selftest`. `.venv/`, `build/` and `dist/` are git-ignored. |
| `cuboid.py` | Cuboid path generator (no tkinter): `generate_from_loop` (any base loop, exact counts; App6's Automate passes N+1) and the parametric `CuboidParams` / `validate` / `generate` (exact N, B used everywhere, no tilt clamp) for the main app. |
| `cylinder.py` | Cylinder path generator (no tkinter): `CylinderParams`, `validate`, `generate` → (path_model items, info), `_lane_change` (tangent biarc between rings). |
| `view3d.py` | Shared 3D view window (`open_view(parent, get_text, empty_message)`), used by the main app and App6. |
| `PythonApplication6.py` | The old cuboid app, now the **manual 11-point editor** (advanced; opened from the main app's Tools menu). Automate uses `cuboid.py` (N+1 counting kept). Back: closes it if started with `--from-main`, otherwise starts the main app. Opens a project `.json` given on the command line. |
| `PythonApplication5.py` | Free-form LIN/CIRC/SPLINE editor (experimental, set aside; Tools menu). Back as in App6. Still writes its own header (not `krl_export`). |
| `PythonApplication1–4.py` | Early prototypes (unused). |
| Retired in 5d (in git history) | `Main_Window_Program_Selector_.py` (old launcher), `PythonApplication7.py` (cylinder app; everything is in the main app), the launcher images (`KUKAPIC.png`, `cuboid_image.png`, `cylinderical_image.png`, `free_form_image.png`). |
| `Sequence.txt` | Design spec for the alternating spiral output order. |
| `krl_export.py` | Shared `.src` export (no tkinter): header, `ExportSettings` profiles (built-in `NOUVTETE`; JSON load/save, `active_settings`), `add_c_dis`, rounding, DEF-name check, `build_program`. Used by the main app and App6 (App5 not yet). |
| `export_profiles.json` | The export profiles (active + named profiles). Edited through the Export Settings dialog. Currently only "NouvTete". |
| `project_files.py` | Project files (`.json`, no tkinter): `save_project`, `load_project` (checks app and format), `profile_mismatch`. Format 1: `format`, `app` ("main", or the old "cuboid"/"cylinder"), `saved`, `export_profile` (copy), plus the app's own keys. |
| `export_settings_dialog.py` | Export Settings dialog (TOOL/BASE, motion values, decimals, header comments; Save / Save as New / Delete), shared by the main app and App6. |
| `path_model.py` | Path model (no tkinter): `Pose`, `Ptp`/`Lin`/`Circ`/`Comment`/`Raw` items with `to_krl()`; `fmt()` = the ONE number formatter; `parse_krl` (text → items, exact round trip for all app output, unknown lines kept as `Raw`, case-insensitive); `path_3d` (items → 3D polylines with layer/transition flags) and `path_length`. |
| `shapes.py` | Shape geometry (no tkinter): `rounded_rect_base`, `auto_corner_radius`, and the generic turn offset `offset_loop` (outward normals from the geometry; any order or direction). The cylinder/circle base goes here next. |
| `tests/regression.py` | Headless regression test: App6 cases (Auto-Generate → Automate ×2 → Export, Save/Import Points) and cylinder cases (through the main app) against `tests/golden/`, plus unit and app checks (krl_export, path_model, shapes, cylinder, profiles, projects, A arrows, cuboid API, main app, old projects). `tests/fixtures/` holds an App7 project and its export (made before App7 was retired) for the old-format checks. Run after every change; `--update` only when an output change is intended. Line endings are ignored (git `autocrlf`). |

## How PythonApplication6 works

### Data model (module-level globals)
- `points`: PTP/LIN points `(x, y, z)`. `points[0]` is the PTP start.
- `points_circ`: CIRC points in pairs `[via, end, via, end, ...]`.
- `motion_commands`: `"LIN"` / `"CIRC"` sequence (excludes the initial PTP).
- `orientations`: A/B/C per point (in insertion order).
- `current_a_angle`: tracked tool A angle for auto-orient.

### Stage 1: base loop (11 points)
Fixed order: `PTP P1 → LIN P2 → CIRC P3,P4 → LIN P5 → CIRC P6,P7 → LIN P8 → CIRC P9,P10 → LIN P11`. That is 4 edges and 3 rounded corners. The 4th corner (P11 → P1) is closed by a transition CIRC.
Ways to build it:
- Manually: "Add Point" plus the CIRC popup.
- **Auto-Generate Base** (`open_generate_popup` → `shapes.rounded_rect_base`): centre Xr/Yr/Zr, length, width, tool height, corner radius (blank = automatic: `shapes.auto_corner_radius` = 15% of min(L, W), clamped to [2, min/3]; a given radius must be in (0, min(L, W)/2]). The via point sits at 45° on each fillet. Order: start top-right, then go counter-clockwise (top edge → TL → left → BL → bottom → BR → right).
- Import/Save `.txt`: lines `X Y Z A B C` (origin), `X Y Z A B C LIN`, `x1 y1 z1 x2 y2 z2 A B C CIRC`.
- "Change Center" offsets every point by (Xc, Yc, Zc).

### Stage 2: Automate (`automate()` → `cuboid.generate_from_loop`)
Since step 5a the path is generated in `cuboid.py`, which has no tkinter and is shared with the main app. App6's `automate()` only validates the inputs, clamps the tilt to 5–20°, passes `turns + 1` / `layers + 1` (App6 keeps its N+1 counting), writes `program_to_krl(items)` into the box, sets `current_a_angle` to the returned final A, and draws with `draw_output_path()`.
- Turn t: `shapes.offset_loop(base, E*t)` moves every point by `E*t` along its outward normal. Edges shift by E*t; each fillet keeps its centre and its radius grows by E*t, so it stays tangent. The normals come from the geometry (edge perpendicular, arc radial, CW/CCW from the signed area, snapped to exact 0/±1/±√½), so any base order or direction works. `e` is positive (no more negation).
- Layer l: Z += `W*l`.
- Even layers spiral outward (T0 → Tn); odd layers spiral inward (Tn → T0), following `Sequence.txt`.
- Turn and layer changes use `cuboid._transition`: the exact tangent fillet (`cuboid._fillet_transition`: LIN + CIRC or CIRC + LIN), falling back to the old single CIRC with a 20% via offset if the geometry does not allow a fillet. Drawn purple.

### Orientation (Auto-Orient Along Travel, default on)
- A = `atan2(dy, dx)` of the next edge, updated only at CIRC ends. LIN keeps the current A ("pen-like").
- B = tilt angle (interface, clamped to 5–20° in the main file).
- C = interface value.

### Export (`save_krl_code` → `krl_export.build_program`)
`save_krl_code` (and App7's `export_to`) only handle the file dialog and the messages. The `.src` text comes from `krl_export.build_program(name, body, settings, approximate)`, which writes:
1. The standard KUKA header (INI folds, PTP HOME).
2. `; Export profile: <name>`.
3. The profile's BASE/TOOL/approximation/speed/acceleration lines.
4. The moves, rounded to the profile's `decimals` (motion lines only; comments and other lines are untouched; hand-typed lines are rounded too), with `add_c_dis` unless switched off.
5. `END`.

The `DEF` name is the file name and must pass `is_valid_program_name`.

**Export profiles:**
- They live in `export_profiles.json` (repo root, synced by git): `{"active": name, "profiles": {name: {...}}}`.
- Edit them with **Export Settings** (App6: Functions menu; App7: button), from `export_settings_dialog.py`.
- **Save** stores the profile and makes it active; **Save as New** and **Delete** are also there (the last profile can't be deleted).
- Export always uses the active profile (`krl_export.active_settings()`).
- A missing file gives the built-in `NOUVTETE` silently. A broken or invalid file gives the built-in plus a warning.
- Current NouvTete values: `BASE_DATA[1] = {Z 200}`, `TOOL_DATA[3] = {X 10, Y 0, Z 205, A 180}` (assumed), `$APO.CDIS = 5`, `BAS(#VEL_CP, 2)` (m/s), 100% accelerations, decimals 3.
- To change a TCP, speed or decimals, use the dialog. Change the built-in `NOUVTETE` in `krl_export.py` only for the fallback/test default.

**Regression test:** it sets `krl_export.PROFILES_PATH` to a non-existent temp file, so it always uses the built-in profile, never the user's file.

## Cylinder (in the main app; was PythonApplication7, retired in 5d)
Decisions from the owner (2026-11-04):
- Concentric rings with a tangent lane change (not a continuous spiral).
- Layer change at the seam (stepped), plus an optional helix for 1 turn.
- No direction reversal: NouvTete15 ran about 9 CCW loops without an A6 error, so A6 is not limiting.
- Exactly N turns/layers.
- Diameters 100–200 mm; warning when an arc radius is below 20 mm (the cuboid printed fine at r = 22.5).
- Start at angle 0 (+X side).

Path (`cylinder.generate`):
- Ring t: radius R_t = D_inner/2 + E·t, counter-clockwise, made of 4 quarter CIRCs (via at 45°), each starting at angle 0.
- The last quarter (270° → 360°) is the seam:
  - Lane change to the next ring: two tangent 45° arcs (`_lane_change`). The centres are offset by s = ΔR(1+cos45°)/(2 sin²45°) = 1.707·ΔR along the end radials. Arc radii are R+1.707E and R−0.707E outward (mirrored inward), so the smallest arc is R0 − 0.707E. The other root of that equation gives a joint on the far side, which is wrong; this was checked.
  - On the last ring of a layer: the climb to the next layer (Z rises along the quarter, kink = slope, about 0.5–1.6°).
  - On the very last ring: a flat quarter.
- Even layers go outward, odd layers inward. Moves per layer: 5N − 1.
- Helix (N = 1 only): every quarter rises H/4, and the last loop is flat.
- Comments: `===== LAYER n ===== (OUTWARD|INWARD SPIRAL | SINGLE RING[, HELIX])`, `Ll Tt`, `Ll Tt -> Tt' TRANSITION (2 moves)`, `Ll -> Ll+1 TRANSITION (1 move)`. `path_3d` understands `(n moves)`.
- Orientation, auto-orient on: A = travel direction at each CIRC end (rounded 0.1), the PTP already points along the travel direction (A 90), B = B/Tilt field, C as entered. Auto-orient off: A/B/C as entered. B is not clamped (App6 clamps its tilt to 5–20). PTP S 2 / T 43 as in App6.
- Coordinates use full precision (same as App6). Rounding is still on the backlog.

## Known issues / refinement backlog (found 2026-11-03; [x] = fixed in PythonApplication6.py only)
KRL / robot level:
- [x] No `C_DIS` on LIN/CIRC lines, so the robot stops exactly at every point (blobs when extruding), even though `$APO.CDIS` is set.
- [x] The main file's export header wrote the OLD head TCP. Now it writes `{X 10, Y 0, Z 205, A 180}` (NouvTete, assumed). The old value is kept as a comment in the `.src`.
- [ ] Verify the NouvTete TCP (owner): compare with the `TOOL_DATA[3]` line in `NouvTete15.src` and with the controller's tool data.
- [ ] Export overwrites `TOOL_DATA[3]` / `BASE_DATA[1]` on the controller permanently (and App5 writes a different TCP into `TOOL_DATA[1]`).
- [ ] Verify `BAS(#VEL_CP, 2)`: the unit is m/s, so 2 m/s is very fast for printing.
- [x] `DEF` name from the file name must be a valid KRL identifier (no spaces or dashes, length limit).

Logic:
- [x] Turn offsets were hardcoded by index (`i==1..4`, `j==0,2,4`) and only correct for the Auto-Generate (CCW from top-right) order. Now generic (`shapes.offset_loop`), step 4.
- [ ] `range(turns + 1)` / `range(layers + 1)`: entering N gives N+1 turns/layers.
- [x] After Automate, the globals hold the last turn, so a second Automate compounds offsets.
- [ ] The final closing CIRC (last turn back to pt1, from Sequence.txt) is not generated.
- [x] `current_a_angle = 180.0` in `automate_alternating_spiral` lacks `global` (no effect).
- [x] The tilt toggle only affects LIN; both CIRC branches (~line 824) are identical.
- [x] Automation Help text says "A constant, B/C tilt", but the code does A rotating and B tilt.
- [x] Labels: "Filament Thickness (E)" was the in-plane step and "Filament Width (W)" the Z step. Renamed (2026-11-04) to "Turn Step E (mm)" / "Layer Height W (mm)" in App6, and "Turn Step E" / "Layer Height" in the main app.

Minor:
- [x] The 11-point limit is checked after appending the 12th point.
- [x] Automate clears the output before validating inputs; it also pushes two undo snapshots.
- [x] Undo does not capture `current_a_angle`.
- [x] `save_points` indexes `orientations` with separate LIN/CIRC counters (wrong when orientations differ).

## Progress log
- 2026-11-03: Initial analysis of the codebase; this file created.
- 2026-11-03 (home): Fixed 9 backlog items in `PythonApplication6.py`: DEF-name validation, base restored after Automate (re-Automate is idempotent), `global current_a_angle`, tilt-off CIRC uses interface A/B/C, Help text, 11-point check before append, validate-then-clear in Automate (one undo snapshot), undo stores `current_a_angle`, `save_points` orientation index. Verified with a headless Tk test (generate base, Automate twice gives identical output, undo works). Variant files are NOT updated.
  Still open, needs the owner's decision: C_DIS on moves, TOOL/BASE overwrite, VEL_CP value, N vs N+1 turns/layers, E/W label meaning, final closing CIRC, hardcoded turn-offset indices.
- 2026-11-03 (home): Analysed the real print `NouvTete15.src` (150×300 base, r = 22.5, E = 2, Z step 2, B -3). Findings:
  - The three normal corners were sent with the CIRC via point at 0.536·r from the fillet centre instead of 0.707·r. Each CIRC is therefore a nearly flat arc (R ≈ 111 mm, 16° sweep) with **about 37° kinks at both ends**, close to a chamfer.
  - The turn-transition CIRC at the top-right corner is a real, nearly tangent arc (R ≈ 24, 87° sweep, kinks ≤ 4°). So that corner is the only truly round one.
  - Answered: the owner had changed `inv_sqrt2 = 2 ** -0.5` to `2 ** -0.9` (= 0.536) while experimenting with values from -0.1 to -1. The correct value is -0.5 (the 45° point on the fillet).
  - The real print shows **outward blobs/loops** at corners 3, 6-7 and 9-10 (owner's sketch), not chamfers. Explanation: A is interpolated over 90° during each CIRC. On the chamfer-like arc the travel direction turns only 16°, so the roller and lamp point up to **37° away from the travel direction**, the roller skids and drags fiber and resin sideways, and the robot stops at the kinks. On a true fillet, linear A matches the tangent exactly (0° misalignment).
  - Why transition 11→1 is good: its via point sits 20% of the chord off the chord midpoint; an exact quarter circle needs 20.7%. So it is almost a perfect quarter circle (misalignment ≤ 4°). With `2 ** -0.5` the three corners become the same kind of arc. The remaining corner error for turns > 0 is the `E*t/2` via shift (should be `E*t/√2`).
  - Real speed of this print: about 7.9 m of path in about 50 s at 10% override, so **about 150 mm/s**, roughly 15× the intended 10 mm/s.
  - Owner's data: 150×300 base, E = W = 2 mm, 10% override, bed tilted about 1-2° (lower to the left, unconfirmed), big resin blob on the bottom edge from stopping at points (no C_DIS).
- 2026-11-04: Curve fix plan agreed: (1) via shift `E*t/√2`, (2) C_DIS on LIN/CIRC, (3) optional controller-side tangent orientation (`$ORI_TYPE`/`$CIRC_TYPE`, depends on KSS), (4) dry run, then a small 2-3 turn print.
  - Step 1 done in `PythonApplication6.py`: the turn offset for CIRC via points is now `E*t/√2` (was `E*t/2`). Headless test (150×300, E = 2, 5 turns, 2 layers): corner kinks went from up to 13° (radius 43.4 instead of 32.5 at turn 5) to 0°, with exact radii 22.5 to 32.5. The transition CIRCs are unchanged (kinks ≤ 3.8°). Variant files are NOT updated (`large curve` still uses `2 ** -0.0`).
  - The old 20% transition rule gave kinks of 2.6° (E = 1, r = 22.5) up to 20° (20×20, E = 3), so it got worse when E was large compared with r.
  - Step 1b done: the turn/layer transition is now an exact tangent fillet (`_fillet_transition`, called from `create_circ_transition` with the new `prev_point`, taken from `get_last_two_points_of_turn`). A single CIRC can't be tangent to both edges, because start and end lie on rings one E apart. So: outward = LIN of E up the right edge, then a quarter circle of radius r + d_t. Inward = quarter circle of radius r + d_(t-1), then a LIN of E along the top edge into P1. Layer change = a single quarter circle with Z rising along it. The routine is generic (it reads the directions from the path) and falls back to the old 20% rule if the geometry is degenerate. It assumes the previous turn ends with a LIN, which is true for the 11-point base.
  - Verified headlessly on 7 cases (20×20 to 600×80, E = 1 to 5, up to 20 turns, 1 to 3 layers, moved centres): max kink 0° on ALL moves, all non-transition lines byte-identical to before, Z monotone, re-Automate identical, tilt-off works. Hand-checked T0→T1, L0→L1 and T2→T1 for the 300×150 case.
  - Effect on the `.src`: transitions are now 1 or 2 lines (LIN + CIRC or CIRC + LIN) instead of 1 CIRC. The extra LIN is only E long, so C_DIS (step 2) matters there to avoid a stop.
  - Committed as 4a56bbd.
  - Step 2 done: `add_c_dis()` runs at export (`save_krl_code`), controlled by the checkable entry "Approximate Moves on Export (C_DIS)" in the Functions menu, under Auto-Orient (on by default, `c_dis_var`). It adds ` C_DIS` to every LIN/CIRC except PTP lines and the very last motion. It is idempotent and keeps trailing `;` comments. The on-screen preview is unchanged. `$APO.CDIS` stays 5 mm (owner's choice). Verified with a headless export (52 moves → 50 with C_DIS; off-export has none; header unchanged). On the robot, blending only happens in continuous run, not in single-step mode.
- 2026-11-04: TCP switched to NouvTete (b2eb00b). Push from this PC failed (GitHub credentials), so the owner pushes manually.
- 2026-11-04: Canvas cleanup (drawing only; KRL output verified byte-identical):
  - Every CIRC is drawn as the real arc (`draw_arc`) instead of two straight lines, with the via dot on the arc. Transitions are drawn in purple (arc and the short LIN pieces).
  - Labels are small and grey, placed beside the line or arc on the outside, with one label per group (same text within 12 px is skipped).
  - The canvas keeps its 400×320 size. `visualize_cuboid()` ends with `fit_view()` (zoom + scroll so the whole drawing fits, auto-zoom capped at 3×). Mouse wheel zooms around the pointer. Double-click the canvas, or use Functions → "Fit Canvas to Drawing", to fit again. The zoom is `view_zoom` on top of `scaling_factor` and always scales about the canvas origin; dots and label offsets keep their pixel size. Clearing the canvas resets the zoom.
  - The top-right corner looked messy before because outward, inward and layer transitions take different (real) paths there, while the other corners overlap exactly across layers. It was not leftover drawings.
  - The manual-mode "dummy" closing CIRC drawing in `add_point` is unchanged (still two lines).
  - Testing tip: `runpy.run_path` returns a COPY of the globals, so use `g["automate"].__globals__` for live values. For screenshots, use PowerShell `CopyFromScreen`, with Tk coordinates multiplied by the display scale (1.25 on this PC).
- 2026-11-04: Canvas cleanup committed and pushed (5814381). Pushing from this PC works again.
- 2026-11-04: Canvas drag to move: left-drag pans 1:1 (`start_pan`/`do_pan`/`end_pan`, via `scan_mark`/`scan_dragto`). On press, the scroll region is enlarged by one window size on each side, so you can drag past the drawing. Double-click still fits. Testing tip: synthetic Tk events need increasing `time=` values, otherwise every second press counts as a double-click.
- 2026-11-04: 3D View (Functions → "3D View", Ctrl+Shift+D), with no extra libraries (option B; matplotlib/numpy are not installed on this PC). It is a separate window (class `View3D`); the 2D canvas is unchanged.
  - It reads the KRL output text (`parse_path_3d`), so it shows exactly what goes to the robot. CIRCs are real 3D arcs through start/via/end (`_arc_points_3d`).
  - Transitions are in purple: moves after a `TRANSITION` comment up to the first CIRC, plus the inward trailing LIN (detected because two LINs in a row never happen inside a turn).
  - Layers are coloured from the `; ===== LAYER n` comments.
  - Controls: Z exaggeration slider 1-40 (the default makes the stack about 15% of the shape size), "Colour by layer" checkbox, Iso/Top/Front/Side buttons, Reload (re-reads the output after a new Automate). Orthographic view: left-drag rotates, right/middle-drag moves, wheel zooms around the pointer, double-click resets. Axis cross with mm lengths in the info line; green dot = start, red dot = end.
  - Verified: all 51 moves parsed, path continuous, arc ends exact, top-view corner radii exact, 9 transition moves as expected (2 turns, 2 layers). Screenshots checked (iso/front/top). KRL output unchanged.
  - Possible next: arrows showing the head direction (A) along the path.
- 2026-11-04: Roadmap agreed (after the curve fix, pending the lab test):
  - Priority 0 (`$VEL.CP` from a mm/s field; A6 wind-up from always-CCW loops) is DEFERRED by the owner: speed is controlled by override for now, and the owner believes A6 rotates endlessly (the datasheet says ±350° unless the option is fitted). Revisit if a print stops on an A6 limit.
  - Priority 1, shared core, step by step with a check after each step: (1) regression test; (2) `krl_export.py` (header, TOOL/BASE, speed, C_DIS, DEF check, JSON tool/base profiles) shared by all apps (App5 currently writes `TOOL_DATA[1] {Z 20}`); (3) `path_model.py` (segment list; the text box and the 3D view become views of it); (4) parametric cuboid generator (turn t = rounded rectangle L+2d, W+2d, r+d), which removes the hardcoded index offsets; corner radius as an input; (5) delete the variant files and turn their differences into options.
  - Priority 2, cylinder (App7 is only a stub with invalid KRL): 4 quarter CIRCs per loop (2 halves give an ambiguous 180° A change; many LINs give facets), with an optional helix (Z rising through each loop, no seam). Concentric turns reuse the cuboid transitions.
  - Priority 3, UI: parametric panel as the main view, pre-export checks (length, time, reach, warnings), JSON project files, A arrows in the 3D view, later a PyInstaller exe. Keep Tkinter.
  - Later, a deliberate output change: round coordinates (they were written like `391.59009742330267`). Done 2026-11-04, see Priority 3 step 2.
  - Step 1 done: `tests/regression.py` + `tests/golden/` (6 cases: sizes 20×20 to 600×80, E 1-3, up to 5 turns, 1-2 layers, moved centres, tilt off, C_DIS off; 18 files). It also checks that Automate is idempotent. A deliberately corrupted golden line is caught. App code unchanged. Committed as 5d936fc.
  - Step 2 done: `krl_export.py` created. App6's `add_c_dis`, the regexes, the DEF-name check and the 60-line header f-string were removed; `save_krl_code` calls `krl_export.build_program(..., approximate=c_dis_var.get())`. Regression: ALL IDENTICAL (byte-identical `.src`). The app also starts normally when launched from another folder. App5 NOT switched yet (it still writes its own header with `TOOL_DATA[1] {Z 20}`, `BASE {Z 50}`); switching it changes its output, so that needs the owner's OK. JSON profiles / a settings dialog are deferred to Priority 3 (UI). Committed as cdf475a.
  - Step 3 done: `path_model.py`. Decision: the output text box stays the source for export (the user adds comments/approach moves and may edit by hand); the model is the single way lines are written and read.
    - App6: all ~25 f-string KRL writers replaced by `emit(item)` / `emit_ptp` / `emit_lin` / `emit_circ` / `emit_comment` (plus `ptp_item`/`lin_item`/`circ_item` for `generate_krl_code`). Values that were written with `:.1f` now go through `a1()` = `round(v, 1)`, which gives identical text. PTP S/T = `PTP_S, PTP_T = 2, 43`.
    - The 3D view uses `pm.path_3d(pm.parse_krl(text))`. App6's own parser, `_xyz_3d`, `_arc_points_3d` and the vector helpers were removed (93 lines), as was the unused `format_point`.
    - Verified: regression ALL IDENTICAL. All 18 golden files round-trip byte-exact. Old vs new 3D parser give identical moves on all goldens and on hand edits (the only difference: lowercase `lin` is now read, which is correct KRL). Manual flows (Add Point, CIRC popup, Approach, Comment, base preview) give identical text compared with the previous commit. The 3D window opens and draws (51 moves, 9 transitions). The app launches from another folder.
    - The regression test now also checks path_model (round trip, continuous 3D path with one move per LIN/CIRC, hand-edit tolerance). Arc start points match the previous end only up to about 4e-15 mm (float noise), so the check uses a 1e-9 tolerance.
  - Step 3 committed as bc623ec.
  - Step 4 done: `shapes.py` (no tkinter): `auto_corner_radius`, `rounded_rect_base` (the popup formulas, moved), `loop_orientation`, `loop_normals`, `offset_loop`.
    - Automate: the hardcoded `i/j` offset table and the unused `dummy_circ_*` lines were removed, and `e` is no longer negated. Each turn is `offset_loop(base, E*t)`.
    - Auto-Generate: geometry from `shapes`, a new "Corner Radius (blank = auto)" field (row 6, Generate button now row 7), validation (L, W > 0; 0 < r ≤ min/2), and a single undo snapshot (it used to push one before validating, plus one in `clear_all`).
    - `clear_all` now also empties `orientations` (it used to grow with every Generate).
    - Verified:
      - The new offset is bit-identical to the old table on 2004 rectangles × 5 E × 6 turns. One bug was found and fixed on the way: zero-length edges (the r = L/2 "stadium") now take the normal of the adjacent arc or the other edge end.
      - Regression ALL IDENTICAL.
      - Explicit r = 40: radii 40/42/44/46 exactly, tangent.
      - Invalid inputs show an error and leave the state unchanged.
      - A clockwise base now grows exactly d on every side, with radius r + d and tangent; the old table did not grow it at all.
    - Regression additions: case `REG_r40` (3 new golden files; the existing goldens are unchanged) and `check_shapes` (CCW + CW, including the stadium).
  - Step 4 committed as 1330d96.
  - Step 5 done (owner's decision: none of their differences are needed): the variant files `PythonApplication6 - Backup.py`, `- Copie.py`, `- Copie (2).py` and `- large curve.py` were deleted with `git rm`. They are still in git history (e.g. `git show 1330d96:"PythonApplication6 - Copie (2).py"`). What they had: Copie (2) had tilt clamped to 0, TCP `{X 10, Y 0, Z 205, A 180}` (now the default anyway) and Zr default 0; large curve was the same plus `inv_sqrt2 = 2 ** -0.0` (bulging corners); Copie had an older "smooth" shortest-rotation A and `krl_counter`; Backup predated the spiral and orientation work. Nothing referenced them.
  - Priority 1 (shared core) is complete. Variant deletion committed as f16c0fd.
- 2026-11-04: Priority 2, cylinder app (steps C1–C5, see "How PythonApplication7 works"):
  - C1 `cylinder.py`. Also added to `path_model`: `move_tangents`, `tangent_kinks` (atan2-based, accurate near 0°; acos gave a 1e-6° floor) and the `TRANSITION (n moves)` rule in `path_3d`. Verified on 6 parameter sets: flat joins tangent to 1e-13°, radii exact, counts, Z, A within the 0.1 rounding, 3D transition counts. In 3D, App6's layer climbs also kink by their slope (about 2° on 300×150; the 2D checks were 0°).
  - C2 `view3d.py`: the 3D view moved out of App6 (206 lines). App6 regression identical; open twice → one window; close/reopen works.
  - C3 `PythonApplication7.py` rewritten from scratch (the old file was a stub with invalid KRL). Headless and screenshot checks were done (top view + 3D view of 5 turns × 3 layers). The text box does not wrap and has a horizontal scrollbar.
  - C4: the selector's Cylindrical button launches App7; App7 has Back and Help.
  - C5: regression has 5 `CYL_*` cases (golden `.src`) and `check_cylinder`. The App6 goldens are unchanged. ALL IDENTICAL.
  - Next: the owner tests the cylinder (dry run first). Committed as 63ba375.
- 2026-11-04: Priority 3 plan agreed:
  - (1) Pre-export checks: SKIPPED for now (too many open lab variables; the owner will measure them first, then they come back as a precaution). Reach assumptions for later: robot base = world origin, wrist point = TCP + 205 mm up, reach 901 mm from A2 (25 mm forward, 400 mm up).
  - (2) Export profiles + settings dialog: done, see below.
  - (3) JSON project files.
  - (4) A arrows in the 3D view.
  - (5) One main app with a shape choice (last).
  - (6) A PyInstaller exe later.
  - Owner's decisions: time estimate skipped; rounding yes, as a profile option; only the NouvTete profile for now.
  - Step 2a (no output change):
    - `path_model.fmt(v, decimals)` and `to_krl(decimals)` / `program_to_krl(items, decimals)`.
    - `krl_export` profiles (JSON at `PROFILES_PATH`, `settings_to_dict/from_dict` with validation: tool 1..16, base 1..32, decimals 0..6).
    - `export_settings_dialog.py`, wired into both apps.
    - Regression stayed identical. New `check_profiles`: JSON round trip, header identical from JSON, broken-file fallback for 4 bad files, rounding moves no number by more than 0.0005, and the dialog edit/Save/Save as New/invalid input/Delete/last-profile guard.
  - Step 2b (intended output change):
    - NOUVTETE `decimals=3`, plus the header line `; Export profile: <name>`.
    - Verified against the previous goldens: only the 12 `.src` files changed, by exactly one added line each, and 439 motion lines changed only in their numbers (max 0.000495 mm). Points/preview files unchanged.
    - Largest kink at a flat join after rounding: 0.02° (20×20 shape), typically < 0.007°.
    - Full precision could also print `1e-07`-style numbers, which KRL may not accept; rounding avoids that.
    - `export_profiles.json` created from the built-in.
  - Committed as ba8aee2.
  - Step 3 done: project files.
    - App6: Functions menu "Open Project... / Save Project..." (Ctrl+Shift+O / Ctrl+Shift+S; not Ctrl+O, because Tk's Text widget inserts a new line on Ctrl+O). App7: buttons.
    - App6 project keys: `base` (points, points_circ, motion_commands, orientations), `base_params` (Auto-Generate Xr/Yr/Zr/L/W/Th/r/r_auto, or null if the base was made or changed by hand), `generate_popup` (the popup pre-fill), `entries` (X..C, E, W, turns, layers, tilt), `options` (auto_orient, c_dis), `current_a_angle`, `output`.
    - App7 project keys: `inputs`, `options` (auto_orient, helix, c_dis), `output`.
    - Open: restores everything, then regenerates (App6: Automate, if the saved output has LAYER comments and E/W/turns/layers are filled; App7: Generate). If the result differs from the SAVED output (hand edits or a program change), the saved output is kept and a notice is shown. A profile mismatch gives a warning; the active profile is still used for export. A wrong app, damaged JSON or a newer format is refused with an error and nothing changes.
    - In App6, Open plus its Automate is ONE undo step: the extra snapshot pushed by Automate is popped.
    - New App6 state: `base_params` (included in the undo snapshot, reset by clear_all, Add Point, the CIRC popup, Import and Change Center) and `generate_popup_values` (the Auto-Generate popup now remembers the last values).
    - `check_projects` in the regression covers both apps: reopen gives an identical output and `.src`, hand edits are kept with a notice, the profile warning, damaged and wrong-app files are refused cleanly, undo after open, a base-only project, and restored parameters and fields. ALL IDENTICAL.
  - Owner's lab test found an issue: Open Project (automated) → Undo → Redo restored the output and the values, but the canvas showed only the 11 base points.
    - Cause: `_restore_state` always called `visualize_cuboid()` (base only); the automated turns are drawn only while Automate runs. The same happened for Automate → Clear All → Undo.
    - Fix: `draw_output_path()` draws the path from the OUTPUT TEXT the way Automate does (blue moves with labels and red dots, purple transitions with a purple via dot). `redraw_canvas_from_state()` uses it when the output has `===== LAYER` comments, otherwise `visualize_cuboid()`. Used by `_restore_state` (undo/redo) and by Open Project (also when the saved output is kept).
    - Verified with a geometric comparison of the canvas (each shape's start/mid/end in mm, so the 30 vs 31 arc sample points caused by float noise don't matter): Redo and Clear+Undo are identical to the live Automate drawing in 4 cases. The regression now checks Open, Undo (empty canvas), Redo, and Clear All + Undo against the live drawing (`_canvas_moves`/`_same_drawing`, 0.05 mm tolerance); with the old behaviour put back temporarily it fails as expected. Screenshot confirmed.
  - Committed as 0a73d26.
  - Step 4 done: head-direction arrows in the 3D view.
    - `path_model.heading_checks(items)` returns, for every LIN/CIRC, A at the MIDDLE (interpolated the short way from the previous A) and at the END, compared with the exact travel direction there (analytic arc tangent via `_arc_frame`): `dev` = |A − heading|. Also `angle_diff`.
    - `view3d`: checkbox "Head direction (A)" (off by default). It draws 16 px arrows (cos A, sin A in XY), tagged `head_arrow`: green ≤ 5°, orange ≤ 20°, red > 20°. The info line shows the largest deviation and the number of red arrows.
    - Results: all auto-orient goldens (App6 and App7) are within 0.33° at move ends and mid-arcs; orientation-off cases are red. The old NouvTete15 corner (via 0.536 r) is flagged at 36.8° at the arc end, matching the 37° analysis; the fixed corner shows 0°.
    - Regression `check_heading`: goldens, the old-corner case, and the view drawing one arrow per check. Do not call `update()` on a new Tk root in the test: it runs stale events of earlier test windows and prints "ThemeChanged" Tk noise.
    - Screenshots checked (top view: all green for REG_300x150; red where A stays 180 while travelling +Y in REG_tilt_off).
  - Committed as 309ece3. Pre-export checks (step 1) are still deferred; `tangent_kinks` and `heading_checks` are ready for them.
- 2026-11-04: Step 5 plan agreed with the owner (one all-in-one app):
  - The new main app is the entry point. App6 stays reachable from it as the advanced "manual 11-point editor". App7 and the selector retire (git keeps them).
  - Exact N turns/layers in the new app; App6 keeps N+1.
  - No tilt clamp: the B / Tilt value is used as typed.
  - Field names "Turn/Ring step E (mm)" and "Layer height (mm)".
  - Layout like App7: inputs left, top view right, output bottom, shape selector at the top. No function may be lost.
  - Sub-steps: 5a cuboid generator out of App6; 5b main window; 5c open old project files; 5d entry point; 5e tests/screenshots/CLAUDE.md.
  - Step 5a done: `cuboid.py`.
    - The App6 Automate code (`automate_alternating_spiral`, `generate_turn_path`, `_fillet_transition`, `create_circ_transition`, `get_last_(two_)point(s)_of_turn`, `calculate_transition_a_angle`; 397 lines) was moved out. The global `current_a_angle` became `_Writer.a`, and the Auto-Orient checkbox became a parameter.
    - App6 `automate()` calls `cuboid.generate_from_loop(..., turns + 1, layers + 1, ..., tilt (clamped 5–20), auto_orient)` and draws with `draw_output_path()`.
    - Verified before switching: App6's old Automate vs the new generator on 60 random cases (15 clockwise bases, 11 orientation-off, tilt outside 5–20, r = L/2, up to 6 turns × 4 layers): all byte-identical, including the final A. After switching: regression ALL IDENTICAL.
    - New `check_cuboid_params`: the parametric `cuboid.generate` (exact N) reproduces every auto-orient App6 golden `.src` byte for byte. Orientation-off differs only in B on the transition moves: App6 wrote the tilt there, the new API uses B everywhere (intended cleanup).
  - Committed as e01eb0a.
  - Step 5b done: `KRL_Generator.py` (see the Files table). Every App6/App7 function is mapped: Auto-Generate/Automate/Generate → shape panel + Generate; Change Center → the centre fields; manual Add Point/CIRC/Import/Save Points → Tools > Manual 11-point editor (opens App6); the Help tab → Help menu; the .src/.txt format → the export dialog file types.
    - Cuboid "Start Z" = App6's Zr + tool height.
    - Ctrl+Z / Ctrl+Y inside the text box undo the typing (Text undo=True); elsewhere they are the app undo (inputs + output, 20 steps).
    - Regression `check_main_app`: the new app reproduces EVERY auto-orient App6 golden (App6 N+1 entered as N) and every App7 golden byte for byte from the same inputs. It also checks shape switching keeping values (and helix shown only for the cylinder), undo/redo of Generate/Clear, comment and approach inserted at the cursor (undoable), the project round trip, a hand edit kept with a notice, an old cylinder project refused (until 5c), and refused Generates leaving the state unchanged. ALL IDENTICAL.
    - Screenshots checked (cuboid and cylinder). Launches from another folder.
    - Owner's defaults (2026-11-04): cuboid Length X 150 × Width Y 300, Number of Layers 3, B / Tilt 0 (turns 3, E 2, layer height 2, A 180, C 180, centre 535/10, Start Z 65; cylinder inner Ø 100).
  - Committed as 8d415da.
  - Step 5c done: the main app opens old projects (`project_files.load_project_any`; converters `state_from_cylinder_project` / `state_from_cuboid_project` in KRL_Generator).
    - App7 cylinder: 1:1.
    - App6 cuboid with `base_params`: Xr/Yr → centre, Zr+Th → Start Z, L/W, corner radius (blank if `r_auto`), E/W entries → step/layer height, turns/layers **+1** (N+1 → exact), B = the clamped tilt (auto-orient) or the B entry (off). Numbers are written with `_num` (full precision, not `%g`).
    - Base-only App6 project (no LAYER comments): sizes are loaded, the output is kept, with a notice.
    - Hand-made base (`base_params` null): asks, then starts App6 with the project path. App6 now opens a `.json` given as `argv[1]` via `root.after(200, ...)`.
    - The title shows the project name, plus "(from the … app; Save Project writes the new format)" for converted projects. The old file is never changed.
    - Regression `check_old_projects`: the App7 and App6 projects made by `check_projects` open with no notice and the identical output; the App7 export is identical; Generate after opening is identical; converted values are checked; base-only gets a notice; manual base: "No" changes nothing, "Yes" starts App6 with the path; App6's start-up hook is run without `update()`. Also checked with the real event loop in a separate process. ALL IDENTICAL.
  - Committed as 0ad2927.
  - Rounding question (owner): the text box shows full precision; rounding to the profile's decimals (3) happens at EXPORT, for LIN and CIRC alike. The LIN points are just exact numbers, while CIRC vias at 45° are irrational. Left as is; the box could show rounded values later if wanted.
  - Step 5d done: the main app is the entry point.
    - `git rm` of the selector, App7 and the 4 launcher images.
    - App6/App5 Back: `--from-main` → only close; otherwise start `KRL_Generator.py`. App6 opens the first existing `*.json` in argv.
    - Main app: Tools → Free-form editor (App5); both editors are started with `--from-main`.
    - The `project_files` wrong-app message now points to the KRL Generator.
    - Tests: the CYL goldens run through the main app (`cyl_case_fields` fills in App7's defaults: B 20, 2 layers); `check_projects` uses the main app for the cylinder part; old-format checks use `tests/fixtures/app7_cylinder_project.json` + `APP7_CYLINDER.src` (made by App7, saved time fixed). New checks: App6 Back with and without `--from-main`, and the free-form launch args. ALL IDENTICAL. All three apps launch.
  - Committed as a96a4ca.
  - Text box rounding (owner's request): the main app now SHOWS the moves rounded like the export.
    - `show_items(items)` renders with the active profile's decimals and keeps `_generated = (items, text)`.
    - `round_text()` rounds any text like the export. Export is unchanged because rounding a rounded value gives the same digits (all goldens still identical).
    - Open Project compares `round_text(regenerated)` with `round_text(saved)`, so old full-precision projects open without a notice and are then shown rounded.
    - Export Settings → `on_profile_saved`: if the box still holds exactly the generated text, it is re-rendered from the full-precision items with the new decimals (3 → 5 works); hand-edited text is left alone.
    - The info line says "values as exported: N decimals (profile …)".
    - App6 (manual editor) still shows full precision.
    - Regression `check_box_rounding`.
  - Step 5e done (final review of step 5):
    - All 17 menu entries are wired (File: Open/Save Project, Export, Exit; Edit: Undo, Redo, Add Comment, Add Approach, Clear; Tools: 3D View, Fit, Export Settings, Manual editor, Free-form editor; Help: How to use, Current shape, Keyboard and mouse).
    - Screenshots with frame and menu were checked: main cuboid, main cylinder helix (Z +0.5 per quarter), 3D view with arrows (0 red of 154), Add Approach (pre-filled A/B/C), manual editor started with `--from-main`.
    - App6 tidy (owner's OK): title is now "Manual 11-point Cuboid Editor (advanced) - KRL Generator"; labels are "Turn Step E (mm)" / "Layer Height W (mm)". Its N+1 counting stays.
  - Step 5 (all-in-one app) is complete. Committed as aa260ff (with the App6 title/label tidy).
- 2026-11-04: Step 6, the stand-alone exe. Owner's decisions: one-file exe; Windows 10/11 64-bit lab PC; build the exe first, polish the UI afterwards (then rebuild).
  - 6a, exe-ready code:
    - `krl_export.app_dir()` = the exe folder when frozen (else the source folder); `PROFILES_PATH` is there, never in the one-file temp unpack folder.
    - `KRL_Generator.main()` switches: `--tool manual|freeform` (runs App6/App5 in-process by importing them; argv passed on), `--selftest [--quiet]`.
    - `tool_command()`: frozen → `[exe, --tool, name]`, else `[python, script]`; the main app adds `--from-main` (+ project path).
    - App6/App5 Back when frozen and not `--from-main`: start `sys.executable` (the exe).
    - Self-test: generates and exports the default cuboid and cylinder to a temp folder and checks header, END, moves and A vs travel. It writes `selftest_report.txt` next to the program (git-ignored), including the active TOOL/BASE/decimals/CDIS/VEL_CP, shows a message box unless `--quiet`, and the exit code is 0 if OK.
    - Regression `check_frozen_mode` simulates `sys.frozen` (app_dir, tool commands, App6 Back restarting the exe).
  - 6b, `build_exe.py` (run with the 3.7 Python):
    - Creates `.venv` with PyInstaller 5.13.2 (the last version for Python 3.7; needs internet the first time).
    - Builds `dist/KRL_Generator.exe` (`--onefile --windowed`, hidden imports PythonApplication5/6, work/spec files in `build/`), copies `export_profiles.json` next to it, and runs `--selftest --quiet`.
    - The exe is about 8.1 MB. `.venv`, `build/` and `dist/` are git-ignored. The only "missing module" warning is `org` (optional, from pickle).
  - 6c, real exe tests (all OK): the self-test inside the exe (program folder = dist, profile read); a changed profile next to the exe is used after a restart (X 11.5 / 4 decimals) and the restored one again; the main window launches and stays open (screenshot); `--tool manual --from-main project.json` opens the project with all turns drawn (screenshot); `--tool freeform` opens; an unknown tool is refused.
  - For the lab PC: copy `dist/KRL_Generator.exe` and `dist/export_profiles.json` together. `KRL_Generator.exe --selftest` shows a check, including the TCP it will write.
  - Next: UI polish (owner agreed: after the exe; show a mock-up first), then rebuild with `python build_exe.py`. Deferred: pre-export checks (step 1), App5 on `krl_export`.
- Python on the home PC: `D:\University\Microsoft Visual Studio\Shared\Python37_64\python.exe` (the `py` launcher's default 3.12 entry points to a missing file).
