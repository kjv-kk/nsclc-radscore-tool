# Rad-score Tool v1 - Validation / Reconciliation Record (2026-11-06)

## 1. Environment

| Purpose | Python | Key packages |
| --- | --- | --- |
| UI + DICOM->NIfTI | `python\python.exe` (3.13) | streamlit 1.63, pydicom 3.0.2, SimpleITK 2.5.6, matplotlib |
| Feature extraction + scoring | `python39\python.exe` (3.9.13) | PyRadiomics 3.1.0, SimpleITK 2.5.7, numpy 1.26.4 |

> PyRadiomics 3.1.0 supports <= 3.9; Streamlit 1.63 requires >= 3.10 -> local two-process design.

## 2. Test data

`影像学\测试\LUNG1-001`, `LUNG1-002` (CT DICOM series + RTSTRUCT + SEG).
GTV contour identified as `GTV-1`.

## 3. Hard reconciliation (Rad-score must equal the frozen value, tol 1e-6)

| Case | This tool Rad-score | Frozen Phase 4 value | Abs. diff | Result |
| --- | --- | --- | --- | --- |
| LUNG1-001 | **-0.415361** | -0.41536100913722 | ~1e-8 | PASS |
| LUNG1-002 | **0.509282** | 0.509282057639918 | ~4e-8 | PASS |

## 4. Conversion QC (mask volume vs RTSTRUCT-parsed volume)

| Case | Slices | Mask volume (cc) | RTSTRUCT-parsed volume (cc) | Relative deviation |
| --- | --- | --- | --- | --- |
| LUNG1-001 | 134 | 156.2061 | 156.3462 | -0.09% |
| LUNG1-002 | 111 | 359.3601 | 359.4327 | -0.02% |

> The PyRadiomics-reported mask volume (155.907 / 359.292 cc) is computed after
> resampling to 1x1x1 mm (consistent with the training extraction params); it is
> slightly smaller than the original-resolution volume, which is expected.

## 5. Feature count

1130 features extracted (same params as `03_p3_features`); all 6 model features found.

## 6. Conclusion

The tool pipeline (DICOM -> NIfTI -> 1130 features -> frozen formula -> Rad-score)
reproduces the training-set values and is ready for Phase 7 local-cohort scoring.
