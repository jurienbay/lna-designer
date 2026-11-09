## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

import numpy as np
from termcolor import colored


class MicrostripStubBiasDesigner:
    def __init__(self, loader_instance, er=4.2, h_mm=1.6, t_um=35, z0=50):
        """
        Initializes the distributed microstrip bias network designer.

        Parameters:
        - loader_instance: Object containing f_center_mhz, f_max_mhz, etc.
        - er: Relative permittivity (dielectric constant) of substrate (e.g., 4.2 for FR-4)
        - h_mm: Substrate thickness in millimetres
        - t_um: Copper foil thickness in micrometres
        - z0: Main characteristic impedance (typically 50 Ohms)
        """
        self.loader = loader_instance
        self.er = er
        self.h_mm = h_mm
        self.t_um = t_um
        self.z0 = z0
        self.c0 = 299792458  # Speed of light in m/s

    def calculate_microstrip_w_and_eff(self, target_z0):
        """
        Dynamically solves microstrip trace width (w) and effective dielectric
        constant (er_eff) using Wheeler/Hammerstad transmission line synthesis.
        """
        h = self.h_mm
        # Intermediate synthesis variables
        A = (target_z0 / 60) * math.sqrt((self.er + 1) / 2) + ((self.er - 1) / (self.er + 1)) * (0.23 + (0.11 / self.er))
        B = (377 * math.pi) / (2 * target_z0 * math.sqrt(self.er))

        # Determine Width/Height ratio approximation
        w_over_h_A = 8 * math.exp(A) / (math.exp(2 * A) - 2)
        w_over_h_B = (2 / math.pi) * (B - 1 - math.log(2 * B - 1) + ((self.er - 1) / (2 * self.er)) * (math.log(B - 1) + 0.39 - (0.61 / self.er)))

        w_over_h = w_over_h_A if w_over_h_A < 2 else w_over_h_B
        w_mm = w_over_h * h

        # Calculate precise effective dielectric constant
        er_eff = ((self.er + 1) / 2) + ((self.er - 1) / 2) * (1 / math.sqrt(1 + 12 * (h / w_mm)))
        return round(w_mm, 3), round(er_eff, 3)

    def design_radial_stub_network(self, stub_angle_deg=60, num_stages=2):
        """
        Dynamically designs a multi-stage radial stub bias decoupling network.
        Higher stages alternate frequencies or create cascade rejection bands.
        """
        f_center = self.loader.f_center_mhz * 1e6
        f_max = self.loader.f_max_mhz * 1e6

        print("\n" + "=" * 75)
        print(" DISTRIBUTED MICROSTRIP RADIAL STUB BIAS CHOKE DESIGN")
        print("=" * 75)
        print(f"[*] Substrate Profile: Er={self.er} | Thickness={self.h_mm}mm")
        print(f"[*] Operational Center Band: {self.loader.f_center_mhz:.1f} MHz")
        print(f"[*] Desired Topology: {num_stages}-Stage Cascaded {stub_angle_deg}° Radial Network")
        print("-" * 75)

        # High impedance line constraints (Make as narrow as fab allows, e.g., ~100-110Ω max)
        z_high = 100.0
        w_high, er_eff_high = self.calculate_microstrip_w_and_eff(z_high)

        # Calculate quarter wavelength for the high-Z transmission line feed
        lambda_g_high = self.c0 / (f_center * math.sqrt(er_eff_high))
        quarter_wave_feed_length_mm = (lambda_g_high / 4) * 1000

        print("[+] Quarter-Wave High-Z Isolation Trace Feed Line:")
        print(f"    - Target Impedance: {z_high} Ω")
        print(f"    - Trace Width:      {w_high} mm")
        print(f"    - Physical Length:  {quarter_wave_feed_length_mm:.2f} mm (λ/4 Transformed Open)")
        print("-" * 75)

        # Evaluate stubs per stage
        theta_rad = math.radians(stub_angle_deg)

        for stage in range(1, num_stages + 1):
            # For multi-stage networks, stagger frequencies to expand bandwidth
            # Stage 1 targets center band; Stage 2 targets upper limit band edges
            target_f = f_center if stage == 1 else f_max

            # Approximate matching width for radial node throat injection point
            w_throat = w_high

            # Synthesize microstrip properties for an average stub body
            # (Radial stubs typically operate on effective er approximations close to the substrate bulk)
            _, er_eff_stub = self.calculate_microstrip_w_and_eff(self.z0)

            # Compute radial radius (R) which dictates the fundamental lambda length (~λ/4)
            lambda_g_stub = self.c0 / (target_f * math.sqrt(er_eff_stub))
            radius_r_mm = (lambda_g_stub / 4) * 1000

            # Calculate outer arc width boundary
            outer_arc_w_mm = 2 * radius_r_mm * math.sin(theta_rad / 2)

            print(colored(f"[ Stage {stage} Radial Decoupling Element (Targeting {target_f/1e6:.1f} MHz) ]", "cyan"))
            print(f"    - Radial Radius (R):     {radius_r_mm:.2f} mm")
            print(f"    - Throat Entrance Width: {w_throat:.2f} mm")
            print(f"    - Outer Arc Length:      {outer_arc_w_mm:.2f} mm")

            if stage < num_stages:
                # Calculate separation transmission line spacing between cascaded elements (λ/4 at f_max)
                lambda_spacing = self.c0 / (f_max * math.sqrt(er_eff_high))
                spacing_len_mm = (lambda_spacing / 4) * 1000
                print(f"    - Inter-Stage Line:      {spacing_len_mm:.2f} mm separation length ({z_high}Ω trace)")

    def generate_3d_mesh_data(self, stub_angle_deg=60, num_stages=2, phase_shift=0.0, eval_freq_mhz=None, mode='cw', device_name="PHA-13HLN+"):
        """
        Synthesizes raw 3D mesh arrays modeling the substrate bulk, etched copper planes,
        3D vertical thermal via cylinders, and active time-dependent RF electric field waves.
        """
        import numpy as np
        from .hardware_profiles import DEVICE_PROFILES, PACKAGE_FOOTPRINTS

        target_f_mhz = eval_freq_mhz if eval_freq_mhz is not None else self.loader.f_center_mhz
        f_hz = target_f_mhz * 1e6

        _, er_eff_stub = self.calculate_microstrip_w_and_eff(self.z0)
        z_high = 100.0
        w_high, _ = self.calculate_microstrip_w_and_eff(z_high)

        lambda_g = self.c0 / (f_hz * math.sqrt(er_eff_stub))
        radius_r_mm = (lambda_g / 4) * 1000

        # Substrate Block
        sub_x, sub_y = np.meshgrid(np.linspace(-25, 25, 30), np.linspace(-30, 10, 30))
        sub_z_top = np.zeros_like(sub_x)
        sub_z_bot = np.zeros_like(sub_x) - self.h_mm

        # Synthesize Radial Stub Copper Polygon Points
        theta = np.linspace(-math.radians(stub_angle_deg)/2, math.radians(stub_angle_deg)/2, 20)

        # Track physical cascading offsets across multi-stage calculations
        stubs_polygons = []
        current_y_offset = -5.0 # Starting throat injection node position

        for stage in range(1, num_stages + 1):
            target_f = (eval_freq_mhz if eval_freq_mhz is not None else self.loader.f_center_mhz) * 1e6 if stage == 1 else self.loader.f_max_mhz * 1e6
            _, er_eff_stub = self.calculate_microstrip_w_and_eff(self.z0)
            lambda_g_stage = self.c0 / (target_f * math.sqrt(er_eff_stub))
            radius_r_mm = (lambda_g_stage / 4) * 1000

            # Build independent mesh paths for each cascading section
            s_x = [0.0 - w_high/2] + [0.0 + radius_r_mm * math.sin(t) for t in theta] + [0.0 + w_high/2]
            s_y = [current_y_offset] + [current_y_offset - radius_r_mm * math.cos(t) for t in theta] + [current_y_offset]
            stubs_polygons.append((np.array(s_x), np.array(s_y), np.zeros_like(s_x) + 0.02))

            # Advance layout coordinates by adding the required inter-stage isolation spacing line length
            _, er_eff_high = self.calculate_microstrip_w_and_eff(z_high)
            lambda_spacing = self.c0 / ((self.loader.f_max_mhz * 1e6) * math.sqrt(er_eff_high))
            spacing_len_mm = (lambda_spacing / 4) * 1000
            current_y_offset -= (radius_r_mm + spacing_len_mm)

        # Model 3D Thermal Via Cylinders from Hardware Registry
        dev_cfg = DEVICE_PROFILES.get(device_name, DEVICE_PROFILES["PHA-13HLN+"])
        pkg_cfg = PACKAGE_FOOTPRINTS.get(dev_cfg["package"], PACKAGE_FOOTPRINTS["SOT-89-3"])

        via_positions = pkg_cfg["vias"]
        via_radius = pkg_cfg["via_drill"] / 2.0
        via_cylinders = []

        z_cylinder = np.linspace(-self.h_mm, 0, 10)
        phi_cylinder = np.linspace(0, 2 * np.pi, 12)
        P, Z = np.meshgrid(phi_cylinder, z_cylinder)

        for vx, vy in via_positions:
            vx_mesh = vx + via_radius * np.cos(P)
            vy_mesh = vy + via_radius * np.sin(P)
            via_cylinders.append((vx_mesh, vy_mesh, Z))

        # --- HIGH-FIDELITY VECTOR FIELD CORE SIMULATION ENGINE ---
        # Generate Time-Dependent Signal Wave Propagation Trace
        wave_y = np.linspace(-15.0, 2.0, 100)
        wave_x = np.zeros_like(wave_y)

        # Fetch live S-parameter performance thresholds from the network data profile
        s11_mag = 0.1  # Highly matched baseline default
        s21_mag = 1.0  # Perfect transmission default

        if self.loader.network is not None:
            f_hz_query = f_hz
            idx_q = np.argmin(np.abs(self.loader.network.f - f_hz_query))
            s11_mag = np.abs(self.loader.network.s[idx_q, 0, 0])
            s21_mag = np.abs(self.loader.network.s[idx_q, 1, 0])

        # Derive true microstrip phase constant (beta) and alpha (dielectric/conductor loss factor)
        beta = (2.0 * math.pi) / (lambda_g * 1000.0)
        # Scaled rough approximation of skin effect + loss tangent dielectric absorption over frequency
        alpha = 0.005 * math.sqrt(target_f_mhz / 500.0)

        # Mathematically model the overlapping forward, reflected, and transmitted boundary waves
        wave_z = np.zeros_like(wave_y)
        wave_hx = np.zeros_like(wave_y)

        for i, y_pos in enumerate(wave_y):
            # Distance calculated from the source injection terminal upward
            dist_source = y_pos - wave_y[0]

            # Sub-RF Network Segment A: Path leading up to the radial stub throat injection node (y < -5)
            if y_pos < -5.0:
                # Forward incident wave vector
                v_forward = 0.4 * math.exp(-alpha * dist_source) * math.sin(beta * y_pos - phase_shift)
                # Reflected return wave vector scaling directly with raw S11 magnitudes
                v_reflect = 0.4 * s11_mag * math.exp(alpha * y_pos) * math.sin(beta * (-y_pos) - phase_shift)

                # Superposition constructs true Standing Wave nodes/nulls
                wave_z[i] = v_forward + v_reflect
                wave_hx[i] = (v_forward - v_reflect) * 8.5

            # Sub-RF Network Segment B: Path bleeding into the stub networks and exiting toward active chip pads
            else:
                # Transmitted wave shrinks dynamically based on your S21 RF isolation attenuation performance!
                # If your stub is working perfectly, the wave past y = -5 will flatten completely to zero.
                v_transmit = 0.4 * s21_mag * math.exp(-alpha * dist_source) * np.sin(beta * y_pos - phase_shift)

                wave_z[i] = v_transmit
                wave_hx[i] = v_transmit * 8.5

        return {
            "substrate": (sub_x, sub_y, sub_z_top, sub_z_bot),
            "stubs": stubs_polygons,
            "vias": via_cylinders,
            "wave_trace": (wave_x, wave_y, wave_z, wave_hx),
            "target_freq": target_f_mhz
        }
