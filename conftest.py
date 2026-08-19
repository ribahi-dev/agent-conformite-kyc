"""Rend le package `src` importable depuis les tests, quel que soit le repertoire d'appel."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
