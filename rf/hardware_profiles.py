## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

# Centralized library of physical IC package geometric land dimensions
PACKAGE_FOOTPRINTS = {
    "SOT-89-3": {
        "pads": [
            ["pad", "", "smd", "rect", ["at", -1.5, 2.0], ["size", 0.65, 1.5]],
            ["pad", "", "smd", "rect", ["at", 0.0, 1.0], ["size", 1.8, 3.5]],
            ["pad", "", "smd", "rect", ["at", 1.5, 2.0], ["size", 0.65, 1.5]]
        ],
        "vias": [(-0.4, -0.3), (0.4, -0.3), (-0.4, 0.7), (0.4, 0.7), (-0.4, 1.7), (0.4, 1.7)],
        "via_drill": 0.3,
        "via_size": 0.6
    }
}

# Centralized manufacturer specification profiles for targeted RF MMIC silicon
DEVICE_PROFILES = {
    "PHA-13HLN+": {
        "v_d": 8.0,
        "i_d": 0.234,
        "theta_jc": 29.3,
        "package": "SOT-89-3",
        "schematic_symbol": "Amplifier_RF:GALI-74+",
        "sourcing": {
            "mpn": "PHA-13HLN+",
            "digikey": "PHA-13HLN+-ND",
            "mouser": "Mini-Circuits PHA-13HLN+"
        }
    }
}
