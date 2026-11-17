"""Add a cost to the Studio's Costs page from the terminal.

    py -3.15 tools/log_cost.py <paid-to> "<what for>" <usd>
    py -3.15 tools/log_cost.py gemini "video render: 6 images + voice" 0.42
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import ledger  # noqa: E402

if len(sys.argv) != 4:
    sys.exit(__doc__)
ledger.record(sys.argv[1].lower(), sys.argv[2], float(sys.argv[3]), cap=False, note="logged from the terminal")
print(f"Logged ${float(sys.argv[3]):.2f} to {sys.argv[1]}: {sys.argv[2]}")
