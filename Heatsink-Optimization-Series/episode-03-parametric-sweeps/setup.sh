#!/bin/bash
# setup.sh — One-time setup for the parametric-sweep pipeline.
# Run once before your first sweep.
#
# What this does:
#   1. Creates the local results/ and VM staging directories
#   2. Verifies the Multipass shared mount the driver uses
#   3. Creates (or updates) the 'heatsink-opt' conda environment on the host
#   4. Verifies OpenFOAM is accessible inside the VM

set -euo pipefail

# --- EDIT THESE to match the config block in optimize_heatsink.py ------------
VM_NAME="rewarded-bluefish"                                    # your OpenFOAM VM
MULTIPASS_HOST="/Users/siddharthamonisha/Home/Multipass_Files" # host side of the shared mount
MULTIPASS_VM="/home/ubuntu/Multipass_Files"                    # VM side of that mount
# ----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_DIR="$MULTIPASS_HOST/heatsink-opt"

# --- 1. Directories ---------------------------------------------------------
echo "=== Step 1: Directories ==="
mkdir -p "$SCRIPT_DIR/results"
mkdir -p "$STAGING_DIR/runs"
echo "Results (host):   $SCRIPT_DIR/results"
echo "Staging (shared): $STAGING_DIR/runs"

# --- 2. Verify the Multipass shared mount inside the VM ---------------------
echo ""
echo "=== Step 2: Multipass shared mount ==="
if ! multipass info "$VM_NAME" >/dev/null 2>&1; then
    echo "ERROR: VM '$VM_NAME' not found. Create/start it first, then re-run:"
    echo "  multipass start $VM_NAME"
    exit 1
fi
if multipass exec "$VM_NAME" -- bash -c "test -d '$MULTIPASS_VM'" 2>/dev/null; then
    echo "Shared mount OK: $MULTIPASS_HOST -> VM:$MULTIPASS_VM"
else
    echo "Mount missing — adding it..."
    multipass mount "$MULTIPASS_HOST" "$VM_NAME:$MULTIPASS_VM"
    echo "Mounted: $MULTIPASS_HOST -> VM:$MULTIPASS_VM"
fi

# --- 3. Conda environment ---------------------------------------------------
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

# --- 4. Verify OpenFOAM on VM -----------------------------------------------
echo ""
echo "=== Step 4: Verify OpenFOAM on VM ==="
multipass exec "$VM_NAME" -- bash -c \
    "source /usr/lib/openfoam/openfoam2506/etc/bashrc 2>/dev/null \
     && which buoyantSimpleFoam \
     && echo 'OpenFOAM OK'"

# --- Done -------------------------------------------------------------------
echo ""
echo "=== Setup complete ==="
echo ""
echo "Activate the environment and run a sweep (values in metres):"
echo "  conda activate heatsink-opt"
echo "  cd $SCRIPT_DIR"
echo "  python optimize_heatsink.py check"
echo "  python optimize_heatsink.py sweep --variable t_fin --values 0.001 0.0015 0.002 0.0025 0.003"
echo ""
echo "Results accumulate in: $SCRIPT_DIR/results/results.csv"
