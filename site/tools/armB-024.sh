#!/bin/bash
# armB-024.sh -- arm B: 0.2.4 + site patch + PDI=0 (long-档 D + solo cold prefill + PDI N=0).
set -uo pipefail
cd "$HOME/luz017"
export API_KEY="$(cat state-tp4/api-key)"
export MODEL=deepseek-v4.1-flash
TAG="luz024-B-$(date +%Y%m%dT%H%M%S)"
LOG="logs-tp4/armB-$TAG.log"
exec > "$LOG" 2>&1
echo "=== armB start $(date -Is) tag=$TAG (PDI=0) ==="
mkdir -p "bench-results/arms/$TAG"

echo "--- [1] fingerprint ---"
python3 scripts/verify/fingerprint.py | tail -3

echo "--- [2] freshness control: D 8K (seed 941) ---"
python3 scripts/verify/prefill_distinct.py 8435 941

echo "--- [3] long-档 D: target 585000 (seed 919) ---"
python3 scripts/verify/prefill_distinct.py 585000 919

echo "--- [4] solo cold prefill: target 100000 (seed 923) ---"
python3 scripts/verify/prefill_distinct.py 100000 923

echo "--- [5] PDI storm probe, N=0 arm ---"
python3 scripts/verify/pdi-storm-probe.py --label pdi0-024

echo "=== armB done $(date -Is) tag=$TAG ==="
