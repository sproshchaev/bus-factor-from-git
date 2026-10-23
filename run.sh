#!/usr/bin/env bash
# Считает отчёт по готовым данным из data/ и сверяет его с expected.txt.
# Код выхода 1, если хотя бы одна цифра разошлась с эталоном.
set -euo pipefail
cd "$(dirname "$0")"

python3 bus_factor.py data/*.tsv > out.txt
cat out.txt

if diff -u expected.txt out.txt; then
  echo
  echo "OK: отчёт совпал с expected.txt"
else
  echo
  echo "FAIL: отчёт разошёлся с expected.txt" >&2
  exit 1
fi
