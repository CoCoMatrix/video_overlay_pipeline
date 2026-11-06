#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -lt 1 ]]; then echo "Usage: run.sh prepare|ocr|infer|report|serve [arguments]"; exit 2; fi
stage="$1"; shift
case "$stage" in
prepare) exec "${CPU_PYTHON:-python3}" "$REPO/scripts/prepare.py" "$@";;
ocr) exec "${OCR_PYTHON:-python3}" "$REPO/scripts/prepare_ocr_regions.py" "$@";;
infer) exec "${MODEL_PYTHON:-python3}" "$REPO/scripts/run_dataset.py" "$@";;
report) exec "${CPU_PYTHON:-python3}" "$REPO/scripts/report.py" "$@";;
serve) exec "${CPU_PYTHON:-python3}" "$REPO/scripts/serve.py" "$@";;
*) echo "Unknown stage: $stage" >&2; exit 2;;
esac
