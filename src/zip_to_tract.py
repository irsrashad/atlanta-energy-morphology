"""ZIP-to-census-tract energy comparison.

ZIP-level energy estimates are redistributed to census tracts by
population-weighted areal interpolation, then compared with the tract-level
model estimates.

Caveats carried with every output:
- MATLAB estimates are unreliable (many negative tract values). They are kept
  and flagged, but should not be used for cross-scale conclusions without a note.
- The 10% agreement bands and the HIGH/LOW cluster labels are analyst choices,
  not standards.
"""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.join_keys import pad_tract, pad_zip  # noqa: E402

ENERGY_COLS = ["predictedRF_train", "predictedRF_cv_train", "predictedmatlab_train", "actual"]
SUM_COLS = ["ZIP_RF_sum", "ZIP_RF_cv_sum", "ZIP_Matlab_sum", "ZIP_Actual_sum"]
# (short model key, ZIP-side sum column, tract-side column, display name)
MODELS = [
    ("RF", "ZIP_RF_sum", "RFnewCensus_RF", "RF Train"),
    ("RF_cv", "ZIP_RF_cv_sum", "RFnewCensus_cv", "RF CV"),
    ("Matlab", "ZIP_Matlab_sum", "matlabnewCens", "MATLAB"),
]
TIERS = ["Very Low", "Low", "Moderate", "High", "Very High"]
# sheets holding the ZIP ids and tract ids, row-aligned with the estimate sheets
CLUSTERS = {
    "HIGH": dict(file="highEE_FullData.xlsx", zip_sheet="ZipCode Coordinates", tract_sheet="Census Coordinates"),
    "LOW": dict(file="lowEE_FullData.xlsx", zip_sheet="Coordinates", tract_sheet="testCoordinates"),
}
MATLAB_NOTE = "Negative tract estimate - % unreliable"
# Bands are (lo, hi]: exactly 10 is Very Low. Both edge conventions give 0 mismatches
# against Step5 (no tract sits on an edge), so this is a convention, not a fitted value.
TIER_RIGHT_INCLUSIVE = True


def tier(abs_pct, right=TIER_RIGHT_INCLUSIVE):
    """Agreement tier for abs(PctDelta); NaN input gives 'N/A'."""
    out = pd.cut(abs_pct, [0, 10, 20, 30, 40, np.inf], labels=TIERS, right=right, include_lowest=True)
    return out.astype(object).where(abs_pct.notna(), "N/A")


def load_crosswalk(raw_dir):
    xw = pd.read_csv(Path(raw_dir) / "ga_zip_tract_equivalence.csv", dtype={"ZIPCode": str, "TractGeoID": str})
    xw["ZIPCode"], z_fix = pad_zip(xw["ZIPCode"])
    xw["TractGeoID"], t_fix = pad_tract(xw["TractGeoID"])
    assert xw["Pct"].max() <= 1, "Pct is expected to be a 0-1 fraction"
    return xw, {"crosswalk ZIP": z_fix, "crosswalk tract": t_fix}


CENSUS_REL = "census_rel_2010/zcta_tract_rel_10.txt"


def load_census2010(raw_dir):
    """Census 2010 ZCTA-to-tract relationship file as a crosswalk frame (Pct = POPPT / ZPOP, 0-1)."""
    df = pd.read_csv(Path(raw_dir) / CENSUS_REL, dtype=str, index_col=False)  # header has stray spaces / trailing comma
    df.columns = df.columns.str.strip()
    df = df[["ZCTA5", "GEOID", "POPPT", "ZPOP"]].copy()
    df["ZIPCode"], z_fix = pad_zip(df.pop("ZCTA5"))
    df["TractGeoID"], t_fix = pad_tract(df.pop("GEOID"))
    df["Pct"] = pd.to_numeric(df.pop("POPPT")) / pd.to_numeric(df.pop("ZPOP"))
    return df, {"crosswalk ZIP": z_fix, "crosswalk tract": t_fix}


def load_cluster(raw_dir, cluster):
    """Return (zip energy, tract estimates, padding log) for one cluster."""
    cfg = CLUSTERS[cluster]
    path = Path(raw_dir) / cfg["file"]
    z = pd.read_excel(path, sheet_name="RF_ZCTA_Estimates")
    zc = pd.read_excel(path, sheet_name=cfg["zip_sheet"], dtype={"ZCTA": str})
    t = pd.read_excel(path, sheet_name="censusEstimates")
    tc = pd.read_excel(path, sheet_name=cfg["tract_sheet"])
    assert len(z) == len(zc) and len(t) == len(tc), "id sheets are not row-aligned with estimates"
    z = z.assign(ZIPCode=zc["ZCTA"].values)
    t = t.assign(TractGeoID=tc["Census"].values, lat=tc["lat"].values, lon=tc["lon"].values)
    z["ZIPCode"], z_fix = pad_zip(z["ZIPCode"])
    t["TractGeoID"], t_fix = pad_tract(t["TractGeoID"])
    assert z["ZIPCode"].is_unique and t["TractGeoID"].is_unique
    return z, t, {f"{cluster} energy ZIP": z_fix, f"{cluster} study tract": t_fix}


def allocate(zip_df, xw):
    """Inner-join ZIP energy to the crosswalk, weight by Pct, sum by tract."""
    merged = zip_df.merge(xw[["ZIPCode", "TractGeoID", "Pct"]], on="ZIPCode", how="inner")
    weighted = merged.copy()
    weighted[ENERGY_COLS] = merged[ENERGY_COLS].mul(merged["Pct"], axis=0)
    agg = weighted.groupby("TractGeoID").agg(
        ZIP_count=("ZIPCode", "nunique"),
        ZIPs_Contributing=("ZIPCode", lambda s: ", ".join(sorted(set(s)))),
        Pct_Sum=("Pct", "sum"),
        ZIP_RF_sum=("predictedRF_train", "sum"),
        ZIP_RF_cv_sum=("predictedRF_cv_train", "sum"),
        ZIP_Matlab_sum=("predictedmatlab_train", "sum"),
        ZIP_Actual_sum=("actual", "sum"),
    ).reset_index()
    return merged, weighted, agg


def compare(agg, tract_df, cluster, right=TIER_RIGHT_INCLUSIVE):
    df = agg.merge(tract_df, on="TractGeoID", how="inner")
    df["Cluster"] = cluster
    df["Source"] = CLUSTERS[cluster]["file"]
    df["Matlab_Note"] = np.where(df["matlabnewCens"] <= 0, MATLAB_NOTE, "")
    for key, zcol, tcol, _ in MODELS:
        delta = df[zcol] - df[tcol]
        pct = (delta / df[tcol] * 100).where(df[tcol] > 0)  # not defined for tract estimates <= 0
        df[f"Delta_{key}"] = delta
        df[f"Exceed_{key}"] = delta > 0
        df[f"PctDelta_{key}"] = pct
        df[f"Agreement_{key}"] = tier(pct.abs(), right)
    return df


KEYS = ("RF", "RF_cv", "Matlab")
OUT_COLS = (["TractGeoID", "ZIP_count", "ZIPs_Contributing", "Pct_Sum"] + SUM_COLS
            + ["lat", "lon", "RFnewCensus_RF", "RFnewCensus_cv", "matlabnewCens", "Cluster", "Source"]
            + [f"Delta_{k}" for k in KEYS] + [f"Exceed_{k}" for k in KEYS]
            + [f"PctDelta_{k}" for k in KEYS] + ["Matlab_Note"] + [f"Agreement_{k}" for k in KEYS])


def build(raw_dir, right=TIER_RIGHT_INCLUSIVE, crosswalk="proximityone2020"):
    """Run the whole pipeline; returns a dict of every intermediate the tests need.

    ZIP energy from BOTH clusters is aggregated to tracts once (all 196 ZIPs), and
    each cluster's tract estimates are then joined to that single aggregate. This
    matches Workings_Transparent.xlsx; a strictly per-cluster aggregation loses
    tract 13063040606 (a LOW-list tract fed by two HIGH-cluster ZIPs).
    """
    if crosswalk == "census2010":
        xw, pad_log = load_census2010(raw_dir)
    else:
        xw, pad_log = load_crosswalk(raw_dir)
    res = {"crosswalk": xw, "pad_log": pad_log, "clusters": {}}
    for cl in CLUSTERS:
        z, t, log = load_cluster(raw_dir, cl)
        pad_log.update(log)
        res["clusters"][cl] = dict(zip=z.assign(Cluster=cl), tract=t)
    all_zip = pd.concat([d["zip"] for d in res["clusters"].values()], ignore_index=True)
    assert all_zip["ZIPCode"].is_unique, "a ZIP appears in both clusters"
    res["all_zip"] = all_zip
    if crosswalk == "census2010":  # the national file: keep only the study ZIPs
        res["crosswalk"] = xw = xw[xw["ZIPCode"].isin(all_zip["ZIPCode"])].reset_index(drop=True)
    res["merged"], res["weighted"], res["agg"] = allocate(all_zip, xw)
    parts = []
    for cl, d in res["clusters"].items():
        d["out"] = compare(res["agg"], d["tract"], cl, right)[OUT_COLS]
        parts.append(d["out"])
    res["combined"] = pd.concat(parts, ignore_index=True)
    return res


def summarize(df):
    rows = []
    for cl in ("HIGH", "LOW", "ALL"):
        sub = df if cl == "ALL" else df[df["Cluster"] == cl]
        for key, _, _, name in MODELS:
            pct = sub[f"PctDelta_{key}"].dropna()
            ag = sub[f"Agreement_{key}"]
            row = {"Model": name, "Cluster": cl, "n_matched": len(sub),
                   "exceedance_count": int(sub[f"Exceed_{key}"].sum()),
                   "mean_PctDelta": pct.mean(), "median_PctDelta": pct.median()}
            row.update({t: int((ag == t).sum()) for t in TIERS + ["N/A"]})
            rows.append(row)
    return pd.DataFrame(rows)


# ---- charts -----------------------------------------------------------------
# Okabe-Ito palette (color-blind safe)
C_HIGH, C_LOW = "#0072B2", "#E69F00"
TIER_COLORS = ["#F0E442", "#E69F00", "#D55E00", "#CC79A7", "#56B4E9", "#BBBBBB"]
NOTE = "Population-weighted areal interpolation of ZIP estimates; MATLAB tract estimates are unreliable (many negative)."


def _save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_agreement(df, path, tag=""):
    names = [m[3] for m in MODELS]
    fig, ax = plt.subplots(figsize=(8, 5))
    bottom = np.zeros(len(MODELS))
    for t, c in zip(TIERS + ["N/A"], TIER_COLORS):
        vals = np.array([(df[f"Agreement_{k}"] == t).sum() for k, *_ in MODELS])
        ax.bar(names, vals, bottom=bottom, color=c, label=t, edgecolor="white")
        for i, v in enumerate(vals):
            if v >= 3:  # smaller segments are left unlabeled to avoid overlap; counts are in the summary CSV
                ax.text(i, bottom[i] + v / 2, str(v), ha="center", va="center", fontsize=9)
        bottom += vals
    ax.set_ylabel("Number of tracts")
    ax.set_title(f"Agreement tier by model (n = {len(df)} matched tract rows){tag}")
    ax.legend(title="|PctDelta| tier", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.text(0.5, -0.04, "N/A = tract estimate <= 0, % difference not computed. Tier bands are analyst choices.\n" + NOTE,
             ha="center", fontsize=7)
    _save(fig, path)


def chart_exceedance(df, path, tag=""):
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(MODELS))
    bottom = np.zeros(len(MODELS))
    for cl, c in (("HIGH", C_HIGH), ("LOW", C_LOW)):
        vals = np.array([df.loc[df["Cluster"] == cl, f"Exceed_{k}"].sum() for k, *_ in MODELS])
        ax.bar(x, vals, bottom=bottom, color=c, label=cl, edgecolor="white")
        bottom += vals
    for i, v in enumerate(bottom):
        ax.text(i, v + 0.6, f"{int(v)} of {len(df)}", ha="center", fontsize=10)
    ax.set_xticks(x, [m[3] for m in MODELS])
    ax.set_ylabel("Tracts where ZIP-sum exceeds tract estimate")
    ax.set_ylim(0, len(df))
    ax.set_title(f"Exceedance count by model{tag}")
    ax.legend(title="Cluster")
    hi = df[df["Cluster"] == "HIGH"]
    high_note = "HIGH cluster exceedances: " + ", ".join(f"{n} {int(hi[f'Exceed_{k}'].sum())}" for k, _, _, n in MODELS)
    fig.text(0.5, -0.05, "Exceedance = ZIP-derived sum > tract estimate (also computed for MATLAB where the tract estimate is negative).\n" + high_note,
             ha="center", fontsize=7)
    _save(fig, path)


def chart_scatter(df, path, tag=""):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for ax, (k, zcol, tcol, name) in zip(axes, MODELS):
        ok = df[tcol] > 0
        for cl, c in (("HIGH", C_HIGH), ("LOW", C_LOW)):
            s = df[ok & (df["Cluster"] == cl)]
            ax.scatter(s[tcol], s[zcol], s=22, color=c, label=cl, alpha=0.85)
        lo = min(df.loc[ok, tcol].min(), df.loc[ok, zcol].min())
        hi = max(df.loc[ok, tcol].max(), df.loc[ok, zcol].max())
        ax.plot([lo, hi], [lo, hi], color="black", lw=1, label="1:1")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Tract estimate")
        ax.set_ylabel("ZIP-sum (population-weighted)")
        ax.set_title(f"{name}: {int(ok.sum())} plotted, {int((~ok).sum())} excluded", fontsize=10)
    axes[0].legend()
    fig.suptitle(f"ZIP-derived sum vs tract estimate (log axes; estimate <= 0 excluded){tag}")
    fig.text(0.5, -0.02, NOTE, ha="center", fontsize=7)
    fig.tight_layout()
    _save(fig, path)


def chart_hist(df, path, tag=""):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
    shown = (-100, 200)
    bins = np.arange(shown[0], shown[1] + 1, 10)
    for ax, (k, _, _, name) in zip(axes, MODELS):
        pct = df[f"PctDelta_{k}"].dropna()
        ax.hist(pct.clip(*shown), bins=bins, color=C_HIGH, edgecolor="white")
        ax.axvline(0, color="black", lw=1)
        ax.axvline(pct.median(), color="#D55E00", lw=1.5, ls="--", label=f"median {pct.median():.1f}%")
        n_na = int(df[f"PctDelta_{k}"].isna().sum())
        ax.set_title(f"{name}: n = {len(pct)}, {n_na} N/A excluded", fontsize=10)
        ax.set_xlabel("PctDelta (%)")
        ax.legend(loc="upper center")
    axes[0].set_ylabel("Number of tracts")
    fig.suptitle(f"Percent difference, ZIP-sum vs tract estimate (beyond -100/+200 shown in end bins){tag}")
    fig.text(0.5, -0.02, NOTE, ha="center", fontsize=7)
    fig.tight_layout()
    _save(fig, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ZIP-to-tract energy comparison")
    ap.add_argument("--raw-dir", default="data/raw/tables")
    ap.add_argument("--out-dir", default="data/processed")
    ap.add_argument("--fig-dir", default="docs/figures")
    ap.add_argument("--crosswalk", choices=["proximityone2020", "census2010"], default="proximityone2020")
    a = ap.parse_args(argv)
    out, figs = Path(a.out_dir), Path(a.fig_dir)
    out.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    c10 = a.crosswalk == "census2010"
    suf = "_census2010" if c10 else ""
    tag = " - 2010 Census crosswalk" if c10 else ""
    res = build(a.raw_dir, crosswalk=a.crosswalk)
    print("Padding fixes:", res["pad_log"])
    comb = res["combined"]
    comb.to_csv(out / f"zip_to_tract_comparison{suf}.csv", index=False)
    for cl in CLUSTERS:
        res["clusters"][cl]["out"].to_csv(out / f"zip_to_tract_comparison_{cl.lower()}{suf}.csv", index=False)
    summ = summarize(comb)
    summ.to_csv(out / f"zip_to_tract_summary{suf}.csv", index=False)
    chart_agreement(comb, figs / f"agreement_tiers{suf}.png", tag)
    chart_exceedance(comb, figs / f"exceedance{suf}.png", tag)
    chart_scatter(comb, figs / f"zip_vs_tract_scatter{suf}.png", tag)
    chart_hist(comb, figs / f"pctdelta_histogram{suf}.png", tag)
    if c10:
        print("Note: tract 13089021909 is in both clusters' estimate lists (different models); both rows are kept, "
              f"so {len(comb)} rows = {comb['TractGeoID'].nunique()} unique tracts.")
    print(f"{len(comb)} matched tracts ({comb['Cluster'].value_counts().to_dict()})")
    print(summ.round(2).to_string(index=False))
    print("Note: MATLAB estimates are unreliable (negative tract values); weighting is population-weighted areal interpolation.")


if __name__ == "__main__":
    main()
