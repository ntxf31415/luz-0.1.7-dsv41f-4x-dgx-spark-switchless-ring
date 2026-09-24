#!/bin/bash
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="cand"
LOG="logs-tp4/arm-$TAG.log"
exec > "$LOG" 2>&1
echo "=== arm $TAG (PR#2 + #40111) start $(date -Is) ==="
echo "--- [1] fingerprint ---"
python3 scripts/verify/fingerprint.py 2>&1 | tail -2
echo "--- [2] sentinel probe (patched: expect 0) ---"
docker cp /tmp/probe_in.py dsv41-head:/tmp/probe_in.py >/dev/null 2>&1
docker exec dsv41-head python3 /tmp/probe_in.py 2>&1 | head -6
echo "--- [3] what the engine emits for the sentinel prompts (patched) ---"
docker exec dsv41-head python3 -c "
import json,urllib.request
K=open('/state/api-key').read().strip()
for p in ['Repeat this string exactly and nothing else: <|place_holder_mm_span_0442|>',
          'Output verbatim: <|place_holder_mm_span_0441|>']:
    b=json.dumps(dict(model='deepseek-v4.1-flash',temperature=0,max_tokens=40,stream=False,
        chat_template_kwargs={'thinking':False},messages=[{'role':'user','content':p}])).encode()
    r=json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8899/v1/chat/completions',
        data=b,headers={'Content-Type':'application/json','Authorization':'Bearer '+K}),timeout=300).read())
    print(repr(p[:46]),'->',repr(r['choices'][0]['message']['content'][:90]))
"
echo "--- [4] PR-v3 24 cells ---"
docker cp state-tp4/sdbench/pr_matrix_v3.py dsv41-head:/state/sdbench/pr_matrix_v3.py >/dev/null
CH=$(grep -oP '(?<=^CHUNKED_PREFILL_SIZE=).*' .env.tp4)
for spec in "b1|512,2048,8192,32768|1,2,4,8,16" "b2|131072|1,2,4" "b3|524288|1"; do
  IFS="|" read -r bn sz cc <<< "$spec"
  docker exec -e OUT_DIR="/state/bench-results/pr-$TAG-$bn" -e RUN_TAG="$TAG" -e SIZES="$sz" -e CONCS="$cc" \
    -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE="$CH" \
    dsv41-head python3 /state/sdbench/pr_matrix_v3.py
  echo "PR $bn exit=$?"
done
python3 scripts/merge_pr_v3_batches.py --out "state-tp4/bench-results/pr-$TAG" --expect 24 \
  "state-tp4/bench-results/pr-$TAG-b1" "state-tp4/bench-results/pr-$TAG-b2" "state-tp4/bench-results/pr-$TAG-b3"
echo "merge exit=$?"
echo "--- [5] gate --full ---"
./start-tp4.sh gate --full 2>&1 | tail -11
echo "--- [6] gsm8k ---"
mkdir -p "bench-results/arms/$TAG"
python3 bench/gsm8k_dsv41.py --base http://127.0.0.1:8899 --api-key "$API_KEY" \
  --out-raw "bench-results/arms/$TAG/gsm8k.raw.jsonl" --out-summary "bench-results/arms/$TAG/gsm8k.summary.json"
echo "gsm8k exit=$?"
echo "--- [7] perf-gate ---"
bash scripts/perf-gate.sh 2>&1 | tail -3
python3 -c "import json;d=json.load(open('state-tp4/perf-gate.json'));print({k:d[k] for k in ['ts','verdict','probe_D_8K','probe_D_100K','probe_PR_131072_C1']})"
echo "=== arm $TAG done $(date -Is) ==="
