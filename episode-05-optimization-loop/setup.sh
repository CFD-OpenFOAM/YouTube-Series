#!/bin/bash
# setup.sh — One-time setup for the heatsink optimization pipeline
# Run once before starting any optimization runs.
#
# What this does:
#   1. Creates the results directory on the external drive (/Volumes/Sid)
#   2. Verifies the existing Multipass shared mount used by the driver
#   3. Creates (or updates) the 'heatsink-opt' conda environment on the host
#   4. Verifies OpenFOAM is accessible inside the VM

set -euo pipefail

VM_NAME="${HEATSINK_VM_NAME:-rewarded-bluefish}"
SID_DIR="${HEATSINK_RESULTS_DIR:-/Volumes/Sid/heatsink-opt}"
VM_SHARED_ROOT="${HEATSINK_MULTIPASS_VM:-/home/ubuntu/Multipass_Files}"
VM_RESULTS_DIR="$VM_SHARED_ROOT/heatsink-opt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── 1. External drive ────────────────────────────────────────────────────────
echo "=== Step 1: External drive (Sid) ==="
if [ ! -d "/Volumes/Sid" ]; then
    echo "ERROR: /Volumes/Sid not found. Please connect the external drive first."
    exit 1
fi

mkdir -p "$SID_DIR/runs"
echo "Results directory: $SID_DIR"
df -h "$SID_DIR" | tail -1

# ─── 2. Verify shared mount inside VM ─────────────────────────────────────────
echo ""
echo "=== Step 2: Verify Multipass shared mount ==="
multipass exec "$VM_NAME" -- bash -c "mkdir -p '$VM_RESULTS_DIR/runs' && ls '$VM_SHARED_ROOT' > /dev/null 2>&1 && echo 'VM shared mount OK: $VM_RESULTS_DIR' || echo 'WARNING: VM cannot access $VM_SHARED_ROOT'"

# ─── 3. Conda environment ─────────────────────────────────────────────────────
echo ""
echo "=== Step 3: Conda environment 'heatsink-opt' ==="
if conda env list | grep -q "^heatsink-opt"; then
    echo "Environment exists — updating..."
    conda env update -n heatsink-opt -f "$SCRIPT_DIR/environment.yml" --prune -q
else
    echo "Creating environment (this may take a few minutes)..."
    conda env create -f "$SCRIPT_DIR/environment.yml" -q
fi
echo "conda env 'heatsink-opt' ready"

# ─── 4. Verify OpenFOAM on VM ────────────────────────────────────────────────
echo ""
echo "=== Step 4: Verify OpenFOAM on VM ==="
multipass exec "$VM_NAME" -- bash -c \
    "source /usr/lib/openfoam/openfoam2506/etc/bashrc 2>/dev/null \
     && which buoyantSimpleFoam \
     && buoyantSimpleFoam --help 2>&1 | head -2 \
     && echo 'OpenFOAM OK'"

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup complete ==="
echo ""
echo "Activate the environment and run the Episode 5 workflow:"
echo "  conda activate heatsink-opt"
echo "  cd $SCRIPT_DIR"
echo "  export HEATSINK_VM_NAME=$VM_NAME"
echo "  export HEATSINK_RESULTS_DIR=$SID_DIR"
echo "  export HEATSINK_MULTIPASS_VM=$VM_SHARED_ROOT"
echo "  python optimize_heatsink.py check"
echo "  python optimize_heatsink.py optimize --trials 20"
echo ""
echo "Results will accumulate in: $SID_DIR/results.csv"
