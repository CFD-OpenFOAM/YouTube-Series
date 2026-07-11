# Episode 2 — The Baseline: One Case, End to End

📺 **Watch:** https://youtu.be/NMkb8JBXnU8 · Part of the [Heatsink Optimization Series](../README.md)

Before you can optimize anything, you need a **number to beat**. This episode
builds that number: a single 5-fin aluminium heatsink, simulated properly in
OpenFOAM from a blank case to a real result — STL → mesh → physics → solve.

---

## The baseline design

| Parameter | Value |
|-----------|-------|
| Footprint (L × W) | 60 × 60 mm |
| Base thickness | 3 mm |
| Number of fins (N) | 5 |
| Fin thickness (t) | 2.0 mm |
| Fin height (H) | 20 mm |
| Inlet velocity | 3 m/s |
| Wall temperature | 350 K (heat source) |
| Ambient | 300 K |

## The result — the number to beat

| Metric | Value |
|--------|-------|
| Heat dissipated **Q** | ≈ 24.6 W |
| Specific heat rate **Q/V** | **1.08 W/cm³** |
| Thermal resistance **R_th** | 2.03 K/W |

Everything in the rest of the series is about beating **Q/V = 1.08**.

---

## What's in here

```
episode-02-baseline/
├── case/                       ← the OpenFOAM case (surface-refined mesh)
│   ├── 0/                      #   initial & boundary conditions (U, T, p, p_rgh, alphat)
│   ├── constant/               #   physics + geometry (thermophysical, turbulence, STL)
│   ├── system/                 #   blockMesh, snappyHexMesh, solver settings
│   ├── Allrun                  #   one-shot mesh + solve
│   └── Allclean                #   reset the case
├── feature-refined-mesh/       ← optional higher-quality mesh (feature-edge refinement)
└── scripts/
    └── generate_heatsink_stl.py   ← turns (N, t, H) into the heatsink STL — no CAD
```

---

## Run it

Requires **OpenFOAM 2506** (source its `bashrc` first).

> ⚠️ Run on a **local disk**, not a virtualized shared mount (e.g. a Multipass
> shared folder). snappyHexMesh does thousands of tiny file writes and slows to a
> near-standstill on virtiofs/sshfs — copy the case to `/tmp` or `$FOAM_RUN` first.

```bash
cp -r case /tmp/ep2 && cd /tmp/ep2

# (optional) regenerate the STL from parameters (script lives in ../scripts)
# Python deps: Python 3.8+, numpy, numpy-stl  →  pip install numpy numpy-stl
python generate_heatsink_stl.py \
    --n-fins 5 --fin-thickness 0.002 --fin-height 0.020 \
    --output constant/triSurface/heatsink.stl

# mesh + solve in one shot
./Allrun

# ...or step by step
blockMesh
snappyHexMesh -overwrite
buoyantSimpleFoam
```

Reset any time with `./Allclean`.

### Optional: a sharper mesh

The main case uses surface refinement only. For a higher-quality mesh with
**feature-edge refinement**, see [`feature-refined-mesh/`](feature-refined-mesh/)
— same physics and result (Q/V ≈ 1.08), just crisper fin edges.

## Read the result

The heat dissipated is written by the `wallHeatFlux` function object to
`postProcessing/wallHeatFlux1/…/wallHeatFlux.dat` (the last column is the
integral Q in watts). Divide by the solid volume to get Q/V.

---

## The parametric STL — the hinge of the whole series

`generate_heatsink_stl.py` takes three numbers and writes an STL. That's what
makes everything else possible: in later episodes the optimizer calls this exact
script **hundreds of times** with different numbers — no mouse, no CAD.

**Dependencies** — a Python 3.8+ interpreter with two packages (no OpenFOAM
needed just to build the STL):

```bash
pip install numpy numpy-stl
```

The script imports `numpy` and `stl` (the `stl` module is provided by the
**numpy-stl** package — note the install name differs from the import name).

```bash
python scripts/generate_heatsink_stl.py --help
```

---

**Next up →** Episode 3 automates this whole workflow in Python to run 15 cases
with a single command.
