## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import matplotlib.pyplot as plt
import numpy as np


class StabilityAnalyzer:
    def __init__(self, loader_instance, z0=50):
        """
        Initializes the stability analyzer engine by linking a shared
        reference to the active SParameterLoader instance.
        """
        self.loader = loader_instance
        self.z0 = z0

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
        )[0].flatten()

        if len(band_indices) == 0:
            band_indices = np.array([np.argmin(np.abs(f_all_mhz - target_freq_mhz))])

        # Extract the swept data chunks across your customized frequency limits
        s11_sweep = self.loader.network.s[band_indices, 0, 0].flatten()
        s22_sweep = self.loader.network.s[band_indices, 1, 1].flatten()

        # --- LIVE VSWR PEAK RADIAL MARKER TRACKING ENGINE ---
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

        # Render background chart grids via network reference plot hooks
        import skrf as rf
        rf.plotting.smith(ax=ax1)
        rf.plotting.smith(ax=ax2)

        ax1.set_title(rf"Source Stability ($\Gamma_S$) @ {actual_freq_ghz:.3f} GHz")
        ax2.set_title(rf"Load Stability ($\Gamma_L$) @ {actual_freq_ghz:.3f} GHz")

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

        theta = np.linspace(0, 2 * np.pi, 200)

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

        ax1.plot(np.real(s11_sweep[0]), np.imag(s11_sweep[0]), "go", markersize=5, label="Start Freq")
        ax1.plot(np.real(s11_sweep[-1]), np.imag(s11_sweep[-1]), "ro", markersize=5, label="End Freq")
        ax2.plot(np.real(s22_sweep[0]), np.imag(s22_sweep[0]), "go", markersize=5, label="Start Freq")
        ax2.plot(np.real(s22_sweep[-1]), np.imag(s22_sweep[-1]), "ro", markersize=5, label="End Freq")

        src_circle_pts = c_source + r_source * np.exp(1j * theta)
        ax1.plot(np.real(src_circle_pts), np.imag(src_circle_pts), color="red", linestyle="--", linewidth=1.5, label="Stability Circle Bound")

        load_circle_pts = c_load + r_load * np.exp(1j * theta)
        ax2.plot(np.real(load_circle_pts), np.imag(load_circle_pts), color="blue", linestyle="--", linewidth=1.5, label="Stability Circle Bound")

        src_center_stable = "STABLE ZONE" if np.abs(s22) < 1 else "UNSTABLE"
        load_center_stable = "STABLE ZONE" if np.abs(s11) < 1 else "UNSTABLE"

        ax1.text(0, -0.15, f"Chart Center (50Ω):\n{src_center_stable}", color="darkgreen", ha="center", va="center", weight="bold", bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"})
        ax2.text(0, -0.15, f"Chart Center (50Ω):\n{load_center_stable}", color="darkgreen", ha="center", va="center", weight="bold", bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"})

        for ax in [ax1, ax2]:
            ax.set_xlim(-1.1, 1.1)
            ax.set_ylim(-1.1, 1.1)
            ax.legend(loc="lower left", fontsize="x-small")

        fig.tight_layout()
        if not embed_fig:
            plt.show()
