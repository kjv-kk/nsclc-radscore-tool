# Rad-score Radiomics Prognostic Score Tool (v1)

> Paper companion tool: upload "CT DICOM + RTSTRUCT" -> extract 1130 radiomics
> features -> apply the **frozen** Rad-score formula -> output score, groups,
> feature tables and figures.

## What it is

**A pure calculator.** The model is frozen (`model.csv`; 6 coefficients +
cutoffs, all from the LUNG1 training set). The tool only applies it and
**never fits / re-trains / tunes**. Clinical fields are archived only and are
**not** used in the score.

## Input / Output

- **Input**: CT DICOM series + RTSTRUCT (GTVp contours exported from TPS).
  Recommended: pack both into one ZIP; multiple files also work.
- **Output**:
  - Rad-score (continuous) + median split (low/high) + tertile (T1/T2/T3);
  - the 6 model features (value, z-score, contribution);
  - all 1130 features (downloadable CSV);
  - clinical info (age / sex / histology / TNM; archived only);
  - a single-case report CSV.

## Environment (two Pythons — important)

The tool **must use two Python interpreters**, because PyRadiomics and
Streamlit have conflicting Python-version requirements:

| Purpose | Python | Installed packages |
| --- | --- | --- |
| UI + DICOM -> NIfTI | **3.13** (`python\python.exe`) | streamlit, pydicom, SimpleITK, matplotlib |
| Feature extraction + scoring | **python39** (`python39\python.exe`) | PyRadiomics 3.1.0, SimpleITK 2.5.7 |

> PyRadiomics 3.1.0 supports Python <= 3.9 only; Streamlit 1.63 requires >= 3.10.
> Hence the local tool runs as two processes: the UI (3.13) spawns a python39
> subprocess for extraction.

## Quick start (Windows)

1. Double-click **`Rad-score Tool.lnk`** in this folder (or `start.bat`).
2. A browser tab opens automatically at `http://127.0.0.1:8501`.
3. Go to **Upload & Extract**, upload CT + RTSTRUCT (or a ZIP), click **Extract features**.
4. Go to **Analyze** to view the Rad-score, risk group and chart, and download the report.

> The `.lnk` stores absolute paths. It keeps working as long as this folder stays
> where it is. If you move the folder, double-click `start.bat` instead (it
> resolves paths relative to itself), or re-create the shortcut: right-click
> `launch.py` -> **Open with** -> **Choose another app** -> Python, then set the
> icon to `icon.ico`.

## Local setup (first time on a new machine)

The tool needs **two** Python interpreters (see the table above). If `start.bat`
reports "Python not found", edit these two lines at the top of `start.bat`:

```bat
set "PY313=<path to your Python 3.13>"
set "RADSCORE_PY39=<path to your Python 3.9 (PyRadiomics)>"
```

Then double-click `start.bat` (or the shortcut) again.

To create the desktop shortcut yourself: right-click `start.bat` -> **Show more
options** -> **Send to** -> **Desktop (create shortcut)**; then right-click the
shortcut -> **Properties** -> **Change Icon** -> choose `icon.ico`.

## For others (downloading from GitHub)

The tool needs two Python interpreters (see the table above). It **auto-detects**
them: `config.py` override -> environment variable -> PATH -> common install
locations -> a `python39` folder next to your Python 3.13.

1. Install **Python 3.13** and run `pip install -r requirements.txt`.
2. Install **Python 3.9** and run `pip install -r requirements-py39.txt`.
3. Double-click **`start.bat`** (or run `python launch.py`).
4. If it reports "PyRadiomics (python39) not found", open `config.py` and fill in
   `PY313` / `PY39` with your Python paths — this is the only edit needed.

> `Rad-score Tool.lnk` stores absolute paths and only works on the machine where
> it was created. **Others should use `start.bat`**, not the `.lnk`.

## Pages

- **Home** — what the tool does and how to use it.
- **Upload & Extract** — upload DICOM, extract the 6 model features, download an Excel/CSV table.
- **Analyze** — Rad-score, risk group, compact risk ruler, feature contributions, clinical fields, report download.
- **About** — model and disclaimer.

## Validation (hard check)

Tested on LUNG1-001 / LUNG1-002: the Rad-score matches the frozen Phase 4 values
**exactly** (1e-6):

| Case | This tool | Frozen Phase 4 value |
| --- | --- | --- |
| LUNG1-001 | -0.415361 | -0.41536101... |
| LUNG1-002 | 0.509282 | 0.50928206... |

Conversion QC: mask volume vs RTSTRUCT-parsed volume relative deviation < 0.1%.

## File structure

```
tool/
├── app.py               # Streamlit UI (Python 3.13), 4 pages
├── batch.py             # batch helpers (extract / table / parse), no Streamlit
├── core_convert.py      # DICOM (CT+RTSTRUCT) -> NIfTI image+mask (3.13)
├── core_extract.py      # NIfTI -> 1130 features + Rad-score (python39)
├── launch.py            # launcher (starts the server + opens the browser)
├── start.bat            # fallback launcher (calls launch.py; saved as GBK)
├── config.py            # optional Python path overrides (leave empty = auto-detect)
├── paths.py             # auto-detect the two Python interpreters
├── icon.png             # app icon (png)
├── icon.ico             # app icon (ico, for the shortcut)
├── requirements.txt     # 3.13-side dependencies
├── requirements-py39.txt# python39-side dependencies
├── model.csv            # frozen model (6 coefficients + cutoffs)
├── params.yaml          # frozen PyRadiomics params (byte-identical to training)
├── train_radscore.csv   # training-set Rad-score distribution
├── VALIDATION.md        # acceptance / reconciliation record
└── .gitignore
```

> `model.csv` / `params.yaml` / `train_radscore.csv` are found either in the tool
> root or in a `frozen/` sub-folder (both layouts work).

## Disclaimer

- All results are **apparent (training-set cutoffs, optimistic)**;
- P is nominal, uncorrected; **association != causation**;
- For research only, **not for clinical decision-making**.

## Known limitations

1. **Domain shift**: the frozen formula contains gray-level features with tiny SDs;
   in external cohorts (different scanner/contrast) the Rad-score may drift from
   the training distribution (see the project's Phase 8c analysis).
2. **RTSTRUCT only**: requires GTVp contours exported from TPS; CT-only AI
   auto-segmentation is planned for v2.
3. **Local-only by design**: this tool is meant to run on the local machine.
   Streamlit Community Cloud runs Python >= 3.10, which cannot install
   PyRadiomics 3.1.0, so cloud deployment is not supported.
