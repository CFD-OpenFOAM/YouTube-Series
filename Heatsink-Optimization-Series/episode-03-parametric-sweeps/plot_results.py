"""
plot_results.py — Summary charts from results.csv
==================================================
Generates PNG charts suitable for PPT assembly from the accumulated
results.csv in the results/ folder.

Charts produced:
  sweep_t_fin.png     Q and Q/V vs fin thickness (Sweep A)
  sweep_N_fin.png     Q and Q/V vs number of fins (Sweep B)
  sweep_H_fin.png     Q and Q/V vs fin height     (Sweep C)
  optimization.png    Q/V vs trial number (Bayesian opt progress)
  pareto.png          Q vs V scatter for all runs (coloured by Q/V)
  summary_table.png   Tabulated results as a matplotlib table image

Usage:
  conda activate heatsink-opt
  python plot_results.py

All charts are saved to results/charts/
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────
RESULTS_DIR  = Path(__file__).resolve().parent / "results"
RESULTS_CSV  = RESULTS_DIR / "results.csv"
CHARTS_DIR   = RESULTS_DIR / "charts"

# Baseline design (Iteration 2 with boundary layers)
BASELINE = {
    "t_fin_mm":  2.0,
    "N_fin":     5,
    "H_fin_mm":  20.0,
    "V_cm3":     22.8,
    "Q_W":       23.42,
    "Q_over_V":  1.03,
}

# ── Style ──────────────────────────────────────────────────────────────────────
STYLE = {
    "color_Q":        "#1f77b4",   # blue
    "color_QV":       "#d62728",   # red
    "color_baseline": "#2ca02c",   # green
    "color_ok":       "#1f77b4",
    "color_fail":     "#aec7e8",
    "figsize":        (9, 5.5),
    "dpi":            150,
}


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_results():
    """Load results.csv into a list of dicts (skips failed runs for plotting)."""
    if not RESULTS_CSV.exists():
        print(f"ERROR: {RESULTS_CSV} not found. Run some simulations first.")
        sys.exit(1)

    try:
        import pandas as pd
        df = pd.read_csv(RESULTS_CSV)
        return df
    except ImportError:
        pass

    # Manual CSV parse fallback (no pandas)
    import csv
    rows = []
    with open(RESULTS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Convert numeric fields
    numeric = ["t_fin_mm", "N_fin", "H_fin_mm", "V_cm3", "Q_W", "Q_over_V"]
    for row in rows:
        for col in numeric:
            try:
                row[col] = float(row[col])
            except (ValueError, KeyError):
                row[col] = float("nan")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dual_axis_sweep(ax1, xs, Qs, QVs, xlabel, title, x_is_int=False):
    """Plot Q (left axis, blue) and Q/V (right axis, red) on dual-axis chart."""
    ax2 = ax1.twinx()

    ax1.plot(xs, Qs,  "o-", color=STYLE["color_Q"],  lw=2, ms=8, label="Q [W]")
    ax2.plot(xs, QVs, "s--", color=STYLE["color_QV"], lw=2, ms=8, label="Q/V [W/cm³]")

    # Baseline reference lines
    ax1.axhline(BASELINE["Q_W"],       color=STYLE["color_Q"],
                lw=1, ls=":", alpha=0.6, label=f"Baseline Q = {BASELINE['Q_W']:.1f} W")
    ax2.axhline(BASELINE["Q_over_V"],  color=STYLE["color_QV"],
                lw=1, ls=":", alpha=0.6, label=f"Baseline Q/V = {BASELINE['Q_over_V']:.2f}")

    # Thermal requirement line
    ax1.axhline(23.4, color="grey", lw=1, ls="--", alpha=0.5, label="Q ≥ 23.4 W (min)")

    ax1.set_xlabel(xlabel, fontsize=12)
    ax1.set_ylabel("Q  [W]",        color=STYLE["color_Q"],  fontsize=12)
    ax2.set_ylabel("Q/V  [W/cm³]", color=STYLE["color_QV"], fontsize=12)
    ax1.tick_params(axis="y", colors=STYLE["color_Q"])
    ax2.tick_params(axis="y", colors=STYLE["color_QV"])

    if x_is_int:
        ax1.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

    ax1.set_title(title, fontsize=13, pad=10)
    ax1.grid(True, alpha=0.3)


# ─────────────────────────────────────────────────────────────────────────────
# Individual sweep charts
# ─────────────────────────────────────────────────────────────────────────────

def _get_ok_rows(df, variable, fixed_vals):
    """Filter DataFrame/list to OK rows matching fixed variable values."""
    try:
        # pandas path
        mask = df["status"] == "OK"
        for col, val in fixed_vals.items():
            mask &= (df[col] == val)
        sub = df[mask].copy()
        sub = sub.sort_values(variable)
        xs  = sub[variable].tolist()
        Qs  = sub["Q_W"].tolist()
        QVs = sub["Q_over_V"].tolist()
        return xs, Qs, QVs
    except (AttributeError, TypeError):
        # list-of-dicts path
        import math
        sub = [r for r in df
               if r["status"] == "OK"
               and all(abs(float(r[c]) - v) < 1e-9 for c, v in fixed_vals.items()
                       if not math.isnan(float(r.get(c, float("nan")))))]
        sub.sort(key=lambda r: float(r[variable]))
        return ([float(r[variable]) for r in sub],
                [float(r["Q_W"])     for r in sub],
                [float(r["Q_over_V"]) for r in sub])


def plot_sweep_t_fin(df) -> Path:
    xs, Qs, QVs = _get_ok_rows(df, "t_fin_mm",
                                 {"N_fin": 5.0, "H_fin_mm": 20.0})
    if not xs:
        print("  No t_fin sweep data found — skipping")
        return None

    fig, ax = plt.subplots(figsize=STYLE["figsize"])
    _dual_axis_sweep(ax, xs, Qs, QVs,
                     xlabel="Fin Thickness  t_fin  [mm]",
                     title="Sweep A: Effect of Fin Thickness  (N=5, H=20 mm)")
    fig.tight_layout()
    out = CHARTS_DIR / "sweep_t_fin.png"
    fig.savefig(out, dpi=STYLE["dpi"])
    plt.close(fig)
    print(f"  Saved {out.name}")
    return out


def plot_sweep_N_fin(df) -> Path:
    xs, Qs, QVs = _get_ok_rows(df, "N_fin",
                                 {"t_fin_mm": 2.0, "H_fin_mm": 20.0})
    if not xs:
        print("  No N_fin sweep data found — skipping")
        return None

    fig, ax = plt.subplots(figsize=STYLE["figsize"])
    _dual_axis_sweep(ax, xs, Qs, QVs,
                     xlabel="Number of Fins  N_fin",
                     title="Sweep B: Effect of Number of Fins  (t=2 mm, H=20 mm)",
                     x_is_int=True)
    fig.tight_layout()
    out = CHARTS_DIR / "sweep_N_fin.png"
    fig.savefig(out, dpi=STYLE["dpi"])
    plt.close(fig)
    print(f"  Saved {out.name}")
    return out


def plot_sweep_H_fin(df) -> Path:
    xs, Qs, QVs = _get_ok_rows(df, "H_fin_mm",
                                 {"t_fin_mm": 2.0, "N_fin": 5.0})
    if not xs:
        print("  No H_fin sweep data found — skipping")
        return None

    fig, ax = plt.subplots(figsize=STYLE["figsize"])
    _dual_axis_sweep(ax, xs, Qs, QVs,
                     xlabel="Fin Height  H_fin  [mm]",
                     title="Sweep C: Effect of Fin Height  (t=2 mm, N=5)")
    fig.tight_layout()
    out = CHARTS_DIR / "sweep_H_fin.png"
    fig.savefig(out, dpi=STYLE["dpi"])
    plt.close(fig)
    print(f"  Saved {out.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Scatter: Q vs V (all runs)
# ─────────────────────────────────────────────────────────────────────────────

def plot_pareto(df) -> Path:
    try:
        ok = df[df["status"] == "OK"].copy()
        V   = ok["V_cm3"].tolist()
        Q   = ok["Q_W"].tolist()
        QV  = ok["Q_over_V"].tolist()
    except (AttributeError, TypeError):
        ok  = [r for r in df if r["status"] == "OK"]
        V   = [float(r["V_cm3"])    for r in ok]
        Q   = [float(r["Q_W"])      for r in ok]
        QV  = [float(r["Q_over_V"]) for r in ok]

    if not V:
        print("  No OK runs for pareto plot — skipping")
        return None

    fig, ax = plt.subplots(figsize=STYLE["figsize"])
    sc = ax.scatter(V, Q, c=QV, cmap="plasma", s=80, edgecolors="k", linewidths=0.5, zorder=3)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("Q/V  [W/cm³]", fontsize=11)

    # Baseline marker
    ax.scatter([BASELINE["V_cm3"]], [BASELINE["Q_W"]],
               s=150, marker="*", color=STYLE["color_baseline"],
               zorder=5, label=f"Baseline ({BASELINE['Q_over_V']:.2f} W/cm³)")

    ax.axhline(23.4, color="grey", lw=1, ls="--", alpha=0.6, label="Q min = 23.4 W")

    ax.set_xlabel("Heatsink Volume  V  [cm³]", fontsize=12)
    ax.set_ylabel("Heat Dissipation  Q  [W]",  fontsize=12)
    ax.set_title("Design Space: Q vs V  (all runs, colour = Q/V)", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out = CHARTS_DIR / "pareto.png"
    fig.savefig(out, dpi=STYLE["dpi"])
    plt.close(fig)
    print(f"  Saved {out.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Summary table image
# ─────────────────────────────────────────────────────────────────────────────

def plot_summary_table(df) -> Path:
    try:
        rows = df[["run_id", "t_fin_mm", "N_fin", "H_fin_mm",
                    "V_cm3", "Q_W", "Q_over_V", "status"]].values.tolist()
    except (AttributeError, TypeError):
        cols = ["run_id", "t_fin_mm", "N_fin", "H_fin_mm",
                "V_cm3", "Q_W", "Q_over_V", "status"]
        rows = [[r.get(c, "") for c in cols] for r in df]

    if not rows:
        return None

    col_labels = ["Run", "t_fin\n[mm]", "N_fin", "H_fin\n[mm]",
                  "V\n[cm³]", "Q\n[W]", "Q/V\n[W/cm³]", "Status"]

    fig_h = max(3.0, 0.35 * (len(rows) + 2))
    fig, ax = plt.subplots(figsize=(12, fig_h))
    ax.axis("off")

    tbl = ax.table(
        cellText   = rows,
        colLabels  = col_labels,
        loc        = "center",
        cellLoc    = "center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.4)

    # Colour header row
    for j in range(len(col_labels)):
        tbl[(0, j)].set_facecolor("#2c3e50")
        tbl[(0, j)].set_text_props(color="white", weight="bold")

    # Colour rows by status
    for i, row in enumerate(rows):
        status = str(row[-1]).upper()
        bg = "#d5f5e3" if status == "OK" else "#fadbd8"
        for j in range(len(col_labels)):
            tbl[(i + 1, j)].set_facecolor(bg)

    ax.set_title("All Simulation Results", fontsize=14, pad=10)
    fig.tight_layout()
    out = CHARTS_DIR / "summary_table.png"
    fig.savefig(out, dpi=STYLE["dpi"], bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Optuna optimisation progress (if study DB exists)
# ─────────────────────────────────────────────────────────────────────────────

def plot_optimization(df) -> Path:
    study_path = RESULTS_DIR / "optuna_study.db"
    if not study_path.exists():
        print("  No optuna_study.db found — skipping optimization chart")
        return None

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("  optuna not installed — skipping optimization chart")
        return None

    study = optuna.load_study(
        study_name="heatsink_opt",
        storage=f"sqlite:///{study_path}",
    )
    trials = [t for t in study.trials
              if t.value is not None and t.value > -990]

    if not trials:
        return None

    ns   = [t.number for t in trials]
    vals = [t.value  for t in trials]
    best = [max(vals[:i+1]) for i in range(len(vals))]

    fig, ax = plt.subplots(figsize=STYLE["figsize"])
    ax.scatter(ns, vals, s=50, alpha=0.7, color=STYLE["color_Q"],    label="Trial Q/V")
    ax.plot(ns, best,    lw=2,             color=STYLE["color_QV"],   label="Best so far")
    ax.axhline(BASELINE["Q_over_V"], color=STYLE["color_baseline"],
               lw=1, ls="--", label=f"Baseline {BASELINE['Q_over_V']:.2f} W/cm³")

    ax.set_xlabel("Trial number",  fontsize=12)
    ax.set_ylabel("Q/V  [W/cm³]", fontsize=12)
    ax.set_title("Bayesian Optimisation Progress", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out = CHARTS_DIR / "optimization.png"
    fig.savefig(out, dpi=STYLE["dpi"])
    plt.close(fig)
    print(f"  Saved {out.name}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"Loading {RESULTS_CSV}")
    df = load_results()

    try:
        n = len(df)
    except TypeError:
        n = len(df)
    print(f"  {n} runs found")

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving charts to {CHARTS_DIR}\n")

    plot_sweep_t_fin(df)
    plot_sweep_N_fin(df)
    plot_sweep_H_fin(df)
    plot_pareto(df)
    plot_summary_table(df)
    plot_optimization(df)

    print("\nDone. Charts ready for PPT assembly.")
    print(f"Location: {CHARTS_DIR}")


if __name__ == "__main__":
    main()
