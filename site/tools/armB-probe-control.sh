#!/bin/bash
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="ctrl"
LOG="logs-tp4/arm-$TAG.log"
exec > "$LOG" 2>&1
echo "=== arm $TAG (UNPATCHED control) start $(date -Is) ==="
echo "--- [1] sentinel logprob probe (sensitivity control: expect masked ids TO APPEAR) ---"
docker cp /tmp/probe_in.py dsv41-head:/tmp/probe_in.py >/dev/null 2>&1
docker exec dsv41-head python3 /tmp/probe_in.py 2>&1 | tail -20
echo "--- [2] what does the engine actually emit for the 0442 prompt? ---"
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
echo "--- [3] PR-v3 24 cells ---"
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
echo "=== arm $TAG done $(date -Is) ==="
