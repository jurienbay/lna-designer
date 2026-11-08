## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

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
