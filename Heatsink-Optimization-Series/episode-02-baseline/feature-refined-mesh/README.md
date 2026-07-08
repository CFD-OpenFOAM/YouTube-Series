# Optional: feature-refined mesh

This is an **alternative, higher-quality mesh** for the same baseline heatsink —
provided for viewers who want to run the study with a sharper mesh. The main
[`../case`](../case) uses **surface refinement only**; this variant adds
**feature-edge refinement** so the fin edges are resolved more crisply.

<!-- add a render of the two meshes side by side here if you like -->

## Why a separate case?

Feature refinement needs every feature edge to lie **inside** the mesh domain.
The main case deliberately extends the heatsink base ~1 mm **below** the domain
floor (`base_extension=0.001`) as a meshing trick for a clean cut at the heated
wall — but that pushes the base-perimeter feature edges *outside* the domain, and
snappyHexMesh then hangs at `Feature refinement iteration 0`.

This variant fixes that by using a **flush base** (`base_extension=0`, base bottom
exactly at `y=0`). Every feature edge is now inside the domain, so feature
refinement runs cleanly. The base is a purely numerical detail — the simulated
geometry (base at `y=0`, whole surface at 350 K, adiabatic floor) is identical, so
the result is the same: **Q ≈ 24.7 W, Q/V ≈ 1.08 W/cm³**.

## What's different from `../case`

| | `../case` (main) | this variant |
|---|---|---|
| Base | protrudes 1 mm below floor | **flush at y=0** |
| `system/snappyHexMeshDict` → `features` | empty (disabled) | **`{ file "heatsink.eMesh"; level 2; }`** |
| `refinementSurfaces` level | `(1 2)` | **`(2 3)`** |
| `surfaceFeatureExtract` | not needed | **required** (builds the eMesh) |
| Cells | ~130k | ~196k |

Everything else (`0/`, physics, boundary conditions) is identical.

## Run it

Run on the VM's **local disk**, not a shared mount (see the note in `Allrun`):

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
cp -r feature-refined-mesh /tmp/ep2fr && cd /tmp/ep2fr
./Allrun
```

`Allrun` runs `blockMesh → surfaceFeatureExtract → snappyHexMesh → checkMesh →
buoyantSimpleFoam`. Meshing takes ~15 s; feature refinement iterations 0→4 should
complete with no hang, and `checkMesh` reports **Mesh OK**.

> Note: this variant is **not** the one used for the published study numbers — the
> optimization pipeline (Episodes 3/5/6) uses the protruding base + surface
> refinement. It's here purely as a better-mesh option for the baseline.
