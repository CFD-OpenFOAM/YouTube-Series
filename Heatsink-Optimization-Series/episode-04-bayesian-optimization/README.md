# Episode 4 — Bayesian Optimization, Explained

📺 **Watch:** _coming soon_ · Part of the [Heatsink Optimization Series](../README.md)

Episode 3 swept each design knob **one at a time** — great for intuition, but a
full grid over (N, t, H) would be *days* of CFD. This episode is the **theory
break**: how do you find the best design in a handful of expensive evaluations
instead of hundreds? The answer is **Bayesian Optimization**.

There's no CFD here — just a tiny, illustrative notebook that builds the whole
idea from scratch with hand-drawn sketches.

---

## What's in here

```
episode-04-bayesian-optimization/
└── bayesian_optimization_explained.ipynb   ← the whiteboard walkthrough
```

Open **[bayesian_optimization_explained.ipynb](bayesian_optimization_explained.ipynb)**
— it renders on GitHub with all the sketches already embedded, so you can read it
without running anything.

---

## The idea in one breath

Our objective is **Q/V**, and each evaluation is an ~8-minute CFD run, so we can
only afford a handful. Bayesian Optimization makes every run count:

1. **Surrogate** — fit a cheap model that predicts Q/V *everywhere*, with an
   honest sense of its own uncertainty.
2. **Acquisition** — blend "predicted good" (exploit) with "still unknown"
   (explore); its peak is the single best design to try next.
3. **Loop** — run that design, add the result, refit, repeat. Each run sharpens
   the model and the optimum emerges fast.

The engine we actually use is **Optuna's TPE** sampler, which handles our mixed
integer/continuous search space (`N` ∈ 3–11, `t` ∈ 1–3 mm, `H` ∈ 10–30 mm)
cleanly.

---

## Run it yourself (optional)

The notebook only needs `numpy` + `matplotlib`:

```bash
conda activate heatsink-opt        # from Episode 3's environment.yml
jupyter lab bayesian_optimization_explained.ipynb
```

---

## What's next

➡️ **Episode 5** wires the theory up for real — the Optuna driver,
manufacturability pruning, a resumable SQLite study, and the full automated loop
chewing through CFD runs until it lands on the optimal design
(**N = 11, t ≈ 1.0 mm, H ≈ 23.7 mm → +87 % Q/V**).

Continue to [`episode-05-optimization-loop/`](../episode-05-optimization-loop/) _(coming soon)_.
