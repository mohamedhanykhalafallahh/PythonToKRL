# PythonToKRL: project notes for Claude

Tkinter tool that generates KUKA KRL programs offline. You design a path in the GUI and export a `.src` file. The file goes to the robot (KRC) on a USB stick, so no teaching on the smartPAD is needed. The use case is robotic extrusion / 3D printing of rounded-cuboid walls: several concentric loops ("turns") stacked in Z ("layers").

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
| `PythonApplication6.py` | **Main program**, "Cuboidal KRL Code Generator". |
| `PythonApplication1–5, 7.py` | Early prototypes. 5 = free-form LIN/CIRC/SPLINE editor (launched as "Free form"); 7 = circle drawer. |
| `Main_Window_Program_Selector_.py` | Launcher: Cuboid opens App6, Free form opens App5, Cylindrical is a placeholder. Not the current focus. |
| `Sequence.txt` | Design spec for the alternating spiral output order. |
| `krl_export.py` | Shared `.src` export (no tkinter): header, BASE/TOOL/speed profile (`ExportSettings`, `NOUVTETE`), `add_c_dis`, DEF-name check, `build_program`. Used by App6; App5 and the cylinder app are to follow. |
| `path_model.py` | Path model (no tkinter): `Pose`, `Ptp`/`Lin`/`Circ`/`Comment`/`Raw` items with `to_krl()`; `fmt()` = the ONE number formatter; `parse_krl` (text → items, exact round trip for all app output, unknown lines kept as `Raw`, case-insensitive); `path_3d` (items → 3D polylines with layer/transition flags) and `path_length`. |
| `shapes.py` | Shape geometry (no tkinter): `rounded_rect_base`, `auto_corner_radius`, and the generic turn offset `offset_loop` (outward normals from the geometry; any order or direction). The cylinder/circle base goes here next. |
| `tests/regression.py` | Headless regression test of App6 (Auto-Generate → Automate ×2 → Export, Save/Import Points) against `tests/golden/`, plus `krl_export` unit checks and an invalid-file-name check. Run after every change; `--update` only when an output change is intended. Line endings are ignored (git `autocrlf`). |

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

### Stage 2: Automate (`automate_alternating_spiral`)
- Turn t: `shapes.offset_loop(base, E*t)` moves every point by `E*t` along its outward normal. Edges shift by E*t; each fillet keeps its centre and its radius grows by E*t, so it stays tangent. The normals come from the geometry (edge perpendicular, arc radial, CW/CCW from the signed area, snapped to exact 0/±1/±√½), so any base order or direction works. `e` is positive (no more negation).
- Layer l: Z += `W*l`.
- Even layers spiral outward (T0 → Tn); odd layers spiral inward (Tn → T0), following `Sequence.txt`.
- Turn and layer changes use `create_circ_transition`: a CIRC whose via point is offset perpendicular to the jump by 20% of its length (drawn purple on the canvas).

### Orientation (Auto-Orient Along Travel, default on)
- A = `atan2(dy, dx)` of the next edge, updated only at CIRC ends. LIN keeps the current A ("pen-like").
- B = tilt angle (interface, clamped to 5–20° in the main file).
- C = interface value.

### Export (`save_krl_code` → `krl_export.build_program`)
`save_krl_code` only does the file dialog and the error message. The `.src` text comes from the shared module `krl_export.py`: the standard KUKA header (INI folds, PTP HOME), then the settings of an `ExportSettings` profile (currently `NOUVTETE` = `DEFAULT_SETTINGS`: `BASE_DATA[1] = {Z 200}`, `TOOL_DATA[3] = {X 10, Y 0, Z 205, A 180}` (assumed), `$APO.CDIS = 5`, `BAS(#VEL_CP, 2)` and accelerations), then the moves (with `add_c_dis` unless switched off) and `END`. The `DEF` name is the file name and must pass `is_valid_program_name`. To change a TCP, speed or header line, edit the profile in `krl_export.py`, not the apps.

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
- [ ] Labels: "Filament Thickness (E)" is used as the in-plane step and "Filament Width (W)" as the Z step (looks swapped).

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
  - Later, a deliberate output change: round coordinates (they are currently written like `391.59009742330267`).
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
  - Priority 1 (shared core) is complete. Next: Priority 2, the cylinder app (App7 rewrite on `krl_export` + `path_model` + `shapes`).
- Python on the home PC: `D:\University\Microsoft Visual Studio\Shared\Python37_64\python.exe` (the `py` launcher's default 3.12 entry points to a missing file).
