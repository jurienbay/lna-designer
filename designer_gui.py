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
    MicrostripStubBiasDesigner,
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

    def run_animation_frame_tick(self):
        """Executes a single redraw slice and schedules the subsequent frame tick."""
        if not self.animating:
            return

        # Advance the wave's phase slice (omega * t)
        self.current_phase += 0.15
        if self.current_phase >= 2 * math.pi:
            self.current_phase = 0.0

        # Fetch fresh time-dependent wave arrays
        mesh_data = self.stub_designer.generate_3d_mesh_data(phase_shift=self.current_phase)

        # Clear previous frame vector paths while keeping camera angles locked
        curr_elev = self.em_3d_ax.elev
        curr_azim = self.em_3d_ax.azim
        self.em_3d_ax.clear()

        # Redraw all elements for the new frame
        sub_x, sub_y, z_top, z_bot = mesh_data["substrate"]
        self.em_3d_ax.plot_surface(sub_x, sub_y, z_top, color='green', alpha=0.1, edgecolor='none')
        self.em_3d_ax.plot_surface(sub_x, sub_y, z_bot, color='gold', alpha=0.2, edgecolor='none')

        cu_x, cu_y, cu_z = mesh_data["stub_poly"]
        self.em_3d_ax.plot_trisurf(cu_x, cu_y, cu_z, color='darkorange', alpha=0.8, edgecolor='brown', linewidth=0.5)

        for v_x, v_y, v_z in mesh_data["vias"]:
            self.em_3d_ax.plot_surface(v_x, v_y, v_z, color='crimson', alpha=0.7, edgecolor='none')

        wx, wy, wz, hx = mesh_data["wave_trace"]
        self.em_3d_ax.plot(wx, wy, wz, color='cyan', linewidth=3.5, label='E-Field Vector Wave ($E_z$)')
        for i in range(0, len(wy), 3):
            self.em_3d_ax.plot([wx[i], wx[i]], [wy[i], wy[i]], [0, wz[i]], color='cyan', linestyle=':', linewidth=1.2)

        # Overlay Orthogonal Pink/Magenta Magnetic Field Vector Arrows (H)
        # Using 3D quiver to draw horizontal arrows wrapping right-angles around the track path
        sample_stride = 2 # Prevent arrow crowding on layout screen
        self.em_3d_ax.quiver(
            wx[::sample_stride], wy[::sample_stride], np.zeros_like(wz)[::sample_stride], # Arrow origins
            hx[::sample_stride], np.zeros_like(hx)[::sample_stride], np.zeros_like(hx)[::sample_stride], # Vector directions (X-axis offset)
            color='deeppink', length=0.8, normalize=True, label='Magnetic Field ($H_x$)'
        )

        # Restore configuration properties and views
        self.em_3d_ax.set_title(f"Live 3D EM Wave Propagation Solver (Phase: {self.current_phase:.2f} rad)")
        self.em_3d_ax.set_xlabel("X-Axis (mm)")
        self.em_3d_ax.set_ylabel("Y-Axis (mm)")
        self.em_3d_ax.set_zlabel("Field Strength / Height (Z)")
        self.em_3d_ax.set_zlim(-2.5, 1.5)
        self.em_3d_ax.view_init(elev=curr_elev, azim=curr_azim)
        self.em_3d_ax.legend(loc='upper right', fontsize='x-small')

        # Flush the buffer updates to the UI canvas
        self.em_3d_canvas.draw_idle()

        # Schedule next frame update (~50ms delay for roughly 20 FPS)
        self.anim_loop_id = self.root.after(50, self.run_animation_frame_tick)

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

        # Tab 6: 3D Electromagnetic Structural Mesh Previewer Panel
        self.em_3d_fig = plt.figure(figsize=(8, 6))
        self.em_3d_ax = self.em_3d_fig.add_subplot(111, projection='3d') # 3D projection viewport coordinates

        # Master layout container for tab 6
        tab6_frame = ttk.Frame(self.notebook, padding="5")
        self.em_3d_canvas = FigureCanvasTkAgg(self.em_3d_fig, master=tab6_frame)
        self.em_3d_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Play/Pause interactive media dock
        media_btn_frame = ttk.Frame(tab6_frame)
        media_btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        self.play_btn = ttk.Button(media_btn_frame, text="▶ Play Wave Propagation", command=self.toggle_wave_animation)
        self.play_btn.pack(side=tk.TOP, pady=5)

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
            self.fmin_var.set(round(self.loader.f_min_mhz, 1))
            self.fmax_var.set(round(self.loader.f_max_mhz, 1))
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

        log_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = log_capture

        ## XXX hacked in.
        # Sync runtime updates across your distributed microstrip calculator parameters
        board_name = self.board_type_var.get()
        substrate_profiles = {
            "FR-4 Standard (1.6mm)": {"er": 4.2, "h": 1.6},
            "Rogers RO3003 (10mil)": {"er": 3.00, "h": 0.254},
            "Rogers RO4003C (20mil)": {"er": 3.38, "h": 0.508},
            "Rogers RO4350B (30mil)": {"er": 3.48, "h": 0.762},
        }
        profile = substrate_profiles.get(board_name, {"er": 4.2, "h": 1.6})
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
            mesh_data = self.stub_designer.generate_3d_mesh_data()
            self.em_3d_ax.clear()

            # Layer 1: Draw Substrate Box and Ground planes
            sub_x, sub_y, z_top, z_bot = mesh_data["substrate"]
            self.em_3d_ax.plot_surface(sub_x, sub_y, z_top, color='green', alpha=0.1, edgecolor='none')
            self.em_3d_ax.plot_surface(sub_x, sub_y, z_bot, color='gold', alpha=0.2, edgecolor='none')

            # Layer 2: Draw Etched Copper Radial Stub Wedge
            cu_x, cu_y, cu_z = mesh_data["stub_poly"]
            self.em_3d_ax.plot_trisurf(cu_x, cu_y, cu_z, color='darkorange', alpha=0.8, edgecolor='brown', linewidth=0.5)

            # Layer 3: Render 3D Stitched Thermal Vias through back-plane
            for v_x, v_y, v_z in mesh_data["vias"]:
                # Color copper walls bright crimson to make barrel geometry boundaries highly clear
                self.em_3d_ax.plot_surface(v_x, v_y, v_z, color='crimson', alpha=0.7, edgecolor='none')

            # Layer 4: Render active Voltage/E-Field Wave Propagation paths
            wx, wy, wz, hx = mesh_data["wave_trace"]
            # Primary Traveling wave entry track path line
            self.em_3d_ax.plot(wx, wy, wz, color='cyan', linewidth=3.5, label='E-Field Vector Wave ($E_z$)')
            # Add decorative standing wave directional drop indicators
            for i in range(0, len(wy), 3):
                self.em_3d_ax.plot([wx[i], wx[i]], [wy[i], wy[i]], [0, wz[i]], color='cyan', linestyle=':', linewidth=1.2)

            # Overlay Orthogonal Pink/Magenta Magnetic Field Vector Arrows (H)
            # Using 3D quiver to draw horizontal arrows wrapping right-angles around the track path
            sample_stride = 2 # Prevent arrow crowding on layout screen
            self.em_3d_ax.quiver(
                wx[::sample_stride], wy[::sample_stride], np.zeros_like(wz)[::sample_stride], # Arrow origins
                hx[::sample_stride], np.zeros_like(hx)[::sample_stride], np.zeros_like(hx)[::sample_stride], # Vector directions (X-axis offset)
                color='deeppink', length=0.8, normalize=True, label='Magnetic Field ($H_x$)'
            )

            # Formating Viewport Boundaries
            self.em_3d_ax.set_title(f"3D EM Simulation & Thermal Via Array Preview (Substrate h = {self.stub_designer.h_mm}mm)")
            self.em_3d_ax.set_xlabel("X-Axis Dimensions (mm)")
            self.em_3d_ax.set_ylabel("Y-Axis Dimensions (mm)")
            self.em_3d_ax.set_zlabel("Field Strength / Height (Z)")
            self.em_3d_ax.set_zlim(-2.5, 1.5)
            self.em_3d_ax.view_init(elev=22, azim=-55)
            self.em_3d_ax.legend(loc='upper right', fontsize='x-small')
            self.em_3d_fig.tight_layout()
            self.em_3d_canvas.draw()

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

            serialize_pcb_layout(
                output_filename=lay_file,
                trace_width_mils=best_w,
                stub_engine_instance=stub_pass
            )
            serialize_schematic(output_filename=sch_file)

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
    root = tk.Tk()
    app = DesignerApp(root)
    root.mainloop()
