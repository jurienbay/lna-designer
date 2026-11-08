## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

from termcolor import colored


class ChokeBlockDesigner:
    def __init__(self, loader_instance, z0=50):
        """
        Initializes the bias choking and decoupling calculator component block.
        """
        self.loader = loader_instance
        self.z0 = z0

    def design_bias_choke(self, srf_safety_factor=1.5):
        package_constraints = {
            "1210": {
                "cp_pf": 2.2,
                "desc": "Large wirewound power inductor / High current capacity",
            },
            "1206": {"cp_pf": 1.5, "desc": "Standard wirewound choke / Balanced power"},
            "0805": {"cp_pf": 0.8, "desc": "Compact multilayer ferrite / Mod. current"},
            "0603": {
                "cp_pf": 0.3,
                "desc": "Ultra-small ceramic chip / Low current, high-SRF",
            },
        }
        f_min, f_max = self.loader.f_min_mhz * 1e6, self.loader.f_max_mhz * 1e6
        target_xl_min = 10 * self.z0
        target_srf_min = srf_safety_factor * f_max
        l_min = target_xl_min / (2 * math.pi * f_min)

        print("\n" + "=" * 75)
        print(" 1. RF BIAS CHOKE PACKAGING DESIGN")
        print("=" * 75)
        print(f"[*] Target Inductance Required: >= {l_min * 1e6:.2f} uH")
        print(f"[*] Minimum Required SRF Line:  >= {target_srf_min / 1e6:.1f} MHz")
        print("-" * 75)

        selected_package, best_l_max = None, 0
        for pkg, specs in package_constraints.items():
            cp = specs["cp_pf"] * 1e-12
            l_max = 1 / (4 * (math.pi**2) * (target_srf_min**2) * cp)

            if l_min <= l_max:
                status = f"👍 VALID ({specs['desc']})"
                if selected_package is None:
                    selected_package, best_l_max = pkg, l_max
            else:
                status = "😞 INVALID (SRF violation)"
            print(
                f"{pkg:<10} | {specs['cp_pf']:>4.1f} pF | Max L Allowed: {l_max * 1e6:>7.2f} uH | {status}"
            )

        if selected_package:
            print(colored(f"\n[+] Recommended Footprint: {selected_package}", "green", attrs=["bold"]))
            standard_values = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2, 10.0, 12.0, 15.0]
            suggestions = [v for v in standard_values if (l_min * 1e6) <= v <= (best_l_max * 1e6)]
            print(f"    Sourcing window: {l_min * 1e6:.2f} uH to {best_l_max * 1e6:.2f} uH")
            if suggestions:
                print(f"    Standard E12 Values: {', '.join([f'{v} uH' for v in suggestions])}")
        else:
            print(colored("\n[!] Design Warning: Single-stage choke cannot clear SRF. Consider a conical choke.", "red"))

    def design_dc_block(self):
        cap_package_constraints = {
            "1210": {"esl_nh": 1.2},
            "1206": {"esl_nh": 1.0},
            "0805": {"esl_nh": 0.8},
            "0603": {"esl_nh": 0.6},
            "0402": {"esl_nh": 0.4},
        }
        f_min, f_center = self.loader.f_min_mhz * 1e6, self.loader.f_center_mhz * 1e6
        c_min = 1 / (2 * math.pi * f_min * (self.z0 / 10))
        standard_pf = [10, 22, 47, 100, 220, 470, 1000, 2200, 4700, 10000]

        print("\n" + "=" * 75)
        print(" 2. DC-BLOCK / COUPLING CAPACITOR SELECTION")
        print("=" * 75)
        print(f"[*] Target Freq: {self.loader.f_center_mhz:.1f} MHz | Min Cap Req: {c_min * 1e12:.1f} pF")
        print("-" * 75)

        for pkg, specs in cap_package_constraints.items():
            esl = specs["esl_nh"] * 1e-9
            c_ideal = 1 / (4 * (math.pi**2) * (f_center**2) * esl)
            closest_val = min(standard_pf, key=lambda x: abs(x - (c_ideal * 1e12)))

            status = f"👍 Optimal: {closest_val} pF" if (closest_val * 1e-12) >= c_min else "😞 Too small for passband"
            print(f"SMD {pkg:<6} | ESL: {specs['esl_nh']:.1f} nH | Center SRF Target C: {c_ideal * 1e12:>7.1f} pF | {status}")
