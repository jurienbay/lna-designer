## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import matplotlib.pyplot as plt
import numpy as np


class RFPerformanceVisualizer:
    def __init__(self, loader_instance):
        """
        Initializes the performance visualizer engine by linking a shared
        reference to the active SParameterLoader instance.
        """
        self.loader = loader_instance

    def plot_linear_performance(self, embed_fig=None):
        """Plots standard S-parameters, stability factor K, and Max Gain."""
        freq_ghz = self.loader.network.f / 1e9
        s11_db = self.loader.network.s11.s_db.flatten()
        s21_db = self.loader.network.s21.s_db.flatten()
        s22_db = self.loader.network.s22.s_db.flatten()
        k_factor = self.loader.network.stability.flatten()
        g_max_db = self.loader.network.max_gain.flatten()

        if embed_fig:
            fig = embed_fig
            axs = fig.get_axes()
            if len(axs) < 4:
                fig.clear()
                axs = fig.subplots(2, 2)
            else:
                for ax in axs:
                    ax.clear()
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
            ax.set_xlim(self.loader.f_min_mhz / 1000.0, self.loader.f_max_mhz / 1000.0)

        fig.tight_layout()
        if not embed_fig:
            plt.show()
