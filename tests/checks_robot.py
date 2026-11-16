"""Checks for the robot arm model and the robot in the 3D view (used by regression.py).

    check_robot_model()      kinematics (known pose, there-and-back), a program on the robot:
                             Status / Turn, reach, axis limits, singularity, long programs
    check_robot_view()       main app: reach in the checks chip; 3D view: robot drawn, slider, Play
Each check returns a list of problems (empty = ok).
"""
import dataclasses
import math
import random
import tkinter as tk

import cuboid
import krl_export
import path_model as pm
import robot_model as rm


def _cuboid(xc=150, yc=225, turns=3, layers=3, b=-3.0):
    items, _info = cuboid.generate(cuboid.CuboidParams(
        xc=xc, yc=yc, z0=10, length=150, width=300, corner_radius=None, step=2, layer_height=2,
        turns=turns, layers=layers, a=180, b=b, c=180, auto_orient=True))
    return items


def check_robot_model():
    bad = []
    R, S = rm.KR6_R900, krl_export.NOUVTETE

    # the data sheet: reach, and the flange with the arm upright and the forearm level
    for robot, reach in ((rm.KR6_R900, 901.5), (rm.KR6_R700, 706.7), (rm.KR10_R1100, 1101.2)):
        if abs(robot.reach - reach) > 0.06:
            bad.append("%s: reach %.2f, data sheet %.1f" % (robot.name, robot.reach, reach))
    home = rm.pose_of(R, (0, -90, 90, 0, 0, 0))
    if max(abs(a - b) for a, b in zip(home, (525.0, 0.0, 890.0, 0.0, 90.0, 0.0))) > 1e-9:
        bad.append("upright pose: flange %s, expected X 525, Z 890, B 90" % (home,))
    # KUKA directions: A1 + turns clockwise seen from above, A2 + lowers the arm
    if rm.pose_of(R, (30, -90, 90, 0, 0, 0))[1] >= 0 or rm.pose_of(R, (0, -80, 90, 0, 0, 0))[2] >= 890:
        bad.append("axis directions: A1 +30 must give Y < 0, A2 -80 must be lower than A2 -90")

    # there and back: every solution gives the asked flange, and the asked angles are among them
    rnd = random.Random(7)
    worst, missing = 0.0, 0
    for _ in range(400):
        q = tuple(rnd.uniform(lo, hi) for lo, hi in R.limits[:3]) + (rnd.uniform(-180, 180),
                                                                    rnd.uniform(-120, 120), rnd.uniform(-180, 180))
        fl = rm.forward(R, q)
        sols = rm.inverse(R, fl)
        for s in sols:
            f2 = rm.forward(R, s)
            worst = max(worst, max(abs(a - b) for a, b in zip(f2[1], fl[1])),
                        100 * max(abs(f2[0][i][j] - fl[0][i][j]) for i in range(3) for j in range(3)))
        if not any(max(abs(rm._wrap(a - b)) for a, b in zip(s, q)) < 1e-6 for s in sols):
            missing += 1
    if worst > 1e-8 or missing:
        bad.append("inverse kinematics: error %.2e mm, %d of 400 poses not found again" % (worst, missing))
    abc = rm.abc_of(rm.rot_abc(123.0, -41.0, 77.0))
    if max(abs(a - b) for a, b in zip(abc, (123.0, -41.0, 77.0))) > 1e-9:
        bad.append("A B C <-> rotation: %s" % (abc,))

    # the default cuboid with the calibrated TOOL / BASE
    items = _cuboid()
    rep = rm.analyse(items, S)
    if rep.messages or rep.unreachable:
        bad.append("default cuboid should be fine on the robot: %s" % rep.messages)
    # the model finds the Status / Turn that the programs write (and that run on the real robot)
    if rep.start_st != (cuboid.PTP_S, cuboid.PTP_T):
        bad.append("Status / Turn of the start point: model %s, programs write S 2 / T 43" % (rep.start_st,))
    # the solved axes really put the TCP on the programmed points
    err = 0.0
    for ps in rep.poses[::25]:
        got = rm.pose_of(R, ps['q'], S)
        err = max(err, max(abs(got[k] - ps['xyz'][k]) for k in range(3)))
    if err > 1e-6:
        bad.append("solved axes miss the programmed points by %.2e mm" % err)
    # the head turns once per loop: axis 6 follows (3 turns x 3 layers, about 9 loops)
    turns6 = (rep.ranges[5][1] - rep.ranges[5][0]) / 360.0
    if not 8.0 < turns6 < 9.5:
        bad.append("axis 6 should turn about 9 times over 9 loops, model says %.1f" % turns6)
    jump = max(max(abs(b['q'][k] - a['q'][k]) for k in range(6)) for a, b in zip(rep.poses, rep.poses[1:]))
    if jump > 45:                 # 10 mm along a corner arc of radius 22.5 turns the head 25 deg
        bad.append("axes jump %.0f deg between neighbouring points (should move smoothly)" % jump)

    # without the endless axis 6 the same program must be reported
    rep6 = rm.analyse(items, S, robot=dataclasses.replace(R, a6_endless=False))
    if not any("Axis 6" in m and "limits" in m for m in rep6.messages):
        bad.append("axis 6 limit not reported: %s" % rep6.messages)
    # out of reach
    far = rm.analyse(_cuboid(xc=450), S)
    if not far.unreachable or not any("cannot reach" in m for m in far.messages):
        bad.append("a part 300 mm further out must be out of reach: %s" % far.messages)
    edge = rm.analyse(_cuboid(xc=370), S)
    if edge.unreachable or not any("edge of the reach" in m for m in edge.messages):
        bad.append("a part at the edge of the reach must give a message")
    # wrist singularity: the flange in line with the forearm (axis 5 at 0) is reported
    flat = [pm.Ptp(pm.Pose(525, 0, 890, 0, 90, 0, 2, 43)), pm.Lin(pm.Pose(560, 0, 880, 0, 90, 0))]
    world = dataclasses.replace(S, base=(0, 0, 0, 0, 0, 0), tool=(0, 0, 0, 0, 0, 0))
    sing = rm.analyse(flat, world)
    if not any("Axis 5" in m for m in sing.messages):
        bad.append("wrist singularity not reported: %s (min A5 %s)" % (sing.messages, sing.min_a5))
    # a long program stays within the budget of solved points
    long_items = _cuboid(turns=6, layers=60)
    n_moves = sum(1 for i in long_items if isinstance(i, (pm.Lin, pm.Circ)))
    quick = rm.analyse(long_items, S, step=25.0, max_poses=1500)
    if n_moves < 3000 or len(quick.poses) > 1700 or quick.unreachable:
        bad.append("long program: %d moves gave %d solved points (budget 1500), %d out of reach"
                   % (n_moves, len(quick.poses), quick.unreachable))
    # a program without A B C or without moves does not break the check
    for odd in ([], [pm.Comment("nothing")], [pm.Ptp(pm.Pose(100, 100, 10)), pm.Lin(pm.Pose(150, 100, 10))]):
        try:
            rm.analyse(odd, S)
        except Exception as e:
            bad.append("analyse failed on %s: %r" % (odd, e))
    return bad


def check_robot_view(new_main_app):
    """new_main_app() -> (root, app), as in regression.py."""
    import view3d
    bad = []
    root, app = new_main_app()
    try:
        if not app.generate():
            return ["main app: Generate failed"]
        if app.warnings or "checks OK" not in app.checks_chip.cget("text"):
            bad.append("default cuboid: checks should be OK with the robot check (%s)" % app.warnings)
        if "within reach" not in app._robot_ok_text():
            bad.append("the OK text should speak about the reach: %s" % app._robot_ok_text())
        rep = app.robot_report()
        if app.robot_report() is not rep:
            bad.append("the robot report should be kept while nothing changes")
        app.shape_vars["cuboid"]["xc"].set("450")
        app.generate()
        if not any("cannot reach" in w for w in app.warnings) or "to check" not in app.checks_chip.cget("text"):
            bad.append("a part out of reach must show in the checks chip (%s)" % app.warnings)
        app.shape_vars["cuboid"]["xc"].set("150")
        app.generate()

        told = []
        view = view3d.View3D(root, app.body_text, on_position=told.append)
        try:
            view.canvas.configure(width=600, height=400)
            view.redraw()
            if view.canvas.find_withtag("robot"):
                bad.append("the robot must not be drawn until it is switched on")
            view.robot_var.set(True)
            view.redraw()
            n = len(view.report.poses)
            if len(view.canvas.find_withtag("robot")) < 8 or n < 100:
                bad.append("robot not drawn (%d items, %d positions)" % (len(view.canvas.find_withtag("robot")), n))
            if "A6" not in view.info.cget("text") or "OK" not in view.info.cget("text"):
                bad.append("robot info line: %s" % view.info.cget("text"))
            view.pos_var.set(n - 1)
            view.redraw()
            last = view.report.poses[-1]
            want = pm.path_3d(pm.parse_krl(app.body_text()))[1][-1]['pts'][-1]
            if max(abs(a - b) for a, b in zip(last['xyz'], want)) > 1e-9:
                bad.append("the last robot position is not the end of the program")
            view.toggle_play()                       # at the end: starts again from the first position
            if not view._playing or view.pos_var.get() > n / 2:
                bad.append("Play should start from the beginning")
            view.toggle_play()
            if view._playing or view.play_btn.cget("text") != "Play":
                bad.append("Play pressed again should stop")
            # speed, framing, stepping with the keys, the program line told to the main window
            view.speed_var.set("0.25x")
            if view.speed() != 0.25 or "1x" not in view3d.SPEEDS or "0.5x" not in view3d.SPEEDS:
                bad.append("speed choice: %r" % view.speed())
            view.toggle_frame()
            if not view.frame_path or view.frame_btn.cget("text") != "Whole robot"                     or view.report.frame_path[1] >= view.report.frame_robot[1]:
                bad.append("Zoom to path should frame the path (smaller than the whole robot)")
            view.toggle_frame()
            view.pos_var.set(40)
            view.step(1)
            view.step(-1)
            if view.position() != 40 or not told or told[-1] != view.report.poses[40]['item']:
                bad.append("Left / Right keys: position %d, told %s" % (view.position(), told[-3:]))
            # only the robot is drawn again when just the position changes
            path_items = [i for i in view.canvas.find_all() if "robot" not in view.canvas.gettags(i)]
            view.step(5)
            if [i for i in view.canvas.find_all() if "robot" not in view.canvas.gettags(i)] != path_items:
                bad.append("a robot step should leave the path on the canvas as it is")
            # live drawing: nothing drawn at the start, more with every step, less after going back
            view.live_var.set(True)
            view.pos_var.set(0)
            view.redraw()
            n0 = len(view.canvas.find_withtag("live"))
            view.pos_var.set(300)
            view.redraw()
            n300 = len(view.canvas.find_withtag("live"))
            drawn = sum(len(view.canvas.coords(i)) // 2 - 1 for i in view.canvas.find_withtag("live"))
            view.pos_var.set(100)
            view.redraw()
            back = sum(len(view.canvas.coords(i)) // 2 - 1 for i in view.canvas.find_withtag("live"))
            if n0 or not n300 or drawn != 300 or back != 100:
                bad.append("live drawing: %d lines at the start, %d pieces at position 300, %d after going back "
                           "to 100" % (n0, drawn, back))
            view.live_var.set(False)
            view.redraw()
            if view.canvas.find_withtag("live"):
                bad.append("live drawing still shown after switching it off")
            old = view.report
            view.reload()
            if view.report is old:
                bad.append("Reload must work the robot out again")
            view.robot_var.set(False)
            view.redraw()
            if view.canvas.find_withtag("robot"):
                bad.append("robot still drawn after switching it off")
        finally:
            view.win.destroy()
    finally:
        root.destroy()

    # a long program: moves are drawn as few lines, and the light picture (dragging) is much smaller
    text = pm.program_to_krl(_cuboid(turns=6, layers=60), 3)
    root = tk.Tk()
    root.withdraw()
    try:
        view = view3d.View3D(root, lambda: text)
        view.redraw()
        full_items = len(view.canvas.find_all())
        if full_items > len(view.moves) / 3:
            bad.append("long program: %d canvas lines for %d moves" % (full_items, len(view.moves)))
        view.redraw(fast=True)                      # (the hidden test window is tiny: count lines, not points)
        if len(view.canvas.find_all()) > full_items / 2:
            bad.append("light picture: %d lines, the full one has %d" % (len(view.canvas.find_all()), full_items))
        view.arrows_var.set(True)
        view.redraw()
        n = len(view.canvas.find_withtag("head_arrow"))
        if not 0 < n <= view3d.MAX_ARROWS or "arrows drawn" not in view.info.cget("text"):
            bad.append("long program: %d arrows drawn (limit %d)" % (n, view3d.MAX_ARROWS))
        view.redraw(fast=True)
        if len(view.canvas.find_withtag("head_arrow")) > view3d.FAST_ARROWS:
            bad.append("light picture: %d arrows" % len(view.canvas.find_withtag("head_arrow")))
        view.win.destroy()
    finally:
        root.destroy()
    return bad


def check_head_and_picking(new_main_app):
    """Robot / head choice, the collision warning, and the Import start point / outline by clicking."""
    import checks_import
    import ui_theme
    bad = []
    S = krl_export.NOUVTETE
    was_bed = rm.BED_SIZE
    rm.BED_SIZE = (300.0, 455.0)
    try:
        # the head's simple shape: fine as calibrated, the UV lamp digs in with a strong tilt
        if rm.analyse(_cuboid(), S).hits:
            bad.append("default cuboid: no collision expected (%s)" % rm.analyse(_cuboid(), S).messages)
        steep = rm.analyse(_cuboid(b=-20.0), S)
        if not any("UV lamp" in m and "into the bed" in m and "Suggestion" in m for m in steep.messages) \
                or not any(p.get('hit') for p in steep.poses):
            bad.append("tilt -20: the UV lamp in the bed must be reported (%s)" % steep.messages)
        if rm.analyse(_cuboid(b=-20.0), S, head=rm.NO_HEAD).hits:
            bad.append("without a head shape nothing of the head can be reported")
        block = rm.Head("test", (("block", "#000000", (-20, 20), (-20, 20), (-5, 15), False),))
        if not rm.analyse(_cuboid()[:40], S, head=block).hits:
            bad.append("a head part 15 mm below the roller must be reported")
        # a pressed first layer (Start Z below 0) is what the roller is for: not a collision
        low = cuboid.generate(cuboid.CuboidParams(xc=150, yc=225, z0=-2, length=150, width=300, corner_radius=None,
                                                  step=2, layer_height=2, turns=2, layers=1, a=180, b=-3, c=180,
                                                  auto_orient=True))[0]
        if rm.analyse(low, S).hits:
            bad.append("a pressed roller (Z -2) must not count as a collision")
        if len(rm.box_corners(rm.NOUVTETE_HEAD.boxes[0])) != 8 or "KR 10 R900 sixx" not in rm.ROBOTS:
            bad.append("head box corners / robot list")
    finally:
        rm.BED_SIZE = was_bed

    msgs = checks_import._quiet()
    root, app = new_main_app()
    try:
        # Tools > Robot and head: used by the checks, kept for the next start
        app.generate()
        app.robot_name_var.set("KR 6 R700 sixx")
        app.choose_robot()
        if not any("Axis 6" in w for w in app.warnings):
            bad.append("another robot (no endless axis 6) must change the checks (%s)" % app.warnings)
        if rm.load_choice(ui_theme._path())[0].name != "KR 6 R700 sixx":
            bad.append("the robot choice must be saved")
        app.robot_name_var.set(rm.DEFAULT_ROBOT.name)
        app.head_name_var.set(rm.NO_HEAD.name)
        app.choose_robot()
        if app.warnings or app.robot_report().head is not rm.NO_HEAD:
            bad.append("back to the default robot, no head: %s" % app.warnings)
        app.head_name_var.set(rm.DEFAULT_HEAD.name)
        app.choose_robot()

        # Import: the start point by clicking
        if not app.import_design(checks_import.design("corners_px.svg")):
            return bad + ["corners_px.svg could not be imported"]
        first = app.state()["output"]
        start0 = pm.path_3d(pm.parse_krl(first))[0]
        d = app._design[2]
        if len(d.paths) < 2:
            bad.append("the test drawing should hold several outlines")
        target = (start0[0] - 30.0, start0[1] + 25.0)
        if not app.set_start_point(*target) or app.state()["output"] == first:
            bad.append("set_start_point should give another program")
        start1 = pm.path_3d(pm.parse_krl(app.state()["output"]))[0]
        moved = math.hypot(start1[0] - start0[0], start1[1] - start0[1])
        if moved < 5 or math.hypot(start1[0] - target[0], start1[1] - target[1]) > 45:
            bad.append("the loop should start near the clicked point (start %s, clicked %s)" % (start1[:2], target))
        if not app.shape_vars["import"]["seam"].get() or not app.more_var.get():
            bad.append("the start point should show in its field under More settings")
        st = app.state()
        if not app.set_start_point(None) or app.state()["output"] != first:
            bad.append("automatic start point should give the first program again")
        app.set_state(st)                                # a project keeps the start point
        if not app.generate() or app.state()["output"] != st["output"]:
            bad.append("a saved start point must give the same program again")
        old = {k: v for k, v in st["inputs"]["import"].items() if k != "seam"}
        app.set_state(dict(st, inputs=dict(st["inputs"], **{"import": old})))
        if app.shape_vars["import"]["seam"].get():
            bad.append("a project without a start point must not keep the one typed before")
        app.shape_vars["import"]["seam"].set("12")
        del msgs[:]
        if app.generate() or not msgs or "Start point" not in msgs[-1][1]:
            bad.append("half a start point must be refused with a message (%s)" % msgs[-1:])
        app.shape_vars["import"]["seam"].set("")

        # Import: the outline by clicking
        app.generate()
        win = app.open_outline_chooser()
        if win is None or not hasattr(win, "outline_at"):
            bad.append("the outline chooser did not open")
        else:
            if win.outline_at(-500, -500) is not None:
                bad.append("a click far from every outline must choose nothing")
            win.destroy()
        if not app.choose_outline(2) or app.shape_vars["import"]["outline"].get() != "2" \
                or app.state()["output"] == first:
            bad.append("choose_outline(2) should print the second outline")
        if not app.choose_outline(1) or app.state()["output"] != first:
            bad.append("choose_outline(1) should give the first program again")
    finally:
        rm.set_active(rm.DEFAULT_ROBOT.name, rm.DEFAULT_HEAD.name)
        try:
            rm.save_choice(ui_theme._path())             # the checks after this one start with the defaults
        except OSError:
            pass
        root.destroy()
    return bad
