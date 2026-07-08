<!-- Heatsink Optimization Series — public code companion -->
<h1 align="center">🔥 Heatsink Optimization Series</h1>

<p align="center">
  <b>Wrapping OpenFOAM in Python and letting a Bayesian optimizer redesign a heatsink — from scratch.</b><br>
  Same footprint. Same fan. <b>More than double the cooling.</b>
</p>

<p align="center">
  <img src="assets/heatsink-evolution.gif" alt="Heatsink design evolving from the baseline to the optimized design" width="90%">
</p>

<p align="center">
  <a href="https://www.youtube.com/@CFD_OpenFOAM"><img src="https://img.shields.io/badge/YouTube-CFD__OpenFOAM-red?logo=youtube" alt="YouTube"></a>
  <img src="https://img.shields.io/badge/OpenFOAM-2506-blue" alt="OpenFOAM 2506">
  <img src="https://img.shields.io/badge/Optuna-TPE-purple" alt="Optuna">
  <img src="https://img.shields.io/badge/Python-3.11-yellow?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0">
</p>

---

## The one-line story

We took an ordinary aluminium plate-fin heatsink and let an algorithm search the
design space — running ~30 CFD simulations to find the geometry that dissipates
the most heat **per unit volume** (Q/V). The winner: **11 razor-thin fins**.

| Metric | Baseline | Optimized | Change |
|--------|:--------:|:---------:|:------:|
| Fins × thickness | 5 × 2.0 mm | 11 × 1.01 mm | — |
| Specific heat rate **Q/V** | 1.08 W/cm³ | **2.02 W/cm³** | **+87%** ¹ |
| Thermal resistance **R_th** | 2.14 K/W | **0.53 K/W** | **−75%** |

<sub>¹ +87% is the high-fidelity, boundary-layer-resolved validated figure (Q/V 1.08 → 2.02). The fast optimization search estimated +106% (Q/V ≈ 2.22). See [Episode 6](episode-06-cht-validation/) for the validation — and the conjugate-heat-transfer deep-dive.</sub>

<p align="center">
  <img src="assets/baseline-vs-optimal.gif" alt="Side-by-side tour of the baseline vs the optimized heatsink" width="90%">
</p>

---

## 📺 The Series — episode → code map

Code for each episode is published **when that episode goes live**. Episode 1 is
pure motivation, so it has no code.

| # | Episode | Watch | Code | Status |
|:-:|---------|:-----:|------|:------:|
| 1 | **Why Optimize a Heatsink?** | _coming soon_ | [`episode-01-why-optimize/`](episode-01-why-optimize/) — planner &amp; background | ✅ |
| 2 | **The Baseline: One Case, End to End** | _coming soon_ | [`episode-02-baseline/`](episode-02-baseline/) | ✅ |
| 3 | **Automating CFD: Parametric Sweeps** | _coming soon_ | [`episode-03-parametric-sweeps/`](episode-03-parametric-sweeps/) | ✅ |
| 4 | **Bayesian Optimization, Explained** | _coming soon_ | [episode-04-bayesian-optimization/](episode-04-bayesian-optimization/) | ✅ |
| 5 | **Running the Optimization Loop** | _coming soon_ | [`episode-05-optimization-loop/`](episode-05-optimization-loop/) | ✅ |
| 6 | **The Optimal Design & CHT Validation** | _coming soon_ | [`episode-06-cht-validation/`](episode-06-cht-validation/) | ✅ |
| 7 | **Full Code Walkthrough & GitHub** | _coming soon_ | [this repo](#reproduce-the-whole-study) | ✅ |

> ⏳ = airing soon · ✅ = code available · 🔜 = drops with its episode

**New here?** Watch Episode 1 for the *why*, then read the episode folders in
order — or jump straight to [reproducing the whole study](#reproduce-the-whole-study).

---

## The design problem

Maximise the **specific heat dissipation** Q/V [W/cm³] of a forced-convection
plate-fin heatsink — i.e. get the most cooling out of the least metal.

| Variable | Symbol | Range |
|----------|:------:|-------|
| Number of fins | N | 3 – 11 |
| Fin thickness | t | 1.0 – 3.0 mm |
| Fin height | H | 10 – 30 mm |

**Fixed:** 60 × 60 mm footprint · 3 mm base · 3 m/s inlet · aluminium.

The three knobs fight each other — more fins add surface area but choke the
airflow; thinner fins pack in more but conduct less; taller fins help with
diminishing returns. Finding the sweet spot is exactly what the optimizer is for.

---

## How it works (the pipeline)

```
   Python  ──▶  parametric STL  ──▶  OpenFOAM (mesh + solve)  ──▶  extract Q
      ▲                                                              │
      └──────────────  Optuna (Bayesian optimization)  ◀────────────┘
```

1. A Python script turns three numbers (N, t, H) into a heatsink STL — **no CAD**.
2. OpenFOAM meshes it (`snappyHexMesh`) and solves the buoyant flow (`buoyantSimpleFoam`).
3. The heat dissipated Q is extracted and fed back to **Optuna**, which proposes
   the next design to try — learning as it goes.
4. The winner is re-validated at **high fidelity** (fine mesh + boundary layers),
   with **conjugate heat transfer** (`chtMultiRegionSimpleFoam`) as the deeper
   physical check.

---

## Repository layout

```
Heatsink-Optimization-Series/
├── README.md                       ← you are here
├── assets/                         ← GIFs / images for this page
├── episode-01-why-optimize/        ← Ep 1: planner &amp; background (the why + the plan)
├── episode-02-baseline/            ← Ep 2: one full OpenFOAM case, end to end
│   ├── case/                       #   the OpenFOAM case (0/, constant/, system/)
│   └── scripts/                    #   parametric STL generator
├── episode-03-parametric-sweeps/   ← Ep 3: Python-driven CFD sweeps
├── episode-04-bayesian-optimization/  ← Ep 4: BO theory (illustrative notebook)
├── episode-05-optimization-loop/   ← Ep 5: the Optuna optimization loop
└── episode-06-cht-validation/      ← Ep 6: high-fidelity + CHT validation
```

> Episode 7 (the walkthrough) has no folder of its own — its "code" is this whole
> repo. The [runbook](#reproduce-the-whole-study) below ties the six code episodes
> together.

---

## Prerequisites

- **OpenFOAM 2506** (Linux, or a VM on macOS/Windows)
- **Python 3.11** with `numpy-stl`, `optuna`, `pyvista`, `pandas`, `matplotlib`
- **ParaView** (optional, for the renders)

Each episode folder has its own README with the exact steps to run it.

---

## Reproduce the whole study

The six code episodes are the study, start to finish. Each folder is
self-contained, but here's the full arc in one place — the same path the
optimizer took from a blank slate to the validated optimum.

```bash
# 0. Clone and enter the series folder
git clone https://github.com/CFD-OpenFOAM/YouTube-Series.git
cd YouTube-Series/Heatsink-Optimization-Series

# 1. One environment for everything (identical across episodes)
conda env create -f episode-05-optimization-loop/environment.yml
conda activate heatsink-opt

# 2. Baseline — one case, end to end  (Episode 2)
cd episode-02-baseline/case && ./Allrun && cd ../..
#    → the N=5, 2 mm reference design: Q/V ≈ 1.08 W/cm³

# 3. Parametric sweeps — vary one knob at a time  (Episode 3)
cd episode-03-parametric-sweeps
python optimize_heatsink.py check                       # verify VM + paths first
python optimize_heatsink.py sweep --variable N_fin --values 3 5 7 9 11
python optimize_heatsink.py sweep --variable t_fin --values 0.001 0.0015 0.002 0.0025 0.003
python optimize_heatsink.py sweep --variable H_fin --values 0.010 0.015 0.020 0.025 0.030
python plot_results.py && cd ..

# 4. Bayesian optimization — let Optuna search  (Episode 5)
cd episode-05-optimization-loop
python optimize_heatsink.py optimize --trials 20        # seeds from the sweep CSV
python plot_bo_results.py && cd ..
#    → the winner: N=11, t=1.01 mm, H=23.7 mm, Q/V ≈ 2.22 W/cm³ (estimate)

# 5. Validate the optimum — fine mesh + boundary layers  (Episode 6)
cd episode-06-cht-validation
python optimize_heatsink.py validate                    # defaults to the optimum
#    → trustworthy Q = 53.70 W, Q/V = 2.02 W/cm³  (+87% vs baseline)
```

> ⚙️ Every driver has a rig-specific config block (VM name, paths, results dir) —
> see the **⚙️ Configuration** table in each episode README before running. If you
> run OpenFOAM natively instead of in a VM, only `run_openfoam.sh` changes.

**Rough budget:** ~30 CFD evaluations total. Sweeps + optimization runs are ~8 min
each on the coarse mesh; the single high-fidelity validation run is ~70 min. Plan
for a few hours of mostly-unattended compute.

---

## Lessons & what's next

A few things worth taking away from this study:

- **Match the model to the question.** A fast, approximate CFD model (isothermal
  wall, coarse mesh) is the *right* tool for *ranking* hundreds of designs; you
  only need the expensive, accurate model for the *one* final number. Using the
  cheap model everywhere would be dishonest; using the accurate one everywhere
  would take weeks. Splitting the job is the key idea.
- **The ranking held; the magnitude moved.** Validation trimmed the headline gain
  from an estimated +106% to a solid **+87%** — the fast model was *optimistic*,
  not *wrong*. Every conclusion of the search survived high-fidelity physics.
- **Optimize the right objective.** We maximised **Q/V** (cooling per unit metal),
  not raw Q — which is why the winner is *thin fins*, not *big fins*.
- **Prune before you pay.** Rejecting un-manufacturable designs *before* the 8-min
  CFD call is what makes a real-CFD optimization loop tractable.
- **Make it resumable.** A SQLite-backed Optuna study survives the inevitable
  overnight crash and picks up exactly where it left off.

**Extend it yourself** — the loop is geometry-agnostic:

- Point `generate_heatsink_stl.py` at a **different geometry** (pin fins, offset
  strips) and the whole pipeline still applies.
- Add a **second objective** (pressure drop / fan power) and switch Optuna to
  **multi-objective** for a Pareto front.
- **Finish the CHT post-processing** (see Episode 6's honest note) to report true
  `T_max` and thermal resistance from the coupled solid+fluid solve.
- Swap `multipass exec` for a **native OpenFOAM** call to run the loop on a
  cluster.

---

## Citation

If this repo helps your work, please cite it — see [`CITATION.cff`](CITATION.cff).

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE). Use it, fork it, point it at your own geometry.

---

<p align="center"><sub>Built for <a href="https://www.youtube.com/@CFD_OpenFOAM">@CFD_OpenFOAM</a> · OpenFOAM · Optuna · Python · ParaView</sub></p>
