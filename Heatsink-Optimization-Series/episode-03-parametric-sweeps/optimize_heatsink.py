"""
Heat Sink Design Optimization Driver
=====================================
macOS + Multipass (rewarded-bluefish) version

Workflow per evaluation:
  1. Set up case directory (host): copy template, patch dicts
  2. Generate parameterised STL into constant/triSurface/ (host Python)
  3. VM copies case to /tmp, runs:
       blockMesh -> surfaceFeatureExtract -> snappyHexMesh -> buoyantSimpleFoam -> foamToVTK
  4. VM copies results (mesh, fields, logs, VTK) back to RESULTS_DIR (default ./results)
  5. VM cleans up its /tmp work directory
  6. Host extracts Q from postProcessing/wallHeatFlux1
  7. Host runs PyVista to generate PNG images
  8. Host logs run to results.csv

Usage:
  conda activate heatsink-opt

  # Phase 1 -- parametric sweeps
  python optimize_heatsink.py sweep --variable t_fin --values 0.001 0.0015 0.002 0.0025 0.003
  python optimize_heatsink.py sweep --variable N_fin --values 3 5 7 9 11
  python optimize_heatsink.py sweep --variable H_fin --values 0.010 0.015 0.020 0.025 0.030

  # Single run
  python optimize_heatsink.py single --t-fin 0.0015 --n-fins 7 --h-fin 0.025

  # Phase 2 -- Bayesian optimisation (seeds from Phase 1 CSV automatically)
  python optimize_heatsink.py optimize --trials 20

  # Verify prerequisites
  python optimize_heatsink.py check
"""

import argparse
import csv
import fcntl
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_DIR  = Path(__file__).resolve().parent
TEMPLATE_DIR = PROJECT_DIR / "openfoam-template"   # complete base case, bundled here
SCRIPTS_DIR  = PROJECT_DIR / "scripts"             # parametric STL generator

# ══════════════════════════════════════════════════════════════════
# EDIT THESE TWO for your machine (Multipass shared mount + VM name). Everything
# else below is derived automatically and needs no changes.
# ══════════════════════════════════════════════════════════════════
# Multipass shared-mount mapping: host path -> VM path
_MULTIPASS_HOST = Path("/Users/siddharthamonisha/Home/Multipass_Files")
_MULTIPASS_VM   = "/home/ubuntu/Multipass_Files"

# Staging area: writable from both host and VM via the Multipass shared mount
STAGING_DIR  = _MULTIPASS_HOST / "heatsink-opt"
STAGING_RUNS = STAGING_DIR / "runs"

# Persistent results (results.csv + final run data). Defaults to a local
# ./results folder so a fresh clone runs out-of-the-box; point anywhere you like.
RESULTS_DIR = PROJECT_DIR / "results"
RUNS_DIR    = STAGING_RUNS   # VM writes here; we rsync to RESULTS_DIR afterwards
RESULTS_CSV = RESULTS_DIR / "results.csv"

# ── Multipass VM ───────────────────────────────────────────────────────────
VM_NAME          = "rewarded-bluefish"        # <-- EDIT: your OpenFOAM VM name
VM_WORK_BASE     = "/tmp/heatsink-opt"        # temp work dir inside VM
VM_RESULTS_BASE  = "/home/ubuntu/Multipass_Files/heatsink-opt"  # staging inside VM


def _host_to_vm(host_path: Path) -> str:
    """Translate a host path (under the Multipass shared mount) to its VM path."""
    rel = host_path.relative_to(_MULTIPASS_HOST)
    return f"{_MULTIPASS_VM}/{rel}"


# run_openfoam.sh as seen by the VM (via the shared mount)
VM_OF_SCRIPT = _host_to_vm(PROJECT_DIR / "run_openfoam.sh")

# Python interpreter in the heatsink-opt conda env (has pyvista, etc.)
_CONDA_PYTHON = Path.home() / "miniconda3/envs/heatsink-opt/bin/python"
VIS_PYTHON = str(_CONDA_PYTHON) if _CONDA_PYTHON.exists() else sys.executable

# ── Fixed design parameters ───────────────────────────────────────────────────
FIXED = {
    "L":      0.060,   # base length [m]
    "W":      0.060,   # base width  [m]
    "H_base": 0.003,   # base height [m]
}

# ── Solver settings (optimisation -- speed over accuracy) ────────────────────
OPT_END_TIME       = 500
OPT_WRITE_INTERVAL = 500   # write only the final step
OPT_PURGE_WRITE    = 1     # keep only the last written time

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run_in_vm(cmd: str, timeout: int = 14400) -> subprocess.CompletedProcess:
    """Execute a bash command inside the Multipass VM and return the result."""
    return subprocess.run(
        ["multipass", "exec", VM_NAME, "--", "bash", "-c", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def compute_volume_cm3(N_fin: int, t_fin: float, H_fin: float) -> float:
    """Heatsink solid volume [cm3] -- computed analytically."""
    L, W, H_base = FIXED["L"], FIXED["W"], FIXED["H_base"]
    V_m3 = L * W * H_base + N_fin * t_fin * H_fin * L
    return V_m3 * 1e6


# ─────────────────────────────────────────────────────────────────────────────
# Case setup (runs on host)
# ─────────────────────────────────────────────────────────────────────────────

def setup_case(run_dir: Path) -> None:
    """
    Populate run_dir with patched OpenFOAM case files from the template.
    Copies system/, 0/, and constant/ (without polyMesh -- regenerated by blockMesh).
    The STL is placed at constant/triSurface/heatsink.stl by generate_stl().
    """
    for folder in ("system", "0"):
        dst = run_dir / folder
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(TEMPLATE_DIR / folder, dst)

    # constant/ -- copy everything EXCEPT polyMesh (large, regenerated per run)
    const_src = TEMPLATE_DIR / "constant"
    const_dst = run_dir / "constant"
    const_dst.mkdir(exist_ok=True)
    for item in const_src.iterdir():
        if item.name == "polyMesh":
            continue
        dst_item = const_dst / item.name
        if dst_item.exists():
            shutil.rmtree(dst_item) if dst_item.is_dir() else dst_item.unlink()
        if item.is_dir():
            shutil.copytree(item, dst_item)
        else:
            shutil.copy2(item, dst_item)

    # Patch controlDict: shorter run, write only the last step
    ctrl = run_dir / "system" / "controlDict"
    txt  = ctrl.read_text()
    txt  = re.sub(r"endTime\s+\d+;",       f"endTime         {OPT_END_TIME};",       txt)
    txt  = re.sub(r"writeInterval\s+\d+;", f"writeInterval   {OPT_WRITE_INTERVAL};", txt)
    txt  = re.sub(r"purgeWrite\s+\d+;",    f"purgeWrite      {OPT_PURGE_WRITE};",    txt)
    ctrl.write_text(txt)

    # Disable boundary layers (faster meshing)
    snappy = run_dir / "system" / "snappyHexMeshDict"
    txt    = snappy.read_text()
    txt    = re.sub(r"addLayers\s+true;",          "addLayers       false;",   txt)
    # Coarsen mesh for optimization speed: nCellsBetweenLevels 3->1,
    # feature level 3->2, surface levels (2 3)->(1 2), maxGlobalCells 2M->400k
    txt    = re.sub(r"nCellsBetweenLevels\s+\d+;", "nCellsBetweenLevels 1;",   txt)
    txt    = re.sub(r"maxGlobalCells\s+\d+;",      "maxGlobalCells      400000;", txt)
    txt    = re.sub(r"(file\s+\"heatsink\.eMesh\";\s*\n\s*)level\s+\d+;",
                    r"\g<1>level 2;", txt)
    txt    = re.sub(r"level\s+\(2\s+3\);",         "level (1 2);",             txt)
    # Empty the features block: OpenFOAM 2506 writes heatsink.eMesh to
    # constant/triSurface/ but snappyHexMesh looks in extendedFeatureEdgeMesh/
    # causing Feature refinement iteration 0 to hang indefinitely.
    # Feature edges are not needed for relative Q comparisons.
    txt    = re.sub(r"features\s*\([^)]*\)\s*;", "features\n    (\n    );", txt, flags=re.DOTALL)
    snappy.write_text(txt)

    print(f"  Case set up (endTime={OPT_END_TIME}, noLayers, serial snappy, no features)")


def generate_stl(run_dir: Path, t_fin: float, N_fin: int, H_fin: float):
    """
    Generate the parameterised heatsink STL.
    Output: run_dir/constant/triSurface/heatsink.stl
    Must be called AFTER setup_case() so constant/ already exists.
    """
    stl_path = run_dir / "constant" / "triSurface" / "heatsink.stl"
    stl_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "generate_heatsink_stl.py"),
        "--length",        str(FIXED["L"]),
        "--width",         str(FIXED["W"]),
        "--base-height",   str(FIXED["H_base"]),
        "--n-fins",        str(N_fin),
        "--fin-height",    str(H_fin),
        "--fin-thickness", str(t_fin),
        "--output",        str(stl_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STL generation FAILED:\n{result.stderr.strip()}")
        return None
    print("  STL generated: constant/triSurface/heatsink.stl")
    return stl_path


# ─────────────────────────────────────────────────────────────────────────────
# OpenFOAM execution (runs inside VM via multipass exec)
# ─────────────────────────────────────────────────────────────────────────────

def run_openfoam(run_id: int, timeout: int = 14400) -> bool:
    """
    Run the full OpenFOAM pipeline for this run inside the Multipass VM.
    Streams stdout so progress is visible; times out gracefully without
    crashing the sweep if the VM takes too long.
    """
    import select
    import threading

    vm_work_dir    = f"{VM_WORK_BASE}/run_{run_id:03d}"
    vm_results_dir = f"{VM_RESULTS_BASE}/runs/run_{run_id:03d}"
    run_dir = RUNS_DIR / f"run_{run_id:03d}"

    print(f"  Launching OpenFOAM on VM  (work={vm_work_dir})")
    t0 = time.time()

    proc = subprocess.Popen(
        ["multipass", "exec", VM_NAME, "--", "bash", "-c",
         f"bash '{VM_OF_SCRIPT}' '{vm_work_dir}' '{vm_results_dir}'"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    last_report  = t0
    timed_out    = False

    def _drain(pipe, buf):
        for line in pipe:
            buf.append(line)

    t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_lines), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_lines), daemon=True)
    t_out.start(); t_err.start()

    while proc.poll() is None:
        elapsed = time.time() - t0
        if elapsed > timeout:
            print(f"  TIMEOUT after {elapsed/3600:.1f}h — VM process left running; "
                  f"re-attach with: multipass exec {VM_NAME} -- bash")
            timed_out = True
            break
        if time.time() - last_report >= 120:
            # Print a heartbeat every 2 minutes showing which stage we're at
            stage = "running"
            for keyword in ["buoyantSimpleFoam", "foamToVTK",
                            "snappyHexMesh", "surfaceFeatureExtract", "blockMesh"]:
                probe = run_in_vm(
                    f"ps -C {keyword} -o pid= 2>/dev/null | head -1", timeout=10
                )
                if probe.stdout.strip():
                    stage = keyword
                    break
            elapsed_m = elapsed / 60
            print(f"  [{elapsed_m:.0f}m] {stage} still running …")
            last_report = time.time()
        time.sleep(10)

    t_out.join(timeout=5); t_err.join(timeout=5)
    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)

    elapsed = time.time() - t0
    print(f"  VM finished in {elapsed:.0f}s  (exit={proc.returncode if not timed_out else 'timeout'})")

    (run_dir / "vm_stdout.log").write_text(stdout)
    if stderr:
        (run_dir / "vm_stderr.log").write_text(stderr)

    if timed_out:
        print("  Run logged as TIMEOUT")
        return False

    if "PIPELINE_COMPLETE" not in stdout:
        print("  WARNING: Pipeline may not have completed successfully")
        for line in stdout.strip().splitlines()[-15:]:
            print(f"    {line}")
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Results extraction (reads files on host from Sid)
# ─────────────────────────────────────────────────────────────────────────────

def extract_heat_flux(run_dir: Path):
    """Parse Q [W] from wallHeatFlux.dat written to postProcessing/."""
    candidates = sorted(run_dir.glob("postProcessing/wallHeatFlux1/*/wallHeatFlux.dat"))
    if not candidates:
        print("  WARNING: wallHeatFlux.dat not found in postProcessing/")
        return None

    dat_file   = candidates[-1]
    data_lines = [
        ln for ln in dat_file.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    if not data_lines:
        return None

    parts = data_lines[-1].split()
    if len(parts) >= 5:
        Q     = float(parts[-1])
        q_min = float(parts[-3])
        q_max = float(parts[-2])
        print(f"  Heat flux: Q={Q:.2f} W  (q_min={q_min:.1f}, q_max={q_max:.1f} W/m2)")
        return Q

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Visualisation (runs on host, uses PyVista)
# ─────────────────────────────────────────────────────────────────────────────

def run_visualize(run_dir: Path) -> None:
    """Invoke visualize_run.py for this run directory."""
    vis_script = PROJECT_DIR / "visualize_run.py"
    if not vis_script.exists():
        print("  visualize_run.py not found -- skipping")
        return

    result = subprocess.run(
        [VIS_PYTHON, str(vis_script), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        print(f"  Visualization failed:\n{result.stderr.strip()[:400]}")
    else:
        print(result.stdout.strip())


# ─────────────────────────────────────────────────────────────────────────────
# Sync staging -> Sid
# ─────────────────────────────────────────────────────────────────────────────

def sync_run_to_sid(run_id: int) -> None:
    """Rsync a completed run from the staging area to RESULTS_DIR."""
    src = str(STAGING_RUNS / f"run_{run_id:03d}") + "/"
    dst = str(RESULTS_DIR / "runs" / f"run_{run_id:03d}") + "/"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "runs").mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["rsync", "-a", src, dst],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"  WARNING: rsync to results failed: {result.stderr.strip()[:200]}")
    else:
        print(f"  Synced run_{run_id:03d} to {RESULTS_DIR}/runs/")


# ─────────────────────────────────────────────────────────────────────────────
# CSV logging
# ─────────────────────────────────────────────────────────────────────────────

def log_result(run_id, t_fin, N_fin, H_fin, V_cm3, Q, status):
    """Append one row to the master results CSV on Sid."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = RESULTS_CSV.exists()
    Q_over_V    = (Q / V_cm3) if Q and V_cm3 > 0 else None

    with open(RESULTS_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["run_id", "t_fin_mm", "N_fin", "H_fin_mm",
                         "V_cm3", "Q_W", "Q_over_V", "status"])
        w.writerow([
            f"{run_id:03d}",
            f"{t_fin * 1000:.2f}",
            N_fin,
            f"{H_fin * 1000:.1f}",
            f"{V_cm3:.2f}",
            f"{Q:.2f}"        if Q       else "N/A",
            f"{Q_over_V:.4f}" if Q_over_V else "N/A",
            status,
        ])


_RUN_ID_LOCK = STAGING_DIR / ".run_id.lock"

def get_next_run_id() -> int:
    """
    Atomically reserve the next sequential run ID.
    Uses a file lock so concurrent sweep processes don't collide.
    Creates the run directory while holding the lock to guarantee uniqueness.
    """
    STAGING_RUNS.mkdir(parents=True, exist_ok=True)
    _RUN_ID_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUN_ID_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            ids = [
                int(d.name.split("_")[1])
                for d in RUNS_DIR.iterdir()
                if d.is_dir() and d.name.startswith("run_") and d.name.split("_")[1].isdigit()
            ] if RUNS_DIR.exists() else []
            run_id = max(ids, default=0) + 1
            # Create directory inside the lock to reserve the ID before releasing
            (RUNS_DIR / f"run_{run_id:03d}").mkdir(parents=True, exist_ok=True)
            return run_id
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ─────────────────────────────────────────────────────────────────────────────
# Core evaluation
# ─────────────────────────────────────────────────────────────────────────────

def run_single(t_fin, N_fin, H_fin, run_id=None, visualize=True):
    """
    Full single-design evaluation:
      setup -> STL -> OpenFOAM -> extract Q -> visualise -> log
    Returns (Q [W], V [cm3]).
    """
    if run_id is None:
        run_id = get_next_run_id()

    run_dir = RUNS_DIR / f"run_{run_id:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    V_cm3 = compute_volume_cm3(N_fin, t_fin, H_fin)

    print(f"\n{'='*62}")
    print(f"  Run {run_id:03d}: t_fin={t_fin*1000:.2f} mm  N_fin={N_fin}  H_fin={H_fin*1000:.1f} mm")
    print(f"  Volume: {V_cm3:.2f} cm3  ->  {run_dir}")
    print('='*62)

    # 1. Populate run_dir with template files
    setup_case(run_dir)

    # 2. Generate STL after setup_case (constant/triSurface/ now exists)
    stl = generate_stl(run_dir, t_fin, N_fin, H_fin)
    if stl is None:
        log_result(run_id, t_fin, N_fin, H_fin, V_cm3, None, "STL_FAILED")
        return None, V_cm3

    # 3. Run OpenFOAM on the VM (reads from Sid, writes back to Sid)
    success = run_openfoam(run_id)

    # 4. Extract Q from postProcessing written back to Sid
    Q = None
    if success:
        Q = extract_heat_flux(run_dir)

    # 5. Log to CSV
    status = "OK" if Q else "FAILED"
    log_result(run_id, t_fin, N_fin, H_fin, V_cm3, Q, status)

    if Q:
        print(f"  >>> Q/V = {Q/V_cm3:.4f} W/cm3  (baseline: 1.03 W/cm3)")

    # 6. Visualise (offscreen PNG generation)
    if visualize:
        run_visualize(run_dir)

    # 7. Sync completed run to Sid for permanent storage
    sync_run_to_sid(run_id)

    return Q, V_cm3


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 -- 1D parametric sweep
# ─────────────────────────────────────────────────────────────────────────────

def run_sweep(variable, values, N_fin=5, H_fin=0.020, t_fin=0.002):
    """
    Run a 1D parametric sweep over `variable`, keeping others fixed.
    Prints a summary table and saves a per-sweep CSV at the end.
    """
    print(f"\n{'#'*62}")
    print(f"  SWEEP: {variable}  ->  {values}")
    print(f"  Fixed: N_fin={N_fin}, H_fin={H_fin*1000:.1f}mm, t_fin={t_fin*1000:.2f}mm")
    print('#'*62)

    results  = []

    for val in values:
        if variable == "t_fin":
            Q, V = run_single(t_fin=float(val), N_fin=N_fin,    H_fin=H_fin)
        elif variable == "N_fin":
            Q, V = run_single(t_fin=t_fin,       N_fin=int(val), H_fin=H_fin)
        elif variable == "H_fin":
            Q, V = run_single(t_fin=t_fin,        N_fin=N_fin,   H_fin=float(val))
        else:
            raise ValueError(f"Unknown variable: {variable}")
        results.append({"value": val, "Q": Q, "V": V,
                         "Q_over_V": Q / V if Q else None})

    BASELINE_QV = 1.03
    print(f"\n{'='*62}")
    print(f"  SWEEP SUMMARY: {variable}")
    print('='*62)
    hdr = f"  {'Value':>12s}  {'V (cm3)':>10s}  {'Q (W)':>10s}  {'Q/V':>12s}  {'vs base':>8s}"
    print(hdr)
    print(f"  {'-'*12}  {'-'*10}  {'-'*10}  {'-'*12}  {'-'*8}")
    for r in results:
        v_str  = f"{int(r['value']):d}"         if variable == "N_fin" else f"{r['value']*1000:.2f} mm"
        Q_str  = f"{r['Q']:.2f}"                if r["Q"]       else "FAILED"
        QV_str = f"{r['Q_over_V']:.4f}"         if r["Q_over_V"] else "N/A"
        delta  = (f"{(r['Q_over_V'] - BASELINE_QV) / BASELINE_QV * 100:+.1f}%"
                  if r["Q_over_V"] else "N/A")
        print(f"  {v_str:>12s}  {r['V']:>10.2f}  {Q_str:>10s}  {QV_str:>12s}  {delta:>8s}")

    sweep_csv = RESULTS_DIR / f"sweep_summary_{variable}.csv"
    with open(sweep_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([variable, "V_cm3", "Q_W", "Q_over_V"])
        for r in results:
            w.writerow([
                r["value"],
                f"{r['V']:.2f}",
                f"{r['Q']:.2f}"        if r["Q"]       else "FAILED",
                f"{r['Q_over_V']:.4f}" if r["Q_over_V"] else "N/A",
            ])
    print(f"\n  Sweep CSV: {sweep_csv}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 -- Bayesian optimisation (Optuna)
# ─────────────────────────────────────────────────────────────────────────────

def run_optimize(n_trials=20, seed_from_csv=True):
    """
    Bayesian optimisation using Optuna TPE sampler.
    Objective: maximise Q/V  |  Constraint: Q >= 23.4 W (penalty if violated).
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("ERROR: optuna not installed. Activate the heatsink-opt conda env.")
        sys.exit(1)

    BASELINE_Q = 23.4   # W -- hard thermal requirement

    def objective(trial):
        t_fin = trial.suggest_float("t_fin", 0.001, 0.003)
        N_fin = trial.suggest_int  ("N_fin", 3,     11)
        H_fin = trial.suggest_float("H_fin", 0.010, 0.030)
        Q, V  = run_single(t_fin=t_fin, N_fin=N_fin, H_fin=H_fin, visualize=True)
        if Q is None:
            return -999.0
        Q_over_V = Q / V
        if Q < BASELINE_Q:
            penalty = 10.0 * (BASELINE_Q - Q) / BASELINE_Q
            return Q_over_V - penalty
        return Q_over_V

    study_path = RESULTS_DIR / "optuna_study.db"
    study = optuna.create_study(
        direction      = "maximize",
        study_name     = "heatsink_opt",
        storage        = f"sqlite:///{study_path}",
        load_if_exists = True,
        sampler        = optuna.samplers.TPESampler(seed=42),
    )

    if seed_from_csv and RESULTS_CSV.exists():
        try:
            import pandas as pd
            df = pd.read_csv(RESULTS_CSV)
            df = df[df["status"] == "OK"].copy()
            seeded = 0
            for _, row in df.iterrows():
                try:
                    trial = optuna.trial.create_trial(
                        params={
                            "t_fin": float(row["t_fin_mm"]) / 1000.0,
                            "N_fin": int(row["N_fin"]),
                            "H_fin": float(row["H_fin_mm"]) / 1000.0,
                        },
                        distributions={
                            "t_fin": optuna.distributions.FloatDistribution(0.001, 0.003),
                            "N_fin": optuna.distributions.IntDistribution(3, 11),
                            "H_fin": optuna.distributions.FloatDistribution(0.010, 0.030),
                        },
                        value=float(row["Q_over_V"]),
                    )
                    study.add_trial(trial)
                    seeded += 1
                except Exception:
                    pass
            print(f"  Seeded {seeded} trials from {RESULTS_CSV}")
        except ImportError:
            print("  WARNING: pandas not available -- skipping CSV seed")

    print(f"\n{'#'*62}")
    print(f"  BAYESIAN OPTIMISATION: {n_trials} trials")
    print(f"  Storage: {study_path}")
    print('#'*62)

    study.optimize(objective, n_trials=n_trials)

    best = study.best_trial
    print(f"\n  BEST DESIGN:")
    print(f"    t_fin = {best.params['t_fin']*1000:.2f} mm")
    print(f"    N_fin = {best.params['N_fin']}")
    print(f"    H_fin = {best.params['H_fin']*1000:.1f} mm")
    print(f"    Q/V   = {best.value:.4f} W/cm3")
    return study


# ─────────────────────────────────────────────────────────────────────────────
# Setup check
# ─────────────────────────────────────────────────────────────────────────────

def check_setup():
    """Verify all prerequisites before kicking off a run campaign."""
    ok = True
    print("Checking setup...")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if RESULTS_DIR.exists():
        print(f"  [OK] Results dir ready: {RESULTS_DIR}")
    else:
        print(f"  [FAIL] Cannot create results dir: {RESULTS_DIR}")
        ok = False

    r = subprocess.run(["multipass", "info", VM_NAME],
                       capture_output=True, text=True, timeout=10)
    if "Running" in r.stdout:
        print(f"  [OK] VM {VM_NAME!r} is running")
    else:
        print(f"  [FAIL] VM {VM_NAME!r} not running -- start with: multipass start {VM_NAME}")
        ok = False

    r2 = run_in_vm(f"ls '{VM_RESULTS_BASE}' 2>/dev/null && echo MOUNT_OK", timeout=15)
    if "MOUNT_OK" in r2.stdout:
        print(f"  [OK] VM staging area {VM_RESULTS_BASE} accessible")
    else:
        print(f"  [FAIL] VM staging area {VM_RESULTS_BASE} not accessible")
        print(f"         Expected Multipass shared mount at /home/ubuntu/Multipass_Files")
        ok = False

    r3 = run_in_vm(
        "source /usr/lib/openfoam/openfoam2506/etc/bashrc 2>/dev/null "
        "&& which buoyantSimpleFoam && echo OF_OK",
        timeout=20,
    )
    if "OF_OK" in r3.stdout:
        print("  [OK] OpenFOAM-2506 available on VM")
    else:
        print("  [FAIL] buoyantSimpleFoam not found on VM")
        ok = False

    try:
        import stl  # noqa: F401
        print("  [OK] numpy-stl available on host")
    except ImportError:
        print("  [FAIL] numpy-stl not installed -- pip install numpy-stl")
        ok = False

    if (TEMPLATE_DIR / "system" / "controlDict").exists():
        print(f"  [OK] Template case found at {TEMPLATE_DIR}")
    else:
        print(f"  [FAIL] Template case not found at {TEMPLATE_DIR}")
        ok = False

    print()
    print("All checks passed. Ready to run." if ok else
          "Some checks FAILED -- resolve the issues above before running.")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Heat Sink Optimisation Driver (macOS + Multipass)",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="Verify setup before running")

    ps = sub.add_parser("single", help="Single design evaluation")
    ps.add_argument("--t-fin",  type=float, default=0.002)
    ps.add_argument("--n-fins", type=int,   default=5)
    ps.add_argument("--h-fin",  type=float, default=0.020)
    ps.add_argument("--no-vis", action="store_true", help="Skip PyVista images")

    pw = sub.add_parser("sweep", help="1D parametric sweep")
    pw.add_argument("--variable", required=True, choices=["t_fin", "N_fin", "H_fin"])
    pw.add_argument("--values",   required=True, type=float, nargs="+")
    pw.add_argument("--t-fin",  type=float, default=0.002)
    pw.add_argument("--n-fins", type=int,   default=5)
    pw.add_argument("--h-fin",  type=float, default=0.020)

    po = sub.add_parser("optimize", help="Bayesian optimisation (Phase 2)")
    po.add_argument("--trials",      type=int,  default=20)
    po.add_argument("--no-seed-csv", action="store_true")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "check":
        check_setup()
    elif args.command == "single":
        run_single(t_fin=args.t_fin, N_fin=args.n_fins, H_fin=args.h_fin,
                   visualize=not args.no_vis)
    elif args.command == "sweep":
        run_sweep(variable=args.variable, values=args.values,
                  N_fin=args.n_fins, H_fin=args.h_fin, t_fin=args.t_fin)
    elif args.command == "optimize":
        run_optimize(n_trials=args.trials, seed_from_csv=not args.no_seed_csv)


if __name__ == "__main__":
    main()
