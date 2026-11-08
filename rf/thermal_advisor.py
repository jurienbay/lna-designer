## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

import matplotlib.pyplot as plt
import numpy as np
from termcolor import colored

from .substrate_config import SUBSTRATE_PROFILES


class ThermalAdvisor:
    def __init__(self, loader_instance):
        """
        Initializes the thermal advisor engine linked to the shared SParameterLoader.
        """
        self.loader = loader_instance

    def analyze_thermal_profile(
        self, t_ambient_c=85.0, v_d=8.0, i_d=0.234, theta_jc=29.3, board_type="FR-4 Standard (1.6mm)", embed_fig=None
    ):
        """
        Calculates Junction Temperature (Tj) and visualises the 2D thermal dissipation
        gradient across the PCB copper plane relative to the selected substrate type.
        """
        p_dc = v_d * i_d
        t_j_max_allowed = 150.0
        t_j = t_ambient_c + (p_dc * theta_jc)
        safety_margin = t_j_max_allowed - t_j

        # --- DYNAMIC MATERIAL THERMODYNAMICS MATRIX ENGINE ---
        profile = SUBSTRATE_PROFILES.get(board_type, SUBSTRATE_PROFILES["FR-4 Standard (1.6mm)"])
        h_mils = profile["h_mils"]

        h_conv_base = 0.000015  # W/mm^2*K
        h_conv = h_conv_base * (h_mils / 62.0)

        t_case_target = 115.0
        min_copper_area_mm2 = p_dc / (h_conv * (t_case_target - t_ambient_c)) if t_ambient_c < t_case_target else 999.9
        spreading_radius_mm = math.sqrt(min_copper_area_mm2 / math.pi) if min_copper_area_mm2 > 0 else 0.0

        decay_constant = 0.35 * (62.0 / h_mils)

        print("\n" + "=" * 75)
        print(f" 5. DEVICE THERMAL RELIABILITY & PCB LAYOUT ADVISOR ({board_type.upper()})")
        print("=" * 75)
        print(f"[*] Input Bias Power:  {v_d:.1f} V @ {i_d*1000:.1f} mA --> {p_dc:.2f} Watts")
        print(f"[+] Calculated Junction Temp (Tj): {t_j:.1f} °C (Absolute Max: {t_j_max_allowed}°C)")
        print(f"[+] Required Ground Heat-Sink Pour: >= {min_copper_area_mm2:.1f} mm² (~{math.sqrt(min_copper_area_mm2):.1f} x {math.sqrt(min_copper_area_mm2):.1f} mm square)")
        print(f"[+] Keep-Out Radius for Passives:   >= {spreading_radius_mm:.1f} mm around package center")

        if t_j < t_j_max_allowed:
            print(colored(f"👍 THERMAL PASS: Margin is {safety_margin:.1f} °C below absolute max ({t_j_max_allowed}°C).", "green", attrs=["bold"]))
        else:
            print(colored(f"😞 THERMAL FAILURE: Tj exceeds safe operating limits by {abs(safety_margin):.1f} °C!", "red", attrs=["bold"]))
            print("    Remedy: You must use explicit copper ground pouring and thermal via stitching arrays.")
        print("=" * 75)

        if embed_fig:
            fig = embed_fig
            if fig.get_axes():
                ax = fig.get_axes()[0]
                ax.clear()
            else:
                ax = fig.add_subplot(111)
        else:
            fig, ax = plt.subplots(figsize=(8, 6))

        size = 200
        x = np.linspace(-10, 10, size)
        y = np.linspace(-10, 10, size)
        X, Y = np.meshgrid(x, y)
        distance = np.sqrt(X**2 + Y**2)

        t_pcb_grid = t_ambient_c + (t_j - t_ambient_c) * np.exp(-decay_constant * distance)
        thermal_map = ax.imshow(t_pcb_grid, extent=[-10, 10, -10, 10], cmap='jet', origin='lower')

        levels = [t_ambient_c + 15, 100.0, 125.0]
        levels = [lvl for lvl in levels if t_ambient_c < lvl < t_j]
        if levels:
            contours = ax.contour(X, Y, t_pcb_grid, levels=sorted(set(levels)), colors='white', linewidths=1.0, linestyles=':')
            ax.clabel(contours, inline=True, fmt='%1.0f°C', fontsize=9, colors='white')

        ax.add_patch(plt.Rectangle((-2.25, -2.0), 4.5, 4.0, fill=False, edgecolor='black', linewidth=1.5, linestyle='--', alpha=0.7, label='SOT-89 Body'))
        ax.add_patch(plt.Rectangle((-0.9, -4.0), 1.8, 2.0, fill=True, color='black', alpha=0.15, label='Ground Paddle Sink'))

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
