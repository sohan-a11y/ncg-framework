"""Conftest to add project root to sys.path for hardware/model imports."""
import sys
from pathlib import Path

# Add project root and software dir to sys.path so hardware/model imports work
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))