## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import skrf as rf


class SParameterLoader:
    def __init__(self, s2p_file_path=None):
        """
        Initializes the designer by loading the Mini-Circuits Touchstone .s2p data.
        """
        self.network = None
        self.f_min_mhz = 10.0
        self.f_max_mhz = 1000.0
        self.f_center_mhz = 505.0
        if s2p_file_path:
            self.load(s2p_file_path)

    def load(self, s2p_file_path, f_min_override=None, f_max_override=None):
        """Loads or updates the Touchstone file profile dynamically with optional band window clipping."""
        self.network = rf.Network(s2p_file_path)
        native_min = self.network.frequency.start / 1e6
        native_max = self.network.frequency.stop / 1e6

        self.f_min_mhz = f_min_override if f_min_override is not None else native_min
        self.f_max_mhz = f_max_override if f_max_override is not None else native_max
        self.f_center_mhz = (self.f_min_mhz + self.f_max_mhz) / 2
        return self.network
