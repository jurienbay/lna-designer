## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

from typing import ClassVar

# Single global source of truth for all mechanical and electrical substrate properties
SUBSTRATE_PROFILES : ClassVar[dict[str, dict[str, float]]] = {
    "FR-4 Standard (1.6mm)": {"er": 4.2, "h": 1.6, "h_mm": 1.6, "h_mils": 62.0},
    "Rogers RO3003 (10mil)": {"er": 3.00, "h": 0.254, "h_mm": 0.254, "h_mils": 10.0},
    "Rogers RO4003C (20mil)": {"er": 3.38, "h": 0.508, "h_mm": 0.508, "h_mils": 20.0},
    "Rogers RO4350B (30mil)": {"er": 3.48, "h": 0.762, "h_mm": 0.762, "h_mils": 30.0},
}
