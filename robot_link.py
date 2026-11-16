"""Send the exported program to the robot over the network instead of a USB stick (no tkinter).

How it works: the program is written into a TRANSFER FOLDER that both this PC and the robot
controller can see. Two ways to get such a folder (both use plain Windows file sharing):
    1. a folder shared by the controller, reached from this PC as  \\\\<robot IP>\\<share>
    2. a folder shared by this PC, connected on the controller as a network drive
On the smartPAD the file is then copied from that folder into R1\\Program with the Navigator
(the same step as with the USB stick, without walking the stick over).

Nothing is started on the robot from here: selecting and running the program stays on the
smartPAD, with the operator at the cell.

    load_settings(path) / save_settings(path, settings)   kept in app_settings.json (per PC)
    check_folder(folder)            -> (ok, message)      reachable and writable?
    send_program(folder, name, code, overwrite)           -> path of the written file
"""
import json
import os
import socket

DEFAULTS = {"folder": "", "last_name": ""}
SMB_PORT = 445
TIMEOUT = 2.5            # s: how long to wait for the robot's PC before giving up


class RobotLinkError(Exception):
    """Sending failed (the message is shown to the user)."""


class ProgramExists(RobotLinkError):
    """A program with this name is already in the transfer folder."""


# ------------------------------------------------------------------ settings

def load_settings(path):
    out = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f).get("robot", {})
        for k in DEFAULTS:
            if isinstance(data.get(k), str):
                out[k] = data[k]
    except (OSError, ValueError, AttributeError):
        pass
    return out


def save_settings(path, settings):
    """Keeps the other entries of the file (e.g. the theme)."""
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        pass
    data["robot"] = {k: str(settings.get(k, DEFAULTS[k])) for k in DEFAULTS}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ checks

def unc_host(folder):
    """'\\\\\\\\172.31.1.147\\\\share\\\\x' -> '172.31.1.147'; None for a local or mapped-drive folder."""
    f = folder.replace("/", "\\")
    if f.startswith("\\\\"):
        parts = f[2:].split("\\")
        if parts and parts[0]:
            return parts[0]
    return None


def reachable(host, port=SMB_PORT, timeout=TIMEOUT):
    """Can the PC at `host` be reached for file sharing? (ok, message)"""
    try:
        s = socket.create_connection((host, port), timeout)
        s.close()
        return True, "%s answers." % host
    except socket.timeout:
        return False, ("%s does not answer (waited %.0f s). Check the network cable, that this PC and the robot "
                       "are in the same address range, and the robot's address." % (host, timeout))
    except OSError as ex:
        return False, "%s cannot be reached for file sharing (%s)." % (host, ex.strerror or ex)


def check_folder(folder):
    """Is the transfer folder there and can a file be written into it? (ok, message)"""
    folder = (folder or "").strip()
    if not folder:
        return False, "No transfer folder is set."
    host = unc_host(folder)
    if host:
        ok, msg = reachable(host)
        if not ok:
            return False, msg
    if not os.path.isdir(folder):
        return False, ("The folder was not found:\n%s\n\nCheck the share name, and that this PC is allowed to "
                       "open it (open it once in the Windows Explorer and enter the user name and password "
                       "there if Windows asks)." % folder)
    probe = os.path.join(folder, "krl_generator_write_test.tmp")
    try:
        with open(probe, "w") as f:
            f.write("test")
        os.remove(probe)
    except OSError as ex:
        return False, "The folder is there, but files cannot be written into it (%s)." % (ex.strerror or ex)
    return True, "Connected: the folder is there and can be written to."


# ------------------------------------------------------------------ send

def send_program(folder, name, code, overwrite=False):
    """Write <name>.src into the transfer folder and read it back to make sure it arrived
    complete. Returns the file path. Raises ProgramExists (unless overwrite) or RobotLinkError."""
    ok, msg = check_folder(folder)
    if not ok:
        raise RobotLinkError(msg)
    path = os.path.join(folder.strip(), name + ".src")
    if os.path.exists(path) and not overwrite:
        raise ProgramExists("%s.src is already in the transfer folder." % name)
    tmp = path + ".part"
    try:
        with open(tmp, "w") as f:
            f.write(code)
        os.replace(tmp, path)
        with open(path) as f:
            arrived = f.read()
    except (OSError, UnicodeError) as ex:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise RobotLinkError("The program could not be written to the transfer folder:\n%s" % ex)
    if arrived != code:
        raise RobotLinkError("The file in the transfer folder differs from what was sent. Send it again.")
    return path
