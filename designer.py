#!/usr/bin/env python3

## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from rf import (
    SUBSTRATE_PROFILES,
    BiasFeedbackDesigner,
    ChokeBlockDesigner,
    MicrostripStubBiasDesigner,
    RFPerformanceVisualizer,
    SParameterLoader,
    StabilityAnalyzer,
    ThermalAdvisor,
    TransmissionLineSuite,
    calculate_spatial_tdr,
    serialize_markdown_report,
    serialize_pcb_layout,
    serialize_schematic,
)


class DesignerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Mini-Circuits Monolithic Linear Amplifier CAD Space Suite")
        self.root.geometry("1300x850")

        # Instantiate the analysis engine with no initial file path
        self.loader = SParameterLoader()
        self.z0 = 50.0
        self.visualizer = RFPerformanceVisualizer(loader_instance=self.loader)
        self.stability = StabilityAnalyzer(loader_instance=self.loader, z0=50.0)
        self.choke_block = ChokeBlockDesigner(loader_instance=self.loader, z0=50.0)
        self.bias_feedback = BiasFeedbackDesigner(loader_instance=self.loader, z0=50.0)
        self.thermals = ThermalAdvisor(loader_instance=self.loader)
        self.t_lines = TransmissionLineSuite(loader_instance=self.loader, z0=50.0)
        self.stub_designer = MicrostripStubBiasDesigner(loader_instance=self.loader, z0=50.0)

        # Interactive animation loop flags
        self.animating = False
        self.current_phase = 0.0
        self.anim_loop_id = None

        # New Diagnostic Variables
        self.simulation_mode = tk.StringVar(value="cw")
        self.live_freq_tuner_var = tk.DoubleVar(value=500.0)

        # Core GUI Reactive Application Variables
        self.vcc_var = tk.DoubleVar(value=12.0)
        self.tamb_var = tk.DoubleVar(value=25.0)
        self.fmin_var = tk.DoubleVar(value=30.0)
        self.fmax_var = tk.DoubleVar(value=500.0)
        self.attn_var = tk.DoubleVar(value=3.0)
        self.layout_mode = tk.StringVar(value="Standard Microstrip")
        self.board_type_var = tk.StringVar(value="FR-4 Standard (1.6mm)")
        self.s2p_path_var = tk.StringVar(value="No File Loaded")
        self.active_device_var = tk.StringVar(value="PHA-13HLN+")

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_secure_close)

    def toggle_wave_animation(self):
        """Toggles the execution state of the time-domain wave solver."""
        if not self.loader.network:
            messagebox.showwarning("Data Profile Missing", "Please load an .s2p Touchstone dataset file first.")
            return

        self.animating = not self.animating
        if self.animating:
            self.play_btn.config(text="⏸ Pause Wave Propagation")
            self.run_animation_frame_tick()
        else:
            self.play_btn.config(text="▶ Play Wave Propagation")
            if self.anim_loop_id:
                self.root.after_cancel(self.anim_loop_id)

    def render_3d_viewport(self):
        """Unified rendering logic for the 3D EM core lamination stackup view."""

        # Sync live slider string label text indicator lookups
        f_tuned = self.live_freq_tuner_var.get()
        self.freq_lbl.config(text=f"{f_tuned:.1f} MHz")

        # Fetch parameterized mesh state maps
        mesh_data = self.stub_designer.generate_3d_mesh_data(
            phase_shift=self.current_phase,
            eval_freq_mhz=f_tuned,
            mode=self.simulation_mode.get(),
            device_name=self.active_device_var.get()
        )

        # Clear previous frame vector paths while keeping camera angles locked
        curr_elev, curr_azim = self.em_3d_ax.elev, self.em_3d_ax.azim
        self.em_3d_ax.clear()

        # Render Core Lamination Layers
        sub_x, sub_y, z_top, z_bot = mesh_data["substrate"]
        self.em_3d_ax.plot_surface(sub_x, sub_y, z_top, color='green', alpha=0.08, edgecolor='none')
        self.em_3d_ax.plot_surface(sub_x, sub_y, z_bot, color='gold', alpha=0.15, edgecolor='none')

        cu_x, cu_y, cu_z = mesh_data["stub_poly"]
        self.em_3d_ax.plot_trisurf(cu_x, cu_y, cu_z, color='darkorange', alpha=0.75, edgecolor='brown', linewidth=0.5)

        # Render Fields traces
        wx, wy, wz, hx = mesh_data["wave_trace"]
        self.em_3d_ax.plot(wx, wy, wz, color='cyan', linewidth=2.5, label='E-Field Vector Wave ($E_z$)')
        for i in range(0, len(wy), 3):
            self.em_3d_ax.plot([wx[i], wx[i]], [wy[i], wy[i]], [0, wz[i]], color='cyan', linestyle=':', linewidth=0.8)

        self.em_3d_ax.quiver(wx[::2], wy[::2], np.zeros_like(wz)[::2], hx[::2], np.zeros_like(hx)[::2], np.zeros_like(hx)[::2], color='deeppink', length=0.8, normalize=True, label='Magnetic Field ($H_x$)')

        # --- DYNAMIC MATRIX HOOK: LIVE VIEWPORT S-PARAMETER CARDS INTERPOLATION ---
        # Query your loaded network live to read attenuation levels at this specific slider frequency
        s21_db_val = -35.0  # Safe default isolation attenuation boundary line
        if self.loader.network is not None:
            f_hz_query = f_tuned * 1e6
            idx = np.argmin(np.abs(self.loader.network.f - f_hz_query))
            s21_db_val = self.loader.network.s21.s_db[idx][0][0]

        # Draw a live telemetry overlay board box directly inside the axes projection coordinates
        telemetry_text = (
            f"  [ RF COMPILER LIVE TELEMETRY ]\n"
            f"  • Operation Freq : {f_tuned:.1f} MHz\n"
            f"  • Transmission S21: {s21_db_val:.2f} dB\n"
            f"  • Isolation Level: {'EXCELLENT (<-25dB)' if s21_db_val < -25 else 'POOR CORNER BOUNDARY'}"
        )
        self.em_3d_ax.text2D(-0.20, 0.90, telemetry_text, transform=self.em_3d_ax.transAxes,
                             color='white', weight='bold', fontname='monospace', fontsize=9,
                             bbox=dict(facecolor='#1e1e1e', alpha=0.85, edgecolor='#444444', boxstyle='round,pad=0.5'))

        # Global layout styling configurations
        self.em_3d_ax.set_title("Real-Time Transmission Line Field Diagnostics", fontsize=10, weight='bold')
        self.em_3d_ax.set_xlim(-25, 25)
        self.em_3d_ax.set_ylim(-30, 10)
        self.em_3d_ax.set_zlim(-2.5, 1.5)
        self.em_3d_ax.view_init(elev=curr_elev, azim=curr_azim)
        self.em_3d_ax.legend(loc='upper right', fontsize='x-small')
        self.em_3d_fig.tight_layout()
        self.em_3d_canvas.draw_idle()

    def run_animation_frame_tick(self):
        """Executes a single redraw slice and schedules the subsequent frame tick."""
        if not self.animating:
            return

        # Handle phase increments / reset envelope step boundaries for the TDR window loop
        if self.simulation_mode.get() == "cw":
            self.current_phase += 0.15
            if self.current_phase >= 2 * math.pi:
                self.current_phase = 0.0
        else:
            self.current_phase += 0.08
            if self.current_phase >= 7.5:  # Let pulse scale pass out of frame viewport cleanly before wrap
                self.current_phase = 0.0

        # Execute unified render pass
        self.render_3d_viewport()
        # Schedule next frame update (~45ms delay for roughly 20 FPS)
        self.anim_loop_id = self.root.after(45, self.run_animation_frame_tick)

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
            values=list(SUBSTRATE_PROFILES.keys()),
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
        # Register the virtual event hook to track tab selection changes
        self.notebook.bind("<<NotebookTabChanged>>", self.on_notebook_tab_switched)

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

        # Tab 6: 3D Electromagnetic Structural Mesh Previewer Panel
        self.em_3d_fig = plt.figure(figsize=(8, 6))
        self.em_3d_ax = self.em_3d_fig.add_subplot(111, projection='3d') # 3D projection viewport coordinates

        # Master layout container for tab 6
        tab6_frame = ttk.Frame(self.notebook, padding="5")
        self.em_3d_canvas = FigureCanvasTkAgg(self.em_3d_fig, master=tab6_frame)
        self.em_3d_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Enhanced Diagnostic Media Control Panel
        dash_panel = ttk.LabelFrame(tab6_frame, text=" Interactive Diagnostic Controls ", padding="8")
        dash_panel.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        # Sub-grid column 1: Play state toggle and wave type profile selections
        left_sub = ttk.Frame(dash_panel)
        left_sub.pack(side=tk.LEFT, padx=10)

        self.play_btn = ttk.Button(left_sub, text="▶ Play Wave Propagation", command=self.toggle_wave_animation)
        self.play_btn.pack(side=tk.LEFT, padx=5)

        ttk.Radiobutton(left_sub, text="Continuous Wave (CW)", variable=self.simulation_mode, value="cw").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(left_sub, text="Transient TDR Pulse Packet", variable=self.simulation_mode, value="tdr").pack(side=tk.LEFT, padx=5)

        # Sub-grid column 2: Dynamic Real-time Frequency tuning scale slider
        right_sub = ttk.Frame(dash_panel)
        right_sub.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=20)

        ttk.Label(right_sub, text="Live Tuning Frequency:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
        self.freq_slider = ttk.Scale(right_sub, from_=10.0, to=2000.0, variable=self.live_freq_tuner_var, orient=tk.HORIZONTAL)
        self.freq_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.freq_lbl = ttk.Label(right_sub, text="500.0 MHz", font=("Courier", 9, "bold"))
        self.freq_lbl.pack(side=tk.RIGHT, padx=5)

        self.notebook.add(tab6_frame, text=" 3D Structural EM Viewer ")

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

    def on_notebook_tab_switched(self, event):
        """Monitors tab navigation changes and pauses the 3D wave thread if focus leaves tab 6."""
        # Only check tab indices if data records exist to prevent initialization timing race conditions
        if not self.loader.network or not self.animating:
            return

        try:
            # Query the index string name of the currently selected workbook view tab panel
            active_tab_index = self.notebook.index(self.notebook.select())

            # If active tab index is not Tab 6 (index 5 since counts start at 0), pause the loop
            if active_tab_index != 5:
                # Toggle flag to False and restore text state layout properties cleanly
                self.animating = False
                self.play_btn.config(text="▶ Play Wave Propagation")
                if self.anim_loop_id:
                    self.root.after_cancel(self.anim_loop_id)
        except Exception:
            pass # Prevent thread exception noise during early runtime window instantiation teardowns

    def on_secure_close(self):
        """
        Forces Matplotlib memory handles to clear completely, preventing the
        background thread hang when shutting down the desktop application.
        """
        self.animating = False
        if self.anim_loop_id:
            self.root.after_cancel(self.anim_loop_id)
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
            # If the parser returns values shifted into decimals (like 0.3), scale them up to true MHz values (30.0)
            f_min_val = self.loader.f_min_mhz if self.loader.f_min_mhz >= 1.0 else self.loader.f_min_mhz * 100.0
            f_max_val = self.loader.f_max_mhz if self.loader.f_max_mhz >= 1.0 else self.loader.f_max_mhz * 100.0
            # Update the UI state variables safely with the verified MHz numbers
            self.fmin_var.set(round(f_min_val, 1))
            self.fmax_var.set(round(f_max_val, 1))
            self.freq_slider.config(from_=round(self.loader.f_min_mhz, 1), to=round(self.loader.f_max_mhz, 1))
            self.live_freq_tuner_var.set(round(self.loader.f_center_mhz, 1))
            self.status_msg_var.set(f"Loaded: {os.path.basename(fpath)} | Substrate Model Configured")
            self.recompute_all()

    def recompute_all(self):
        if not self.loader.network:
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

        from rf.hardware_profiles import DEVICE_PROFILES  # Dynamic profile import

        target_device = self.active_device_var.get()
        dev_spec = DEVICE_PROFILES.get(target_device, DEVICE_PROFILES["PHA-13HLN+"])

        log_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = log_capture

        # Sync runtime updates across your distributed microstrip calculator parameters
        board_name = self.board_type_var.get()
        profile = SUBSTRATE_PROFILES.get(board_name, {"er": 4.2, "h": 1.6})
        self.stub_designer.er = profile["er"]
        self.stub_designer.h_mm = profile["h"]

        try:
            # Determine topology switch execution based on operational frequency ceiling limits
            if self.loader.f_max_mhz >= 2000.0:
                print("\n[!] Frequency > 2.0 GHz: Executing Distributed Planar Layout Calculations...")
                self.stub_designer.design_radial_stub_network(stub_angle_deg=60, num_stages=2)
            else:
                print("\n[*] Low-Frequency Window Active: Standard SMD footprint design active.")
                self.choke_block.design_bias_choke()
                self.choke_block.design_dc_block()

            self.bias_feedback.design_feedback_loop()
            self.bias_feedback.design_active_dc_bias(
                v_cc=self.vcc_var.get(), v_d=8.0, i_d=0.234
            )

            if self.layout_mode.get() == "Standard Microstrip":
                best_w = self.t_lines.calculate_pcb_microstrip(
                    board_type=self.board_type_var.get()
                )
            else:
                best_w, _ = self.t_lines.calculate_pcb_gcpw(
                    board_type=self.board_type_var.get()
                )

            # Match and calculate electrical characteristics exactly at the center of your targeted working band
            self.t_lines.design_lc_matching(target_freq_mhz=self.loader.f_center_mhz)
            # Map dynamic height parameter in mils (h_mm * 39.3701)
            active_h_mils = profile["h"] * 39.3701
            er_eff, _ = self.t_lines.calculate_microstrip_electrical_length(
                h_mils=active_h_mils,
                er=profile["er"],
                target_deg=90.0,
                target_freq_mhz=self.loader.f_center_mhz,
            )
            self.t_lines.design_fixed_attenuator_pad(
                target_attn_db=self.attn_var.get()
            )

            # Execute structural spatial TDR sweeps via the rf_engine pipeline package
            dist_axis, z_profile = calculate_spatial_tdr(self.loader.network, er_eff=er_eff, z0=self.z0)

            # Clear and redraw the TDR axis canvas container explicitly
            self.tdr_ax.clear()
            self.tdr_ax.plot(dist_axis, z_profile, color='deeppink', linewidth=2, label='Line Profile ($Z_{inst}$)')
            self.tdr_ax.axhline(self.z0, color='grey', linestyle='--', alpha=0.7, label='Target $Z_0$ Baseline (50Ω)')

            self.tdr_ax.set_title("PCB Spatial Mismatch Profile (Time-Domain Reflectometry Simulation)")
            self.tdr_ax.set_xlabel("Physical Distance Along the Input Transmission Trace Path (mm)")
            self.tdr_ax.set_ylabel(r"Instantaneous Discontinuity Impedance ($\Omega$)")
            self.tdr_ax.set_ylim(35.0, 65.0)  # Bound standard viewport range cleanly around 50 Ohms
            self.tdr_ax.grid(True, linestyle=':', alpha=0.6)
            self.tdr_ax.legend(loc='upper right')
            self.tdr_fig.tight_layout()
            self.tdr_canvas.draw()

            # --- RENDER ADVANCED 3D EM STRUCTURAL VIEWPORT ---
            self.render_3d_viewport()

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
            v_d=dev_spec["v_d"],
            i_d=dev_spec["i_d"],
            theta_jc=dev_spec["theta_jc"],
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
            best_w = self.t_lines.calculate_pcb_microstrip(
                board_type=self.board_type_var.get()
            )
        else:
            best_w, _ = self.t_lines.calculate_pcb_gcpw(
                board_type=self.board_type_var.get()
            )

        # Output project blocks straight to workspace directory path with environment safety checks
        lay_file = "gui_layout.kicad_pcb"
        sch_file = "gui_schematic.kicad_sch"
        rpt_file = "gui_report.md"

        try:
            # Determine if the active frequency profile demands a distributed planar stub
            stub_pass = self.stub_designer if self.loader.f_max_mhz >= 2000.0 else None
            # Extract active profile name parameter safely
            active_part = self.active_device_var.get()

            serialize_pcb_layout(
                output_filename=lay_file,
                trace_width_mils=best_w,
                stub_engine_instance=stub_pass,
                device_name=active_part
            )
            serialize_schematic(output_filename=sch_file, device_name=active_part)

            # Re-compute active parameters to pass down spatial trace telemetry live maps
            er_eff, _ = self.t_lines.calculate_microstrip_electrical_length(
                h_mils=62.0, er=4.2, target_deg=90.0, target_freq_mhz=self.loader.f_center_mhz
            )
            dist_axis, z_profile = calculate_spatial_tdr(self.loader.network, er_eff=er_eff, z0=self.z0)

            serialize_markdown_report(
                output_filename=rpt_file,
                f_min=self.loader.f_min_mhz,
                f_max=self.loader.f_max_mhz,
                f_center=self.loader.f_center_mhz,
                z0=self.z0,
                tdr_distance=dist_axis,
                tdr_impedance=z_profile,
                stub_engine_instance=self.stub_designer if self.loader.f_max_mhz >= 2000.0 else None
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
    # If no shell arguments are passed, launch the GUI workspace immediately
    if len(sys.argv) == 1:
        root = tk.Tk()
        app = DesignerApp(root)
        root.mainloop()
        sys.exit(0)

    # Arguments exist -> Execute automated headless CLI pipeline instead
    import argparse

    from termcolor import colored

    parser = argparse.ArgumentParser(
        description="Unified Mini-Circuits Linear Amplifier Physical Hardware Designer"
    )
    parser.add_argument("s2p_file", type=str, help="Path to target Touchstone file standard")
    parser.add_argument("-z", "--z0", type=float, default=50.0, help="System line target impedance")
    parser.add_argument("-f", "--freq-eval", type=float, default=None, help="Evaluation frequency match node")
    parser.add_argument("--fmin", type=float, default=None, help="Custom lower band limit")
    parser.add_argument("--fmax", type=float, default=None, help="Custom upper band limit")
    parser.add_argument("--vcc", type=float, default=12.0, help="Bias system voltage")
    parser.add_argument("--t-amb", type=float, default=85.0, help="Environmental background ambient temperature")
    parser.add_argument("--attn-pad", type=float, default=3.0, help="Inline target attenuator match")
    parser.add_argument("--gcpw-mode", action="store_true", help="Toggle GCPW synthesis mode")
    parser.add_argument("--export-path", type=str, default="design_report.md")
    parser.add_argument("--pcb-path", type=str, default="amp_layout.kicad_pcb")
    parser.add_argument("--sch-path", type=str, default="amp_schematic.kicad_sch")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--skip-smith", action="store_true")
    parser.add_argument(
        "--board-type",
        type=str,
        default="FR-4 Standard (1.6mm)",
        choices=list(SUBSTRATE_PROFILES.keys()),
        help="Select target PCB dielectric laminate substrate profile material",
    )

    args = parser.parse_args()
    print(colored(f"[*] CLI Engine Running: Compiling analytical configurations for '{args.s2p_file}'", "cyan", attrs=["bold"]))

    # Initialize Headless Core Classes
    cli_loader = SParameterLoader()
    cli_loader.load(args.s2p_file, f_min_override=args.fmin, f_max_override=args.fmax)

    cli_choke = ChokeBlockDesigner(loader_instance=cli_loader, z0=args.z0)
    cli_bias = BiasFeedbackDesigner(loader_instance=cli_loader, z0=args.z0)
    cli_thermal = ThermalAdvisor(loader_instance=cli_loader)
    cli_tlines = TransmissionLineSuite(loader_instance=cli_loader, z0=args.z0)
    cli_stub = MicrostripStubBiasDesigner(loader_instance=cli_loader, z0=args.z0)

    # Extract Substrate Map Metadata Profile
    prof = SUBSTRATE_PROFILES.get(args.board_type, substrate_profiles["FR-4 Standard (1.6mm)"])
    cli_stub.er, cli_stub.h_mm = prof["er"], prof["h"]

    # Headless Pipeline Execution Sweep
    if cli_loader.f_max_mhz >= 2000.0:
        cli_stub.design_radial_stub_network(stub_angle_deg=60, num_stages=2)
    else:
        cli_choke.design_bias_choke(srf_safety_factor=args.srf_safety)
        cli_choke.design_dc_block()

    cli_bias.design_feedback_loop()
    cli_bias.design_active_dc_bias(v_cc=args.vcc, v_d=8.0, i_d=0.234)
    cli_thermal.analyze_thermal_profile(t_ambient_c=args.t_amb, v_d=8.0, i_d=0.234, theta_jc=29.3, board_type=args.board_type)

    if args.gcpw_mode:
        best_w, _ = cli_tlines.calculate_pcb_gcpw(board_type=args.board_type)
    else:
        best_w = cli_tlines.calculate_microstrip(board_type=args.board_type)

    cli_tlines.design_lc_matching(target_freq_mhz=args.freq_eval)
    cli_tlines.calculate_microstrip_electrical_length(h_mils=prof["h_mils"], er=prof["er"], target_deg=90.0, target_freq_mhz=args.freq_eval)
    cli_tlines.design_fixed_attenuator_pad(target_attn_db=args.attn_pad)

    er_eff_calc, _ = cli_tlines.calculate_microstrip_electrical_length(h_mils=prof["h_mils"], er=prof["er"], target_deg=90.0, target_freq_mhz=cli_loader.f_center_mhz)
    dist_vec, z_vec = calculate_spatial_tdr(cli_loader.network, er_eff=er_eff_calc, z0=args.z0)

    # Serialize Hardcopy Assets to Disk
    serialize_markdown_report(
        output_filename=args.export_path, f_min=cli_loader.f_min_mhz, f_max=cli_loader.f_max_mhz,
        f_center=cli_loader.f_center_mhz, z0=args.z0, tdr_distance=dist_vec, tdr_impedance=z_vec,
        stub_engine_instance=cli_stub if cli_loader.f_max_mhz >= 2000.0 else None
    )
    serialize_pcb_layout(output_filename=args.pcb_path, trace_width_mils=best_w, stub_engine_instance=cli_stub if cli_loader.f_max_mhz >= 2000.0 else None)
    serialize_schematic(output_filename=args.sch_path)

    # 5. Optional Plot Operations
    if not args.skip_plots:
        cli_visualizer = RFPerformanceVisualizer(loader_instance=cli_loader)
        cli_visualizer.plot_linear_performance()
    if not args.skip_smith:
        cli_stability = StabilityAnalyzer(loader_instance=cli_loader, z0=args.z0)
        cli_stability.plot_stability_circles(target_freq_mhz=args.freq_eval)
