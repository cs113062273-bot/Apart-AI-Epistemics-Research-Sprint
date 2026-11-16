#!/usr/bin/env bash
# Recompute every number and figure in the paper from the logged model outputs (no model calls), then build the PDF.
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python}
$PY scripts/run_verifiers.py --set contrast --split test --score > /dev/null
$PY scripts/run_verifiers.py --set contrast_long --split test --score > /dev/null
$PY scripts/run_verifiers.py --set heldout --score > /dev/null
$PY scripts/item_analysis.py --set contrast --split test > /dev/null
$PY scripts/item_analysis.py --set heldout > /dev/null
$PY scripts/qbr_certificates.py > /dev/null
for s in discovery replication; do
  $PY scripts/analyze_natural.py --set $s > /dev/null
  $PY scripts/natural_statistics.py --set $s > /dev/null
done
$PY scripts/gold_check.py > /dev/null
$PY scripts/masked_reaudit.py compare > /dev/null
$PY scripts/make_figures.py
$PY scripts/make_paper_numbers.py
if command -v tectonic > /dev/null; then (cd paper && tectonic -X compile main.tex && mv -f main.pdf supported-is-not-applicable.pdf); fi
