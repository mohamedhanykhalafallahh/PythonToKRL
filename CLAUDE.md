# PythonToKRL: project notes for Claude

Tkinter tool that generates KUKA KRL programs offline. You design a path in the GUI and export a `.src` file. The file goes to the robot (KRC) on a USB stick, so no teaching on the smartPAD is needed. The use case is robotic extrusion / 3D printing of rounded-cuboid walls: several concentric loops ("turns") stacked in Z ("layers").

The owner works on two PCs (office and home) and keeps them in sync through git. Keep this file up to date with decisions and progress, because it is the shared memory between machines.

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
- [ ] No `C_DIS` on LIN/CIRC lines, so the robot stops exactly at every point (blobs when extruding), even though `$APO.CDIS` is set.
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
- Python on the home PC: `D:\University\Microsoft Visual Studio\Shared\Python37_64\python.exe` (the `py` launcher's default 3.12 entry points to a missing file).
