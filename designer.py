#!/usr/bin/env python3

## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

import matplotlib.pyplot as plt
import numpy as np
import skrf as rf
from termcolor import colored

from rf import (
    SParameterLoader,
    serialize_pcb_layout,
    serialize_schematic,
    serialize_markdown_report,
    RFPerformanceVisualizer,
    StabilityAnalyzer,
    ChokeBlockDesigner,
    BiasFeedbackDesigner,
    ThermalAdvisor,
)


class MiniCircuitsLinearAmpDesigner:
    SUBSTRATE_PROFILES = {
        "FR-4 Standard (1.6mm)": {"er": 4.2, "h_mils": 62.0},
        "Rogers RO3003 (10mil)": {"er": 3.00, "h_mils": 10.0},
        "Rogers RO4003C (20mil)": {"er": 3.38, "h_mils": 20.0},
        "Rogers RO4350B (30mil)": {"er": 3.48, "h_mils": 30.0},
    }

    def __init__(self, loader_instance, z0=50):
        """
        Initializes the designer by loading the Mini-Circuits Touchstone .s2p data.
        """
        self.z0 = z0
        self.loader = loader_instance

    def calculate_pcb_microstrip(self, board_type="FR-4 Standard (1.6mm)", t_oz=1.0):
        """
        Synthesizes the exact microstrip trace width required to maintain a 50-Ohm match
        relative to the dynamically selected PCB material stackup profile.
        """
        profile = self.SUBSTRATE_PROFILES.get(
            board_type, self.SUBSTRATE_PROFILES["FR-4 Standard (1.6mm)"]
        )
        er = profile["er"]
        h = profile["h_mils"]
        t = t_oz * 1.37  # Convert copper oz weight to mils thickness

        target_zo = self.z0
        best_w = 0.0
        min_err = float("inf")

        for w_check in np.linspace(1, 200, 2000):
            zo_calc = (87.0 / math.sqrt(er + 1.41)) * math.log(
                (5.98 * h) / (0.8 * w_check + t)
            )
            if abs(zo_calc - target_zo) < min_err:
                min_err = abs(zo_calc - target_zo)
                best_w = w_check

        print("\n" + "=" * 75)
        print(f" 6. PCB COPPER MICROSTRIP TRACE SYNTHESIS ({board_type.upper()})")
        print("=" * 75)
        print(f"[*] Substrate Dielectric Constant (Er):  {er:.2f}")
        print(f"[*] Dielectric Substrate Height (h):    {h:.1f} Mils")
        print("-" * 75)
        print(
            colored(
                f"[+] Mandatory Trace Design Width:        {best_w:.1f} Mils",
                "cyan",
                attrs=["bold"],
            )
        )
        print(
            f"    --> Metric Conversion Target:        {(best_w * 0.0254):.2f} mm Trace Width Layout"
        )
        print("=" * 75)
        return best_w

    def calculate_pcb_gcpw(
        self, board_type="FR-4 Standard (1.6mm)", t_oz=1.0, default_gap_mils=10.0
    ):
        """
        Synthesizes Grounded Coplanar Waveguide configurations mapping to selected laminates.

        Synthesises the required center conductor width for a Grounded Coplanar
        Waveguide (GCPW) given a fixed manufacturing side-ground clearance gap.
        Uses conformal mapping approximations for 50-Ohm trace optimization.
        """
        import scipy.special as sp

        profile = self.SUBSTRATE_PROFILES.get(
            board_type, self.SUBSTRATE_PROFILES["FR-4 Standard (1.6mm)"]
        )
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
                k2 = (math.sinh(math.pi * w_check / (4.0 * h))) / (
                    math.sinh(math.pi * (w_check + 2 * s) / (4.0 * h))
                )
                k2_prime = math.sqrt(1.0 - k2**2)
                k_ratio2 = sp.ellipk(k2) / sp.ellipk(k2_prime)

                er_eff = (1.0 + er * (k_ratio2 / k_ratio1)) / (
                    1.0 + (k_ratio2 / k_ratio1)
                )
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
        """
        Synthesises discrete, lumped-element L-C matching networks to match
        un-matched S11 and S22 ports back to the system Z0 reference.
        """
        if target_freq_mhz is None:
            target_freq_mhz = self.loader.f_center_mhz

        freq_hz = target_freq_mhz * 1e6
        idx = np.argmin(np.abs(self.loader.network.f - freq_hz))
        actual_freq_mhz = self.loader.network.f[idx] / 1e6
        omega = 2 * math.pi * freq_hz

        print("\n" + "=" * 75)
        print(
            f" 7. AUTOMATED PORT L-C MATCHING SYNTHESIS (@ {actual_freq_mhz:.1f} MHz)"
        )
        print("=" * 75)

        for port_name, s_param in [
            ("Input Matching (S11)", self.loader.network.s[idx, 0, 0]),
            ("Output Matching (S22)", self.loader.network.s[idx, 1, 1]),
        ]:
            # Convert S-parameters to complex impedance
            gamma = s_param
            if abs(1.0 - gamma) < 1e-4:
                gamma = gamma * 0.999  # Prevent division by zero
            z_port = self.z0 * (1.0 + gamma) / (1.0 - gamma)
            r_p, x_p = np.real(z_port), np.imag(z_port)

            print(colored(f"[Node] {port_name}:", "cyan", attrs=["bold"]))
            print(f"       Raw Port Impedance: {r_p:.2f} + j({x_p:.2f}) \u03a9")

            # Normalise against system impedance
            r = r_p / self.z0
            x = x_p / self.z0

            try:
                # Matching algorithm assuming standard low-pass matching topology constraints
                if r > 1.0:
                    # Case A: Down-matching network structure
                    b_shunt = math.sqrt((r - 1.0) / 1.0) / r
                    x_series = math.sqrt(r - 1.0) - x
                else:
                    # Case B: Up-matching network structure
                    b_shunt = math.sqrt((1.0 - r) / r)
                    x_series = (1.0 / b_shunt) - x

                # Denormalise susceptance/reactance to find physical values
                b_actual = b_shunt / self.z0
                x_actual = x_series * self.z0

                # Derive physical component types from mathematical signs
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
                print(
                    f"       -> [Error] Matrix boundary limit hit for this impedance node: {e}"
                )
            print("-" * 75)
        print("=" * 75)

    def calculate_microstrip_electrical_length(
        self, h_mils=62.0, er=4.2, target_deg=90.0, target_freq_mhz=None
    ):
        """
        Calculates the Effective Dielectric Constant (Er_eff) and converts target
        electrical lengths (like quarter-wave 90 deg bias lines) into raw mm PCB layout dimensions.
        """
        if target_freq_mhz is None:
            target_freq_mhz = self.loader.f_center_mhz

        freq_hz = target_freq_mhz * 1e6
        c_speed = 299792458  # Speed of light in m/s

        # Pull the width calculation from our existing tool logic path
        # Assume a standard 50-Ohm trace width ratio approximation for Er_eff sizing
        w_h_ratio = 50.0 / h_mils

        # Schneider's standard effective dielectric formula for microstrips
        er_eff = ((er + 1) / 2) + ((er - 1) / 2) * (1 / math.sqrt(1 + 12 / w_h_ratio))

        # Calculate free space vs guided wavelength
        lambda_free = c_speed / freq_hz
        lambda_guided = lambda_free / math.sqrt(er_eff)

        # Convert degree targets to physical layout size lengths
        physical_length_mm = (target_deg / 360.0) * lambda_guided * 1000

        print("\n" + "=" * 75)
        print(" 8. PCB MICROSTRIP TRANSMISSION LINE WAVELENGTH LENGTHS")
        print("=" * 75)
        print(f"[*] Evaluation Frequency Node:          {target_freq_mhz:.1f} MHz")
        print(f"[*] Effective Dielectric Scale (Eeff):   {er_eff:.3f}")
        print(
            f"[*] Total Guided Wavelength (\u03bb):       {(lambda_guided * 1000):.2f} mm"
        )
        print("-" * 75)
        print(
            colored(
                f"[+] Quarter-Wave Isolation (\u03bb/4 - 90\u00b0): {physical_length_mm:.2f} mm physical length",
                "cyan",
                attrs=["bold"],
            )
        )
        print("=" * 75)
        return er_eff, physical_length_mm

    def design_fixed_attenuator_pad(self, target_attn_db=3.0):
        """
        Computes the standard resistor network boundaries for an inline
        matched Pi (兀) attenuator padding stage.
        """
        print("\n" + "=" * 75)
        print(
            f" 9. INLINE SYSTEM GAIN PROTECTION ATTENUATOR PAD ({target_attn_db:.1f} dB Target)"
        )
        print("=" * 75)

        # Transmission loss linear scale variable factor
        k = 10 ** (target_attn_db / 20.0)

        # Standard Pi-Network resistor configuration equations
        r_shunt = self.z0 * ((k + 1) / (k - 1))
        r_series = self.z0 * ((k**2 - 1) / (2 * k))

        print(f"[*] Matched Core Impedance Target (Z0): {self.z0} \u03a9")
        print(f"[+] Shunt Side Ground Resistors (R1, R3): {r_shunt:.1f} \u03a9")
        print(f"[+] Series Inline Bridge Resistor (R2):   {r_series:.1f} \u03a9")
        print("-" * 75)
        print(
            "[TIP] Place an attenuator pad at the input or output port plane to flatten out"
        )
        print(
            "      high matching ripples and protect subsequent stages from over-driven line clipping."
        )
        print("=" * 75)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Unified Mini-Circuits Linear Amplifier Physical Hardware Designer"
    )

    # Required positional argument (the file path)
    parser.add_argument(
        "s2p_file", type=str, help="Path to the input Touchstone (.s2p) file"
    )

    # Optional setup configurations
    parser.add_argument(
        "-z", "--z0", type=float, default=50.0, help="System Port Impedance (Ohms)"
    )
    parser.add_argument(
        "-f",
        "--freq-eval",
        type=float,
        default=None,
        help="Specific frequency target (MHz) for Smith circles",
    )
    parser.add_argument(
        "-s",
        "--srf-safety",
        type=float,
        default=1.5,
        help="SRF safety margin factor for chokes",
    )

    parser.add_argument(
        "--fmin",
        type=float,
        default=None,
        help="Custom Lower working band frequency constraint boundary (MHz)",
    )
    parser.add_argument(
        "--fmax",
        type=float,
        default=None,
        help="Custom Upper working band frequency constraint boundary (MHz)",
    )

    # DC Input Parameters
    parser.add_argument(
        "--vcc", type=float, default=12.0, help="DC Input Supply Voltage Rail"
    )
    parser.add_argument(
        "--t-amb",
        type=float,
        default=85.0,
        help="Environmental Operating Ambient Boundary Temp (\u00b0C)",
    )

    parser.add_argument(
        "--attn-pad",
        type=float,
        default=3.0,
        help="Target attenuation pad reduction level (dB)",
    )
    parser.add_argument(
        "--export-path",
        type=str,
        default="design_report.md",
        help="Filename path for generated markdown reports",
    )
    parser.add_argument(
        "--pcb-path",
        type=str,
        default="amp_layout.kicad_pcb",
        help="Filename path for generated KiCad board layouts",
    )
    parser.add_argument(
        "--sch-path",
        type=str,
        default="amp_schematic.kicad_sch",
        help="Filename path for generated KiCad schematics",
    )

    # Optional execution flags
    parser.add_argument(
        "--skip-plots",
        action="store_true",
        help="Skip rendering 4-panel linear performance plots",
    )
    parser.add_argument(
        "--skip-smith",
        action="store_true",
        help="Skip rendering Smith Chart stability circles",
    )
    parser.add_argument(
        "--gcpw-mode",
        action="store_true",
        help="Toggle GCPW synthesis track calculations over standard microstrip",
    )
    parser.add_argument(
        "--board-type",
        type=str,
        default="FR-4 Standard (1.6mm)",
        choices=[
            "FR-4 Standard (1.6mm)",
            "Rogers RO3003 (10mil)",
            "Rogers RO4003C (20mil)",
            "Rogers RO4350B (30mil)",
        ],
        help="Select target PCB dielectric laminate substrate profile material",
    )

    args = parser.parse_args()

    # Instantiate your designer class using the arguments
    print(
        colored(
            f"[*] Starting Line Designer Suite for: {args.s2p_file}",
            "cyan",
            attrs=["bold"],
        )
    )

    loader = SParameterLoader()
    loader.load(args.s2p_file, f_min_override=args.fmin, f_max_override=args.fmax)

    designer = MiniCircuitsLinearAmpDesigner(loader_instance=loader, z0=args.z0)
    visualizer = RFPerformanceVisualizer(loader_instance=loader)
    stability = StabilityAnalyzer(loader_instance=loader, z0=args.z0)
    choke_block = ChokeBlockDesigner(loader_instance=loader, z0=args.z0)
    bias_feedback = BiasFeedbackDesigner(loader_instance=loader, z0=args.z0)
    thermals = ThermalAdvisor(loader_instance=loader)

    # Execute the analytical hardware design methods
    choke_block.design_bias_choke(srf_safety_factor=args.srf_safety)
    choke_block.design_dc_block()

    bias_feedback.design_feedback_loop()
    bias_feedback.design_active_dc_bias(v_cc=args.vcc, v_d=8.0, i_d=0.234)

    thermals.analyze_thermal_profile(
        t_ambient_c=args.t_amb, v_d=8.0, i_d=0.234, theta_jc=29.3, board_type=args.board_type
    )

    # Calculate microstrip trace sizing configurations for standard 1.6mm 2-layer FR4 boards
    if args.gcpw_mode:
        # Run coplanar synthesis using a standard 10 mil manufacturing isolation clearance mask gap
        best_w, s_gap = designer.calculate_pcb_gcpw(
            h_mils=62.0, er=4.2, t_oz=1.0, default_gap_mils=10.0
        )
    else:
        # Default back to original standalone microstrip calculation line
        designer.calculate_pcb_microstrip(h_mils=62.0, er=4.2, t_oz=1.0)

    # Synthesise lumped-element L-C matches at target evaluation frequency
    designer.design_lc_matching(target_freq_mhz=args.freq_eval)
    # Length matching, Attenuator sizing, and Markdown generation
    designer.calculate_microstrip_electrical_length(
        h_mils=62.0, er=4.2, target_deg=90.0, target_freq_mhz=args.freq_eval
    )
    designer.design_fixed_attenuator_pad(target_attn_db=args.attn_pad)

    # Calculate the er_eff properties headlessly to pass down to template tracker
    er_eff_calc, _ = designer.calculate_microstrip_electrical_length(target_freq_mhz=designer.loader.f_center_mhz)
    dist_vec, z_vec = calculate_spatial_tdr(designer.loader.network, er_eff=er_eff_calc, z0=designer.z0)

    serialize_markdown_report(
        output_filename=args.export_path,
        f_min=designer.loader.f_min_mhz,
        f_max=designer.loader.f_max_mhz,
        f_center=designer.loader.f_center_mhz,
        z0=designer.z0,
        tdr_distance=dist_vec,
        tdr_impedance=z_vec
    )

    # To grab the calculated value seamlessly without changing your existing function prints,
    # we run a quick internal simulation check variable pass:
    h = 62.0
    t = 1.0 * 1.37
    best_w = 110.0  # Standard fallback
    min_err = float("inf")
    for w_check in np.linspace(1, 200, 2000):
        zo_calc = (87.0 / math.sqrt(4.2 + 1.41)) * math.log(
            (5.98 * h) / (0.8 * w_check + t)
        )
        if abs(zo_calc - designer.z0) < min_err:
            min_err = abs(zo_calc - designer.z0)
            best_w = w_check

    serialize_pcb_layout(output_filename=args.pcb_path, trace_width_mils=best_w)
    serialize_schematic(output_filename=args.sch_path)

    # Handle plotting visibility based on user flags
    if not args.skip_plots:
        visualizer.plot_linear_performance()

    if not args.skip_smith:
        stability.plot_stability_circles(target_freq_mhz=args.freq_eval)
