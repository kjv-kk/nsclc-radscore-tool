# -*- coding: utf-8 -*-
"""
Locate the two Python interpreters the tool needs.

Order for each:
  1) config.py override
  2) environment variable
  3) (python39) sibling folder of the current interpreter
  4) PATH
  5) common install locations

If auto-detection fails, the user only needs to fill in config.py.
"""
import os
import sys
import shutil


def _cfg(name):
    try:
        import config
        v = getattr(config, name, "")
        return v if v and os.path.exists(v) else ""
    except Exception:
        return ""


def find_py39():
    v = _cfg("PY39")
    if v:
        return v
    v = os.environ.get("RADSCORE_PY39", "")
    if v and os.path.exists(v):
        return v
    # sibling folder of the running interpreter: <parent>/python39/python.exe
    if sys.executable:
        parent = os.path.dirname(os.path.dirname(sys.executable))
        cand = os.path.join(parent, "python39", "python.exe")
        if os.path.exists(cand):
            return cand
    for name in ("python39", "python3.9"):
        cand = shutil.which(name)
        if cand:
            return cand
    for cand in (
        r"C:\Python39\python.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python39\python.exe"),
        os.path.expandvars(r"%ProgramFiles%\Python39\python.exe"),
        "/usr/bin/python3.9",
    ):
        if cand and os.path.exists(cand):
            return cand
    return ""


def find_py313():
    v = _cfg("PY313")
    if v:
        return v
    v = os.environ.get("RADSCORE_PY313", "")
    if v and os.path.exists(v):
        return v
    # the interpreter running this script is normally the 3.13 one
    return sys.executable or ""
