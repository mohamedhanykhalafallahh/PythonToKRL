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
| `PythonApplication6 - Copie (2).py` | Variant: tilt clamped to 0, TCP `{X 10, Y 0, Z 205, A 180}`, Zr default 0. |
| `PythonApplication6 - large curve.py` | Same as Copie (2), plus Xr = 525 and `inv_sqrt2 = 2 ** -0.0` (= 1): the CIRC via point lies outside the fillet arc, so corners bulge. |
| `PythonApplication6 - Copie.py` | Older A-angle approach ("smooth" shortest-rotation A) and `krl_counter`. |
| `PythonApplication6 - Backup.py` | Older version from before the alternating spiral and orientation work. |
| `PythonApplication1–5, 7.py` | Early prototypes. 5 = free-form LIN/CIRC/SPLINE editor (launched as "Free form"); 7 = circle drawer. |
| `Main_Window_Program_Selector_.py` | Launcher: Cuboid opens App6, Free form opens App5, Cylindrical is a placeholder. Not the current focus. |
| `Sequence.txt` | Design spec for the alternating spiral output order. |

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
- **Auto-Generate Base** (`open_generate_popup`): centre Xr/Yr/Zr, length, width, tool height. Corner radius r = 15% of min(L, W), clamped to [2, min/3]. The via point sits at 45° on each fillet. Order: start top-right, then go counter-clockwise (top edge → TL → left → BL → bottom → BR → right).
- Import/Save `.txt`: lines `X Y Z A B C` (origin), `X Y Z A B C LIN`, `x1 y1 z1 x2 y2 z2 A B C CIRC`.
- "Change Center" offsets every point by (Xc, Yc, Zc).

### Stage 2: Automate (`automate_alternating_spiral`)
- Turn t: each edge is offset outward by `E*t` (via points move by E*t/2 in both X and Y). `e` is negated in `automate()`.
- Layer l: Z += `W*l`.
- Even layers spiral outward (T0 → Tn); odd layers spiral inward (Tn → T0), following `Sequence.txt`.
- Turn and layer changes use `create_circ_transition`: a CIRC whose via point is offset perpendicular to the jump by 20% of its length (drawn purple on the canvas).

### Orientation (Auto-Orient Along Travel, default on)
- A = `atan2(dy, dx)` of the next edge, updated only at CIRC ends. LIN keeps the current A ("pen-like").
- B = tilt angle (interface, clamped to 5–20° in the main file).
- C = interface value.

### Export (`save_krl_code`)
Standard KUKA header (INI folds, PTP HOME). It then sets `BASE_DATA[1] = {Z 200}`, `TOOL_DATA[3]` = MHK-TOOL TCP `{X -5.711, Y 128.569, Z 204.993}`, `$APO.CDIS = 5`, `BAS(#VEL_CP, 2)` and accelerations. The generated moves and `END` follow. The `DEF` name is taken from the file name.

## Known issues / refinement backlog (found 2026-11-03; [x] = fixed in PythonApplication6.py only)
KRL / robot level:
- [x] No `C_DIS` on LIN/CIRC lines, so the robot stops exactly at every point (blobs when extruding), even though `$APO.CDIS` is set.
- [x] The main file's export header wrote the OLD head TCP. Now it writes `{X 10, Y 0, Z 205, A 180}` (NouvTete, assumed). The old value is kept as a comment in the `.src`.
- [ ] Verify the NouvTete TCP (owner): compare with the `TOOL_DATA[3]` line in `NouvTete15.src` and with the controller's tool data.
- [ ] Export overwrites `TOOL_DATA[3]` / `BASE_DATA[1]` on the controller permanently; variants write different TCPs into the same slot.
- [ ] Verify `BAS(#VEL_CP, 2)`: the unit is m/s, so 2 m/s is very fast for printing.
- [x] `DEF` name from the file name must be a valid KRL identifier (no spaces or dashes, length limit).

Logic:
- [ ] Turn offsets are hardcoded by index (`i==1..4`, `j==0,2,4`) and only correct for the Auto-Generate (CCW from top-right) order; the manual order in Help differs.
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
- Python on the home PC: `D:\University\Microsoft Visual Studio\Shared\Python37_64\python.exe` (the `py` launcher's default 3.12 entry points to a missing file).
