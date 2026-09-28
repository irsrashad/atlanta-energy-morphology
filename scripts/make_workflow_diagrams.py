"""Render the ZIP-level data-preparation workflow as a paper figure and a slide figure.

Run from the repo root:
    .venv/Scripts/python.exe scripts/make_workflow_diagrams.py

Outputs (in figures/):
    workflow_paper.pdf / .svg / .png (600 dpi)  - grayscale-safe, full page width
    workflow_slide.png / .svg                   - 16:9, Okabe-Ito colours

Both figures are drawn from the same DATASETS spec below, so update it when pending data is added.
Both use Montserrat, loaded from figures/fonts/ (SIL OFL, see OFL.txt there).
Counts come from notebooks/01_data_preparation.ipynb and data/interim/zipcode_joined.gpkg.
"""
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
# Shared data spec (single source of truth)
# ---------------------------------------------------------------------------
N_ZIPS, N_VARS = 190, 443

STUDY_FRAME = {
    "name": "Study frame",
    "source": "TIGER ZCTA 2010 + prior ZIP-level energy model",
    "native": "1,470 rows = 735 ZCTAs × 2 cluster copies",
    "preprocessing": "Keep ZIPs with all 3 predictions > 0; key ZIP5 (text); "
                     "project to EPSG:2240 (US ft); zip_area_sqft",
    "frame": f"ZIP study frame\nn = {N_ZIPS} ZIPs (63 HIGH, 127 LOW)\nEPSG:2240 (US ft)",
    "outputs": "energy_actual_kwh + 3 model predictions",
    "family": "energy",
    "slide_source": "ZIP areas + energy model",
    "slide_detail": "735 ZCTAs (TIGER 2010)",
    "slide_join": "Keep ZIPs with all 3 predictions > 0",
    "slide_out": "Energy use + 3 predictions",
}

DATASETS = [
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
     "native": "3.98\u00a0M footprints",
     "preprocessing": "Area (sq ft); representative point",
     "join": "Point in ZIP (1.85\u00a0M assigned)",
     "aggregation": "Count, sum, mean, max area; coverage = footprint sq\u00a0ft / ZIP sq\u00a0ft",
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
    # Planned (drawn dashed)
    {"name": "Remote sensing", "source": "NDVI, impervious, LST, LAI",
     "method": "Zonal mean over each ZIP", "status": "planned", "family": "env",
     "slide_label": "Satellite rasters → zonal mean"},
    {"name": "Roads (TIGER 2012)", "source": "Primary/secondary roads",
     "method": "Road length / ZIP area", "status": "planned", "family": "transport",
     "slide_label": "Major roads → length per area"},
    {"name": "MARTA bus", "source": "MARTA open data",
     "method": "Method to be decided", "status": "planned", "family": "transport",
     "slide_label": "MARTA bus"},
    {"name": "Tree canopy", "source": "NLCD",
     "method": "Method to be decided", "status": "planned", "family": "env",
     "slide_label": "Tree canopy (NLCD)"},
]

MASTER = {
    "title": "Master ZIP table",
    "detail": f"{N_ZIPS} ZIPs × {N_VARS} variables\nzipcode_joined.gpkg",
    "qa": "QA checks + data dictionary",
    "later": "Later: ZIP → tract thread",
}

# Worked example of the area-weighted mean (paper inset)
WORKED_EXAMPLE = {
    "title": "Area-weighted mean (walkability, air quality)",
    "formula": "ZIP value = ∑(value × overlap area) / ∑(overlap area)",
    "example": "e.g. pieces covering 60% / 30% / 10% of a ZIP with scores 15 / 10 / 5 "
               "→ 0.6·15 + 0.3·10 + 0.1·5 = 12.5",
}

STAGES = ["Input data", "Preprocessing", "Spatial join", "Aggregation to ZIP", "Output variables"]

# Okabe-Ito palette, one colour per data family (slide only)
FAMILIES = {
    "energy": ("Energy / base", "#D55E00"),
    "transport": ("Transport", "#0072B2"),
    "built": ("Built form", "#E69F00"),
    "socio": ("Socioeconomic", "#CC79A7"),
    "landuse": ("Land use", "#009E73"),
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
def draw_paper():
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
            for i, name in enumerate(STAGES)]
    h_hdr = max(0.28, max(text_height(t, fs_hdr, 1.1) for t in hdrs) + 0.1)
    y_hdr = H - 0.08 - h_hdr
    for i, t in enumerate(hdrs):
        box(ax, xs[i], y_hdr, widths[i], h_hdr, lw=0.8, **stage_style[i])
        ax.text(xs[i] + widths[i] / 2, y_hdr + h_hdr / 2, t, ha="center", va="center",
                fontsize=fs_hdr, weight="bold", linespacing=1.1, zorder=5,
                bbox=dict(fc="white", ec="none", pad=0.6) if stage_style[i].get("hatch") else None)

    # Study frame band
    sf = STUDY_FRAME
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
    done = [d for d in DATASETS if d["status"] == "done"]
    planned = [d for d in DATASETS if d["status"] == "planned"]
    h_row_min, h_pl, g_row = 0.52, 0.34, 0.075
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

    # "Every row joins to the ZIP study frame": dotted spine down the join column
    ax.plot([frame_x, frame_x], [y_sf, y_last_done], color="0.35", lw=0.8, ls=(0, (1, 1.5)),
            zorder=1)
    ax.text(frame_x + 0.04, y_sf - 0.1, "joined to ZIP frame", fontsize=fs_small, style="italic",
            color="0.3", ha="left", va="center", zorder=5,
            bbox=dict(fc="0.97", ec="none", pad=0.3))

    # Planned rows
    y -= 0.12
    ax.text(xs[0], y, "Planned", fontsize=fs, weight="bold", color="0.40",
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
        cell(4, y, h_pl, "to be added", planned=True)
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
    h_m = 0.46
    x_m = xs[3]
    w_m = x_bus + 0.14 - x_m
    box(ax, x_m, y_m_top - h_m, w_m, h_m, fc="0.80", lw=1.3)
    ax.text(x_m + w_m / 2, y_m_top - 0.13, MASTER["title"], ha="center", va="center",
            fontsize=7.4, weight="bold", zorder=5)
    ax.text(x_m + w_m / 2, y_m_top - 0.31, MASTER["detail"], ha="center", va="center",
            fontsize=fs_small, linespacing=1.25, zorder=5)
    y_q = y_m_top - h_m - 0.14 - 0.26
    w_q = (w_m - 0.1) / 2
    box(ax, x_m, y_q, w_q, 0.26)
    ax.text(x_m + w_q / 2, y_q + 0.13, wrap(MASTER["qa"], w_q - 0.08, fs_small), ha="center",
            va="center", fontsize=fs_small, linespacing=1.1, zorder=5)
    box(ax, x_m + w_q + 0.1, y_q, w_q, 0.26, ls="--", ec="0.45")
    ax.text(x_m + w_q * 1.5 + 0.1, y_q + 0.13, wrap(MASTER["later"], w_q - 0.08, fs_small),
            ha="center", va="center", fontsize=fs_small, linespacing=1.1, color="0.40", zorder=5)
    for xc, ls, c in [(x_m + w_q / 2, "-", "black"), (x_m + w_q * 1.5 + 0.1, "--", "0.45")]:
        arrow(ax, xc, y_m_top - h_m, xc, y_q + 0.26, ls=ls, color=c)

    # Worked example inset (bottom left, beside the master table)
    we = WORKED_EXAMPLE
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
    # Tiny sketch: 2 x 2 model/block-group squares with a ZIP outline cutting across 3 of them
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
    handles = [Line2D([], [], color="black", lw=0.8, label="solid: joined to ZIP table"),
               Line2D([], [], color="0.45", lw=0.8, ls="--", label="dashed: planned"),
               Line2D([], [], color="0.35", lw=0.8, ls=(0, (1, 1.5)),
                      label="dotted: ZIP study frame (n = 190) used by every join")]
    leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(xs[0], y_i - 0.06),
                    bbox_transform=ax.transData, fontsize=fs_small, frameon=False,
                    handlelength=2.6, borderaxespad=0, labelspacing=0.35)

    fig.canvas.draw()
    leg_bottom = ax.transData.inverted().transform(
        leg.get_window_extent(fig.canvas.get_renderer()))[0, 1]
    y_bot = min(y_q, leg_bottom) - 0.08
    ax.set_ylim(y_bot, H)
    fig.set_size_inches(W, H - y_bot)
    save(fig, "workflow_paper", ["pdf", "svg", "png"], dpi=600)


# ---------------------------------------------------------------------------
# Slide figure: 16:9, 3 stages, Okabe-Ito colour per family
# ---------------------------------------------------------------------------
def tint(hex_color, t=0.82):
    rgb = matplotlib.colors.to_rgb(hex_color)
    return tuple(c + (1 - c) * t for c in rgb)


def draw_slide():
    plt.rcParams.update({"font.family": FONT, "svg.fonttype": "none"})
    W, H = 40 / 3, 7.5
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    fs_body, fs_note = 13.5, 13
    ax.text(0.35, H - 0.38, f"ZIP-level data pipeline: {N_ZIPS} Atlanta-area ZIPs",
            fontsize=24, weight="bold", va="center", ha="left")

    cols = [(0.35, 3.3), (3.97, 4.45), (8.74, 2.9)]        # (x, width) per stage
    x_master, w_master = 11.95, 1.1 + 0.18
    headers = ["Data sources", "How it's joined to ZIPs", "What we get"]
    y_hdr = H - 0.9
    for (x, w), hname in zip(cols, headers):
        ax.text(x + w / 2, y_hdr, hname, fontsize=17, weight="bold", ha="center", va="center",
                color="0.2")
        ax.plot([x, x + w], [y_hdr - 0.22, y_hdr - 0.22], color="0.6", lw=1.2)

    rows = [STUDY_FRAME] + [d for d in DATASETS if d["status"] == "done"]
    h_row, g_row = 0.58, 0.05
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
    ax.text(x_master + w_master / 2, (y_mt + y_mb) / 2 + 0.55, "Master\ntable", fontsize=18,
            weight="bold", ha="center", va="center", linespacing=1.2, zorder=5)
    ax.text(x_master + w_master / 2, (y_mt + y_mb) / 2 - 0.45,
            f"{N_ZIPS} ZIPs\n×\n{N_VARS}\nvariables", fontsize=15, ha="center",
            va="center", linespacing=1.25, zorder=5)
    x_out_end = cols[2][0] + cols[2][1]
    for ym in mids:
        arrow(ax, x_out_end + 0.04, ym, x_master - 0.04, ym, color="0.3", lw=1.6, head=8)

    # Planned items grouped in one dashed box
    planned = [d for d in DATASETS if d["status"] == "planned"]
    y_pt, y_pb = y_rows_bottom - 0.2, 0.15
    h_p = y_pt - y_pb
    x_p, w_p = cols[0][0], cols[1][0] + cols[1][1] - cols[0][0]
    box(ax, x_p, y_pb, w_p, h_p, fc="white", ec="0.35", lw=1.8, ls="--", r=0.1)
    ax.text(x_p + 0.25, y_pb + h_p / 2, "Planned\nnext", fontsize=16, weight="bold",
            color="0.3", va="center", ha="left", linespacing=1.15)
    x_items = [x_p + 1.6, x_p + 5.1]
    for i, d in enumerate(planned):
        xi = x_items[i // 2]
        yi = y_pb + h_p * (0.72 if i % 2 == 0 else 0.28)
        col = FAMILIES[d["family"]][1]
        ax.add_patch(Rectangle((xi, yi - 0.1), 0.2, 0.2, fc=tint(col, 0.3), ec=col, lw=1.2,
                               ls="--", zorder=4))
        ax.text(xi + 0.32, yi, d["slide_label"], fontsize=fs_note, color="0.25", va="center",
                zorder=5)

    # Colour key (data family), right of the planned box
    x_k = cols[2][0]
    ax.text(x_k, y_pt, "Colour = data family", fontsize=13.5, weight="bold", va="top",
            color="0.2")
    for i, (label, col) in enumerate(FAMILIES.values()):
        xk = x_k + (i // 3) * 2.2
        yk = y_pt - 0.42 - (i % 3) * 0.26
        ax.add_patch(Rectangle((xk, yk - 0.09), 0.3, 0.18, fc=tint(col), ec=col, lw=1.6))
        ax.text(xk + 0.42, yk, label, fontsize=fs_note, va="center")
    save(fig, "workflow_slide", ["png", "svg"], dpi=150)


if __name__ == "__main__":
    draw_paper()
    draw_slide()
