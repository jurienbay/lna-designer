## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

from termcolor import colored


class ChokeBlockDesigner:
    def __init__(self, loader_instance, z0=50):
        """Initializes the bias choking and decoupling calculator component block."""
        self.loader = loader_instance
        self.z0 = z0

    @staticmethod
    def generate_e_series(series_number=12):
        """
        Generates the standard EIA E-series multipliers dynamically using 10^(n/series).
        Default is E12 (10%, 12 values per decade). Can also pass 24, 96, etc.
        """
        return [round(10 ** (i / series_number), 2) for i in range(series_number)]

    @staticmethod
    def get_e_series_values_in_range(v_min, v_max, series_number=12):
        """
        Dynamically populates all nominal components values across multiple decades
        falling strictly between a structural minimum and maximum threshold.
        """
        base_values = ChokeBlockDesigner.generate_e_series(series_number)

        # Determine decade boundaries based on min/max limits
        dec_start = math.floor(math.log10(v_min)) if v_min > 0 else -12
        dec_end = math.ceil(math.log10(v_max)) if v_max > 0 else 3

        matches = []
        for decade in range(dec_start, dec_end + 1):
            multiplier = 10 ** decade
            for val in base_values:
                actual_val = val * multiplier
                # Floating point rounding adjustment
                actual_val = round(actual_val, 3 if decade < 0 else 1)
                if v_min <= actual_val <= v_max:
                    matches.append(actual_val)
        return sorted(set(matches))

    def get_dynamic_smd_parasitics(self, pkg_string):
        """
        Derives parasitic elements (ESL/CP) directly from standard metric/imperial sizes.
        Uses a generalized scaling approximation based on volumetric chip dimensions.
        """
        # Dictionary format: 'Imperial_Name': (Length_mm, Width_mm)
        dimensions = {
            "1210": (3.2, 2.5),
            "1206": (3.2, 1.6),
            "0805": (2.0, 1.25),
            "0603": (1.6, 0.8),
            "0402": (1.0, 0.5),
            "0201": (0.6, 0.3)
        }

        if pkg_string not in dimensions:
            raise ValueError(f"Unknown package footprint configuration: {pkg_string}")

        l, w = dimensions[pkg_string]
        # Parasitic Inductance (ESL) approximates to ~1 nH per mm of package length
        esl_nh = l * 0.35 + 0.2
        # Parasitic Parallel Capacitance scales roughly with terminal landpad area surface interaction
        cp_pf = (l * w) * 0.2 + 0.1

        return {"esl_nh": round(esl_nh, 2), "cp_pf": round(cp_pf, 2)}

    def design_bias_choke(self, srf_safety_factor=1.5, evaluation_packages=None):
        if evaluation_packages is None:
            evaluation_packages = ["1210", "1206", "0805", "0603", "0402", "0201"]

        # Check if the loader variables are already scaled to raw Hz or sitting at a fractional decade
        f_min_raw = self.loader.f_min_mhz
        f_max_raw = self.loader.f_max_mhz
        # If the values are small (e.g. < 2000), they are in MHz, so scale by 1e6.
        # If they are already raw large integers (e.g. > 1e5), leave them as pure Hz.
        f_min = f_min_raw if f_min_raw > 1e5 else f_min_raw * 1e6
        f_max = f_max_raw if f_max_raw > 1e5 else f_max_raw * 1e6

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
        for pkg in evaluation_packages:
            parasitics = self.get_dynamic_smd_parasitics(pkg)
            cp = parasitics["cp_pf"] * 1e-12
            l_max = 1 / (4 * (math.pi**2) * (target_srf_min**2) * cp)

            if l_min <= l_max:
                status = "👍 VALID"
                if selected_package is None:
                    selected_package, best_l_max = pkg, l_max
            else:
                status = "😞 INVALID (SRF violation)"

            print(f"SMD {pkg:<5} | Calc Cp: {parasitics['cp_pf']:>4.2f} pF | Max L Allowed: {l_max * 1e6:>7.2f} uH | {status}")

        if selected_package:
            print(colored(f"\n[+] Recommended Footprint: {selected_package}", "green", attrs=["bold"]))
            suggestions = ChokeBlockDesigner.get_e_series_values_in_range(l_min * 1e6, best_l_max * 1e6, series_number=12)
            print(f"    Sourcing window: {l_min * 1e6:.2f} uH to {best_l_max * 1e6:.2f} uH")
            if suggestions:
                print(f"    Dynamic E12 Values: {', '.join([f'{v} uH' for v in suggestions])}")
        else:
            print(colored("\n[!] Wideband Contradiction: Single-stage choke cannot clear SRF.", "yellow"))
            print(colored("[*] Executing Automated Multi-Stage Bias Network Synthesis...", "cyan"))

            # Synthesize Stage 1: Target the smallest package available to handle upper frequency boundaries
            stage1_pkg = "0402"
            p1 = self.get_dynamic_smd_parasitics(stage1_pkg)
            l1_max = 1 / (4 * (math.pi**2) * (target_srf_min**2) * (p1["cp_pf"] * 1e-12))

            # Select the optimal standard component value right at the threshold ceiling boundary
            stage1_suggestions = ChokeBlockDesigner.get_e_series_values_in_range(l1_max * 1e6 * 0.5, l1_max * 1e6, series_number=12)
            l1_val_uh = stage1_suggestions[-1] if stage1_suggestions else (l1_max * 1e6 * 0.9)

            # Synthesize Stage 2: Deduct Stage 1 value and compute bulk low-freq complement bounds
            l2_req_uh = (l_min * 1e6) - l1_val_uh

            # Stage 2's SRF line only needs to clear where Stage 1's reactance takes over (lower frequency region)
            stage2_pkg = "1206"

            print(colored(f"\n[+] Synthesized 2-Stage Cascaded Bias Choke Network:", "green", attrs=["bold"]))
            print(f"    - Stage 1 (High-Freq Isolation): {l1_val_uh:.2f} uH [SMD {stage1_pkg}] (Clears Upper SRF Floor)")
            print(f"    - Stage 2 (Low-Freq Bulk):       {l2_req_uh:.2f} uH [SMD {stage2_pkg}] (Provides Base Reactance)")
            print(f"    - Placement Topology Hint: Locate the tiny {stage1_pkg} package immediately next to the RF signal trace path node.")

    def design_dc_block(self, evaluation_packages=None):
        if evaluation_packages is None:
            evaluation_packages = ["1210", "1206", "0805", "0603", "0402"]

        # Apply identical scale check protection bounds
        ##print(self.loader.f_min_mhz)
        f_min_raw = self.loader.f_min_mhz
        f_center_raw = self.loader.f_center_mhz
        f_min = f_min_raw if f_min_raw > 1e5 else f_min_raw * 1e6
        f_center = f_center_raw if f_center_raw > 1e5 else f_center_raw * 1e6

        c_min = 1 / (2 * math.pi * f_min * (self.z0 / 10))

        print("\n" + "=" * 75)
        print(" 2. DC-BLOCK / COUPLING CAPACITOR SELECTION")
        print("=" * 75)
        print(f"[*] Target Freq: {self.loader.f_center_mhz:.1f} MHz | Min Cap Req: {c_min * 1e12:.1f} pF")
        print("-" * 75)

        for pkg in evaluation_packages:
            parasitics = self.get_dynamic_smd_parasitics(pkg)
            esl = parasitics["esl_nh"] * 1e-9
            c_ideal = 1 / (4 * (math.pi**2) * (f_center**2) * esl)

            # Dynamically look for any valid target E12 capacitor nearby
            search_min = max(c_min * 1e12, c_ideal * 1e12 * 0.5)
            search_max = c_ideal * 1e12 * 1.5
            available_caps = ChokeBlockDesigner.get_e_series_values_in_range(search_min, search_max, series_number=12)

            if available_caps:
                closest_val = min(available_caps, key=lambda x: abs(x - (c_ideal * 1e12)))
                status = f"👍 Optimal Dynamic Value: {closest_val} pF"
            else:
                # If no matching standard values in optimal range, fallback to check absolute min boundary
                absolute_check = ChokeBlockDesigner.get_e_series_values_in_range(c_min * 1e12, c_min * 1e12 * 10, series_number=12)
                closest_val = absolute_check[0] if absolute_check else "N/A"
                status = f"😞 Ideal SRF out of range. Closest safe structural passband Cap: {closest_val} pF"

            print(f"SMD {pkg:<5} | Calc ESL: {parasitics['esl_nh']:.2f} nH | Center SRF Target C: {c_ideal * 1e12:>7.1f} pF | {status}")
