# -*- coding: utf-8 -*-
"""
Rad-score tool | batch helpers (no Streamlit dependency; importable/testable)
=============================================================================
extract_one     : convert + extract one patient directory
run_batch       : organize uploaded files into patients and run them
results_to_table: build the feature table (with clinical template columns)
parse_table     : read a filled xlsx/csv and add radscore + group

How patients are detected inside a ZIP:
  - 0 RTSTRUCT -> error
  - 1 RTSTRUCT -> the whole ZIP is one patient
  - >1 RTSTRUCT -> split by the common directory prefix of the RTSTRUCTs, so
    "cohort/LUNG1-001/..." + "cohort/LUNG1-002/..." become two patients.
"""
import os
import re
import glob
import json
import tempfile
import shutil
import subprocess
import zipfile
from io import BytesIO

import numpy as np
import pandas as pd
import pydicom

from core_convert import convert, find_rtstruct
from paths import find_py39

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = os.path.join(TOOL_DIR, "frozen")


def _frozen_path(name):
    """Find a frozen file either in frozen/ or in the tool root (GitHub may be flat)."""
    for p in (os.path.join(FROZEN, name), os.path.join(TOOL_DIR, name)):
        if os.path.exists(p):
            return p
    return os.path.join(FROZEN, name)
PY39 = find_py39() or r"D:\除了文档以外的\农哲的软件\python39\python.exe"
WORKER = os.path.join(TOOL_DIR, "core_extract.py")

model = pd.read_csv(_frozen_path("model.csv"))
FEATS6 = [(str(r["feature"]), float(r["coef"]), float(r["mean_train"]), float(r["sd_train"]))
          for _, r in model.iterrows()]
CUT_M = float(model["cutoff_median_train"][0])
CUT_T1 = float(model["cutoff_tertile1_train"][0])
CUT_T2 = float(model["cutoff_tertile2_train"][0])


def _safe(name):
    return re.sub(r"[^0-9A-Za-z._-]+", "_", str(name)).strip("_") or "patient"


def _find_all_rtstruct(dir_):
    out = []
    for f in glob.glob(os.path.join(dir_, "**", "*"), recursive=True):
        if not os.path.isfile(f):
            continue
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=True)
        except Exception:
            continue
        if str(getattr(ds, "Modality", "")) == "RTSTRUCT":
            out.append(f)
    return out


def _common_prefix(parts_list):
    if not parts_list:
        return []
    pref = list(parts_list[0])
    for p in parts_list[1:]:
        new = []
        for a, b in zip(pref, p):
            if a != b:
                break
            new.append(a)
        pref = new
    return pref


def df_to_xlsx(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="results")
    buf.seek(0)
    return buf


def extract_one(pdir, pid, workdir):
    """Convert + extract one patient directory. Returns a result dict."""
    if not os.path.exists(PY39):
        raise RuntimeError(
            "PyRadiomics environment (python39) not found. Feature extraction must run "
            "locally (start.bat); Streamlit Cloud cannot run PyRadiomics 3.1.0 "
            "(it needs Python <= 3.9)."
        )
    rt = find_rtstruct(pdir)
    if rt is None:
        raise RuntimeError("No RTSTRUCT found (Modality=RTSTRUCT)")
    img = os.path.join(workdir, f"{_safe(pid)}_img.nii.gz")
    msk = os.path.join(workdir, f"{_safe(pid)}_msk.nii.gz")
    qc = convert(pdir, rt, img, msk)
    out_json = os.path.join(workdir, f"{_safe(pid)}_out.json")
    r = subprocess.run(
        [PY39, WORKER, "--img", img, "--msk", msk, "--pid", pid, "--out", out_json],
        capture_output=True, text=True, timeout=600,
    )
    if not os.path.exists(out_json):
        raise RuntimeError(f"extraction failed (exit {r.returncode}): {r.stderr[-400:]}")
    with open(out_json, encoding="utf-8") as f:
        res = json.load(f)
    if res.get("status") != "pass":
        raise RuntimeError(res.get("note", "extraction failed"))
    res["conv_qc"] = qc
    return res


def _patients_from_zip(sub, stem):
    """Split one extracted ZIP directory into (pid, dir) pairs."""
    rts = _find_all_rtstruct(sub)
    if not rts:
        return [], [f"{stem}: No RTSTRUCT found in the ZIP"]
    if len(rts) == 1:
        return [(stem, sub)], []
    rels = [os.path.relpath(os.path.dirname(r), sub) for r in rts]
    parts_list = [p.split(os.sep) for p in rels]
    pref = _common_prefix(parts_list)
    patients, seen = [], set()
    for parts in parts_list:
        cut = min(len(pref) + 1, len(parts))
        d = os.path.join(sub, *parts[:cut]) if cut else sub
        if d not in seen:
            seen.add(d)
            patients.append((os.path.basename(d) or stem, d))
    return patients, []


def run_batch(uploaded_files):
    """Return (results, errors). Each ZIP may hold one patient or several
    patient sub-folders; non-ZIP files are treated as one patient."""
    root = tempfile.mkdtemp(prefix="radbatch_")
    results, errors = [], []
    try:
        patients = []
        zips = [uf for uf in uploaded_files if uf.name.lower().endswith(".zip")]
        others = [uf for uf in uploaded_files if not uf.name.lower().endswith(".zip")]

        for i, uf in enumerate(zips):
            stem = _safe(os.path.splitext(os.path.basename(uf.name))[0])
            sub = os.path.join(root, f"z{i}_{stem}")
            os.makedirs(sub, exist_ok=True)
            zp = os.path.join(root, f"_{i}.zip")
            with open(zp, "wb") as f:
                f.write(uf.getvalue())
            with zipfile.ZipFile(zp) as z:
                z.extractall(sub)
            ps, errs = _patients_from_zip(sub, stem)
            patients.extend(ps)
            errors.extend(errs)

        if others:
            single = os.path.join(root, "_single")
            os.makedirs(single, exist_ok=True)
            for uf in others:
                with open(os.path.join(single, os.path.basename(uf.name)), "wb") as f:
                    f.write(uf.getvalue())
            patients.append(("patient", single))

        for pid, pdir in patients:
            try:
                results.append(extract_one(pdir, pid, root))
            except Exception as e:
                errors.append((pid, f"{type(e).__name__}: {e}"))
        return results, errors
    finally:
        shutil.rmtree(root, ignore_errors=True)


def results_to_table(results):
    rows = []
    for res in results:
        row = {
            "patient_id": res["patient_id"],
            "radscore": res["radscore"],
            "group_median": res["group_median"],
            "group_tertile": res["group_tertile"],
        }
        for name, _, _, _ in FEATS6:
            row[f"feature::{name}"] = res["features6"].get(name)
        row.update({"name": "", "age": "", "sex": "", "histology": "",
                    "T_stage": "", "N_stage": "", "M_stage": ""})
        rows.append(row)
    return pd.DataFrame(rows)


def radscore_from_row(row):
    total = 0.0
    for name, coef, mn, sd in FEATS6:
        col = f"feature::{name}"
        if col not in row or pd.isna(row[col]):
            return None
        try:
            x = float(row[col])
        except (TypeError, ValueError):
            return None
        total += coef * (x - mn) / sd
    return total


def parse_table(f):
    name = getattr(f, "name", "table")
    if name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(f)
    else:
        df = pd.read_csv(f)
    if "radscore" in df.columns and pd.api.types.is_numeric_dtype(df["radscore"]):
        df["radscore"] = pd.to_numeric(df["radscore"], errors="coerce")
    else:
        df["radscore"] = df.apply(radscore_from_row, axis=1)
    df = df[df["radscore"].notna()].copy()
    df["group"] = np.where(df["radscore"] > CUT_M, "high", "low")
    return df
