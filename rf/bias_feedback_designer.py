## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

from termcolor import colored


class BiasFeedbackDesigner:
    def __init__(self, loader_instance, z0=50):
        """
        Initializes the Active Bias and Loop Feedback calculation engine.
        """
        self.loader = loader_instance
        self.z0 = z0

    def design_feedback_loop(self):
        mid_index = len(self.loader.network) // 2
        actual_gain_db = self.loader.network.s21.s_db[mid_index]
        f_min = self.loader.f_min_mhz * 1e6
        a_v = 10 ** (actual_gain_db / 20.0)
        r_fb_ideal = self.z0 * (a_v + 1)
        c_fb_min = 1 / (2 * math.pi * f_min * (r_fb_ideal / 10.0))
        print("\n" + "=" * 75)
        print(" 3. ACTIVE NEGATIVE FEEDBACK NETWORK LINE")
        print("=" * 75)
        print(f"[] Detected Mid-band Device Gain ($S_{21}$): {actual_gain_db.item():.1f} dB")
        print(f"[+] Calculated Target Loop $R_{{fb}}$: {r_fb_ideal.item():.1f} Ω")
        print(f"[+] Calculated Loop Minimum $C_{{fb}}$: {(c_fb_min * 1e12).item():.1f} pF")
        print("-" * 75)
        print("[TIP] Use these starting values to flatten gain variations over frequency.")
        print("=" * 75)

    def design_active_dc_bias(self, v_cc=12.0, v_d=8.0, i_d=0.234):
        """
        Calculates dropping resistor resistance and power rating overhead
        requirements for safe system rail interfacing.
        """
        print("\n" + "=" * 75)
        print(" 4. DC COMPONENT BIAS RUNTIME DROPPING ANALYSIS")
        print("=" * 75)
        print(f"[*] System Rail Input Voltage (Vcc):     {v_cc:.2f} V")
        print(f"[*] Target Device Voltage Node (Vd):     {v_d:.2f} V")
        print(f"[*] Nominal Target Device Current (Id):  {i_d * 1000:.1f} mA")
        print("-" * 75)

        if v_cc <= v_d:
            print(
                colored(
                    f"[Critical] Bias Failure: Supply Rail Vcc ({v_cc}V) must be higher than Vd ({v_d}V)!",
                    "red",
                    attrs=["bold"],
                )
            )
            return None

        v_drop = v_cc - v_d
        r_bias_ideal = v_drop / i_d
        p_dissipated = (i_d**2) * r_bias_ideal
        p_safety_rating = p_dissipated * 2.0  # 100% engineering safety headroom profile

        standard_e24 = [
            1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9,
            4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1, 10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27,
        ]
        closest_base = min(standard_e24, key=lambda x: abs(x - r_bias_ideal))

        print(f"[+] Ideal Target Drop Resistance Rbias:  {r_bias_ideal:.2f} \u03a9")
        print(f"[+] Target Nearest Standard E24 Value:   {closest_base:.1f} \u03a9")
        print(f"[+] Active Heat Dissipation Load:        {p_dissipated:.2f} Watts")
        print(
            colored(
                f"[!] Minimum Specified Resistor Rating:   >= {p_safety_rating:.2f} Watts (Use a 2W or 3W Component Package)",
                "yellow",
                attrs=["bold"],
            )
        )
        print("-" * 75)
        print("[BYPASS SUGGESTIONS] Connect three parallel 4.7 uF, 0.1 uF, and 100 pF capacitors")
        print("                    at the top node of the RF Choke to clean incoming ripple noise.")
        print("=" * 75)
        return r_bias_ideal
