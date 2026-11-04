"""Project files: all inputs of a print saved as JSON, so it can be reproduced later (no tkinter).

File layout (one JSON object):
    format          FORMAT (int), for future changes of the layout
    app             "main" (KRL_Generator), "cuboid" (App6) or "cylinder" (App7)
    saved           local time of saving (ISO, informational)
    export_profile  copy of the export profile active when saving (name + values, informational)
    ...             the app's own keys (inputs, options, base loop, output text, ...)

    save_project(path, app, data)          -> writes the file
    load_project(path, app)                -> data dict (raises ProjectError with a readable message)
    profile_mismatch(data)                 -> warning text if the active export profile differs, else None
"""
import datetime
import json
import os

import krl_export

FORMAT = 1
FILETYPES = [("Project files", "*.json"), ("All files", "*.*")]
APP_NAMES = {"cuboid": "Cuboid (PythonApplication6)", "cylinder": "Cylinder (PythonApplication7)",
             "main": "KRL Generator (main app)"}


class ProjectError(Exception):
    pass


def save_project(path, app, data):
    settings, _ = krl_export.active_settings()
    content = {"format": FORMAT, "app": app,
               "saved": datetime.datetime.now().replace(microsecond=0).isoformat(),
               "export_profile": krl_export.settings_to_dict(settings)}
    content.update(data)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_project(path, app):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as ex:
        raise ProjectError("Could not read the project file:\n%s" % ex)
    if not isinstance(data, dict) or "app" not in data or "format" not in data:
        raise ProjectError("This is not a PythonToKRL project file.")
    if data["app"] != app:
        raise ProjectError("This project was made with the %s app.\nOpen it there instead."
                           % APP_NAMES.get(data["app"], repr(data["app"])))
    if not isinstance(data["format"], int) or data["format"] > FORMAT:
        raise ProjectError("This project file was written by a newer version of the program "
                           "(format %s, this version reads up to %d)." % (data["format"], FORMAT))
    return data


def load_project_any(path):
    """Like load_project, but accepts every known app ("main", "cuboid", "cylinder")."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as ex:
        raise ProjectError("Could not read the project file:\n%s" % ex)
    if not isinstance(data, dict) or "format" not in data or data.get("app") not in APP_NAMES:
        raise ProjectError("This is not a PythonToKRL project file.")
    return load_project(path, data["app"])


def profile_mismatch(data):
    """Warning text if the project's export profile differs from the active one (else None)."""
    saved = data.get("export_profile")
    if not saved:
        return None
    current, _ = krl_export.active_settings()
    current_d = krl_export.settings_to_dict(current)
    if saved == current_d:
        return None
    diffs = [k for k in sorted(set(saved) | set(current_d)) if saved.get(k) != current_d.get(k)]
    return ("This project was saved with export profile '%s'; the active profile is '%s'.\n"
            "Different: %s.\n\nThe ACTIVE profile is used when you export. Check the TOOL/BASE "
            "values in Export Settings before printing."
            % (saved.get("profile", "?"), current.profile, ", ".join(diffs)))
