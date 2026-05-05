"""Render v2.0 charts for the lobby and deck — linear RV only.

Inputs:
  - specs/pillar_decomposition_snapshot.json (refresh via
    pipeline_and_tests/snapshot_pillar_decomposition.py against BigQuery)
  - data_generation/output/*.parquet (for the local-recomputed distribution
    and triage-efficiency charts that don't have a BQ counterpart)

Outputs to charts/:
  realization_headline.png    — stacked bar: ARR = realized + unrealized
  pillar_heatmap.png          — region × pillar decomposition (% of region's ARR)
  rv_distribution.png         — AVRI score distribution
  triage_efficiency.png       — % of $-at-risk surfaced vs % of accounts examined

Run from the project root:
    python charts/render_v2_charts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Path setup — portable, works from any CWD as long as this script lives
# at <repo>/charts/render_v2_charts.py
HERE      = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
OUT_DIR   = HERE
SNAPSHOT  = REPO_ROOT / "specs" / "pillar_decomposition_snapshot.json"

# Make `core` importable regardless of CWD
sys.path.insert(0, str(REPO_ROOT))
from core.scoring import load_config, score_population   # noqa: E402
from core.build_facts import build_facts                  # noqa: E402

if not SNAPSHOT.exists():
    sys.exit(
        f"ERROR: {SNAPSHOT} not found.\n"
        f"Run `python pipeline_and_tests/snapshot_pillar_decomposition.py` first "
        f"(requires BigQuery auth) to generate it."
    )

with open(SNAPSHOT) as f:
    SNAP = json.load(f)
H = SNAP["headline"]

# Local recomputation for charts that need per-account data
FACTS  = build_facts()
SCORED = score_population(FACTS, load_config())

# Style
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.facecolor":    "#fafafa",
    "figure.facecolor":  "white",
    "grid.color":        "#e2e8f0",
    "grid.linewidth":    0.6,
})

GREEN     = "#059669"
YELLOW    = "#d97706"
RED       = "#dc2626"
BLUE      = "#1e40af"
INK       = "#0f172a"
SLATE     = "#475569"
SLATE_LT  = "#94a3b8"

PILLAR_COLORS = {
    "cr":    "#7c3aed",
    "um":    "#0891b2",
    "dm":    "#65a30d",
    "th":    "#dc2626",
    "floor": "#92400e",
}
PILLAR_LABELS = {
    "cr":    "CR (Commit Realization)",
    "um":    "UM (Usage Momentum)",
    "dm":    "DM (Deployment Maturity)",
    "th":    "TH (Technical Health)",
    "floor": "Floor rule residual",
}


# =============================================================================
# CHART 1: Headline stacked bar
# =============================================================================
def render_headline():
    fig, ax = plt.subplots(figsize=(11, 3.0))

    realized   = H["total_rv"] / 1e6
    unrealized = H["total_unrealized"] / 1e6
    grace_arr  = (H["total_arr"] - H["scored_arr"]) / 1e6 if H["scored_arr"] != H["total_arr"] else 0
    total      = H["total_arr"] / 1e6

    bar_y, bar_h = 0.5, 0.5
    x_cursor = 0
    if realized > 0:
        ax.barh([bar_y], [realized], left=x_cursor, height=bar_h, color=GREEN, edgecolor="white")
        ax.text(x_cursor + realized/2, bar_y, f"Realized ${realized:.0f}M",
                ha="center", va="center", color="white", fontweight="bold", fontsize=14)
        x_cursor += realized
    if unrealized > 0:
        ax.barh([bar_y], [unrealized], left=x_cursor, height=bar_h, color=RED, edgecolor="white")
        ax.text(x_cursor + unrealized/2, bar_y, f"Unrealized ${unrealized:.0f}M",
                ha="center", va="center", color="white", fontweight="bold", fontsize=14)
        x_cursor += unrealized
    if grace_arr > 0:
        ax.barh([bar_y], [grace_arr], left=x_cursor, height=bar_h, color=SLATE_LT, edgecolor="white")
        ax.text(x_cursor + grace_arr/2, bar_y, f"In grace ${grace_arr:.0f}M",
                ha="center", va="center", color="white", fontweight="bold", fontsize=12)

    ax.set_xlim(0, total * 1.02)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("ARR ($M)")

    rate    = H["realization_rate"] * 100
    n_scored = int(H["n_scored"])
    n_grace  = int(H["n_grace"])
    title_parts = [
        rf"\${total:.0f}M total ARR",
        f"Realizing {rate:.0f}%",
        rf"\${unrealized:.0f}M unrealized",
        f"({n_scored} scored accounts · {n_grace} in grace)",
    ]
    ax.set_title("  ·  ".join(title_parts), fontsize=13, pad=18, color=INK)

    for x in [0, 100, 200, 300, total]:
        ax.axvline(x, color=SLATE_LT, linewidth=0.4, alpha=0.4, zorder=0)

    plt.tight_layout()
    plt.savefig(OUT_DIR / "realization_headline.png", dpi=140, bbox_inches="tight")
    plt.close()


# =============================================================================
# CHART 2: Pillar heatmap by region
# =============================================================================
def render_pillar_heatmap():
    rows = SNAP["by_region"]
    if not rows:
        return
    df = pd.DataFrame(rows)
    df = df.sort_values("book_arr", ascending=False)

    pillars = ["cr", "um", "dm", "th", "floor"]
    pillar_cols = [f"unrealized_{p}" for p in pillars]

    pct = df[pillar_cols].div(df["scored_arr"], axis=0) * 100
    pct.columns = pillars
    pct.index = df["region"].values

    fig, ax = plt.subplots(figsize=(10, max(3, 0.7 * len(df) + 1.5)))
    im = ax.imshow(pct.values, cmap="OrRd", aspect="auto",
                   vmin=0, vmax=max(pct.values.max(), 8))

    for i, region in enumerate(pct.index):
        for j, p in enumerate(pillars):
            dollars_m = df.iloc[i][f"unrealized_{p}"] / 1e6
            pct_val = pct.iloc[i, j]
            text_color = "white" if pct_val > pct.values.max() * 0.55 else INK
            label = f"${dollars_m:.1f}M\n{pct_val:.1f}%"
            ax.text(j, i, label, ha="center", va="center", fontsize=9.5,
                    color=text_color, fontweight="bold")

    ax.set_xticks(range(len(pillars)))
    ax.set_xticklabels([PILLAR_LABELS[p] for p in pillars], rotation=0, fontsize=10)
    ax.set_yticks(range(len(pct.index)))
    ax.set_yticklabels(
        [f"{r}\n${df.iloc[i].book_arr/1e6:.0f}M ARR" for i, r in enumerate(pct.index)],
        fontsize=10,
    )
    ax.xaxis.set_label_position("top")
    ax.xaxis.tick_top()

    ax.set_title(
        "Where ARR is being lost: pillar attribution by region\n"
        "(cell = $ unrealized · % of region's scored ARR)",
        fontsize=12, pad=20, color=INK,
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("% of region's ARR unrealized to this pillar", fontsize=9)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "pillar_heatmap.png", dpi=140, bbox_inches="tight")
    plt.close()


# =============================================================================
# CHART 3: AVRI distribution
# =============================================================================
def render_distribution():
    fig, ax = plt.subplots(figsize=(11, 4.0))
    in_scope = SCORED[SCORED["avri_score"].notna()]
    ax.hist(in_scope["avri_score"], bins=40, color=BLUE, alpha=0.85,
            edgecolor="white", linewidth=0.5)
    ax.axvspan(0,  50,  alpha=0.07, color=RED)
    ax.axvspan(50, 75,  alpha=0.07, color=YELLOW)
    ax.axvspan(75, 100, alpha=0.07, color=GREEN)
    ax.set_xlim(0, 100)
    ax.set_xlabel("AVRI score")
    ax.set_ylabel("# accounts")
    ax.set_title("AVRI distribution — bimodal by design.  Floor-rule pile at exactly 50.")

    cts = in_scope["avri_color"].value_counts()
    for i, (color_key, label, c_hex) in enumerate([
        ("red", "Red", RED), ("yellow", "Yellow", YELLOW), ("green", "Green", GREEN)
    ]):
        ax.text(0.02, 0.96 - i*0.07, f"{label:<7s} {cts.get(color_key, 0):>4d}",
                transform=ax.transAxes, color=c_hex, fontsize=11,
                fontweight="bold", va="top", family="monospace")

    plt.tight_layout()
    plt.savefig(OUT_DIR / "rv_distribution.png", dpi=140, bbox_inches="tight")
    plt.close()


# =============================================================================
# CHART 4: Triage efficiency
# =============================================================================
def render_triage():
    fig, ax = plt.subplots(figsize=(11, 5.0))

    df = SCORED[SCORED["avri_score"].notna()].copy()
    df["arr_at_risk"] = df["arr_dollars"] - df["rv_dollars"]
    n = len(df)
    total_risk = df["arr_at_risk"].sum()

    def cum_risk(metric_col, ascending=True):
        s = df.sort_values(metric_col, ascending=ascending)
        cum_count = np.arange(1, len(s)+1) / len(s) * 100
        cum_at_risk = s["arr_at_risk"].cumsum().values / total_risk * 100
        return cum_count, cum_at_risk

    df["chs_proxy"] = df["arr_dollars"] / df["arr_dollars"].max() * 60 + df["th_score"] * 0.4
    cc, ca_chs   = cum_risk("chs_proxy",  ascending=True)
    _,  ca_avri  = cum_risk("avri_score", ascending=True)
    _,  ca_rvgap = cum_risk("arr_at_risk", ascending=False)
    rand = df.sample(frac=1, random_state=42)
    ca_rand = rand["arr_at_risk"].cumsum().values / total_risk * 100

    ax.plot(cc, ca_chs,   color=SLATE, linewidth=2.0, label="Triage by lowest CHS-proxy")
    ax.plot(cc, ca_avri,  color=BLUE,  linewidth=2.0, label="Triage by lowest AVRI")
    ax.plot(cc, ca_rvgap, color=RED,   linewidth=2.4, label="Triage by largest unrealized $ (= ARR − RV)")
    ax.plot(cc, ca_rand,  color="#cbd5e1", linewidth=1.0, linestyle="--", label="Random baseline")

    ax.axvline(20, color="#94a3b8", linewidth=0.8, alpha=0.5)
    for ca, lbl, col in [(ca_chs, "CHS-proxy", SLATE), (ca_avri, "AVRI", BLUE), (ca_rvgap, "RV gap", RED)]:
        idx = int(0.20 * n) - 1
        ax.scatter(20, ca[idx], color=col, s=50, zorder=5)
        ax.annotate(f"{lbl}: {ca[idx]:.0f}%", xy=(20, ca[idx]),
                    xytext=(22, ca[idx] - 2),
                    fontsize=10, color=col, fontweight="bold")

    ax.set_xlabel("% of accounts examined (worst-first)")
    ax.set_ylabel("% of total unrealized $ surfaced")
    ax.set_title("Triage efficiency: which sort order finds the most $-at-risk in the first 20%?")
    ax.legend(loc="lower right", frameon=False, fontsize=10)
    ax.grid(alpha=0.4)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.text(20.5, 4, "20% triage budget", fontsize=8, color="#94a3b8", style="italic")

    plt.tight_layout()
    plt.savefig(OUT_DIR / "triage_efficiency.png", dpi=140, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    render_headline()
    print("✓ realization_headline.png")
    render_pillar_heatmap()
    print("✓ pillar_heatmap.png")
    render_distribution()
    print("✓ rv_distribution.png")
    render_triage()
    print("✓ triage_efficiency.png")
    print(f"\nAll charts written to: {OUT_DIR}")
