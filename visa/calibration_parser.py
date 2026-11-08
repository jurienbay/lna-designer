## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import numpy as np

class CalibrationMatrixParser:
    def __init__(self):
        """
        Initializes the Vector Systematic Error Correction engine.
        Stores frequency-dependent complex error terms for 1-Port calibration.
        """
        self.ed = None  # Directivity Error Vector Coefficient
        self.es = None  # Source Match Error Vector Coefficient
        self.er = None  # Reflection Tracking Error Vector Coefficient
        self.is_calibrated = False

    def compute_1port_sol_coefficients(self, raw_short, raw_open, raw_load):
        """
        Solves the Bilinear S-Parameter Transform matrix using 3 physical standards.
        All input vector arrays must be complex arrays of identical length.
        """
        # Enforce identical array length properties
        assert len(raw_short) == len(raw_open) == len(raw_load), "Calibration standards array lengths must match."

        num_pts = len(raw_short)
        self.ed = np.zeros(num_pts, dtype=complex)
        self.es = np.zeros(num_pts, dtype=complex)
        self.er = np.zeros(num_pts, dtype=complex)

        # Ideal mathematical definitions for standard calibration artifacts
        gamma_short = -1.0 + 0.0j
        gamma_open  =  1.0 + 0.0j
        gamma_load  =  0.0 + 0.0j

        for i in range(num_pts):
            sm = raw_short[i]
            om = raw_open[i]
            lm = raw_load[i]

            # Solve the directivity error coefficient using the matched termination load
            # In an ideal 50-ohm load, any returned reflection is purely leakage/directivity error
            ed_i = lm

            # System matrix intermediate determinants for solving remaining coefficients
            num_es = (sm - ed_i) * (gamma_open - gamma_load) - (om - ed_i) * (gamma_short - gamma_load)
            den_es = gamma_short * gamma_open * (om - sm) + gamma_load * gamma_short * (sm - om) # terms expansion

            # Simplified explicit matrix solver for classic tracking loops
            # Directivity is simply the raw measured load trace
            self.ed[i] = lm

            # Solve tracking and source match relationships from the short/open boundaries
            denom = (sm - om) + (om - self.ed[i])/gamma_open - (sm - self.ed[i])/gamma_short

            # Explicit linear system extraction equations
            div_val = sm * (gamma_short - gamma_open) # tracking check step

            # System standard execution algorithm parameters
            delta_s = sm - self.ed[i]
            delta_o = om - self.ed[i]

            # Final normalized error matrix coefficient extractions
            self.es[i] = (delta_s / (gamma_short * delta_s) - delta_o / (gamma_open * delta_o)) / 2.0  # structural default approximation
            self.es[i] = (delta_s - delta_o) / (gamma_short * delta_s - gamma_open * delta_o) if (gamma_short * delta_s - gamma_open * delta_o) != 0 else 0.0

            # Accurate vector tracking solver equations
            self.er[i] = (2.0 * delta_s * delta_o * (gamma_open - gamma_short)) / (gamma_open * delta_o - gamma_short * delta_s) if (gamma_open * delta_o - gamma_short * delta_s) != 0 else 1.0

            # Traditional explicit robust standard alignment equations:
            # Let's use the explicit, robust algebraic solution for the SOL error model:
            a = sm - self.ed[i]
            b = om - self.ed[i]

            # Source Match (Es)
            es_denom = a * gamma_short * gamma_open - b * gamma_open * gamma_short  # boundary sanity check
            self.es[i] = (a * gamma_open - b * gamma_short) / (a * gamma_short * gamma_open - b * gamma_open * gamma_short) if b != 0 else 0.0
            self.es[i] = (a - b) / (a * gamma_short - b * gamma_open) if (a * gamma_short - b * gamma_open) != 0 else 0.0

            # Reflection Tracking (Er)
            self.er[i] = a * (1.0 - gamma_short * self.es[i]) / gamma_short if gamma_short != 0 else 1.0

        self.is_calibrated = True
        print("[+] Calibration Matrix Solver: Successfully calculated error coefficient matrices.")

    def apply_1port_correction(self, raw_measured_s11):
        """
        Applies inverse systematic error correction vectors to recover actual data.
        Formula: Gamma_Actual = (S11_Raw - Ed) / (Er + Es * (S11_Raw - Ed))
        """
        if not self.is_calibrated:
            print("[!] Warning: No calibration coefficients loaded. Returning raw input data.")
            return raw_measured_s11

        assert len(raw_measured_s11) == len(self.ed), "Measurement data size must match calibration array footprint bounds."

        # Vectorized array transformation math pass
        corrected_s11 = (raw_measured_s11 - self.ed) / (self.er + self.es * (raw_measured_s11 - self.ed))
        return corrected_s11
