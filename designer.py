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
)


class MiniCircuitsLinearAmpDesigner:
    def __init__(self, loader_instance, z0=50):
        """
        Initializes the designer by loading the Mini-Circuits Touchstone .s2p data.
        """
        self.z0 = z0
        self.loader = loader_instance

    def plot_linear_performance(self, embed_fig=None):
        """Plots standard S-parameters, stability factor K, and Max Gain."""
        freq_ghz = self.loader.network.f / 1e9
        s11_db = self.loader.network.s11.s_db.flatten()
        s21_db = self.loader.network.s21.s_db.flatten()
        s22_db = self.loader.network.s22.s_db.flatten()
        k_factor = self.loader.network.stability.flatten()
        g_max_db = self.loader.network.max_gain.flatten()

        # Check if we are passing a container from a GUI window canvas layout interface frame
        if embed_fig:
            fig = embed_fig
            axs = fig.get_axes()
            # If the embedded figure doesn't have 4 subplots mapped yet, construct them
            if len(axs) < 4:
                fig.clear()
                axs = fig.subplots(2, 2)
            else:
                for ax in axs:
                    ax.clear()
            # Reshape subplots back into a predictable 2x2 multi-dimensional lookup layout matrix
            axs = np.array(axs).reshape(2, 2)
        else:
            fig, axs = plt.subplots(2, 2, figsize=(12, 9))

        axs[0, 0].plot(freq_ghz, s21_db, label="Gain ($S_{21}$)", color="blue")
        axs[0, 0].plot(
            freq_ghz,
            self.loader.network.s12.s_db.flatten(),
            label="Isolation ($S_{12}$)",
            color="orange",
            linestyle="--",
        )
        axs[0, 0].set_title(f"{self.loader.network.name}: Gain & Isolation")
        axs[0, 0].set_ylabel("dB")
        axs[0, 0].grid(True)
        axs[0, 0].legend()

        axs[0, 1].plot(freq_ghz, s11_db, label="Input RL ($S_{11}$)", color="red")
        axs[0, 1].plot(freq_ghz, s22_db, label="Output RL ($S_{22}$)", color="green")
        axs[0, 1].set_title("Return Losses")
        axs[0, 1].set_ylabel("dB")
        axs[0, 1].grid(True)
        axs[0, 1].legend()

        axs[1, 0].plot(freq_ghz, k_factor, color="purple")
        axs[1, 0].axhline(1.0, color="red", linestyle=":", label="K=1 Stable Bound")
        axs[1, 0].set_title("Stability Factor (K)")
        axs[1, 0].set_xlabel("Frequency (GHz)")
        axs[1, 0].grid(True)
        axs[1, 0].legend()

        axs[1, 1].plot(
            freq_ghz, g_max_db, label="Max Feasible Gain ($G_{max}$)", color="black"
        )
        axs[1, 1].plot(
            freq_ghz, s21_db, label="Raw Gain ($S_{21}$)", color="blue", alpha=0.4
        )
        axs[1, 1].set_title("Maximum Feasible Gain")
        axs[1, 1].set_xlabel("Frequency (GHz)")
        axs[1, 1].grid(True)
        axs[1, 1].legend()

        for ax in axs.flatten():
            # Convert our selected MHz variables to GHz to match the graph's horizontal units
            ax.set_xlim(self.loader.f_min_mhz / 1000.0, self.loader.f_max_mhz / 1000.0)

        fig.tight_layout()
        if not embed_fig:
            plt.show()

    def plot_stability_circles(self, target_freq_mhz=None, embed_fig=None):
        """
        Plots the continuous S11 and S22 frequency sweep traces between the
        lower and upper limits on the Smith Chart, overlaid with the stability
        circles and a live worst-case VSWR tracking marker ring.
        """
        if not self.loader.network:
            return

        if target_freq_mhz is None:
            target_freq_mhz = self.loader.f_center_mhz

        # 1. Extract indices corresponding to your selected working band limits
        f_all_mhz = self.loader.network.f / 1e6
        band_indices = np.where(
            (f_all_mhz >= self.loader.f_min_mhz) & (f_all_mhz <= self.loader.f_max_mhz)
        )[0]

        if len(band_indices) == 0:
            band_indices = np.array([np.argmin(np.abs(f_all_mhz - target_freq_mhz))])

        # Extract the swept data chunks across your customized frequency limits
        s11_sweep = self.loader.network.s[band_indices, 0, 0]
        s22_sweep = self.loader.network.s[band_indices, 1, 1]

        # --- LIVE VSWR PEAK RADIAL MARKER TRACKING ENGINE ---
        # Calculate VSWR arrays across the band: VSWR = (1 + |G|) / (1 - |G|)
        s11_mags = np.abs(s11_sweep)
        s11_vswr_array = (1.0 + s11_mags) / (1.0 - np.clip(s11_mags, 0, 0.999))
        s11_worst_idx = np.argmax(s11_vswr_array)
        s11_max_vswr = s11_vswr_array[s11_worst_idx]
        s11_worst_pt = s11_sweep[s11_worst_idx]
        s11_worst_freq = f_all_mhz[band_indices[s11_worst_idx]]

        s22_mags = np.abs(s22_sweep)
        s22_vswr_array = (1.0 + s22_mags) / (1.0 - np.clip(s22_mags, 0, 0.999))
        s22_worst_idx = np.argmax(s22_vswr_array)
        s22_max_vswr = s22_vswr_array[s22_worst_idx]
        s22_worst_pt = s22_sweep[s22_worst_idx]
        s22_worst_freq = f_all_mhz[band_indices[s22_worst_idx]]

        # 2. Extract specific center evaluation single frequency metrics for stability calculations
        freq_hz = target_freq_mhz * 1e6
        idx = np.argmin(np.abs(self.loader.network.f - freq_hz))
        actual_freq_ghz = self.loader.network.f[idx] / 1e9

        s11 = self.loader.network.s[idx, 0, 0]
        s12 = self.loader.network.s[idx, 0, 1]
        s21 = self.loader.network.s[idx, 1, 0]
        s22 = self.loader.network.s[idx, 1, 1]

        delta = s11 * s22 - s12 * s21
        delta_mag = np.abs(delta)
        k = (1 - np.abs(s11) ** 2 - np.abs(s22) ** 2 + delta_mag**2) / (
            2 * np.abs(s12 * s21)
        )

        c_s_num = np.conj(s11 - delta * np.conj(s22))
        c_s_den = np.abs(s11) ** 2 - delta_mag**2
        c_source = c_s_num / c_s_den
        r_source = np.abs(s12 * s21) / np.abs(c_s_den)

        c_l_num = np.conj(s22 - delta * np.conj(s11))
        c_l_den = np.abs(s22) ** 2 - delta_mag**2
        c_load = c_l_num / c_l_den
        r_load = np.abs(s12 * s21) / np.abs(c_l_den)

        # Handle UI Canvas Context routing structures
        if embed_fig:
            fig = embed_fig
            axs = fig.get_axes()
            if len(axs) < 2:
                fig.clear()
                axs = fig.subplots(1, 2)
            else:
                for ax in axs:
                    ax.clear()
            ax1, ax2 = axs[0], axs[1]
        else:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))

        # Render background chart grids
        rf.plotting.smith(ax=ax1)
        rf.plotting.smith(ax=ax2)

        ax1.set_title(rf"Source Stability ($\Gamma_S$) @ {actual_freq_ghz:.3f} GHz")
        ax2.set_title(rf"Load Stability ($\Gamma_L$) @ {actual_freq_ghz:.3f} GHz")

        # Plot the Continuous S-Parameter Reflection Sweeps
        ax1.plot(
            np.real(s11_sweep),
            np.imag(s11_sweep),
            color="darkorange",
            linewidth=3,
            label=f"S11 Sweep ({self.loader.f_min_mhz:.0f}-{self.loader.f_max_mhz:.0f}MHz)",
        )
        ax2.plot(
            np.real(s22_sweep),
            np.imag(s22_sweep),
            color="darkcyan",
            linewidth=3,
            label=f"S22 Sweep ({self.loader.f_min_mhz:.0f}-{self.loader.f_max_mhz:.0f}MHz)",
        )

        # --- NEW ADDITION: Plot Worst-Case VSWR Tracking Ring & Point Marker ---
        theta = np.linspace(0, 2 * np.pi, 200)

        # Input Port Marker (S11)
        s11_vswr_circle = s11_mags[s11_worst_idx] * np.exp(1j * theta)
        ax1.plot(
            np.real(s11_vswr_circle),
            np.imag(s11_vswr_circle),
            color="magenta",
            linestyle=":",
            linewidth=1.2,
            label="Max VSWR Boundary Ring",
        )
        ax1.plot(
            np.real(s11_worst_pt),
            np.imag(s11_worst_pt),
            color="deeppink",
            marker="X",
            markersize=8,
            linestyle="none",
            label=f"Peak VSWR: {s11_max_vswr:.2f} (:1) @ {s11_worst_freq:.1f}MHz",
        )

        # Output Port Marker (S22)
        s22_vswr_circle = s22_mags[s22_worst_idx] * np.exp(1j * theta)
        ax2.plot(
            np.real(s22_vswr_circle),
            np.imag(s22_vswr_circle),
            color="magenta",
            linestyle=":",
            linewidth=1.2,
            label="Max VSWR Boundary Ring",
        )
        ax2.plot(
            np.real(s22_worst_pt),
            np.imag(s22_worst_pt),
            color="deeppink",
            marker="X",
            markersize=8,
            linestyle="none",
            label=f"Peak VSWR: {s22_max_vswr:.2f} (:1) @ {s22_worst_freq:.1f}MHz",
        )

        # Highlight start and end frequencies with markers
        ax1.plot(
            np.real(s11_sweep[0]),
            np.imag(s11_sweep[0]),
            "go",
            markersize=5,
            label="Start Freq",
        )
        ax1.plot(
            np.real(s11_sweep[-1]),
            np.imag(s11_sweep[-1]),
            "ro",
            markersize=5,
            label="End Freq",
        )
        ax2.plot(
            np.real(s22_sweep[0]),
            np.imag(s22_sweep[0]),
            "go",
            markersize=5,
            label="Start Freq",
        )
        ax2.plot(
            np.real(s22_sweep[-1]),
            np.imag(s22_sweep[-1]),
            "ro",
            markersize=5,
            label="End Freq",
        )

        # Plot the Geometric Stability Boundary Circles
        src_circle_pts = c_source + r_source * np.exp(1j * theta)
        ax1.plot(
            np.real(src_circle_pts),
            np.imag(src_circle_pts),
            color="red",
            linestyle="--",
            linewidth=1.5,
            label="Stability Circle Bound",
        )

        load_circle_pts = c_load + r_load * np.exp(1j * theta)
        ax2.plot(
            np.real(load_circle_pts),
            np.imag(load_circle_pts),
            color="blue",
            linestyle="--",
            linewidth=1.5,
            label="Stability Circle Bound",
        )

        src_center_stable = "STABLE ZONE" if np.abs(s22) < 1 else "UNSTABLE"
        load_center_stable = "STABLE ZONE" if np.abs(s11) < 1 else "UNSTABLE"

        ax1.text(
            0,
            -0.15,
            f"Chart Center (50Ω):\n{src_center_stable}",
            color="darkgreen",
            ha="center",
            va="center",
            weight="bold",
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
        ax2.text(
            0,
            -0.15,
            f"Chart Center (50Ω):\n{load_center_stable}",
            color="darkgreen",
            ha="center",
            va="center",
            weight="bold",
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )

        for ax in [ax1, ax2]:
            ax.set_xlim(-1.1, 1.1)
            ax.set_ylim(-1.1, 1.1)
            ax.legend(loc="lower left", fontsize="x-small")

        fig.tight_layout()
        if not embed_fig:
            plt.show()

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
            print(
                colored(
                    f"\n[+] Recommended Footprint: {selected_package}",
                    "green",
                    attrs=["bold"],
                )
            )
            standard_values = [
                1.0,
                1.2,
                1.5,
                1.8,
                2.2,
                2.7,
                3.3,
                3.9,
                4.7,
                5.6,
                6.8,
                8.2,
                10.0,
                12.0,
                15.0,
            ]
            suggestions = [
                v for v in standard_values if (l_min * 1e6) <= v <= (best_l_max * 1e6)
            ]
            print(
                f"    Sourcing window: {l_min * 1e6:.2f} uH to {best_l_max * 1e6:.2f} uH"
            )
            if suggestions:
                print(
                    f"    Standard E12 Values: {', '.join([f'{v} uH' for v in suggestions])}"
                )
        else:
            print(
                colored(
                    "\n[!] Design Warning: Single-stage choke cannot clear SRF. Consider a conical choke.",
                    "red",
                )
            )

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
        print(
            f"[*] Target Freq: {self.loader.f_center_mhz:.1f} MHz | Min Cap Req: {c_min * 1e12:.1f} pF"
        )
        print("-" * 75)

        for pkg, specs in cap_package_constraints.items():
            esl = specs["esl_nh"] * 1e-9
            c_ideal = 1 / (4 * (math.pi**2) * (f_center**2) * esl)
            closest_val = min(standard_pf, key=lambda x: abs(x - (c_ideal * 1e12)))

            status = (
                f"👍 Optimal: {closest_val} pF"
                if (closest_val * 1e-12) >= c_min
                else "😞 Too small for passband"
            )
            print(
                f"SMD {pkg:<6} | ESL: {specs['esl_nh']:.1f} nH | Center SRF Target C: {c_ideal * 1e12:>7.1f} pF | {status}"
            )

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
        print(
            f"[] Detected Mid-band Device Gain ($S_{21}$): {actual_gain_db.item():.1f} dB"
        )
        print(f"[+] Calculated Target Loop $R_{{fb}}$: {r_fb_ideal.item():.1f} Ω")
        print(
            f"[+] Calculated Loop Minimum $C_{{fb}}$: {(c_fb_min * 1e12).item():.1f} pF"
        )
        print("-" * 75)
        print(
            "[TIP] Use these starting values to flatten gain variations over frequency."
        )
        print("=" * 75)

    def analyze_thermal_profile(
        self, t_ambient_c=85.0, v_d=8.0, i_d=0.234, theta_jc=29.3, board_type="FR-4 Standard (1.6mm)", embed_fig=None
    ):
        """
        Calculates Junction Temperature (Tj) and visualises the 2D thermal dissipation
        gradient across the PCB copper plane relative to the selected substrate type.
        Applies a localized heat-spreading model to calculate layout layout clearances.
        """
        p_dc = v_d * i_d
        t_j_max_allowed = 150.0
        t_j = t_ambient_c + (p_dc * theta_jc)
        safety_margin = t_j_max_allowed - t_j

        # --- DYNAMIC MATERIAL THERMODYNAMICS MATRIX ENGINE ---
        profile = self.SUBSTRATE_PROFILES.get(board_type, self.SUBSTRATE_PROFILES["FR-4 Standard (1.6mm)"])
        h_mils = profile["h_mils"]

        # Convection coefficients scale with substrate height profiles (thinner boards choke vertical spreading)
        # Standard still-air base coefficient adjusted proportionally by dielectric volume constraints
        h_conv_base = 0.000015  # W/mm^2*K
        h_conv = h_conv_base * (h_mils / 62.0)  # Thinner laminates decrease air-interfacing vertical boundaries

        t_case_target = 115.0  # Safe board/paddle copper target limit
        min_copper_area_mm2 = p_dc / (h_conv * (t_case_target - t_ambient_c)) if t_ambient_c < t_case_target else 999.9
        spreading_radius_mm = math.sqrt(min_copper_area_mm2 / math.pi) if min_copper_area_mm2 > 0 else 0.0

        # Adjust the visual 2D exponential math decay constant relative to the substrate material thermal resistance
        # Thinner substrates or high-frequency cores experience a sharper localized hot-spot delta radius
        decay_constant = 0.35 * (62.0 / h_mils)

        print("\n" + "=" * 75)
        print(f" 5. DEVICE THERMAL RELIABILITY & PCB LAYOUT ADVISOR ({board_type.upper()})")
        print("=" * 75)
        print(f"[*] Input Bias Power:  {v_d:.1f} V @ {i_d*1000:.1f} mA --> {p_dc:.2f} Watts")
        print(f"[+] Calculated Junction Temp (Tj): {t_j:.1f} °C (Absolute Max: {t_j_max_allowed}°C)")
        print(f"[+] Required Ground Heat-Sink Pour: >= {min_copper_area_mm2:.1f} mm² (~{math.sqrt(min_copper_area_mm2):.1f} x {math.sqrt(min_copper_area_mm2):.1f} mm square)")
        print(f"[+] Keep-Out Radius for Passives:   >= {spreading_radius_mm:.1f} mm around package center")

        if t_j < t_j_max_allowed:
            print(
                colored(
                    f"👍 THERMAL PASS: Margin is {safety_margin:.1f} °C below absolute max ({t_j_max_allowed}°C).",
                    "green",
                    attrs=["bold"],
                )
            )
        else:
            print(
                colored(
                    f"😞 THERMAL FAILURE: Tj exceeds safe operating limits by {abs(safety_margin):.1f} °C!",
                    "red",
                    attrs=["bold"],
                )
            )
            print(
                "    Remedy: You must use explicit copper ground pouring and thermal via stitching arrays."
            )
        print("=" * 75)

        # Intercept and route matplotlib handles if embedded inside a GUI notebook container
        if embed_fig:
            fig = embed_fig
            if fig.get_axes():
                ax = fig.get_axes()[0]
                ax.clear()
            else:
                ax = fig.add_subplot(111)
        else:
            fig, ax = plt.subplots(figsize=(8, 6))

        # Generate a 2D Heat Dissipation Coordinate Mesh (20mm x 20mm layout space)
        size = 200
        x = np.linspace(-10, 10, size)
        y = np.linspace(-10, 10, size)
        X, Y = np.meshgrid(x, y)
        distance = np.sqrt(X**2 + Y**2)

        t_pcb_grid = t_ambient_c + (t_j - t_ambient_c) * np.exp(-decay_constant * distance)

        # Plot the 2D Continuous Surface Heat Map
        thermal_map = ax.imshow(t_pcb_grid, extent=[-10, 10, -10, 10], cmap='jet', origin='lower')

        # --- Isothermal Contour Lines ---
        levels = [t_ambient_c + 15, 100.0, 125.0]
        levels = [lvl for lvl in levels if t_ambient_c < lvl < t_j]
        if levels:
            contours = ax.contour(X, Y, t_pcb_grid, levels=sorted(list(set(levels))), colors='white', linewidths=1.0, linestyles=':')
            ax.clabel(contours, inline=True, fmt='%1.0f°C', fontsize=9, colors='white')

        # Add SOT-89 footprint outlines to orient the physical components layout scale
        ax.add_patch(plt.Rectangle((-2.25, -2.0), 4.5, 4.0, fill=False, edgecolor='black', linewidth=1.5, linestyle='--', alpha=0.7, label='SOT-89 Body'))
        ax.add_patch(plt.Rectangle((-0.9, -4.0), 1.8, 2.0, fill=True, color='black', alpha=0.15, label='Ground Paddle Sink'))

        # Draw a visual keep-out target circle matching our calculated heat-spreading boundary radius
        if spreading_radius_mm < 10.0:
            circle = plt.Circle((0, 0), spreading_radius_mm, color='white', fill=False, linestyle='-', linewidth=1.5, label='Req. Minimum Heat-Sink Zone')
            ax.add_patch(circle)

        if not hasattr(ax, '_colorbar_attached') or ax._colorbar_attached is None:
            cbar = fig.colorbar(thermal_map, ax=ax, label='Substrate Temperature (°C)')
            ax._colorbar_attached = cbar

        ax.set_title(f"PHA-13HLN+ Substrate Thermal Gradient (Tj = {t_j:.1f}°C)")
        ax.set_xlabel("X-Axis Distance from Package Center (mm)")
        ax.set_ylabel("Y-Axis Distance from Package Center (mm)")
        ax.legend(loc='upper right', fontsize='small')
        ax.grid(False)

        fig.tight_layout()
        if not embed_fig:
            plt.show()

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
            1.0,
            1.1,
            1.2,
            1.3,
            1.5,
            1.6,
            1.8,
            2.0,
            2.2,
            2.4,
            2.7,
            3.0,
            3.3,
            3.6,
            3.9,
            4.3,
            4.7,
            5.1,
            5.6,
            6.2,
            6.8,
            7.5,
            8.2,
            9.1,
            10,
            11,
            12,
            13,
            15,
            16,
            18,
            20,
            22,
            24,
            27,
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
        print(
            "[BYPASS SUGGESTIONS] Connect three parallel 4.7 uF, 0.1 uF, and 100 pF capacitors"
        )
        print(
            "                    at the top node of the RF Choke to clean incoming ripple noise."
        )
        print("=" * 75)
        return r_bias_ideal

    # Define a clean material matrix map as a class constant variable profile
    SUBSTRATE_PROFILES = {
        "FR-4 Standard (1.6mm)": {"er": 4.2, "h_mils": 62.0},
        "Rogers RO3003 (10mil)": {"er": 3.00, "h_mils": 10.0},
        "Rogers RO4003C (20mil)": {"er": 3.38, "h_mils": 20.0},
        "Rogers RO4350B (30mil)": {"er": 3.48, "h_mils": 30.0},
    }

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

    def export_markdown_bom_report(self, output_filename="design_report.md"):
        """
        Gathers tool metrics and auto-saves a clean Markdown procurement summary file.
        """
        try:
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(f"# Automated RF Hardware Design Report\n\n")
                f.write(
                    f"Generated Profile Analysis Suite for Mini-Circuits `.s2p` Device Networks.\n\n"
                )
                f.write(f"## 1. Operating Frequency Band Parameters\n")
                f.write(f"* **Minimum Lower Bound:** {self.loader.f_min_mhz:.2f} MHz\n")
                f.write(f"* **Maximum Upper Bound:** {self.loader.f_max_mhz:.2f} MHz\n")
                f.write(
                    f"* **Calculated Center Band Point:** {self.loader.f_center_mhz:.2f} MHz\n"
                )
                f.write(f"* **Reference Port Line Matching Match:** {self.z0} Ohms\n\n")
                f.write(f"## 2. Mandatory Component Sourcing Bill of Materials (BOM)\n")
                f.write(
                    f"| Circuit Location Block | Component Specified Value / Design Constraint Target |\n"
                )
                f.write(f"| :--- | :--- |\n")
                f.write(
                    f"| **RF Coupling Bias Choke Inductor** | Refer to screen print for working E12 SMD bounds |\n"
                )
                f.write(
                    f"| **Input/Output DC Blocks** | Sized to hit center SRF match criteria |\n"
                )
                f.write(
                    f"| **DC Biasing Resistor (Rbias)** | Sized for target Vcc drop constraints |\n"
                )
                f.write(
                    f"| **Microstrip Line Trace Width Width** | Calculated relative to FR4 height profiles |\n"
                )
            print(
                colored(
                    f"\n[+] Production Design Data Export Complete: Saved report to '{output_filename}'",
                    "green",
                    attrs=["bold"],
                )
            )
        except IOError as e:
            print(
                colored(
                    f"\n[!] System Failure: Could not write file destination path: {e}",
                    "red",
                )
            )



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

    # Execute the analytical hardware design methods
    designer.design_bias_choke(srf_safety_factor=args.srf_safety)
    designer.design_dc_block()
    designer.design_feedback_loop()
    # Defaults configured for a worst-case 85°C industrial ambient environment test environment
    # designer.analyze_thermal_profile(t_ambient_c=85.0)
    # Sized parameters explicitly paired for PHA-13HLN+ datasheet thresholds
    designer.design_active_dc_bias(v_cc=args.vcc, v_d=8.0, i_d=0.234)
    designer.analyze_thermal_profile(
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
    designer.export_markdown_bom_report(output_filename=args.export_path)

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
        designer.plot_linear_performance()

    if not args.skip_smith:
        designer.plot_stability_circles(target_freq_mhz=args.freq_eval)
