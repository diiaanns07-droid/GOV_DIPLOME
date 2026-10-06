"""Подключает проверенные модули r8 K09 (research/round-8-results/K09/k09plan) только для чтения."""
import sys
from pathlib import Path

R8 = Path(__file__).resolve().parents[3] / "round-8-results/K09"
if str(R8) not in sys.path:
    sys.path.insert(0, str(R8))
