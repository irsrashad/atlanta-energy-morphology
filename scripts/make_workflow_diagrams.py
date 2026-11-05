"""Render the data-preparation workflow as a paper figure and a slide figure, for either study unit.

Run from the repo root:
    .venv/Scripts/python.exe scripts/make_workflow_diagrams.py              # ZIP level (default)
    .venv/Scripts/python.exe scripts/make_workflow_diagrams.py --unit tract # census-tract level
    .venv/Scripts/python.exe scripts/make_workflow_diagrams.py --unit comparison # ZIP-to-tract comparison

Outputs (in figures/):
    ZIP:   workflow_paper.pdf / .svg / .png (600 dpi), workflow_slide.png / .svg
    tract: workflow_tract_paper.pdf / .svg / .png (600 dpi), workflow_tract_slide.png / .svg
    comparison: workflow_comparison_paper.pdf / .svg / .png (600 dpi), workflow_comparison_slide.png / .svg
    paper = grayscale-safe, full page width; slide = 16:9, Okabe-Ito colours

Both figures are drawn from the per-unit spec in UNITS below, so update it when pending data is added.
Both use Montserrat, loaded from figures/fonts/ (SIL OFL, see OFL.txt there).
Counts come from notebooks/01_data_preparation.ipynb and data/interim/zipcode_joined.gpkg (ZIP), and from
notebooks/02_tract_preparation.ipynb and data/interim/tract_joined.gpkg (tract). The comparison figure uses
the counts in data/processed/zip_to_tract_*_census2010.csv and docs/zip_to_tract_README.md.
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties, fontManager
from matplotlib.textpath import TextToPath

OUT_DIR = Path("figures")
FONT_DIR = Path(__file__).resolve().parent.parent / "figures" / "fonts"


def setup_fonts():
    """Register the bundled Montserrat TTFs; fall back to DejaVu Sans if the folder is missing."""
    if not FONT_DIR.is_dir():
        print("WARNING: figures/fonts/ not found; falling back to DejaVu Sans")
        return ["DejaVu Sans"]
    for f in sorted(FONT_DIR.glob("*.ttf")):
        fontManager.addfont(str(f))
    return ["Montserrat", "DejaVu Sans"]      # DejaVu only fills glyphs Montserrat lacks


FONT = setup_fonts()

# ---------------------------------------------------------------------------
# Shared data spec (single source of truth). Everything that differs between the ZIP and the
# tract figure lives in UNITS; the drawing code below only reads from the selected entry.
# ---------------------------------------------------------------------------
ZIP_DATASETS = [
    {"name": "CBD", "source": "Atlanta CBD polygon", "native": "1 polygon",
     "preprocessing": "Representative point",
     "join": "— (distance only)",
     "aggregation": "Euclidean distance from each ZIP's representative point (mi)",
     "outputs": "Dist_CBD_mi", "status": "done", "family": "transport",
     "slide_source": "Downtown (CBD)", "slide_detail": "1 polygon",
     "slide_join": "Straight-line distance from each ZIP",
     "slide_out": "Distance to CBD"},
    {"name": "MARTA rail", "source": "MARTA open data", "native": "38 stations",
     "preprocessing": "Reprojected to EPSG:2240",
     "join": "Point-in-polygon (within); nearest neighbour from rep. point",
     "aggregation": "Count; distance (mi)",
     "outputs": "MARTA_stations_in_zip, Dist_MARTA_Rail_mi (32 stations in 20 ZIPs)",
     "status": "done", "family": "transport",
     "slide_source": "MARTA rail", "slide_detail": "38 stations",
     "slide_join": "Count inside ZIP + nearest distance",
     "slide_out": "Station count + distance"},
    {"name": "Walkability", "source": "EPA NWI v3.0",
     "native": "5,711 block groups (2,705 intersect)",
     "preprocessing": "Keep NatWalkInd and D3B (D4A not used)",
     "join": "Overlay cuts block groups at ZIP lines",
     "aggregation": "Area-weighted mean: each block-group piece weighted by its share of ZIP area",
     "outputs": "NatWalkInd_zip, D3B_zip", "status": "done", "family": "built",
     "slide_source": "Walkability (EPA)", "slide_detail": "5,711 block groups",
     "slide_join": "Block groups cut at ZIP lines\n→ area-weighted average",
     "slide_out": "Walkability +\nintersection density"},
    {"name": "Buildings", "source": "Microsoft footprints, 2018–20",
     "native": "3.98 M footprints",
     "preprocessing": "Area (sq ft); representative point",
     "join": "Point in ZIP (1.85 M assigned)",
     "aggregation": "Count, sum, mean, max area; coverage = footprint sq ft / ZIP sq ft",
     "outputs": "ms_* (5 variables)", "status": "done", "family": "built",
     "slide_source": "Building footprints", "slide_detail": "3.98 M buildings (Microsoft)",
     "slide_join": "Assign each building to its ZIP",
     "slide_out": "Count, size, coverage"},
    {"name": "Socioeconomic", "source": "2011 ACS / Census",
     "native": "209 ZIPs + 1,969 tracts",
     "preprocessing": "Codebook; cleaning; energy/pop alignment check",
     "join": "Direct attribute join on ZIP5",
     "aggregation": "None (already ZIP level)",
     "outputs": "356 se_v* variables", "status": "done", "family": "socio",
     "slide_source": "Census / ACS 2011", "slide_detail": "ZIP-level tables",
     "slide_join": "Already by ZIP: direct table join",
     "slide_out": "356 census variables"},
    {"name": "Land use", "source": "ARC LandPro 2012",
     "native": "54,162 polygons, 29 classes",
     "preprocessing": "Repair 363 self-intersecting polygons (= ArcGIS Repair Geometry)",
     "join": "Polygon overlay",
     "aggregation": "Area share (% of covered area); masked if coverage < 99%",
     "outputs": "29 lu_pct_* + 3 DE3 shares + coverage (142/190 ZIPs)",
     "status": "done", "family": "landuse",
     "slide_source": "Land use (ARC 2012)", "slide_detail": "54,162 polygons",
     "slide_join": "% of ZIP area in each class",
     "slide_note": "(broken outlines repaired first)",
     "slide_out": "Land-use shares (142 ZIPs)"},
    {"name": "Land cover", "source": "NLCD 2011 land cover (USGS)",
     "native": "30 m CONUS raster, 15 classes in study area",
     "preprocessing": "Kept on native Albers equal-area grid (no resampling)",
     "join": "ZIPs rasterized onto the grid (pixel centre in ZIP)",
     "aggregation": "Class share: class pixels / classified pixels (equal-area, so = area share)",
     "outputs": "15 nlcd11_pct_* + developed & forest totals (all 190 ZIPs)",
     "status": "done", "family": "landuse",
     "slide_source": "Land cover (NLCD 2011)", "slide_detail": "30 m satellite raster",
     "slide_join": "% of ZIP pixels in each class",
     "slide_out": "Land-cover shares (190 ZIPs)"},
    {"name": "Air quality", "source": "EPA EQUATES CMAQ",
     "native": "July 2010: 12 km grid, 31 days",
     "preprocessing": "Average 31 days per cell → rebuild each cell-centre point as its 12 km "
                      "model grid square (native CMAQ grid, no interpolation) → reproject",
     "join": "Polygon overlay",
     "aggregation": "Area-weighted mean of grid squares overlapping the ZIP",
     "outputs": "14 aq_*_jul2010 (208 cells)", "status": "done", "family": "env",
     "slide_source": "Air quality (EPA model)", "slide_detail": "12 km grid, July 2010",
     "slide_join": "July mean per 12 km grid square\n→ area-weighted average (no interpolation)",
     "slide_out": "14 pollutant averages"},
    {"name": "Remote sensing", "source": "Landsat NDVI & LST, NLCD impervious, LAI",
     "native": "4 Georgia rasters, 2011–12 (30 m; LAI 500 m)",
     "preprocessing": "Kept on native EPSG:4326 grid (no resampling); LAI fill 25.5 → no data",
     "join": "ZIPs rasterized onto the grid (pixel centre in ZIP)",
     "aggregation": "Zonal mean of valid pixels (= ArcGIS Zonal Statistics, MEAN)",
     "outputs": "rs_ndvi, rs_impervious, rs_lst, rs_lai means + LAI valid share (LAI: 179/190 ZIPs)",
     "status": "done", "family": "env",
     "slide_source": "Satellite rasters", "slide_detail": "NDVI, impervious, LST, LAI",
     "slide_join": "Average of the pixels inside each ZIP",
     "slide_out": "4 raster means"},
    # Planned (drawn dashed)
    {"name": "Roads (TIGER 2012)", "source": "Primary/secondary roads",
     "method": "Road length / ZIP area", "status": "planned", "family": "transport",
     "slide_label": "Major roads → length per area"},
]

# Tract rows: the same datasets in the same order; only the strings that differ are listed.
TRACT_DATASET_CHANGES = {
    "CBD": {
        "aggregation": "Euclidean distance from each tract's representative point (mi)",
        "slide_join": "Straight-line distance from each tract"},
    "MARTA rail": {
        "outputs": "MARTA_stations_in_tract, Dist_MARTA_Rail_mi (0 of 38 stations inside a "
                   "study tract)",
        "slide_join": "Count inside tract + nearest distance"},
    "Walkability": {
        "native": "5,711 block groups (1,575 intersect)",
        "join": "Overlay cuts block groups at tract lines",
        "aggregation": "Area-weighted mean: each block-group piece weighted by its share of "
                       "tract area",
        "outputs": "NatWalkInd_tract, D3B_tract",
        "slide_join": "Block groups cut at tract lines\n→ area-weighted average"},
    "Buildings": {
        "join": "Point in tract (0.48 M assigned)",
        "aggregation": "Count, sum, mean, max area; coverage = footprint sq ft / "
                       "tract sq ft",
        "slide_join": "Assign each building to its tract"},
    "Socioeconomic": {
        "native": "1,969 Georgia tracts",
        "join": "Direct attribute join on TractGeoID",
        "aggregation": "None (already tract level)",
        "slide_detail": "Tract-level tables",
        "slide_join": "Already by tract: direct table join"},
    "Land use": {
        "outputs": "29 lu_pct_* + 3 DE3 shares + coverage (142/174 tracts)",
        "slide_join": "% of tract area in each class",
        "slide_out": "Land-use shares (142 tracts)"},
    "Land cover": {
        "join": "Tracts rasterized onto the grid (pixel centre in tract)",
        "outputs": "15 nlcd11_pct_* + developed & forest totals (all 174 tracts)",
        "slide_join": "% of tract pixels in each class",
        "slide_out": "Land-cover shares (all 174)"},
    "Air quality": {
        "aggregation": "Area-weighted mean of grid squares overlapping the tract",
        "outputs": "14 aq_*_jul2010 (203 cells)"},
    "Remote sensing": {
        "join": "Tracts rasterized onto the grid (pixel centre in tract)",
        "outputs": "rs_ndvi, rs_impervious, rs_lst, rs_lai means + LAI valid share "
                   "(LAI: 153/174 tracts)",
        "slide_join": "Average of the pixels inside each tract"},
    "Roads (TIGER 2012)": {"method": "Road length / tract area"},
}
TRACT_DATASETS = [{**d, **TRACT_DATASET_CHANGES.get(d["name"], {})} for d in ZIP_DATASETS]

# ZIP-to-tract comparison workflow: reuses the same drawing code with its own rows.
COMPARISON_DATASETS = [
    {"name": "ZIP estimates", "source": "highEE / lowEE RF_ZCTA_Estimates",
     "native": "196 study ZIPs (63 HIGH, 133 LOW); RF train, RF CV, MATLAB predictions + actual",
     "preprocessing": "ZIP ids from the coordinates sheets; text, zero-padded to 5",
     "join": "Inner join to the ZIP-to-tract table on ZIP",
     "aggregation": "ZIP energy × share, summed by tract across all 196 ZIPs together",
     "outputs": "ZIP_RF_sum, ZIP_RF_cv_sum, ZIP_Matlab_sum, ZIP_Actual_sum, Pct_Sum",
     "status": "done", "family": "energy",
     "slide_source": "ZIP energy estimates", "slide_detail": "196 ZIPs (63 HIGH, 133 LOW)",
     "slide_join": "Inner join to the ZIP-to-tract table on ZIP",
     "slide_out": "ZIP-derived sums\nper tract"},
    {"name": "ZIP-to-tract table", "source": "Main run: Census 2010 ZCTA-to-tract relationship file",
     "native": "1,802 rows for the 196 study ZIPs; 998 tracts",
     "preprocessing": "Keep the study ZIPs; ids as text",
     "join": "Key: ZIP",
     "aggregation": "Share = tract population in ZIP / ZIP population (POPPT / ZPOP)",
     "outputs": "Shares sum to 1 for every ZIP",
     "status": "done", "family": "transport",
     "slide_source": "Census 2010 table", "slide_detail": "1,802 ZIP-tract rows",
     "slide_join": "Share = tract pop in ZIP / ZIP pop",
     "slide_out": "Weights that sum to 1\nper ZIP"},
    {"name": "Tract estimates", "source": "highEE / lowEE censusEstimates",
     "native": "175 rows = 174 unique tracts (tract 13089021909 is in both clusters; both rows kept)",
     "preprocessing": "Tract ids from the tract-coordinates sheets; text, zero-padded to 11",
     "join": "Inner join on TractGeoID, per cluster",
     "aggregation": "None (already tract level)",
     "outputs": "RFnewCensus_RF, RFnewCensus_cv, matlabnewCens",
     "status": "done", "family": "socio",
     "slide_source": "Tract energy estimates", "slide_detail": "175 rows, 174 unique tracts",
     "slide_join": "Inner join on tract id, per cluster",
     "slide_out": "3 tract estimates"},
    {"name": "Comparison", "source": "ZIP-derived sums vs tract estimates",
     "native": "175 matched rows",
     "preprocessing": "Delta = ZIP-derived sum − tract estimate",
     "join": "Side by side on TractGeoID",
     "aggregation": "% Delta = Delta / tract estimate × 100; exceedance = Delta > 0",
     "outputs": "Tier on |% Delta|: 0–10 Very Low, 10–20 Low, 20–30 Moderate, 30–40 High, over 40 "
                "Very High. N/A, no % Delta if tract estimate ≤ 0",
     "status": "done", "family": "built",
     "slide_source": "Comparison", "slide_detail": "Delta, % Delta, exceedance",
     "slide_join": "Delta = ZIP sum − tract estimate\n% Delta = Delta / estimate × 100",
     "slide_out": "Agreement tier\n(Very Low … Very High)"},
    {"name": "Earlier run", "source": "ProximityOne table (2020 tract IDs)",
     "method": "2,483 rows, 1,539 tracts; only 66 of 174 study tracts match",
     "planned_out": "kept for reference", "status": "planned", "family": "transport",
     "slide_label": "2020 IDs: 66 of 174 match"},
]

STAGE_NAMES = ["Input data", "Preprocessing", "Spatial join", "Aggregation to {unit}",
               "Output variables"]

UNITS = {
    "zip": {
        "stem": "workflow_paper", "slide_stem": "workflow_slide",
        "n": 190, "n_vars": 466,
        "stages": [s.format(unit="ZIP") for s in STAGE_NAMES],
        "frame": {
            "name": "Study frame",
            "source": "TIGER ZCTA 2010 + prior ZIP-level energy model",
            "native": "1,470 rows = 735 ZCTAs × 2 cluster copies",
            "preprocessing": "Keep ZIPs with all 3 predictions > 0; key ZIP5 (text); "
                             "project to EPSG:2240 (US ft); zip_area_sqft",
            "frame": "ZIP study frame\nn = 190 ZIPs (63 HIGH, 127 LOW)\nEPSG:2240 (US ft)",
            "outputs": "energy_actual_kwh + 3 model predictions",
            "family": "energy",
            "slide_source": "ZIP areas + energy model",
            "slide_detail": "735 ZCTAs (TIGER 2010)",
            "slide_join": "Keep ZIPs with all 3 predictions > 0",
            "slide_out": "Energy use + 3 predictions",
        },
        "datasets": ZIP_DATASETS,
        "master": {
            "title": "Master ZIP table",
            "detail": "190 ZIPs × 466 variables\nzipcode_joined.gpkg",
            "qa": "QA checks + data dictionary",
            "later": "Later: ZIP → tract thread",
        },
        "worked": {
            "title": "Area-weighted mean (walkability, air quality)",
            "formula": "ZIP value = ∑(value × overlap area) / ∑(overlap area)",
            "example": "e.g. pieces covering 60% / 30% / 10% of a ZIP with scores 15 / 10 / 5 "
                       "→ 0.6·15 + 0.3·10 + 0.1·5 = 12.5",
        },
        "spine_label": "joined to ZIP frame",
        "legend": ["solid: joined to ZIP table", "dashed: planned",
                   "dotted: ZIP study frame (n = 190) used by every join"],
        "slide_title": "ZIP-level data pipeline: 190 Atlanta-area ZIPs",
        "slide_join_header": "How it's joined to ZIPs",
        "slide_master_count": "190 ZIPs\n×\n466\nvariables",
    },
    "tract": {
        "stem": "workflow_tract_paper", "slide_stem": "workflow_tract_slide",
        "n": 174, "n_vars": 461,
        "stages": [s.format(unit="tract") for s in STAGE_NAMES],
        "frame": {
            "name": "Study frame",
            "source": "TIGER tracts 2010 + prior tract-level energy model",
            "native": "1,969 Georgia tracts; 175 workbook rows = 174 tracts "
                      "(1 tract in both clusters)",
            "preprocessing": "Keep all 174 energy-study tracts (not filtered on > 0; 75 negative "
                             "MATLAB estimates flagged); key TractGeoID (text); "
                             "project to EPSG:2240 (US ft); tract_area_sqft",
            "frame": "Tract study frame\n174 energy-study tracts\n(50 HIGH, 124 LOW)\n"
                     "EPSG:2240 (US ft)",
            "outputs": "3 model predictions; energy_actual_kwh empty (no tract energy)",
            "family": "energy",
            "slide_source": "Tract areas + energy model",
            "slide_detail": "1,969 tracts (TIGER 2010)",
            "slide_join": "Keep the 174 energy-study tracts",
            "slide_out": "3 predictions\n(no observed energy)",
        },
        "datasets": TRACT_DATASETS,
        "master": {
            "title": "Master tract table",
            "detail": "174 tracts × 461 variables\ntract_joined.gpkg",
            "qa": "QA checks + data dictionary",
            "later": "Later: ZIP ↔ tract comparison",
        },
        "worked": {
            "title": "Area-weighted mean (walkability, air quality)",
            "formula": "Tract value = ∑(value × overlap area) / ∑(overlap area)",
            "example": "e.g. pieces covering 60% / 30% / 10% of a tract with scores 15 / 10 / 5 "
                       "→ 0.6·15 + 0.3·10 + 0.1·5 = 12.5",
        },
        "spine_label": "joined to tract frame",
        "legend": ["solid: joined to tract table", "dashed: planned",
                   "dotted: tract study frame (n = 174) used by every join"],
        "slide_title": "Tract-level data pipeline: 174 Atlanta-area tracts",
        "slide_join_header": "How it's joined to tracts",
        "slide_master_count": "174 tracts\n×\n461\nvariables",
    },
    "comparison": {
        "stem": "workflow_comparison_paper", "slide_stem": "workflow_comparison_slide",
        "stages": ["Input data", "Preprocessing", "Join", "Aggregation to tract",
                   "Output variables"],
        "frame": {
            "name": "Study frame",
            "source": "Energy-study ZIPs and tracts (both clusters)",
            "native": "196 ZIPs; 175 tract rows = 174 unique tracts",
            "preprocessing": "Ids kept as text (ZIP 5, tract 11 characters); cluster label "
                             "HIGH / LOW on every row",
            "frame": "Study frame\n196 ZIPs\n175 tract rows (174 unique)",
            "outputs": "Cluster (HIGH / LOW)",
            "family": "landuse",
            "slide_source": "Study frame", "slide_detail": "196 ZIPs, 174 tracts",
            "slide_join": "Ids kept as text; HIGH / LOW label",
            "slide_out": "Cluster label",
        },
        "datasets": COMPARISON_DATASETS,
        "master": {
            "title": "Comparison table",
            "detail": "175 rows × 28 columns\nzip_to_tract_comparison_census2010.csv\n"
                      "(+ _high, _low, summary CSVs)",
            "qa": "21 tests incl. mass check and table-vintage diagnostic",
            "later": "Earlier run: 66 of 174 tracts matched",
        },
        "worked": {
            "title": "Population-weighted areal interpolation",
            "formula": "Tract value = ∑(ZIP energy × share)",
            "example": "e.g. a tract holding 30% of ZIP A (100) and 10% of ZIP B (50) gets "
                       "0.3·100 + 0.1·50 = 35",
        },
        "spine_label": "restricted to the study ZIPs",
        "legend": ["solid: main run (Census 2010 table)",
                   "dashed: earlier run (2020 tract IDs)",
                   "dotted: study frame (196 ZIPs / 175 tract rows)"],
        "planned_label": "Earlier run",
        "planned_h": 0.5,
        "caveats": "Caveats: MATLAB estimates are unreliable (75 negative tract estimates); the 10% "
                   "tier bands and HIGH / LOW labels are analyst choices, not standards; the "
                   "weighting is population-weighted areal interpolation.",
        "slide_title": "ZIP-to-tract comparison: 196 ZIPs, 175 tract rows",
        "slide_join_header": "How it is joined",
        "slide_master_title": "Result\ntable",
        "family_labels": {"landuse": "Study frame", "energy": "ZIP estimates",
                          "transport": "ZIP-to-tract table", "socio": "Tract estimates",
                          "built": "Comparison"},
        "slide_master_count": "175 rows\n×\n28\ncolumns",
        "slide_planned_label": "Earlier\nrun",
        "slide_h_row": 0.78,
        "slide_caveat": "MATLAB estimates are unreliable (75 negative tract estimates). "
                        "10% tier bands are analyst choices. Weighting: population-weighted "
                        "areal interpolation.",
    },
}

# Okabe-Ito palette, one colour per data family (slide only)
FAMILIES = {
    "energy": ("Energy / base", "#D55E00"),
    "transport": ("Transport", "#0072B2"),
    "built": ("Built form", "#E69F00"),
    "socio": ("Socioeconomic", "#CC79A7"),
    "landuse": ("Land use / cover", "#009E73"),
    "env": ("Environment", "#56B4E9"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def wrap(text, width_in, fontsize, weight="normal"):
    """Greedy word wrap using measured text width (inches), so text fits its box."""
    prop = FontProperties(family=FONT, size=fontsize, weight=weight)
    measure = lambda s: TextToPath().get_text_width_height_descent(s, prop, ismath=False)[0] / 72
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = f"{line} {word}".strip()
            if line and measure(cand) > width_in:
                lines.append(line)
                line = word
            else:
                line = cand
        lines.append(line)
    return "\n".join(lines)


def text_height(text, fontsize, linespacing):
    """Approximate height (inches) of a multi-line text block."""
    return (text.count("\n") + 1) * fontsize * linespacing * 1.22 / 72


def box(ax, x, y, w, h, fc="white", ec="black", lw=0.6, ls="-", hatch=None,
        hatch_color="0.72", r=0.03, z=2):
    """Rounded box with (x, y) = lower-left corner. Hatching drawn as a separate light layer."""
    style = f"round,pad=0,rounding_size={r}"
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, fc=fc, ec="none", zorder=z))
    if hatch:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, fc="none", ec=hatch_color,
                                    lw=0, hatch=hatch, zorder=z + 0.1))
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, fc="none", ec=ec, lw=lw,
                                ls=ls, zorder=z + 0.2))


def arrow(ax, x0, y0, x1, y1, color="black", lw=0.6, ls="-", head=4, z=3):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), zorder=z,
                arrowprops=dict(arrowstyle=f"-|>,head_length={head / 10},head_width={head / 20}",
                                color=color, lw=lw, ls=ls, shrinkA=0, shrinkB=0))


def save(fig, stem, fmts, dpi):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in fmts:
        fig.savefig(OUT_DIR / f"{stem}.{ext}", dpi=dpi)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Paper figure: grayscale-safe, column per stage, row per dataset
# ---------------------------------------------------------------------------
def draw_paper(U):
    plt.rcParams.update({"font.family": FONT, "hatch.linewidth": 0.35,
                         "svg.fonttype": "none", "pdf.fonttype": 42})
    W, H = 7.0, 10.0
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    fs, fs_small, fs_hdr, ls_body = 6.8, 6.0, 6.8, 1.15
    # Stage styles: separated by fill lightness and hatching, not hue
    stage_style = [dict(fc="0.80"), dict(fc="0.93"), dict(fc="white", hatch="...."),
                   dict(fc="0.93", hatch="////"), dict(fc="white")]
    widths = [1.30, 1.34, 1.14, 1.26, 1.18]
    gap, x0 = 0.11, 0.06
    xs = [x0 + sum(widths[:i]) + gap * i for i in range(5)]
    x_right = xs[-1] + widths[-1]
    x_bus = x_right + 0.09                         # collector line into the master table

    def span_w(i, span):
        return sum(widths[i:i + span]) + gap * (span - 1)

    def cell_body(i, text, span=1):
        return wrap(text, span_w(i, span) - 0.12, fs_small) if text else ""

    def cell_need(i, text, bold=None, span=1):
        """Height a cell needs for its (wrapped) text."""
        body_h = text_height(cell_body(i, text, span), fs_small, ls_body)
        return body_h + (0.2 if bold else 0.09)

    def cell(i, y, h, text, bold=None, planned=False, span=1):
        w = span_w(i, span)
        st = dict(stage_style[i]) if not planned else dict(fc="white")
        box(ax, xs[i], y, w, h, ls="--" if planned else "-",
            ec="0.45" if planned else "black", **st)
        color = "0.40" if planned else "black"
        body = cell_body(i, text, span)
        if bold:
            ax.text(xs[i] + 0.05, y + h - 0.045, bold, ha="left", va="top", fontsize=fs,
                    weight="bold", color=color, zorder=5)
            ax.text(xs[i] + 0.05, y + h - 0.045 - 0.125, body, ha="left", va="top",
                    fontsize=fs_small, color=color, linespacing=ls_body, zorder=5)
        else:
            ax.text(xs[i] + w / 2, y + h / 2, body, ha="center", va="center", fontsize=fs_small,
                    color=color, linespacing=ls_body, zorder=5)

    def row_arrows(y_mid, cols, planned=False):
        for a, b in cols:
            arrow(ax, xs[a] + sum(widths[a:b]) + gap * (b - a - 1), y_mid, xs[b], y_mid,
                  color="0.45" if planned else "black", ls="--" if planned else "-")

    # Column header band (wrapped to two lines where a stage name is too wide)
    hdrs = [wrap(f"{i + 1}. {name}", widths[i] - 0.1, fs_hdr, weight="bold")
            for i, name in enumerate(U["stages"])]
    h_hdr = max(0.28, max(text_height(t, fs_hdr, 1.1) for t in hdrs) + 0.1)
    y_hdr = H - 0.08 - h_hdr
    for i, t in enumerate(hdrs):
        box(ax, xs[i], y_hdr, widths[i], h_hdr, lw=0.8, **stage_style[i])
        ax.text(xs[i] + widths[i] / 2, y_hdr + h_hdr / 2, t, ha="center", va="center",
                fontsize=fs_hdr, weight="bold", linespacing=1.1, zorder=5,
                bbox=dict(fc="white", ec="none", pad=0.6) if stage_style[i].get("hatch") else None)

    # Study frame band
    sf = U["frame"]
    h_sf = max(0.66, cell_need(0, f"{sf['source']}\n{sf['native']}", bold=sf["name"]),
               cell_need(1, sf["preprocessing"]), cell_need(4, sf["outputs"]))
    y_sf = y_hdr - 0.12 - h_sf
    ax.add_patch(Rectangle((0.02, y_sf - 0.06), W - 0.04, h_sf + 0.12, fc="0.97",
                           ec="0.6", lw=0.4, zorder=0))
    cell(0, y_sf, h_sf, f"{sf['source']}\n{sf['native']}", bold=sf["name"])
    cell(1, y_sf, h_sf, sf["preprocessing"])
    sw = span_w(2, 2)
    box(ax, xs[2], y_sf, sw, h_sf, fc="white", lw=1.3)
    ax.text(xs[2] + sw / 2, y_sf + h_sf / 2, sf["frame"], ha="center", va="center",
            fontsize=fs, weight="bold", linespacing=1.3, zorder=5)
    cell(4, y_sf, h_sf, sf["outputs"])
    row_arrows(y_sf + h_sf / 2, [(0, 1), (1, 2)])
    arrow(ax, xs[2] + sw, y_sf + h_sf / 2, xs[4], y_sf + h_sf / 2)

    # Dataset rows (each row as tall as its fullest cell)
    done = [d for d in U["datasets"] if d["status"] == "done"]
    planned = [d for d in U["datasets"] if d["status"] == "planned"]
    h_row_min, h_pl, g_row = 0.52, U.get("planned_h", 0.34), 0.075
    y = y_sf - 0.06 - 0.16
    frame_x = xs[2] + widths[2] / 2
    out_mids = [y_sf + h_sf / 2]
    for d in done:
        texts = [f"{d['source']}\n{d['native']}", d["preprocessing"], d["join"],
                 d["aggregation"], d["outputs"]]
        h_row = max([h_row_min] + [cell_need(i, t, bold=d["name"] if i == 0 else None)
                                   for i, t in enumerate(texts)])
        y -= h_row
        for i, t in enumerate(texts):
            cell(i, y, h_row, t, bold=d["name"] if i == 0 else None)
        row_arrows(y + h_row / 2, [(0, 1), (1, 2), (2, 3), (3, 4)])
        out_mids.append(y + h_row / 2)
        y -= g_row
    y_last_done = y + g_row

    # "Every row joins to the study frame": dotted spine down the join column
    ax.plot([frame_x, frame_x], [y_sf, y_last_done], color="0.35", lw=0.8, ls=(0, (1, 1.5)),
            zorder=1)
    ax.text(frame_x + 0.04, y_sf - 0.1, U["spine_label"], fontsize=fs_small, style="italic",
            color="0.3", ha="left", va="center", zorder=5,
            bbox=dict(fc="0.97", ec="none", pad=0.3))

    # Planned rows
    y -= 0.12
    ax.text(xs[0], y, U.get("planned_label", "Planned"), fontsize=fs, weight="bold", color="0.40",
            ha="left", va="center")
    y -= 0.08
    pl_mids = []
    for d in planned:
        y -= h_pl
        cell(0, y, h_pl, d["source"], bold=d["name"], planned=True)
        cell(1, y, h_pl, d["method"], planned=True, span=3)
        row_arrows(y + h_pl / 2, [(0, 1)], planned=True)
        x_end = xs[1] + span_w(1, 3)
        arrow(ax, x_end, y + h_pl / 2, xs[4], y + h_pl / 2, color="0.45", ls="--")
        cell(4, y, h_pl, d.get("planned_out", "to be added"), planned=True)
        pl_mids.append(y + h_pl / 2)
        y -= g_row

    # Collector into the master table
    for ym in out_mids:
        ax.plot([x_right, x_bus], [ym, ym], color="black", lw=0.6, zorder=3)
    for ym in pl_mids:
        ax.plot([x_right, x_bus], [ym, ym], color="0.45", lw=0.6, ls="--", zorder=3)
    y_m_top = y - 0.12
    ax.plot([x_bus, x_bus], [out_mids[0], pl_mids[0]], color="black", lw=0.6, zorder=3)
    ax.plot([x_bus, x_bus], [pl_mids[0], y_m_top + 0.06], color="0.45", lw=0.6, ls="--",
            zorder=3)
    ax.plot([x_bus, x_bus], [out_mids[-1], y_m_top + 0.06], color="black", lw=0.6, zorder=3)
    arrow(ax, x_bus, y_m_top + 0.06, x_bus, y_m_top)

    # Master table, QA and later thread
    n_det = U["master"]["detail"].count("\n") + 1
    h_m = 0.46 + 0.11 * max(0, n_det - 2)
    x_m = xs[3]
    w_m = x_bus + 0.14 - x_m
    box(ax, x_m, y_m_top - h_m, w_m, h_m, fc="0.80", lw=1.3)
    ax.text(x_m + w_m / 2, y_m_top - 0.13, U["master"]["title"], ha="center", va="center",
            fontsize=7.4, weight="bold", zorder=5)
    ax.text(x_m + w_m / 2, y_m_top - 0.31 - 0.055 * max(0, n_det - 2), U["master"]["detail"], ha="center", va="center",
            fontsize=fs_small, linespacing=1.25, zorder=5)
    y_q = y_m_top - h_m - 0.14 - 0.26
    w_q = (w_m - 0.1) / 2
    box(ax, x_m, y_q, w_q, 0.26)
    ax.text(x_m + w_q / 2, y_q + 0.13, wrap(U["master"]["qa"], w_q - 0.08, fs_small), ha="center",
            va="center", fontsize=fs_small, linespacing=1.1, zorder=5)
    box(ax, x_m + w_q + 0.1, y_q, w_q, 0.26, ls="--", ec="0.45")
    ax.text(x_m + w_q * 1.5 + 0.1, y_q + 0.13, wrap(U["master"]["later"], w_q - 0.08, fs_small),
            ha="center", va="center", fontsize=fs_small, linespacing=1.1, color="0.40", zorder=5)
    for xc, ls, c in [(x_m + w_q / 2, "-", "black"), (x_m + w_q * 1.5 + 0.1, "--", "0.45")]:
        arrow(ax, xc, y_m_top - h_m, xc, y_q + 0.26, ls=ls, color=c)

    # Worked example inset (bottom left, beside the master table)
    we = U["worked"]
    x_i, w_i = xs[0], xs[3] - 0.18 - xs[0]
    s_g = 0.2                                      # grid-sketch cell size (in)
    w_txt = w_i - 0.1 - (2 * s_g + 0.2)
    ex_body = wrap(f"{we['formula']}\n{we['example']}", w_txt, fs_small)
    h_i = 0.07 + 0.13 + text_height(ex_body, fs_small, 1.2) + 0.05
    y_i = y_m_top - h_i
    box(ax, x_i, y_i, w_i, h_i, fc="white", ec="0.45", lw=0.5)
    ax.text(x_i + 0.06, y_i + h_i - 0.06, we["title"], ha="left", va="top", fontsize=fs,
            weight="bold", zorder=5)
    ax.text(x_i + 0.06, y_i + h_i - 0.06 - 0.14, ex_body, ha="left", va="top",
            fontsize=fs_small, linespacing=1.2, zorder=5)
    # Tiny sketch: 2 x 2 model/block-group squares with a unit outline cutting across 3 of them
    gx, gy = x_i + w_i - 0.08 - 2 * s_g, y_i + (h_i - 2 * s_g) / 2
    zip_pts = [(gx + s_g * u, gy + s_g * v) for u, v in
               [(0.25, 0.2), (1.35, 0.15), (1.45, 0.7), (1.0, 0.95), (0.95, 1.45),
                (0.45, 1.3), (0.15, 0.8)]]
    clip = Polygon(zip_pts, closed=True, fc="none", ec="none", transform=ax.transData)
    ax.add_patch(clip)
    for (u, v), g in [((0, 0), "0.55"), ((1, 0), "0.75"), ((0, 1), "0.88"), ((1, 1), "0.88")]:
        ax.add_patch(Rectangle((gx + u * s_g, gy + v * s_g), s_g, s_g, fc="white", ec="0.5",
                               lw=0.4, zorder=5))
        shade = Rectangle((gx + u * s_g, gy + v * s_g), s_g, s_g, fc=g, ec="none", zorder=5.1)
        ax.add_patch(shade)
        shade.set_clip_path(clip)
    ax.add_patch(Polygon(zip_pts, closed=True, fc="none", ec="black", lw=0.8, zorder=5.2))

    # Legend (bottom left, under the inset)
    handles = [Line2D([], [], color="black", lw=0.8, label=U["legend"][0]),
               Line2D([], [], color="0.45", lw=0.8, ls="--", label=U["legend"][1]),
               Line2D([], [], color="0.35", lw=0.8, ls=(0, (1, 1.5)),
                      label=U["legend"][2])]
    leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(xs[0], y_i - 0.06),
                    bbox_transform=ax.transData, fontsize=fs_small, frameon=False,
                    handlelength=2.6, borderaxespad=0, labelspacing=0.35)

    fig.canvas.draw()
    leg_bottom = ax.transData.inverted().transform(
        leg.get_window_extent(fig.canvas.get_renderer()))[0, 1]
    y_low = min(y_q, leg_bottom)
    if U.get("caveats"):
        cv = wrap(U["caveats"], W - 0.2, fs_small)
        ax.text(xs[0], y_low - 0.1, cv, ha="left", va="top", fontsize=fs_small, color="0.25",
                linespacing=1.2, zorder=5)
        y_low -= 0.1 + text_height(cv, fs_small, 1.2)
    y_bot = y_low - 0.08
    ax.set_ylim(y_bot, H)
    fig.set_size_inches(W, H - y_bot)
    save(fig, U["stem"], ["pdf", "svg", "png"], dpi=600)


# ---------------------------------------------------------------------------
# Slide figure: 16:9, 3 stages, Okabe-Ito colour per family
# ---------------------------------------------------------------------------
def tint(hex_color, t=0.82):
    rgb = matplotlib.colors.to_rgb(hex_color)
    return tuple(c + (1 - c) * t for c in rgb)


def draw_slide(U):
    plt.rcParams.update({"font.family": FONT, "svg.fonttype": "none"})
    W, H = 40 / 3, 7.5
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    fs_body, fs_note = 13.5, 13
    ax.text(0.35, H - 0.38, U["slide_title"],
            fontsize=24, weight="bold", va="center", ha="left")

    cols = [(0.35, 3.3), (3.97, 4.45), (8.74, 2.9)]        # (x, width) per stage
    x_master, w_master = 11.95, 1.1 + 0.18
    headers = ["Data sources", U["slide_join_header"], "What we get"]
    y_hdr = H - 0.9
    for (x, w), hname in zip(cols, headers):
        ax.text(x + w / 2, y_hdr, hname, fontsize=17, weight="bold", ha="center", va="center",
                color="0.2")
        ax.plot([x, x + w], [y_hdr - 0.22, y_hdr - 0.22], color="0.6", lw=1.2)

    rows = [U["frame"]] + [d for d in U["datasets"] if d["status"] == "done"]
    h_row, g_row = U.get("slide_h_row", 0.49), 0.035
    y = y_hdr - 0.3
    mids = []
    for d in rows:
        y -= h_row
        col = FAMILIES[d["family"]][1]
        for k, (x, w) in enumerate(cols):
            box(ax, x, y, w, h_row, fc=tint(col), ec=col, lw=1.6, r=0.08)
        ax.add_patch(Rectangle((cols[0][0], y + 0.04), 0.1, h_row - 0.08, fc=col, ec="none",
                               zorder=4))
        (x0, w0), (x1, w1), (x2, w2) = cols
        ax.text(x0 + 0.2, y + h_row * 0.71, d["slide_source"], fontsize=14, weight="bold",
                va="center", zorder=5)
        ax.text(x0 + 0.2, y + h_row * 0.29, d["slide_detail"], fontsize=fs_note, va="center",
                color="0.25", zorder=5)
        if d.get("slide_note"):                    # main line + small grey second line
            ax.text(x1 + w1 / 2, y + h_row * 0.71, d["slide_join"], fontsize=fs_body,
                    va="center", ha="center", zorder=5)
            ax.text(x1 + w1 / 2, y + h_row * 0.29, d["slide_note"], fontsize=fs_note,
                    va="center", ha="center", color="0.3", zorder=5)
        else:
            ax.text(x1 + w1 / 2, y + h_row / 2, d["slide_join"], fontsize=fs_body, va="center",
                    ha="center", linespacing=1.05, zorder=5)
        ax.text(x2 + w2 / 2, y + h_row / 2, d["slide_out"], fontsize=fs_body, va="center",
                ha="center", linespacing=1.05, zorder=5)
        for (xa, wa), (xb, _) in [(cols[0], cols[1]), (cols[1], cols[2])]:
            arrow(ax, xa + wa + 0.04, y + h_row / 2, xb - 0.04, y + h_row / 2, color="0.3",
                  lw=1.6, head=8)
        mids.append(y + h_row / 2)
        y -= g_row
    y_rows_bottom = y + g_row

    # Master table box, fed by every output
    y_mt, y_mb = mids[0] + h_row / 2, y_rows_bottom
    box(ax, x_master, y_mb, w_master, y_mt - y_mb, fc="0.93", ec="0.2", lw=2.2, r=0.12)
    ax.text(x_master + w_master / 2, (y_mt + y_mb) / 2 + 0.55, U.get("slide_master_title", "Master\ntable"), fontsize=18,
            weight="bold", ha="center", va="center", linespacing=1.2, zorder=5)
    ax.text(x_master + w_master / 2, (y_mt + y_mb) / 2 - 0.45,
            U["slide_master_count"], fontsize=15, ha="center",
            va="center", linespacing=1.25, zorder=5)
    x_out_end = cols[2][0] + cols[2][1]
    for ym in mids:
        arrow(ax, x_out_end + 0.04, ym, x_master - 0.04, ym, color="0.3", lw=1.6, head=8)

    # Planned items grouped in one dashed box
    planned = [d for d in U["datasets"] if d["status"] == "planned"]
    y_pt, y_pb = y_rows_bottom - 0.2, 0.15
    h_p = min(y_pt - y_pb, 0.8)
    y_pb = y_pt - h_p
    x_p, w_p = cols[0][0], 5.2                     # one planned item: leave room for the key
    box(ax, x_p, y_pb, w_p, h_p, fc="white", ec="0.35", lw=1.8, ls="--", r=0.1)
    ax.text(x_p + 0.25, y_pb + h_p / 2, U.get("slide_planned_label", "Planned\nnext"), fontsize=16, weight="bold",
            color="0.3", va="center", ha="left", linespacing=1.15)
    x_items = [x_p + 1.6, x_p + 5.1]
    for i, d in enumerate(planned):
        xi = x_items[i // 2]
        yi = y_pb + h_p * (0.5 if len(planned) == 1 else 0.72 if i % 2 == 0 else 0.28)
        col = FAMILIES[d["family"]][1]
        ax.add_patch(Rectangle((xi, yi - 0.1), 0.2, 0.2, fc=tint(col, 0.3), ec=col, lw=1.2,
                               ls="--", zorder=4))
        ax.text(xi + 0.32, yi, d["slide_label"], fontsize=fs_note, color="0.25", va="center",
                zorder=5)

    # Colour key (data family), right of the planned box
    x_k = x_p + w_p + 0.45
    ax.text(x_k, y_pt, "Colour = data family", fontsize=13.5, weight="bold", va="top",
            color="0.2")
    used = {d["family"] for d in rows}
    for i, (label, col) in enumerate(
            (U.get("family_labels", {}).get(k, v[0]), v[1]) for k, v in FAMILIES.items() if k in used):
        xk = x_k + (i // 2) * 2.35
        yk = y_pt - 0.42 - (i % 2) * 0.28
        ax.add_patch(Rectangle((xk, yk - 0.09), 0.3, 0.18, fc=tint(col), ec=col, lw=1.6))
        ax.text(xk + 0.42, yk, label, fontsize=fs_note, va="center")
    if U.get("slide_caveat"):
        ax.text(x_k, y_pt - 1.2, wrap(U["slide_caveat"], W - x_k - 0.3, fs_note), fontsize=fs_note,
                va="top", color="0.25", linespacing=1.2)
    save(fig, U["slide_stem"], ["png", "svg"], dpi=150)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--unit", choices=sorted(UNITS), default="zip",
                        help="study unit to draw (default: zip)")
    unit = UNITS[parser.parse_args().unit]
    draw_paper(unit)
    draw_slide(unit)
