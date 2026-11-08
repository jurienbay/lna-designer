## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

import numpy as np
from termcolor import colored


class TransmissionLineSuite:
    # Retain the global material matrix within the transmission line calculation scope
    SUBSTRATE_PROFILES = {
        "FR-4 Standard (1.6mm)": {"er": 4.2, "h_mils": 62.0},
        "Rogers RO3003 (10mil)": {"er": 3.00, "h_mils": 10.0},
        "Rogers RO4003C (20mil)": {"er": 3.38, "h_mils": 20.0},
        "Rogers RO4350B (30mil)": {"er": 3.48, "h_mils": 30.0},
    }

    def __init__(self, loader_instance, z0=50):
        """
        Initializes the transmission line and matching network synthesis module.
        """
        self.loader = loader_instance
        self.z0 = z0

    def calculate_pcb_microstrip(self, board_type="FR-4 Standard (1.6mm)", t_oz=1.0):
        profile = self.SUBSTRATE_PROFILES.get(board_type, self.SUBSTRATE_PROFILES["FR-4 Standard (1.6mm)"])
        er = profile["er"]
        h = profile["h_mils"]
        t = t_oz * 1.37

        target_zo = self.z0
        best_w = 0.0
        min_err = float("inf")

        for w_check in np.linspace(1, 200, 2000):
            zo_calc = (87.0 / math.sqrt(er + 1.41)) * math.log((5.98 * h) / (0.8 * w_check + t))
            if abs(zo_calc - target_zo) < min_err:
                min_err = abs(zo_calc - target_zo)
                best_w = w_check

        print("\n" + "=" * 75)
        print(f" 6. PCB COPPER MICROSTRIP TRACE SYNTHESIS ({board_type.upper()})")
        print("=" * 75)
        print(f"[*] Substrate Dielectric Constant (Er):  {er:.2f}")
        print(f"[*] Dielectric Substrate Height (h):    {h:.1f} Mils")
        print("-" * 75)
        print(colored(f"[+] Mandatory Trace Design Width:        {best_w:.1f} Mils", "cyan", attrs=["bold"]))
        print(f"    --> Metric Conversion Target:        {(best_w * 0.0254):.2f} mm Trace Width Layout")
        print("=" * 75)
        return best_w

    def calculate_pcb_gcpw(self, board_type="FR-4 Standard (1.6mm)", t_oz=1.0, default_gap_mils=10.0):
        import scipy.special as sp
        profile = self.SUBSTRATE_PROFILES.get(board_type, self.SUBSTRATE_PROFILES["FR-4 Standard (1.6mm)"])
        er = profile["er"]
        h = profile["h_mils"]
        t = t_oz * 1.37
        s = default_gap_mils

        target_zo = self.z0
        best_w, best_er_eff = 0.0, 1.0
        min_err = float("inf")

        for w_check in np.linspace(1, 200, 2000):
            k1 = w_check / (w_check + 2 * s)
            k1_prime = math.sqrt(1.0 - k1**2)
            try:
                k_ratio1 = sp.ellipk(k1) / sp.ellipk(k1_prime)
                k2 = (math.sinh(math.pi * w_check / (4.0 * h))) / (math.sinh(math.pi * (w_check + 2 * s) / (4.0 * h)))
                k2_prime = math.sqrt(1.0 - k2**2)
                k_ratio2 = sp.ellipk(k2) / sp.ellipk(k2_prime)

                er_eff = (1.0 + er * (k_ratio2 / k_ratio1)) / (1.0 + (k_ratio2 / k_ratio1))
                zo_calc = (60.0 * math.pi / math.sqrt(er_eff)) / (k_ratio1 + k_ratio2)
                zo_calc *= 1.0 - (t / (2.0 * s))

                if abs(zo_calc - target_zo) < min_err:
                    min_err = abs(zo_calc - target_zo)
                    best_w = w_check
                    best_er_eff = er_eff
            except:
                continue

        print("\n" + "=" * 75)
        print(f" 6B. GCPW WAVEGUIDE STRUCTURE SYNTHESIS ({board_type.upper()})")
        print("=" * 75)
        print(f"[+] Conductor Center Trace Width (W):    {best_w:.1f} Mils")
        print(f"    --> Structure Effective Er (Eeff):   {best_er_eff:.3f}")
        print("=" * 75)
        return best_w, s

    def design_lc_matching(self, target_freq_mhz=None):
        if target_freq_mhz is None:
            target_freq_mhz = self.loader.f_center_mhz
        freq_hz = target_freq_mhz * 1e6
        idx = np.argmin(np.abs(self.loader.network.f - freq_hz))
        actual_freq_mhz = self.loader.network.f[idx] / 1e6
        omega = 2 * math.pi * freq_hz

        print("\n" + "=" * 75)
        print(f" 7. AUTOMATED PORT L-C MATCHING SYNTHESIS (@ {actual_freq_mhz:.1f} MHz)")
        print("=" * 75)

        for port_name, s_param in [
            ("Input Matching (S11)", self.loader.network.s[idx, 0, 0]),
            ("Output Matching (S22)", self.loader.network.s[idx, 1, 1]),
        ]:
            gamma = s_param
            if abs(1.0 - gamma) < 1e-4:
                gamma = gamma * 0.999
            z_port = self.z0 * (1.0 + gamma) / (1.0 - gamma)
            r_p, x_p = np.real(z_port), np.imag(z_port)
            print(colored(f"[Node] {port_name}:", "cyan", attrs=["bold"]))
            print(f"       Raw Port Impedance: {r_p:.2f} + j({x_p:.2f}) \u03a9")

            r = r_p / self.z0
            x = x_p / self.z0

            try:
                if r > 1.0:
                    b_shunt = math.sqrt((r - 1.0) / 1.0) / r
                    x_series = math.sqrt(r - 1.0) - x
                else:
                    b_shunt = math.sqrt((1.0 - r) / r)
                    x_series = (1.0 / b_shunt) - x

                b_actual = b_shunt / self.z0
                x_actual = x_series * self.z0

                if b_actual >= 0:
                    comp1_str = f"Shunt C: {(b_actual / omega * 1e12):.1f} pF"
                else:
                    comp1_str = f"Shunt L: {(-1.0 / (b_actual * omega) * 1e6):.2f} uH"

                if x_actual >= 0:
                    comp2_str = f"Series L: {(x_actual / omega * 1e6):.2f} uH"
                else:
                    comp2_str = f"Series C: {(-1.0 / (x_actual * omega) * 1e12):.1f} pF"

                print(f"       -> Component 1 (Device Side): {comp1_str}")
                print(f"       -> Component 2 (Source/Load Side): {comp2_str}")
            except Exception as e:
                print(f"       -> [Error] Matrix boundary limit hit for this impedance node: {e}")
            print("-" * 75)
        print("=" * 75)

    def calculate_microstrip_electrical_length(self, h_mils=62.0, er=4.2, target_deg=90.0, target_freq_mhz=None):
        if target_freq_mhz is None:
            target_freq_mhz = self.loader.f_center_mhz
        freq_hz = target_freq_mhz * 1e6
        c_speed = 299792458
        w_h_ratio = 50.0 / h_mils
        er_eff = ((er + 1) / 2) + ((er - 1) / 2) * (1 / math.sqrt(1 + 12 / w_h_ratio))
        lambda_free = c_speed / freq_hz
        lambda_guided = lambda_free / math.sqrt(er_eff)
        physical_length_mm = (target_deg / 360.0) * lambda_guided * 1000

        print("\n" + "=" * 75)
        print(" 8. PCB MICROSTRIP TRANSMISSION LINE WAVELENGTH LENGTHS")
        print("=" * 75)
        print(f"[*] Evaluation Frequency Node:          {target_freq_mhz:.1f} MHz")
        print(f"[*] Effective Dielectric Scale (Eeff):   {er_eff:.3f}")
        print(f"[*] Total Guided Wavelength (\u03bb):       {(lambda_guided * 1000):.2f} mm")
        print("-" * 75)
        print(colored(f"[+] Quarter-Wave Isolation (\u03bb/4 - 90\u00b0): {physical_length_mm:.2f} mm physical length", "cyan", attrs=["bold"]))
        print("=" * 75)
        return er_eff, physical_length_mm

    def design_fixed_attenuator_pad(self, target_attn_db=3.0):
        print("\n" + "=" * 75)
        print(f" 9. INLINE SYSTEM GAIN PROTECTION ATTENUATOR PAD ({target_attn_db:.1f} dB Target)")
        print("=" * 75)
        k = 10 ** (target_attn_db / 20.0)
        r_shunt = self.z0 * ((k + 1) / (k - 1))
        r_series = self.z0 * ((k**2 - 1) / (2 * k))

        print(f"[*] Matched Core Impedance Target (Z0): {self.z0} \u03a9")
        print(f"[+] Shunt Side Ground Resistors (R1, R3): {r_shunt:.1f} \u03a9")
        print(f"[+] Series Inline Bridge Resistor (R2):   {r_series:.1f} \u03a9")
        print("-" * 75)
        print("=" * 75)
