#!/usr/bin/env python3

## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from rf import (
    SParameterLoader,
    calculate_spatial_tdr,
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

# Import the designer class core from your existing file
# (Assumes your file is named 'designer.py')
try:
    from designer import MiniCircuitsLinearAmpDesigner
except ImportError:
    print(
        "[!] Project Architecture Error: Could not locate 'designer.py' in this directory."
    )
    print("    Ensure your core analysis script file is named exactly 'designer.py'.")
    sys.exit(1)


class DesignerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Mini-Circuits Monolithic Linear Amplifier CAD Space Suite")
        self.root.geometry("1300x850")

        # Instantiate the analysis engine with no initial file path
        self.loader = SParameterLoader()
        self.designer = MiniCircuitsLinearAmpDesigner(loader_instance=self.loader, z0=50.0)
        self.visualizer = RFPerformanceVisualizer(loader_instance=self.loader)
        self.stability = StabilityAnalyzer(loader_instance=self.loader, z0=50.0)
        self.choke_block = ChokeBlockDesigner(loader_instance=self.loader, z0=50.0)
        self.bias_feedback = BiasFeedbackDesigner(loader_instance=self.loader, z0=50.0)
        self.thermals = ThermalAdvisor(loader_instance=self.loader)
        self.t_lines = TransmissionLineSuite(loader_instance=self.loader, z0=50.0)

        # Core GUI Reactive Application Variables
        self.vcc_var = tk.DoubleVar(value=12.0)
        self.tamb_var = tk.DoubleVar(value=25.0)
        self.fmin_var = tk.DoubleVar(value=30.0)
        self.fmax_var = tk.DoubleVar(value=500.0)
        self.attn_var = tk.DoubleVar(value=3.0)
        self.layout_mode = tk.StringVar(value="Standard Microstrip")
        self.board_type_var = tk.StringVar(value="FR-4 Standard (1.6mm)")
        self.s2p_path_var = tk.StringVar(value="No File Loaded")

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_secure_close)

    def build_ui(self):
        # Master Grid Layout Configurations
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # ---------------- LEFT CONTROL PANEL DASHBOARD ----------------
        ctrl_frame = ttk.LabelFrame(
            main_frame, text=" Operational Design Parameters ", padding="10"
        )
        ctrl_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        main_frame.rowconfigure(0, weight=1)

        # File S2P Browser Hook
        ttk.Button(
            ctrl_frame, text="Load Touchstone .s2p File", command=self.browse_s2p
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(
            ctrl_frame,
            textvariable=self.s2p_path_var,
            font=("Courier", 8),
            foreground="grey",
            wraplength=220,
        ).grid(row=1, column=0, columnspan=2, pady=(0, 15))

        row = 2
        sliders = [
            ("Supply Rail (Vcc)", self.vcc_var, 8.5, 24.0),
            ("Ambient Temp (\u00b0C)", self.tamb_var, -40.0, 125.0),
            ("Lower Working Freq (MHz)", self.fmin_var, 10.0, 2000.0),
            ("Upper Working Freq (MHz)", self.fmax_var, 10.0, 2000.0),
            ("Attenuator Pad (dB)", self.attn_var, 1.0, 20.0),
        ]

        # Programmatically instantiate tuning control sliders with matching text entry fields
        for name, var, v_min, v_max in sliders:
            ttk.Label(ctrl_frame, text=name, font=("Arial", 10, "bold")).grid(
                row=row, column=0, sticky="w", pady=(5, 0)
            )

            val_entry = tk.Entry(
                ctrl_frame,
                width=7,
                font=("Courier", 9),
                bg=self.root.cget("bg"),
                relief=tk.FLAT,
                highlightthickness=1
            )
            val_entry.grid(row=row, column=1, sticky="e", pady=(5, 0))
            val_entry.insert(0, f"{var.get():.1f}")

            scale = ttk.Scale(
                ctrl_frame,
                from_=v_min,
                to=v_max,
                variable=var,
            )
            scale.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

            # Bi-directional reactive synchronization handlers
            def update_entry_from_slider(val, entry=val_entry):
                if not self.root.focus_get() == entry:  # Only modify text if user isn't actively typing
                    entry.delete(0, tk.END)
                    entry.insert(0, f"{float(val):.1f}")

            def update_slider_from_entry(event, s_var=var, entry=val_entry, v_min=v_min, v_max=v_max, s_obj=scale):
                try:
                    val = float(entry.get())
                    clamped_val = max(v_min, min(val, v_max)) # Enforce hardware constraint bounds
                    s_var.set(clamped_val)
                except ValueError:
                    pass # Silently drop malformed non-numeric characters while the user is mid-keystroke

            # Bind events to lock sync loops together
            scale.config(command=update_entry_from_slider)
            val_entry.bind("<KeyRelease>", update_slider_from_entry)
            val_entry.bind("<FocusOut>", lambda e, entry=val_entry, s_var=var: [entry.delete(0, tk.END), entry.insert(0, f"{s_var.get():.1f}")])

            row += 2

        # Transmission Line Type Dropdown
        ttk.Label(
            ctrl_frame, text="Transmission Line Topology", font=("Arial", 10, "bold")
        ).grid(row=row, column=0, sticky="w", pady=5)
        cb = ttk.Combobox(
            ctrl_frame,
            textvariable=self.layout_mode,
            values=["Standard Microstrip", "Grounded Coplanar (GCPW)"],
            state="readonly",
        )
        cb.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=5)
        row += 2

        # PCB Substrate Dropdown
        ttk.Label(
            ctrl_frame, text="PCB Substrate Material Type", font=("Arial", 10, "bold")
        ).grid(row=row, column=0, sticky="w", pady=5)
        cb_board = ttk.Combobox(
            ctrl_frame,
            textvariable=self.board_type_var,
            values=[
                "FR-4 Standard (1.6mm)",
                "Rogers RO3003 (10mil)",
                "Rogers RO4003C (20mil)",
                "Rogers RO4350B (30mil)",
            ],
            state="readonly",
        )
        cb_board.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=5)
        row += 2

        # Operational Triggers
        ttk.Button(
            ctrl_frame, text="🔄 Recalculate Workspace", command=self.recompute_all
        ).grid(row=row, column=0, columnspan=2, pady=15, sticky="ew")
        ttk.Button(
            ctrl_frame,
            text="💾 Export KiCad Production Files",
            command=self.export_hardware,
        ).grid(row=row + 1, column=0, columnspan=2, pady=5, sticky="ew")

        # ---------------- RIGHT VISUALIZATION WORKBOOK ----------------
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=1, sticky="nsew")
        main_frame.columnconfigure(1, weight=1)

        # Tab 1: Terminal Matrix Logs Console
        self.log_text = tk.Text(
            self.notebook,
            width=60,
            font=("Courier", 10),
            bg="#2b2b2b",
            fg="#a9b7c6",
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.notebook.add(self.log_text, text=" Hardcopy Engineering Logs ")

        # Tab 2: Matplotlib Linear Curves Performance Panel
        self.plot_fig, _ = plt.subplots(2, 2, figsize=(8, 6))
        self.plot_canvas = FigureCanvasTkAgg(self.plot_fig, master=self.notebook)
        self.notebook.add(
            self.plot_canvas.get_tk_widget(), text=" RF Linear Curves (S-Parameters) "
        )

        # Tab 3: Matplotlib Twin Stability Smith Charts
        self.smith_fig, _ = plt.subplots(1, 2, figsize=(8, 4))
        self.smith_canvas = FigureCanvasTkAgg(self.smith_fig, master=self.notebook)
        self.notebook.add(
            self.smith_canvas.get_tk_widget(), text=" Stability Circles Smith Charts "
        )

        # Tab 4: Substrate 2D Heat Dissipation Profiles
        self.therm_fig = plt.figure(figsize=(6, 4.5))
        self.therm_canvas = FigureCanvasTkAgg(self.therm_fig, master=self.notebook)
        self.notebook.add(
            self.therm_canvas.get_tk_widget(), text=" Surface Thermal Gradient "
        )

        # Tab 5: Spatial TDR Mismatch Profiler Layout Canvas
        self.tdr_fig, self.tdr_ax = plt.subplots(figsize=(8, 5))
        self.tdr_canvas = FigureCanvasTkAgg(self.tdr_fig, master=self.notebook)
        self.notebook.add(self.tdr_canvas.get_tk_widget(), text=" Spatial TDR Mismatch Graph ")

        # Fixed Application Footer Metadata Panel ---
        footer_frame = ttk.Frame(main_frame, padding=(5, 2))
        footer_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        main_frame.rowconfigure(1, weight=0) # Lock vertical expansion to the workbook panels

        # Attribution Notice
        author_lbl = ttk.Label(
            footer_frame,
            text="Copyright © 2026, Edward O'Callaghan. All rights reserved.",
            font=("Arial", 9, "italic"),
            foreground="#888888"
        )
        author_lbl.pack(side=tk.LEFT, padx=5)

        # Live Substrate Environment Telemetry Status Tag
        self.status_msg_var = tk.StringVar(value="System Active | No File Ingested")
        status_lbl = ttk.Label(
            footer_frame,
            textvariable=self.status_msg_var,
            font=("Arial", 9, "bold"),
            foreground="#2b2b2b" if sys.platform == "win32" else "#a9b7c6"
        )
        status_lbl.pack(side=tk.RIGHT, padx=5)

    def on_secure_close(self):
        """
        Forces Matplotlib memory handles to clear completely, preventing the
        background thread hang when shutting down the desktop application.
        """
        plt.close("all")  # Purge all underlying figures from system memory
        self.root.quit()  # Terminate the Tkinter master thread block
        self.root.destroy()  # Securely destroy the desktop graphic workspace window

    def browse_s2p(self):
        fpath = filedialog.askopenfilename(
            filetypes=[("Touchstone S-Param Files", "*.s2p"), ("All Files", "*.*")]
        )
        if fpath:
            # Re-initialize complete class references using target model profile path context
            self.loader.load(fpath)
            self.s2p_path_var.set(os.path.basename(fpath))
            self.fmin_var.set(round(self.loader.f_min_mhz, 1))
            self.fmax_var.set(round(self.loader.f_max_mhz, 1))
            self.status_msg_var.set(f"Loaded: {os.path.basename(fpath)} | Substrate Model Configured")
            self.recompute_all()

    def recompute_all(self):
        if not self.designer.loader.network:
            messagebox.showwarning(
                "Data Profile Missing",
                "Please load a Mini-Circuits Touchstone .s2p file descriptor first.",
            )
            return

        # Inject our custom window limits directly into the analysis class variables
        f_low = self.fmin_var.get()
        f_high = self.fmax_var.get()

        if f_low >= f_high:
            messagebox.showerror(
                "Frequency Error",
                "Lower Working Frequency must be strictly less than the Upper Working Frequency.",
            )
            return

        self.loader.f_min_mhz = f_low
        self.loader.f_max_mhz = f_high
        self.loader.f_center_mhz = (f_low + f_high) / 2.0

        import io

        log_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = log_capture

        try:
            self.choke_block.design_bias_choke()
            self.choke_block.design_dc_block()

            self.bias_feedback.design_feedback_loop()
            self.bias_feedback.design_active_dc_bias(
                v_cc=self.vcc_var.get(), v_d=8.0, i_d=0.234
            )

            if self.layout_mode.get() == "Standard Microstrip":
                self.t_lines.calculate_pcb_microstrip(
                    board_type=self.board_type_var.get()
                )
            else:
                _best_w, _ = self.t_lines.calculate_pcb_gcpw(
                    board_type=self.board_type_var.get()
                )

            # Match and calculate electrical characteristics exactly at the center of your targeted working band
            self.t_lines.design_lc_matching(target_freq_mhz=self.loader.f_center_mhz)
            er_eff, _ = self.t_lines.calculate_microstrip_electrical_length(
                h_mils=62.0,
                er=4.2,
                target_deg=90.0,
                target_freq_mhz=self.loader.f_center_mhz,
            )
            self.t_lines.design_fixed_attenuator_pad(
                target_attn_db=self.attn_var.get()
            )

            # Execute structural spatial TDR sweeps via the rf_engine pipeline package
            dist_axis, z_profile = calculate_spatial_tdr(self.loader.network, er_eff=er_eff, z0=self.designer.z0)

            # Clear and redraw the TDR axis canvas container explicitly
            self.tdr_ax.clear()
            self.tdr_ax.plot(dist_axis, z_profile, color='deeppink', linewidth=2, label='Line Profile ($Z_{inst}$)')
            self.tdr_ax.axhline(self.designer.z0, color='grey', linestyle='--', alpha=0.7, label='Target $Z_0$ Baseline (50Ω)')

            self.tdr_ax.set_title("PCB Spatial Mismatch Profile (Time-Domain Reflectometry Simulation)")
            self.tdr_ax.set_xlabel("Physical Distance Along the Input Transmission Trace Path (mm)")
            self.tdr_ax.set_ylabel(r"Instantaneous Discontinuity Impedance ($\Omega$)")
            self.tdr_ax.set_ylim(35.0, 65.0)  # Bound standard viewport range cleanly around 50 Ohms
            self.tdr_ax.grid(True, linestyle=':', alpha=0.6)
            self.tdr_ax.legend(loc='upper right')
            self.tdr_fig.tight_layout()
            self.tdr_canvas.draw()

        finally:
            sys.stdout = old_stdout

        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, log_capture.getvalue())

        self.visualizer.plot_linear_performance(embed_fig=self.plot_fig)
        self.plot_canvas.draw()

        self.stability.plot_stability_circles(
            target_freq_mhz=self.loader.f_center_mhz, embed_fig=self.smith_fig
        )
        self.smith_canvas.draw()

        plt.figure(self.therm_fig.number)
        self.thermals.analyze_thermal_profile(
            t_ambient_c=self.tamb_var.get(),
            v_d=8.0,
            i_d=0.234,
            theta_jc=29.3,
            board_type=self.board_type_var.get(),
            embed_fig=self.therm_fig,
        )
        self.therm_canvas.draw()

    def export_hardware(self):
        if not self.loader.network:
            messagebox.showwarning(
                "Export Blocked",
                "No trace model data loaded to synthesize footprints from.",
            )
            return

        # Handle local track dimensions queries relative to dropdown states
        if self.layout_mode.get() == "Standard Microstrip":
            self.t_lines.calculate_pcb_microstrip(
                board_type=self.board_type_var.get()
            )
        else:
            _best_w, _ = self.t_lines.calculate_pcb_gcpw(
                board_type=self.board_type_var.get()
            )

        # Output project blocks straight to workspace directory path with environment safety checks
        lay_file = "gui_layout.kicad_pcb"
        sch_file = "gui_schematic.kicad_sch"
        rpt_file = "gui_report.md"

        try:
            serialize_pcb_layout(output_filename=lay_file, trace_width_mils=best_w)
            serialize_schematic(output_filename=sch_file)

            # Re-compute active parameters to pass down spatial trace telemetry live maps
            er_eff, _ = self.t_lines.calculate_microstrip_electrical_length(
                h_mils=62.0, er=4.2, target_deg=90.0, target_freq_mhz=self.loader.f_center_mhz
            )
            dist_axis, z_profile = calculate_spatial_tdr(self.loader.network, er_eff=er_eff, z0=self.designer.z0)

            serialize_markdown_report(
                output_filename=rpt_file,
                f_min=self.loader.f_min_mhz,
                f_max=self.loader.f_max_mhz,
                f_center=self.loader.f_center_mhz,
                z0=self.designer.z0,
                tdr_distance=dist_axis,
                tdr_impedance=z_profile
            )

            messagebox.showinfo(
                "Export Complete",
                "Successfully rendered project documents inside directory path:\n\n"
                " -> 'gui_layout.kicad_pcb'\n"
                " -> 'gui_schematic.kicad_sch'\n"
                " -> 'gui_report.md'",
            )
        except ImportError as err:
            messagebox.showerror("Dependency Error", str(err))


if __name__ == "__main__":
    root = tk.Tk()
    app = DesignerApp(root)
    root.mainloop()
