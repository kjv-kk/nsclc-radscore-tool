# -*- coding: utf-8 -*-
"""
Rad-score local web tool v1 | Streamlit frontend (runs on Python 3.13)
=======================================================================
Batch workflow:
  1) Upload & Extract: upload one or more patients (ZIP / DICOM) -> extract
     features -> get a table (Rad-score, group, 6 features, clinical template).
  2) Analyze: upload the filled table (xlsx/csv) -> a violin + scatter chart of
     ONLY the uploaded patients, split into low/high risk.

Rules: the model is frozen; this tool only applies it (never refits).
       Clinical fields are archived only and are NOT used in scoring.
       Everything runs locally; no data is uploaded anywhere.
"""
import os
import sys

import numpy as np
import pandas as pd
import streamlit as st

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOL_DIR)

try:
    from batch import (FEATS6, CUT_M, CUT_T1, CUT_T2, PY39,
                       df_to_xlsx, results_to_table, parse_table, run_batch)
except Exception as e:  # pragma: no cover
    st.error(f"Cannot load batch/core modules (needs Python 3.13 + pydicom + SimpleITK): {e}")
    st.stop()

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False

DISPLAY_ICON = os.path.join(TOOL_DIR, "icon.png")

st.set_page_config(
    page_title="Rad-score Tool",
    page_icon=DISPLAY_ICON if os.path.exists(DISPLAY_ICON) else "🫁",
    layout="wide",
)

# ==================== Sidebar ====================
if not os.path.exists(PY39):
    st.warning(
        "PyRadiomics (python39) was not found on this machine. The UI works, but "
        "**feature extraction needs to run locally** (start.bat); Streamlit Cloud "
        "cannot run PyRadiomics 3.1.0 (it requires Python <= 3.9)."
    )

with st.sidebar:
    if os.path.exists(DISPLAY_ICON):
        st.image(DISPLAY_ICON, width=76)
    st.title("Rad-score Tool")
    page = st.radio("Navigation", ["Home", "Upload & Extract", "Analyze", "About"])
    st.divider()
    st.caption(
        "Frozen model (LUNG1); applies the fixed formula only.\n\n"
        "All results are apparent (training cutoffs, optimistic); "
        "research use only."
    )


def violin_chart(df):
    """Violin + jitter scatter of ONLY the uploaded patients, by risk group."""
    low = df.loc[df["group"] == "low", "radscore"].to_numpy()
    high = df.loc[df["group"] == "high", "radscore"].to_numpy()
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    groups = [("Low risk", low, "#4C9EEB"), ("High risk", high, "#E4572E")]
    for i, (_label, vals, color) in enumerate(groups):
        if len(vals) >= 3:
            parts = ax.violinplot([vals], positions=[i], showmeans=False,
                                  showmedians=False, showextrema=False, widths=0.8)
            for pc in parts["bodies"]:
                pc.set_facecolor(color)
                pc.set_alpha(0.25)
        rng = np.random.default_rng(2026 + i)
        ax.scatter(rng.normal(i, 0.05, len(vals)), vals, s=16, color=color,
                   alpha=0.75, edgecolors="none")
        if len(vals):
            ax.hlines(np.median(vals), i - 0.25, i + 0.25, color=color, lw=2)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([f"Low risk (n={len(low)})", f"High risk (n={len(high)})"])
    ax.set_ylabel("Rad-score", fontsize=10)
    ax.set_title("Rad-score by risk group (uploaded patients)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    return fig


# ==================== Home ====================
def show_home():
    st.title("Rad-score Radiomics Prognostic Score Tool")
    st.caption("Batch: upload CT DICOM + RTSTRUCT -> get a table -> analyze the uploaded patients")

    if os.path.exists(DISPLAY_ICON):
        st.image(DISPLAY_ICON, width=110)

    st.markdown(
        """
        A **frozen** radiomics calculator. Upload CT series + RTSTRUCT (GTVp) for
        one or more patients, get a feature table, fill in clinical fields, then
        re-upload the table to visualize the uploaded patients' risk groups.
        """
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Model features", "6")
    c2.metric("Median cutoff", f"{CUT_M:.3f}")
    c3.metric("Feature count", "1130")

    st.info(
        "**How to use**\n\n"
        "1. Go to **Upload & Extract**, upload one or more patients (a ZIP per patient, "
        "or a ZIP containing patient sub-folders), and extract features.\n"
        "2. Download the Excel table and fill in clinical fields (name, age, ...).\n"
        "3. Go to **Analyze**, upload the filled table, and view the low/high-risk chart."
    )


# ==================== Upload & Extract ====================
def show_upload():
    st.title("Step 1 · Upload & Extract")
    st.caption("Upload one or more patients (ZIP per patient, or one ZIP with patient sub-folders).")

    uploaded = st.file_uploader(
        "Upload DICOM (multiple ZIPs = multiple patients, or one ZIP with patient folders)",
        accept_multiple_files=True,
        help="Each ZIP may be one patient, or contain several patient sub-folders.",
    )

    if st.button("🔍 Extract features", type="primary", disabled=not uploaded):
        with st.spinner(f"Processing {len(uploaded)} upload(s) ... (~10-20 s per patient)"):
            try:
                results, errors = run_batch(uploaded)
            except Exception as e:
                results, errors = [], [("batch", f"{type(e).__name__}: {e}")]
        if errors:
            st.warning("Some patients failed:\n\n" + "\n".join(f"- {p}: {e}" for p, e in errors))
        if results:
            st.session_state["table"] = results_to_table(results)
            st.session_state["results"] = results
            st.success(f"Extracted {len(results)} patient(s). Download the table, fill in clinical fields, "
                       "then go to **Analyze**.")
        else:
            st.error("No patient successfully processed.")

    table = st.session_state.get("table")
    if table is not None and len(table):
        st.divider()
        st.subheader("Extracted feature table")
        st.dataframe(table, width="stretch")
        st.download_button(
            "⬇️ Download table (Excel)",
            df_to_xlsx(table),
            file_name="radscore_features.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "⬇️ Download table (CSV)",
            table.to_csv(index=False, encoding="utf-8-sig"),
            file_name="radscore_features.csv",
            mime="text/csv",
        )


# ==================== Analyze ====================
def show_analyze():
    st.title("Step 2 · Analyze")
    st.caption("Upload the filled table (xlsx/csv). The chart shows ONLY the uploaded patients.")

    f = st.file_uploader("Upload the filled table (xlsx or csv)", type=["xlsx", "xls", "csv"])
    if f is None:
        st.info("Upload the table from **Upload & Extract** after filling in clinical fields.")
        return

    try:
        df = parse_table(f)
    except Exception as e:
        st.error(f"Cannot read the table: {e}")
        return

    if not len(df):
        st.error("No valid patient row (needs a radscore column, or the 6 feature::... columns).")
        return

    n_low = int((df["group"] == "low").sum())
    n_high = int((df["group"] == "high").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Patients", len(df))
    c2.metric("Low risk", n_low)
    c3.metric("High risk", n_high)
    st.caption("apparent (training cutoffs, optimistic) / exploratory / association != causation")

    if HAS_MPL:
        fig = violin_chart(df)
        st.pyplot(fig, width="content")
        plt.close(fig)

    st.subheader("Results")
    show_cols = [c for c in ["patient_id", "name", "age", "sex", "histology",
                             "radscore", "group_median", "group_tertile"] if c in df.columns]
    st.dataframe(df[show_cols], width="stretch")

    d1, d2 = st.columns(2)
    d1.download_button(
        "⬇️ Download results (Excel)",
        df_to_xlsx(df),
        file_name="radscore_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    d2.download_button(
        "⬇️ Download results (CSV)",
        df.to_csv(index=False, encoding="utf-8-sig"),
        file_name="radscore_analysis.csv",
        mime="text/csv",
    )


# ==================== About ====================
def show_about():
    st.title("About")
    st.markdown(
        f"""
        ### Rad-score Radiomics Prognostic Score Tool

        - **Model**: 6 radiomics features (wavelet/texture), frozen from the LUNG1 training set.
        - **Formula**: Rad-score = sum(coef * (x - train_mean) / train_sd).
        - **Cutoffs**: median = {CUT_M:.4f}; tertiles = {CUT_T1:.4f} / {CUT_T2:.4f}.
        - **Input**: CT DICOM series + RTSTRUCT (GTVp contours from TPS).
        - **Workflow**: extract table -> fill clinical -> re-upload -> chart.

        **Disclaimer**: all results are apparent (training-set cutoffs, optimistic);
        P values are nominal; association != causation; for research only,
        not for clinical decision-making.
        """
    )


# ==================== Router ====================
if page == "Home":
    show_home()
elif page == "Upload & Extract":
    show_upload()
elif page == "Analyze":
    show_analyze()
else:
    show_about()
