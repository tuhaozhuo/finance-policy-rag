#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/api/v1}"
TOP_K="${TOP_K:-5}"
INCLUDE_EXPIRED="${INCLUDE_EXPIRED:-true}"

echo "Finance RAG QA (type 'exit' to quit)"
echo "base_url=${BASE_URL} top_k=${TOP_K} include_expired=${INCLUDE_EXPIRED}"

while true; do
  printf "\n你问> "
  IFS= read -r question
  if [[ -z "${question}" ]]; then
    continue
  fi
  if [[ "${question}" == "exit" ]]; then
    break
  fi

  payload=$(cat <<JSON
{"question":"${question//\"/\\\"}","include_expired":${INCLUDE_EXPIRED},"top_k":${TOP_K}}
JSON
)

  response=$(curl -sS "${BASE_URL}/qa" -H "Content-Type: application/json" -d "${payload}" || true)

  RESPONSE="${response}" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("RESPONSE", "")
if not raw:
    print("请求失败：无响应")
    sys.exit(0)

try:
    obj = json.loads(raw)
except Exception:
    print("请求失败：非 JSON 响应")
    print(raw[:500])
    sys.exit(0)

data = obj.get("data") or {}
answer = data.get("answer", "")
citations = data.get("citations", [])
status = data.get("effective_status_summary", "")
conf = data.get("confidence_score")
latency = data.get("latency_ms")

print("\n答> " + (answer or "（空）"))
print(f"\n[meta] confidence={conf} latency_ms={latency} citations={len(citations)}")
if status:
    print("[meta] " + status)
if citations:
    print("[引用]")
    for idx, item in enumerate(citations[:3], start=1):
        title = item.get("title", "")
        article = item.get("article_no") or ""
        print(f"{idx}. {title} {article}".strip())
PY
done
