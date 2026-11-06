# -*- coding: utf-8 -*-
"""
Rad-score tool | feature extraction and scoring core (python39 + PyRadiomics 3.1.0)
====================================================================================
Inputs are pre-converted NIfTI files:
  --img  CT volume .nii/.nii.gz
  --msk  binary mask .nii/.nii.gz (0/1, same geometry as image)
  --pid  patient ID (optional)
  --out  output JSON

Output JSON:
  patient_id, status, note, radscore, group_median, group_tertile,
  features6 {name: value}, all_features {name: value}, qc {mask_vol_cc, n_features}

Rules: fully offline; stop if a package is missing (never auto-install);
       model/params are frozen copies under frozen/.
"""
import os
import sys
import json
import argparse
import logging
import tempfile
import shutil

try:
    import numpy as np
    import SimpleITK as sitk
    from radiomics import featureextractor
    import radiomics
    import pandas as pd
except ImportError as e:
    sys.exit(f"Missing package: {e.name}. Please launch with python39 (PyRadiomics env).")

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = os.path.join(HERE, "frozen")


def _frozen_path(name):
    """Find a frozen file either in frozen/ or in the tool root (GitHub may be flat)."""
    for p in (os.path.join(FROZEN, name), os.path.join(HERE, name)):
        if os.path.exists(p):
            return p
    return os.path.join(FROZEN, name)


MODEL_CSV = _frozen_path("model.csv")
PARAMS = _frozen_path("params.yaml")

if not os.path.exists(MODEL_CSV):
    sys.exit(f"Missing frozen model: {MODEL_CSV}")
if not os.path.exists(PARAMS):
    sys.exit(f"Missing frozen params: {PARAMS}")

# ---- Frozen model (6 coefficients + cutoffs) ----
model = pd.read_csv(MODEL_CSV)
FEATS6 = [(str(r["feature"]), float(r["coef"]), float(r["mean_train"]), float(r["sd_train"]))
          for _, r in model.iterrows()]
CUT_M = float(model["cutoff_median_train"][0])
CUT_T1 = float(model["cutoff_tertile1_train"][0])
CUT_T2 = float(model["cutoff_tertile2_train"][0])

extractor = featureextractor.RadiomicsFeatureExtractor(PARAMS)
radiomics.logger.setLevel(logging.ERROR)


def read_image(path):
    """SimpleITK cannot read NIfTI from non-ASCII paths -> go through an ASCII temp dir."""
    try:
        return sitk.ReadImage(path)
    except Exception:
        tmpdir = tempfile.mkdtemp(prefix="sitk_r_")
        tmp = os.path.join(tmpdir, os.path.basename(path))
        try:
            shutil.copy(path, tmp)
            return sitk.ReadImage(tmp)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True, help="CT NIfTI")
    ap.add_argument("--msk", required=True, help="mask NIfTI")
    ap.add_argument("--pid", default="patient")
    ap.add_argument("--out", required=True, help="output JSON")
    args = ap.parse_args()

    result = {"patient_id": args.pid, "status": "fail", "note": "",
              "radscore": None, "group_median": None, "group_tertile": None,
              "features6": {}, "all_features": {}, "qc": {}}

    try:
        img = read_image(args.img)
        msk = read_image(args.msk)
        res = extractor.execute(img, msk)
        feats = {k: float(v) for k, v in res.items() if not k.startswith("diagnostics_")}

        # Frozen formula (no re-fitting)
        rad = 0.0
        missing = []
        for name, coef, mn, sd in FEATS6:
            if name not in feats or np.isnan(feats[name]):
                missing.append(name)
                continue
            rad += coef * (feats[name] - mn) / sd
        if missing:
            raise RuntimeError(f"Missing model features: {missing}")

        group_median = "low" if rad <= CUT_M else "high"
        group_tertile = "T1" if rad <= CUT_T1 else ("T2" if rad <= CUT_T2 else "T3")

        # Mask volume (PyRadiomics 3.1.0: original_shape_VoxelVolume, mm^3)
        vol_cc = feats.get("original_shape_VoxelVolume", float("nan"))
        if np.isfinite(vol_cc):
            vol_cc = vol_cc / 1000.0

        result.update({
            "status": "pass",
            "radscore": round(float(rad), 6),
            "group_median": group_median,
            "group_tertile": group_tertile,
            "features6": {name: feats[name] for name, _, _, _ in FEATS6},
            "all_features": feats,
            "qc": {
                "n_features": len(feats),
                "mask_vol_cc": None if not np.isfinite(vol_cc) else round(float(vol_cc), 4),
            },
        })
    except Exception as e:
        result["note"] = f"{type(e).__name__}: {e}"

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[core_extract] {args.pid} -> {result['status']} "
          f"radscore={result['radscore']} -> {args.out}")
    sys.exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
