"""Checks for the ZIP-to-tract comparison against Workings_Transparent.xlsx."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.join_keys import pad_tract, pad_zip
from src.zip_to_tract import ENERGY_COLS, KEYS, MODELS, SUM_COLS, TIERS, build, tier

RAW = Path("data/raw/tables")
NEEDED = ["highEE_FullData.xlsx", "lowEE_FullData.xlsx", "ga_zip_tract_equivalence.csv", "Workings_Transparent.xlsx"]
missing = [f for f in NEEDED if not (RAW / f).exists()]
pytestmark = pytest.mark.skipif(bool(missing), reason=f"raw inputs missing in {RAW}: {missing}")


@pytest.fixture(scope="module")
def res():
    return build(RAW)


@pytest.fixture(scope="module")
def step5():
    return pd.read_excel(RAW / "Workings_Transparent.xlsx", sheet_name="Step5_Final_Comparison",
                         dtype={"TractGeoID": str}, keep_default_na=False)


def wb_tier(s):
    # workbook labels look like '30-40% (High)' with an en dash; keep only the bracketed name
    return s.astype(str).str.extract(r"\((.*)\)")[0].fillna("N/A")


def test_01_row_counts(res):
    n_xw, n_tr = len(res["crosswalk"]), len(res["agg"])
    print(f"\ncrosswalk rows {n_xw}, aggregated tracts {n_tr}")
    assert n_xw == 2483 and n_tr == 1539


def test_02_key_lengths(res):
    xw, allz = res["crosswalk"], res["all_zip"]
    print(f"\nvalues fixed by padding: {res['pad_log']}")
    assert (xw["ZIPCode"].str.len() == 5).all() and (allz["ZIPCode"].str.len() == 5).all()
    assert (xw["TractGeoID"].str.len() == 11).all()
    for d in res["clusters"].values():
        assert (d["tract"]["TractGeoID"].str.len() == 11).all()
    # helpers themselves: float tract ids and short ZIPs
    assert pad_tract(pd.Series([13135050532.0]))[0].iloc[0] == "13135050532"
    z, n = pad_zip(pd.Series(["1234", "30303"]))
    assert list(z) == ["01234", "30303"] and n == 1


def test_03_zips_missing_and_energy_lost(res):
    allz, xw = res["all_zip"], res["crosswalk"]
    gone = allz[~allz["ZIPCode"].isin(xw["ZIPCode"])]
    lost = {c: gone[c].sum() / allz[c].sum() * 100 for c in ENERGY_COLS}
    print(f"\nZIPs not in crosswalk: {len(gone)} of {len(allz)}; energy lost % {lost}")
    assert len(gone) == 0


def test_04_pct_sums_to_one(res):
    s = res["crosswalk"].groupby("ZIPCode")["Pct"].sum()
    bad = s[(s - 1).abs() > 0.01]
    print(f"\nZIPs with Pct sum 1.0 +/- 0.01: {len(s) - len(bad)} of {len(s)}; failing: {list(bad.index)}")
    assert res["crosswalk"]["Pct"].max() <= 1
    assert len(s) == 196 and bad.empty


def test_05_mass_conserved(res):
    w, allz = res["weighted"], res["all_zip"].set_index("ZIPCode")
    pct = res["merged"].groupby("ZIPCode")["Pct"].sum()
    full = pct[(pct - 1).abs() <= 0.01].index
    alloc = w.groupby("ZIPCode")[ENERGY_COLS].sum().loc[full]
    rel = ((alloc - allz.loc[full, ENERGY_COLS]).abs() / allz.loc[full, ENERGY_COLS].abs().clip(lower=1)).max().max()
    print(f"\nfully covered ZIPs: {len(full)}; max relative allocation error {rel:.2e}")
    assert rel < 0.001


def test_06_matched_tracts(res, step5):
    c = res["combined"]
    counts = c["Cluster"].value_counts().to_dict()
    only_w = sorted(set(step5["TractGeoID"]) - set(c["TractGeoID"]))
    only_m = sorted(set(c["TractGeoID"]) - set(step5["TractGeoID"]))
    print(f"\nmatched {len(c)} {counts}; in Step5 only {only_w}; in mine only {only_m}")
    assert len(c) == 66 and counts == {"LOW": 49, "HIGH": 17}
    assert not only_w and not only_m


def test_07_exceedance(res):
    got = [int(res["combined"][f"Exceed_{k}"].sum()) for k in KEYS]
    print(f"\nexceedance RF/RF_cv/MATLAB: {got} of {len(res['combined'])}")
    assert got == [11, 16, 44]


def test_08_pctdelta_stats(res):
    c = res["combined"]
    mean = [c[f"PctDelta_{k}"].mean() for k in ("RF", "RF_cv")]
    med = [c[f"PctDelta_{k}"].median() for k in ("RF", "RF_cv")]
    print(f"\nmean {mean}, median {med}")
    assert mean == pytest.approx([-42.6, -38.1], abs=0.05)
    assert med == pytest.approx([-55.5, -49.1], abs=0.05)


def test_09_matches_step5(res, step5):
    m = step5.merge(res["combined"], on="TractGeoID", suffixes=("_w", "_m"))
    assert len(m) == 66
    num = lambda s: pd.to_numeric(s, errors="coerce")
    out = {}
    for c in SUM_COLS + [f"Delta_{k}" for k in KEYS]:
        out[c] = (num(m[c + "_w"]) - m[c + "_m"]).abs().max()
    for k in KEYS:
        d = (num(m[f"PctDelta_{k}_w"]) - m[f"PctDelta_{k}_m"]).abs()
        out[f"PctDelta_{k}"] = d.max()
        assert (num(m[f"PctDelta_{k}_w"]).isna() == m[f"PctDelta_{k}_m"].isna()).all()
    mism = {k: int((wb_tier(m[f"Agreement_{k}_w"]) != m[f"Agreement_{k}_m"]).sum()) for k in KEYS}
    mism_cluster = int((m["Cluster_w"].str.upper() != m["Cluster_m"]).sum())
    print(f"\nmax abs diffs vs Step5: {out}\ntier mismatches {mism}; cluster mismatches {mism_cluster}")
    for c in SUM_COLS + [f"Delta_{k}" for k in KEYS]:
        assert out[c] < 1e-3  # sums are ~1e6-1e7; this is ~1e-10 relative
    assert all(out[f"PctDelta_{k}"] < 0.05 for k in KEYS)
    assert sum(mism.values()) == 0 and mism_cluster == 0


def test_09b_tier_edge_convention(res, step5):
    # both edge conventions are compared with the workbook; report whether it matters
    m = step5.merge(res["combined"], on="TractGeoID", suffixes=("_w", "_m"))
    result = {}
    for right in (True, False):
        n = 0
        for k in KEYS:
            t = tier(m[f"PctDelta_{k}_m"].abs(), right)
            n += int((t != wb_tier(m[f"Agreement_{k}_w"])).sum())
        result["upper-inclusive (lo,hi]" if right else "lower-inclusive [lo,hi)"] = n
    print(f"\ntier mismatches by edge convention: {result}")
    assert result["upper-inclusive (lo,hi]"] == 0


def test_10_direction(res):
    c = res["combined"]
    for k, zcol, tcol, _ in MODELS:
        higher = c[zcol] > c[tcol]
        assert (c.loc[higher, f"Delta_{k}"] > 0).all() and c.loc[higher, f"Exceed_{k}"].all()
        assert (~c.loc[~higher, f"Exceed_{k}"]).all()
    print(f"\ndirection holds for {len(c)} tracts x {len(MODELS)} models")


def test_11_negative_estimates_are_na(res):
    c = res["combined"]
    out = []
    for k, _, tcol, _ in MODELS:
        neg = c[tcol] <= 0
        out.append((k, int(neg.sum())))
        assert (c.loc[neg, f"Agreement_{k}"] == "N/A").all()
        assert c.loc[neg, f"PctDelta_{k}"].isna().all()
        assert (c.loc[~neg, f"Agreement_{k}"] != "N/A").all()
        assert c.loc[~neg, f"PctDelta_{k}"].notna().all()
    assert (c.loc[c["matlabnewCens"] <= 0, "Matlab_Note"] != "").all()
    print(f"\nnegative/zero tract estimates (model, count): {out}")


def test_12_diagnostic_absent_study_tracts(res):
    """Diagnostic only: never fails."""
    xw = set(res["crosswalk"]["TractGeoID"])
    rows = pd.concat([d["tract"][["TractGeoID", "lat", "lon"]] for d in res["clusters"].values()], ignore_index=True)
    absent = rows[~rows["TractGeoID"].isin(xw)]
    print(f"\nstudy tract rows {len(rows)} ({rows['TractGeoID'].nunique()} unique); "
          f"absent from crosswalk: {len(absent)} rows ({absent['TractGeoID'].nunique()} unique)")
    gpkg = Path("data/interim/zipcode_joined.gpkg")
    if not gpkg.exists():
        print("zipcode_joined.gpkg not found; centroid check skipped")
        return
    try:
        import geopandas as gpd
        zips = gpd.read_file(gpkg)
        study = set(res["all_zip"]["ZIPCode"])
        zips = zips[zips["ZIP5"].astype(str).str.zfill(5).isin(study)]
        pts = gpd.GeoDataFrame(absent, geometry=gpd.points_from_xy(absent["lon"], absent["lat"]), crs="EPSG:4326").to_crs(zips.crs)
        inside = gpd.sjoin(pts, zips[["geometry"]], how="inner", predicate="within")
        n_in = inside.index.nunique()
        print(f"of those, centroid inside a study ZIP polygon: {n_in} (expected 109 absent / 106 inside)")
    except Exception as e:  # diagnostic must not fail the run
        print(f"centroid check skipped: {e}")


def test_13_diagnostic_crosswalk_tract_vintage(res):
    """Diagnostic only: how many crosswalk tract IDs exist in the 2010 tract layer."""
    layer = Path("data/raw/vectors/tiger_tracts_2010_georgia.gpkg")
    if not layer.exists():
        print("\ntiger_tracts_2010_georgia.gpkg not found; vintage check skipped")
        return
    try:
        import geopandas as gpd
        t10 = set(gpd.read_file(layer, ignore_geometry=True)["GEOID10"])
        xw = res["crosswalk"]
        ids = set(xw["TractGeoID"])
        pairs_off = (~xw["TractGeoID"].isin(t10)).mean()
        print(f"\ncrosswalk tract IDs not in the 2010 layer: {len(ids - t10)} of {len(ids)} "
              f"({pairs_off:.0%} of ZIP-tract rows); expected 1004 of 1539")
    except Exception as e:  # diagnostic must not fail the run
        print(f"vintage check skipped: {e}")


# ---- Census 2010 ZCTA-tract relationship file (second run) -------------------
CENSUS = RAW / "census_rel_2010" / "zcta_tract_rel_10.txt"
needs_census = pytest.mark.skipif(not CENSUS.exists(), reason=f"census 2010 file missing: {CENSUS}")


@pytest.fixture(scope="module")
def res10():
    return build(RAW, crosswalk="census2010")


@needs_census
def test_c10_a_file_rows_and_study_zips():
    from src.zip_to_tract import load_census2010
    full, _ = load_census2010(RAW)
    study = set(build(RAW)["all_zip"]["ZIPCode"])
    absent = study - set(full["ZIPCode"])
    print(f"\ncensus file rows {len(full)}; study ZIPs {len(study)}; absent {len(absent)}")
    assert len(full) == 148897 and not absent


@needs_census
def test_c10_b_tracts_in_2010_layer(res10):
    layer = Path("data/raw/vectors/tiger_tracts_2010_georgia.gpkg")
    if not layer.exists():
        pytest.skip("2010 tract layer missing")
    import geopandas as gpd
    g = gpd.read_file(layer)
    col = next(c for c in g.columns if c.upper() in ("GEOID10", "GEOID"))
    ids = set(g[col].astype(str).str.zfill(11))
    tr = set(res10["crosswalk"]["TractGeoID"])
    print(f"\nstudy-ZIP tract ids {len(tr)}; not in 2010 layer: {len(tr - ids)}")
    assert not tr - ids


@needs_census
def test_c10_c_pct_sums(res10):
    xw = res10["crosswalk"]
    s = xw.groupby("ZIPCode")["Pct"].sum()
    bad = s[(s - 1).abs() > 0.01]
    print(f"\nrows {len(xw)}, ZIPs {len(s)}; Pct sum 1.0 +/- 0.01: {len(s) - len(bad)}; failing {list(bad.index)}")
    assert len(s) == 196 and bad.empty and xw["Pct"].max() <= 1


@needs_census
def test_c10_d_mass(res10):
    w, allz = res10["weighted"], res10["all_zip"].set_index("ZIPCode")
    alloc = w.groupby("ZIPCode")[ENERGY_COLS].sum()
    rel = ((alloc - allz.loc[alloc.index, ENERGY_COLS]).abs() / allz.loc[alloc.index, ENERGY_COLS].abs().clip(lower=1)).max().max()
    print(f"\nZIPs allocated {len(alloc)}; max relative allocation error {rel:.2e}")
    assert len(alloc) == 196 and rel < 0.001


@needs_census
def test_c10_e_matched_rows(res, res10):
    c = res10["combined"]
    old = set(res["combined"]["TractGeoID"])
    both = c["Cluster"].value_counts().to_dict()
    print(f"\nmatched rows {len(c)} ({both}), unique tracts {c['TractGeoID'].nunique()}; "
          f"workbook 66 all present in new set: {old <= set(c['TractGeoID'])}; "
          f"tract 13089021909 rows: {int((c['TractGeoID'] == '13089021909').sum())}")
    assert len(c) == 175 and c["TractGeoID"].nunique() == 174 and old <= set(c["TractGeoID"])


@needs_census
def test_c10_f_direction_and_na(res10):
    c = res10["combined"]
    for k, zcol, tcol, _ in MODELS:
        higher = c[zcol] > c[tcol]
        assert (c.loc[higher, f"Delta_{k}"] > 0).all() and c.loc[higher, f"Exceed_{k}"].all()
        neg = c[tcol] <= 0
        assert (c.loc[neg, f"Agreement_{k}"] == "N/A").all() and c.loc[neg, f"PctDelta_{k}"].isna().all()
        assert (c.loc[~neg, f"Agreement_{k}"] != "N/A").all()
    print(f"\ndirection and N/A rules hold for {len(c)} rows; MATLAB estimates <= 0: {int((c['matlabnewCens'] <= 0).sum())}")


def _stats(df, label):
    from src.zip_to_tract import summarize
    s = summarize(df)
    print(f"\n[{label}] rows {len(df)}")
    print(s[s["Model"].isin(["RF Train", "RF CV"])].round(1).to_string(index=False))


@needs_census
def test_c10_g_side_by_side(res, res10):
    old, new = res["combined"], res10["combined"]
    # same tract can appear in both clusters, so pair on tract and cluster
    m = old.merge(new, on=["TractGeoID", "Cluster"], suffixes=("_old", "_new"))
    corr = m["ZIP_RF_sum_old"].corr(m["ZIP_RF_sum_new"])
    mad_sum = (m["ZIP_RF_sum_old"] - m["ZIP_RF_sum_new"]).abs().median()
    mad_pct = (m["PctDelta_RF_old"] - m["PctDelta_RF_new"]).abs().median()
    print(f"\nrows matched by both crosswalks: {len(m)}; ZIP_RF_sum corr {corr:.4f}, median abs diff {mad_sum:,.0f}; "
          f"PctDelta_RF median abs diff {mad_pct:.2f} points, corr {m['PctDelta_RF_old'].corr(m['PctDelta_RF_new']):.4f}")
    keys = set(zip(old["TractGeoID"], old["Cluster"]))
    is_old = [k in keys for k in zip(new["TractGeoID"], new["Cluster"])]
    _stats(new[is_old], "2010 crosswalk, the 66 earlier tracts")
    _stats(new[[not i for i in is_old]], "2010 crosswalk, newly covered rows")
    assert len(m) == 66
