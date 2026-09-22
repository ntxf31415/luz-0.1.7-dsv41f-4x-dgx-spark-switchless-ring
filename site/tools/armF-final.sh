#!/bin/bash
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
LOG="logs-tp4/arm-final.log"
exec > "$LOG" 2>&1
echo "=== FINAL adopted-config validation $(date -Is) ==="
echo "--- [1] fingerprint ---"
python3 scripts/verify/fingerprint.py 2>&1 | tail -2
echo "--- [2] sentinel probe (expect 0) ---"
docker exec dsv41-head python3 /tmp/probe_in.py 2>&1 | head -6
echo "--- [3] gate --full ---"
./start-tp4.sh gate --full 2>&1 | tail -11
echo "--- [4] gsm8k ---"
mkdir -p bench-results/arms/final
python3 bench/gsm8k_dsv41.py --base http://127.0.0.1:8899 --api-key "$API_KEY" \
  --out-raw bench-results/arms/final/gsm8k.raw.jsonl --out-summary bench-results/arms/final/gsm8k.summary.json
echo "gsm8k exit=$?"
echo "--- [5] PDI probe N=8 ---"
python3 scripts/verify/pdi-storm-probe.py --label pdi8-p046
echo "--- [6] perf-gate ---"
bash scripts/perf-gate.sh >/dev/null 2>&1
python3 -c "import json;d=json.load(open('state-tp4/perf-gate.json'));print({k:d[k] for k in ['ts','verdict','probe_D_8K','probe_D_100K','probe_PR_131072_C1']})"
echo "=== FINAL done $(date -Is) ==="
