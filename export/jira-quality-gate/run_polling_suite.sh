#!/usr/bin/env bash
# Run all TaxOps polling automations in one job.
# - Always runs every script (one failure does not skip the rest).
# - Exits 1 if any script failed (GitHub shows the workflow as failed).
# - On failure: posts one Slack/Zapier message listing failed scripts + run link.
# - Writes $GITHUB_STEP_SUMMARY so the Actions run page shows pass/fail at a glance.
set -u
cd "$(dirname "$0")"

RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-unknown}"

declare -a FAIL_LINES=()

run_one() {
  local label="$1"
  local script="$2"
  if python "$script"; then
    echo "[ok] $label"
  else
    local ec=$?
    echo "[FAIL] $label (exit $ec)" >&2
    FAIL_LINES+=("$label — $script (exit $ec)")
  fi
}

run_one "A1 WFO accountability"      "a1_wfo_accountability.py"
run_one "A2 Quality gate"          "a2_quality_gate.py"
run_one "A3 Label quadrant"        "a3_label_quadrant.py"
run_one "A4 Sign-off mismatch"     "a4_signoff_mismatch.py"
run_one "A7 New scope detector"    "a7_new_scope.py"
run_one "A8 Auto ownership label"  "a8_auto_label.py"
run_one "A9 Bad ticket notifier"   "a9_bad_ticket.py"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "## TaxOps polling"
    echo ""
    if [[ ${#FAIL_LINES[@]} -eq 0 ]]; then
      echo "All polling scripts completed successfully."
    else
      echo "### Failed (${#FAIL_LINES[@]})"
      for line in "${FAIL_LINES[@]}"; do
        echo "- ${line}"
      done
      echo ""
      echo "[Open this workflow run](${RUN_URL})"
    fi
  } >>"${GITHUB_STEP_SUMMARY}"
fi

if [[ ${#FAIL_LINES[@]} -gt 0 ]]; then
  printf '%s\n' "${FAIL_LINES[@]}" >/tmp/taxops_polling_failures.txt
  export RUN_URL
  python3 <<'PY'
import json
import os
import urllib.request

url = os.environ.get("SLACK_WEBHOOK_OPS", "").strip()
run_url = os.environ.get("RUN_URL", "")
if not url:
    raise SystemExit(0)
with open("/tmp/taxops_polling_failures.txt", encoding="utf-8") as f:
    lines = [ln.strip() for ln in f if ln.strip()]

body = (
    ":rotating_light: *TaxOps polling: one or more scripts failed*\n"
    + "\n".join("• " + ln for ln in lines)
    + f"\n<{run_url}|Open GitHub Actions run>"
)
payload = json.dumps({"message": body}).encode("utf-8")
req = urllib.request.Request(
    url,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
urllib.request.urlopen(req, timeout=30)
PY
  exit 1
fi

exit 0
