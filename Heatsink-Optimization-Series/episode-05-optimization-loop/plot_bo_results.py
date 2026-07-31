"""
Phase-2 BO post-processing plots.

Reads the Optuna study + results.csv and writes 5 figures to logs/plots/:

    bo_history.png            Q/V vs. trial number with running-best line
    bo_param_importance.png   fANOVA parameter importances
    bo_parallel.png           Parallel-coordinate plot over (t, N, H) -> Q/V
    bo_contour.png            2-D contour: N vs H, colored by Q/V
    bo_top9_grid.png          3x3 grid of T_midplane images for top 9 designs
"""

import sys
import os
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np
import pandas as pd

try:
        import optuna
except ImportError:
        print("ERROR: optuna not installed. Activate the heatsink-opt conda environment first.")
        sys.exit(1)

# Suppress Optuna warnings about manually-added seed trials
optuna.logging.set_verbosity(optuna.logging.WARNING)

RESULTS_DIR = Path(os.environ.get("HEATSINK_RESULTS_DIR", "/Volumes/Sid/heatsink-opt")).expanduser()
RESULTS_CSV = RESULTS_DIR / "results.csv"
DB_URI      = f"sqlite:///{RESULTS_DIR / 'optuna_study.db'}"
RUNS_DIR    = RESULTS_DIR / "runs"

# Brand-aligned colours
CB = "#2873ba"  # blue
CG = "#2ec866"  # green
CD = "#1a3a5c"  # dark navy
CR = "#d62728"  # red

# ─────────────────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────────────────
if not RESULTS_CSV.exists():
    print(f"ERROR: {RESULTS_CSV} not found. Run the optimization first.")
    sys.exit(1)

if not (RESULTS_DIR / "optuna_study.db").exists():
    print(f"ERROR: {RESULTS_DIR / 'optuna_study.db'} not found. Run the optimization first.")
    sys.exit(1)

OUT = Path(__file__).resolve().parent / "logs" / "plots"
OUT.mkdir(parents=True, exist_ok=True)

study = optuna.load_study(study_name="heatsink_opt", storage=DB_URI)
df    = pd.read_csv(RESULTS_CSV)
df    = df[df["status"] == "OK"].copy()
df["run_id_int"] = df["run_id"].astype(int)
df_p2 = df[df["run_id_int"] >= 18].sort_values("run_id_int").reset_index(drop=True)

print(f"Loaded study with {len(study.trials)} trials  ({len(df_p2)} Phase-2 OK rows)")

# ─────────────────────────────────────────────────────────────────────────────
# 1. BO history
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
trials = df_p2["run_id_int"].values
qov    = df_p2["Q_over_V"].values
best   = np.maximum.accumulate(qov)

ax.scatter(trials, qov, s=55, color=CB, edgecolor="white", linewidth=1.0,
           zorder=3, label="Trial Q/V")
ax.plot(trials, best, color=CR, lw=2.2, marker="o", ms=4, zorder=2,
        label="Running best")
ax.axhline(1.03, color="grey", ls="--", lw=1.2, label="Baseline N=5 (1.03 W/cm³)")
ax.set_xlabel("Run ID")
ax.set_ylabel(r"$Q/V$ [W/cm³]")
ax.set_title("Phase 2 — Bayesian Optimisation History", fontweight="bold", color=CD)
ax.grid(alpha=0.3)
ax.legend(loc="lower right")
fig.tight_layout()
fig.savefig(OUT / "bo_history.png", dpi=150)
plt.close(fig)
print("  Saved bo_history.png")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Parameter importance (fANOVA)
# ─────────────────────────────────────────────────────────────────────────────
try:
    # Exclude failed runs: STL-generation failures are stored as COMPLETE trials
    # with the sentinel value -999.0 (no CFD result). Including them wrecks the
    # fANOVA variance decomposition, so importance is computed on real runs only.
    good_trials = [
        t for t in study.trials
        if t.state == optuna.trial.TrialState.COMPLETE
        and t.value is not None and t.value > -100.0
    ]
    n_dropped = len(study.trials) - len(good_trials)
    print(f"  Param importance: using {len(good_trials)} real trials "
          f"(dropped {n_dropped} failed/pruned)")
    clean_study = optuna.create_study(direction="maximize")
    clean_study.add_trials(good_trials)
    imp = optuna.importance.get_param_importances(clean_study)
    fig, ax = plt.subplots(figsize=(8, 4))
    names  = list(imp.keys())
    values = [imp[k] for k in names]
    colors = [CB, CG, CD][:len(names)]
    bars   = ax.barh(names, values, color=colors, edgecolor=CD, linewidth=1.2)
    for b, v in zip(bars, values):
        ax.text(v + 0.005, b.get_y() + b.get_height()/2,
                f"{v:.3f}", va="center", fontsize=11, color=CD)
    ax.set_xlabel("fANOVA importance")
    ax.set_title("Parameter Importance — Phase 2 BO", fontweight="bold", color=CD)
    ax.set_xlim(0, max(values) * 1.20)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "bo_param_importance.png", dpi=150)
    plt.close(fig)
    print("  Saved bo_param_importance.png")
except Exception as e:
    print(f"  Skipped param importance: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Parallel-coordinate plot
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
cols = ["t_fin_mm", "N_fin", "H_fin_mm", "Q_over_V"]
data = df_p2[cols].astype(float).values
# Normalise each column to 0..1 for the axes
norm = (data - data.min(axis=0)) / (data.max(axis=0) - data.min(axis=0) + 1e-9)
x    = np.arange(len(cols))
cmap = plt.cm.viridis
qmin, qmax = data[:, -1].min(), data[:, -1].max()
for i, row in enumerate(norm):
    c = cmap((data[i, -1] - qmin) / (qmax - qmin + 1e-9))
    ax.plot(x, row, color=c, alpha=0.65, lw=1.4)
ax.set_xticks(x)
ax.set_xticklabels(["t (mm)", "N", "H (mm)", r"$Q/V$"], fontsize=11)
ax.set_yticks([])
for xi in x:
    ax.axvline(xi, color="grey", lw=0.6, alpha=0.4)
# Annotate min/max of each axis
for j, name in enumerate(cols):
    ax.text(j, -0.04, f"{data[:, j].min():.2f}", ha="center", va="top",
            fontsize=8, color="grey")
    ax.text(j, 1.04, f"{data[:, j].max():.2f}", ha="center", va="bottom",
            fontsize=8, color="grey")
sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(qmin, qmax))
cbar = fig.colorbar(sm, ax=ax, pad=0.02)
cbar.set_label(r"$Q/V$ [W/cm³]")
ax.set_title("Phase 2 BO — Parallel Coordinates", fontweight="bold", color=CD)
ax.set_ylim(-0.08, 1.08)
fig.tight_layout()
fig.savefig(OUT / "bo_parallel.png", dpi=150)
plt.close(fig)
print("  Saved bo_parallel.png")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Contour: N vs H, colored by Q/V
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5.5))
sc = ax.scatter(df_p2["N_fin"], df_p2["H_fin_mm"],
                c=df_p2["Q_over_V"], cmap="viridis",
                s=140, edgecolor="white", linewidth=1.2, zorder=3)
# Highlight top 3
top3 = df_p2.nlargest(3, "Q_over_V")
ax.scatter(top3["N_fin"], top3["H_fin_mm"],
           s=400, facecolor="none", edgecolor=CR, linewidth=2.2, zorder=4,
           label="Top 3 designs")
for _, row in top3.iterrows():
    ax.annotate(f"run_{int(row['run_id_int']):03d}",
                xy=(row["N_fin"], row["H_fin_mm"]),
                xytext=(8, 8), textcoords="offset points",
                fontsize=9, color=CD, fontweight="bold")
ax.set_xlabel("Number of fins  N")
ax.set_ylabel("Fin height  H [mm]")
ax.set_title("BO design space — colored by Q/V", fontweight="bold", color=CD)
cbar = fig.colorbar(sc, ax=ax)
cbar.set_label(r"$Q/V$ [W/cm³]")
ax.grid(alpha=0.3)
ax.legend(loc="lower left")
fig.tight_layout()
fig.savefig(OUT / "bo_contour.png", dpi=150)
plt.close(fig)
print("  Saved bo_contour.png")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Top 9 image grid (T_midplane)
# ─────────────────────────────────────────────────────────────────────────────
top9 = df_p2.nlargest(9, "Q_over_V").reset_index(drop=True)
fig, axes = plt.subplots(3, 3, figsize=(13, 9))
for ax, (_, row) in zip(axes.flat, top9.iterrows()):
    rid = int(row["run_id_int"])
    img = RUNS_DIR / f"run_{rid:03d}" / "images" / "T_midplane.png"
    if img.exists():
        ax.imshow(mpimg.imread(str(img)))
    else:
        ax.text(0.5, 0.5, "image missing", ha="center", va="center",
                transform=ax.transAxes, color="grey")
    ax.set_title(
        f"run_{rid:03d}  Q/V = {row['Q_over_V']:.3f}\n"
        f"N={int(row['N_fin'])}, t={row['t_fin_mm']:.2f}mm, H={row['H_fin_mm']:.1f}mm",
        fontsize=10, color=CD,
    )
    ax.axis("off")
fig.suptitle("Top 9 BO designs — mid-plane temperature field",
             fontsize=15, fontweight="bold", color=CD, y=0.995)
fig.tight_layout()
fig.savefig(OUT / "bo_top9_grid.png", dpi=130)
plt.close(fig)
print("  Saved bo_top9_grid.png")

print(f"\nAll plots in {OUT}")
