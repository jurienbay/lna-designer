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
    TransmissionLineSuite,
)


class MiniCircuitsLinearAmpDesigner:
    def __init__(self, loader_instance, z0=50):
        """
        Initializes the designer by loading the Mini-Circuits Touchstone .s2p data.
        """
        self.z0 = z0
        self.loader = loader_instance

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
    t_lines = TransmissionLineSuite(loader_instance=loader, z0=args.z0)

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
        best_w, s_gap = t_lines.calculate_pcb_gcpw(
            h_mils=62.0, er=4.2, t_oz=1.0, default_gap_mils=10.0
        )
    else:
        # Default back to original standalone microstrip calculation line
        t_lines.calculate_pcb_microstrip(h_mils=62.0, er=4.2, t_oz=1.0)

    # Synthesise lumped-element L-C matches at target evaluation frequency
    t_lines.design_lc_matching(target_freq_mhz=args.freq_eval)
    # Length matching, Attenuator sizing, and Markdown generation
    t_lines.calculate_microstrip_electrical_length(
        h_mils=62.0, er=4.2, target_deg=90.0, target_freq_mhz=args.freq_eval
    )
    t_lines.design_fixed_attenuator_pad(target_attn_db=args.attn_pad)

    # Calculate the er_eff properties headlessly to pass down to template tracker
    er_eff_calc, _ = t_lines.calculate_microstrip_electrical_length(target_freq_mhz=designer.loader.f_center_mhz)
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
