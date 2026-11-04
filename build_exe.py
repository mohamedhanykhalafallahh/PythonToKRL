"""Build the stand-alone program dist/KRL_Generator.exe (one file, no console window).

    python build_exe.py

- Uses a private virtual environment (.venv in this folder, ignored by git) with PyInstaller
  5.13.2 (the last version that supports Python 3.7), so the normal Python stays untouched.
  The first run creates it (needs internet once).
- Copies export_profiles.json next to the .exe (the program reads and saves its profiles
  there; a one-file exe must not keep them in its temporary unpack folder).
- Runs the exe's self-test (KRL_Generator.exe --selftest --quiet) and prints the report.

Copy the two files dist/KRL_Generator.exe and dist/export_profiles.json to the lab PC
(Windows 10/11, 64-bit, no Python needed). There: KRL_Generator.exe --selftest shows a check.
"""
import os
import shutil
import subprocess
import sys
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
VPY = os.path.join(VENV, "Scripts", "python.exe")
PYINSTALLER = "pyinstaller==5.13.2"
DIST = os.path.join(HERE, "dist")
EXE = os.path.join(DIST, "KRL_Generator.exe")


def run(cmd, **kw):
    print(">", " ".join('"%s"' % c if " " in c else c for c in cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=HERE, **kw)


def ensure_pyinstaller():
    if not os.path.exists(VPY):
        print("Creating the build environment (.venv) ...", flush=True)
        venv.create(VENV, with_pip=True)
    has = subprocess.run([VPY, "-c", "import PyInstaller"], capture_output=True).returncode == 0
    if not has:
        run([VPY, "-m", "pip", "install", "--disable-pip-version-check", PYINSTALLER])


def build():
    run([VPY, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
         "--name", "KRL_Generator", "--distpath", DIST,
         "--workpath", os.path.join(HERE, "build"), "--specpath", os.path.join(HERE, "build"),
         # the older editors are started as "KRL_Generator.exe --tool manual / freeform"
         "--hidden-import", "PythonApplication6", "--hidden-import", "PythonApplication5",
         os.path.join(HERE, "KRL_Generator.py")])
    profiles = os.path.join(HERE, "export_profiles.json")
    if os.path.exists(profiles):
        shutil.copy2(profiles, os.path.join(DIST, "export_profiles.json"))


def selftest():
    print("\nSelf-test of the built exe:", flush=True)
    code = subprocess.run([EXE, "--selftest", "--quiet"], cwd=DIST).returncode
    with open(os.path.join(DIST, "selftest_report.txt")) as f:
        print(f.read())
    return code


if __name__ == "__main__":
    if sys.version_info[:2] != (3, 7):
        print("Note: PyInstaller 5.13.2 is pinned for Python 3.7; this is Python %d.%d." % sys.version_info[:2])
    ensure_pyinstaller()
    build()
    code = selftest()
    size = os.path.getsize(EXE) / 1e6
    print("Built %s (%.1f MB) - self-test %s" % (EXE, size, "OK" if code == 0 else "FAILED"))
    sys.exit(code)
