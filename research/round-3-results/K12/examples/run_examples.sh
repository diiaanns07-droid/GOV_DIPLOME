#!/bin/sh
# Rebuild both example inputs and reports. No network. Run from research/round-3-results/K12/.
set -e
python3 examples/make_examples.py
python3 energy_import/k12_energy_import.py examples/bdg1_gb_2014_2015/input.csv \
  --window 2014-12-01:2015-11-30 --out examples/bdg1_gb_2014_2015/report \
  --title "BDG1, Великобритания, 74 школы, Dec 2014 – Nov 2015 (НЕ Шымкент, НЕ Астана)"
python3 energy_import/k12_energy_import.py examples/synthetic_cases/input.csv \
  --window 2025-01-01:2025-12-31 --out examples/synthetic_cases/report \
  --title "SYNTHETIC: проверочные случаи валидатора (не здания Шымкента и Астаны)"
