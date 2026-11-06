# -*- coding: utf-8 -*-
"""
Rad-score tool | DICOM -> NIfTI conversion (Python 3.13: pydicom + SimpleITK)
==============================================================================
Converts "CT series + RTSTRUCT" into the "image NIfTI + mask NIfTI" that
PyRadiomics needs. The logic is reused from 01_p1_convert.py (validated on 422
LUNG1 cases); only the entry point is now a function.

Library usage:
    from core_convert import convert
    qc = convert(ct_dir, rt_path, out_img, out_msk)
"""
import os
import glob

import numpy as np
import pydicom
import SimpleITK as sitk

EXCLUDE_KEYS = ("lnn", "node", "ln_")


def is_gtv_primary(name):
    n = str(name).strip().lower()
    if any(k in n for k in EXCLUDE_KEYS):
        return False
    return "gtv" in n


def poly_area_rc(pts_rc):
    r, c = pts_rc[:, 0], pts_rc[:, 1]
    return abs(np.dot(r, np.roll(c, -1)) - np.dot(c, np.roll(r, -1))) / 2.0


def rasterize_polygon(mask_slice, pts_rc):
    n = len(pts_rc)
    if n < 3:
        return
    r, c = pts_rc[:, 0], pts_rc[:, 1]
    rmin, rmax = int(np.floor(r.min())), int(np.ceil(r.max()))
    rmin, rmax = max(rmin, 0), min(rmax, mask_slice.shape[0] - 1)
    for ri in range(rmin, rmax + 1):
        y = ri + 0.5
        xs = []
        for i in range(n):
            j = (i + 1) % n
            if (r[i] <= y < r[j]) or (r[j] <= y < r[i]):
                xs.append(c[i] + (y - r[i]) * (c[j] - c[i]) / (r[j] - r[i]))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            c0, c1 = int(np.ceil(xs[k] - 0.5)), int(np.floor(xs[k + 1] - 0.5))
            c0, c1 = max(c0, 0), min(c1, mask_slice.shape[1] - 1)
            if c1 >= c0:
                mask_slice[ri, c0:c1 + 1] = 1


def load_ct(ct_dir):
    """Load the largest CT series in a directory. Returns (img, sop2idx, z_arr)."""
    files = [f for f in glob.glob(os.path.join(ct_dir, "**", "*"), recursive=True)
             if os.path.isfile(f)]
    series = {}
    for f in files:
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=True)
        except Exception:
            continue
        if str(getattr(ds, "Modality", "")) != "CT":
            continue
        uid = str(getattr(ds, "SeriesInstanceUID", ""))
        series.setdefault(uid, []).append(f)
    if not series:
        raise RuntimeError("No CT series found in directory")
    _uid, fs = max(series.items(), key=lambda kv: len(kv[1]))

    slices = []
    for f in fs:
        ds = pydicom.dcmread(f, stop_before_pixels=True)
        try:
            ipp = np.array([float(x) for x in ds.ImagePositionPatient])
            iop = np.array([float(x) for x in ds.ImageOrientationPatient])
            ps = [float(x) for x in ds.PixelSpacing]
            sop = str(ds.SOPInstanceUID)
        except Exception:
            continue
        slices.append(dict(file=f, ipp=ipp, iop=iop, ps=ps, sop=sop,
                           rows=int(ds.Rows), cols=int(ds.Columns)))
    if len(slices) < 2:
        raise RuntimeError("Fewer than 2 CT slices; cannot build a volume")

    X = slices[0]["iop"][:3]
    Y = slices[0]["iop"][3:]
    N = np.cross(X, Y)
    N /= np.linalg.norm(N)
    for s in slices:
        s["z"] = float(np.dot(s["ipp"], N))
    slices.sort(key=lambda s: s["z"])
    zs = np.array([s["z"] for s in slices])
    dz = float(np.median(np.diff(zs)))

    imgs = []
    for s in slices:
        im = sitk.ReadImage(s["file"])
        if im.GetDimension() == 3:
            im = im[:, :, 0]
        im.SetOrigin((0.0, 0.0, 0.0))
        imgs.append(im)
    img = sitk.JoinSeries(imgs)
    ps_x = slices[0]["ps"][1]
    ps_y = slices[0]["ps"][0]
    img.SetSpacing((ps_x, ps_y, abs(dz)))
    img.SetOrigin(tuple(slices[0]["ipp"]))
    Xn = X / np.linalg.norm(X)
    Yn = Y / np.linalg.norm(Y)
    direction = (Xn[0], Yn[0], N[0], Xn[1], Yn[1], N[1], Xn[2], Yn[2], N[2])
    img.SetDirection(direction)
    sop2idx = {s["sop"]: i for i, s in enumerate(slices)}
    return img, sop2idx, zs


def parse_gtv_contours(rt_path):
    d = pydicom.dcmread(rt_path, stop_before_pixels=True)
    num2name = {int(r.ROINumber): str(r.ROIName) for r in d.StructureSetROISequence}
    targets = {num for num, name in num2name.items() if is_gtv_primary(name)}
    contours = []
    for rc in d.ROIContourSequence:
        if int(rc.ReferencedROINumber) not in targets:
            continue
        if not hasattr(rc, "ContourSequence"):
            continue
        for cc in rc.ContourSequence:
            if getattr(cc, "ContourGeometricType", "") == "POINT":
                continue
            pts = np.array(cc.ContourData, dtype=float).reshape(-1, 3)
            ref_sop = None
            if hasattr(cc, "ContourImageSequence") and cc.ContourImageSequence:
                ref_sop = str(cc.ContourImageSequence[0].ReferencedSOPInstanceUID)
            contours.append((pts, ref_sop))
    roi_used = sorted({num2name[n] for n in targets})
    return contours, roi_used


def build_mask(img, sop2idx, z_arr, contours):
    direction = np.array(img.GetDirection()).reshape(3, 3)
    X, Y, N = direction[:, 0], direction[:, 1], direction[:, 2]
    spacing = img.GetSpacing()
    ps_x, ps_y = spacing[0], spacing[1]
    origin = np.array(img.GetOrigin())
    arr = sitk.GetArrayFromImage(img)
    mask = np.zeros(arr.shape, dtype=np.uint8)

    area_slices = {}
    n_skipped = 0
    for pts, ref_sop in contours:
        p = pts.astype(float)
        if ref_sop and ref_sop in sop2idx:
            k = sop2idx[ref_sop]
        else:
            zc = float(np.dot(p[0], N))
            k = int(np.argmin(np.abs(z_arr - zc)))
            if abs(z_arr[k] - zc) > 0.75 * spacing[2]:
                n_skipped += 1
                continue
        ipp_k = origin + k * spacing[2] * N
        rc = np.column_stack([
            np.dot(p - ipp_k, Y) / ps_y,
            np.dot(p - ipp_k, X) / ps_x])
        zc = float(np.dot(p[0], N))
        area_slices[zc] = area_slices.get(zc, 0.0) + poly_area_rc(rc) * ps_x * ps_y
        rasterize_polygon(mask[k], rc)

    zs = sorted(area_slices)
    vol = 0.0
    for i, z in enumerate(zs):
        if len(zs) > 1:
            dz_i = (zs[i + 1] - zs[i - 1]) / 2 if 0 < i < len(zs) - 1 else \
                   (zs[1] - zs[0] if i == 0 else zs[-1] - zs[-2])
        else:
            dz_i = spacing[2]
        vol += area_slices[z] * abs(dz_i)

    mimg = sitk.GetImageFromArray(mask)
    mimg.CopyInformation(img)
    return mimg, mask, vol, n_skipped


def find_rtstruct(dir_):
    """Find an RTSTRUCT file (Modality == RTSTRUCT) in a directory; returns path or None."""
    for f in glob.glob(os.path.join(dir_, "**", "*"), recursive=True):
        if not os.path.isfile(f):
            continue
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=True)
        except Exception:
            continue
        if str(getattr(ds, "Modality", "")) == "RTSTRUCT":
            return f
    return None


def write_image(img, dest):
    """SimpleITK cannot write NIfTI to non-ASCII paths -> go through an ASCII temp dir."""
    import tempfile
    import shutil
    tmpdir = tempfile.mkdtemp(prefix="sitk_w_")
    tmp = os.path.join(tmpdir, os.path.basename(dest))
    try:
        sitk.WriteImage(img, tmp)
        shutil.move(tmp, dest)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def convert(ct_dir, rt_path, out_img, out_msk):
    """DICOM (CT + RTSTRUCT) -> NIfTI (image + mask). Returns a QC dict."""
    img, sop2idx, z_arr = load_ct(ct_dir)
    contours, roi_used = parse_gtv_contours(rt_path)
    if not contours:
        raise RuntimeError("No GTV contours found in RTSTRUCT (check ROI names contain 'gtv')")

    mimg, mask, rt_vol, n_skipped = build_mask(img, sop2idx, z_arr, contours)
    if mask.sum() == 0:
        raise RuntimeError("Empty mask (no contour landed on any slice)")

    write_image(img, out_img)
    write_image(mimg, out_msk)

    spacing = img.GetSpacing()
    voxel_mm3 = spacing[0] * spacing[1] * spacing[2]
    mask_vol_cc = mask.sum() * voxel_mm3 / 1000.0
    rt_vol_cc = rt_vol / 1000.0
    rel = (mask_vol_cc - rt_vol_cc) / max(rt_vol_cc, 1e-9) if rt_vol_cc > 0 else None
    return {
        "n_slices": int(img.GetSize()[2]),
        "voxel_size_mm3": round(float(voxel_mm3), 4),
        "mask_vol_cc": round(float(mask_vol_cc), 4),
        "rtstruct_vol_cc": round(float(rt_vol_cc), 4),
        "rel_vol_diff": None if rel is None else round(float(rel), 4),
        "roi_used": roi_used,
        "n_contours": len(contours),
        "n_skipped": int(n_skipped),
    }
