#!/bin/bash
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
LOG="logs-tp4/arm-B40758.log"
exec > "$LOG" 2>&1
echo "=== arm B (#40758) start $(date -Is) ==="
echo "--- [0] fingerprint ---"
python3 scripts/verify/fingerprint.py 2>&1 | tail -2
echo "--- [1] input-side escape probe (expect 200 on all 4) ---"
python3 scripts/verify/mm-input-escape-probe.py 2>&1 | tail -7
echo "--- [2] gate --full ---"
./start-tp4.sh gate --full 2>&1 | tail -11
echo "--- [3] gsm8k ---"
mkdir -p bench-results/arms/b40758
python3 bench/gsm8k_dsv41.py --base http://127.0.0.1:8899 --api-key "$API_KEY" \
  --out-raw bench-results/arms/b40758/gsm8k.raw.jsonl --out-summary bench-results/arms/b40758/gsm8k.summary.json
echo "gsm8k exit=$?"
echo "--- [4] perf-gate ---"
bash scripts/perf-gate.sh >/dev/null 2>&1
python3 -c "import json;d=json.load(open(state-tp4/perf-gate.json));print({k:d[k] for k in [ts,verdict,probe_D_8K,probe_D_100K,probe_PR_131072_C1]})"
echo "=== arm B done $(date -Is) ==="
