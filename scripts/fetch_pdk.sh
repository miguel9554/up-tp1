#!/bin/sh
# Download the sky130 PDK into $PDK_ROOT (~/.ciel on the host) with ciel.
# Runs inside the LibreLane container (see `make pdk`).
#
# The PDK version is the one this LibreLane release is pinned to, and the
# libraries include both std cell libraries used here (hd and hs) and the
# SRAM macros.
set -eu

VERSION=$(python3 -c '
import os, yaml, librelane
path = os.path.join(os.path.dirname(librelane.__file__), "pdk_hashes.yaml")
print(yaml.safe_load(open(path))["sky130"])
')

echo "Fetching sky130 PDK version $VERSION into $PDK_ROOT"
ciel fetch --pdk-family sky130 \
  -l sky130_fd_io \
  -l sky130_fd_pr \
  -l sky130_fd_sc_hd \
  -l sky130_fd_sc_hs \
  -l sky130_fd_sc_hvl \
  -l sky130_ml_xx_hd \
  -l sky130_sram_macros \
  "$VERSION"
