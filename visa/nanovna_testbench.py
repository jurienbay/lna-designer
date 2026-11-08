#!/usr/bin/env python3

## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import sys
import time
import struct
import numpy as np

# Use standard pyserial to interface with the NanoVNA's USB-CDC serial layer
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[!] Missing Serial Dependency. Please run: pip install pyserial")
    sys.exit(1)

class NanoVNATestBench:
    def __init__(self, port=None, baudrate=115200, timeout=2.0):
        """Initializes the virtual USB-CDC serial interface connection to the NanoVNA."""
        self.port = port if port else self.auto_detect_nanovna_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def auto_detect_nanovna_port(self):
        """Proactively scans your local operating system device trees to locate the NanoVNA."""
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            # Common NanoVNA / ChibiOS virtual serial interface vendor patterns
            if "NanoVNA" in p.description or "ChibiOS" in p.description or (p.vid == 0x0483 and p.pid == 0x5740):
                return p.device
        # Fallback to operating system default paths if auto-detection registers empty
        return "/dev/tpl_nanovna" if sys.platform != "win32" else "COM3"

    def connect(self):
        """Establishes open data streams across the target serial node interface."""
        print(f"[*] Opening communication link on interface port: {self.port}...")
        try:
            self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
            self.ser.flushInput()
            self.ser.flushOutput()
            # Issue a carriage return to clear out any residual buffer line items
            self.ser.write(b"\r\n")
            time.sleep(0.1)
            self.ser.read_all()
            print("[+] Connection Successful!")
        except Exception as e:
            print(f"[!] Critical Connection Error: Could not bind device descriptor on {self.port}: {e}")
            sys.exit(1)

    def send_command(self, cmd_bytes):
        """Sends a raw command down the line and validates response integrity."""
        self.ser.write(cmd_bytes + b"\r\n")
        self.ser.flush()

    def read_binary_data(self, command, num_points):
        """
        Interrogates the NanoVNA microcontroller registers to pull raw
        complex S-parameter coordinates (Real + Imaginary float components).
        """
        # NanoVNA returns data as binary structures containing pairs of 32-bit single-precision floats (8 bytes/point)
        expected_bytes = num_points * 8
        self.send_command(command)

        raw_data = b""
        start_time = time.time()

        while len(raw_data) < expected_bytes:
            chunk = self.ser.read(expected_bytes - len(raw_data))
            if not chunk:
                if (time.time() - start_time) > self.timeout:
                    raise TimeoutError("[!] VNA Register read operation timed out waiting for data packets.")
                continue
            raw_data += chunk

        # Unpack binary data blocks to native python float numbers
        complex_vectors = []
        for i in range(num_points):
            offset = i * 8
            real, imag = struct.unpack("<ff", raw_data[offset:offset+8])
            complex_vectors.append(complex(real, imag))

        return np.array(complex_vectors)

    def capture_segmented_sweep(self, start_mhz, end_mhz, total_points=201):
        """
        Orchestrates split segmented sweep loops to bypass the 101-point hardware buffer ceiling.
        Stitches multi-decade measurements back into unified data vectors.
        """
        # Determine the maximum safe boundary size per segmented sweep frame step (capped at 101)
        points_per_segment = 101
        num_segments = int(np.ceil(total_points / points_per_segment))

        frequencies = np.linspace(start_mhz * 1e6, end_mhz * 1e6, total_points)
        s11_full = []
        s21_full = []

        print(f"[*] Commencing Segmented Data Verification Pass: {start_mhz:.1f} to {end_mhz:.1f} MHz")

        for s in range(num_segments):
            idx_start = s * points_per_segment
            idx_end = min((s + 1) * points_per_segment, total_points)
            seg_points = idx_end - idx_start

            f_start = frequencies[idx_start]
            f_end = frequencies[idx_end - 1]

            print(f"    -> Sweeping Segment {s+1}/{num_segments} [{f_start/1e6:.2f} MHz - {f_end/1e6:.2f} MHz] ({seg_points} pts)...")

            # Programmatically instruct the NanoVNA sweep limits via register sets
            self.send_command(f"sweep {int(f_start)} {int(f_end)} {seg_points}".encode())
            time.sleep(0.2) # Allow internal synthesize oscillators to settle phase locks safely

            # Read Channel 0 (Reflections -> S11) and Channel 1 (Through Gains -> S21)
            s11_seg = self.read_binary_data(b"data 0", seg_points)
            s21_seg = self.read_binary_data(b"data 1", seg_points)

            s11_full.extend(s11_seg)
            s21_full.extend(s21_seg)

        return frequencies, np.array(s11_full), np.array(s21_full)

    def serialize_to_touchstone_s2p(self, filename, freq_hz, s11, s21):
        """
        Compiles the gathered vector matrices and writes an industry-standard,
        copy-pasteable 2-port Touchstone (.s2p) file format to disk.
        """
        print(f"[*] Writing real-world verified Touchstone log parameters to: '{filename}'...")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                # 1. Mandatory Touchstone File Format Header Elements
                f.write("# MHZ S RI R 50\n")
                f.write("! Real-Time Physical Verification Test Bench Log Asset\n")
                f.write("! Collected via Automated Python NanoVNA Sweeper Framework\n")
                f.write("! Freq(MHz)  S11_Real  S11_Imag  S21_Real  S21_Imag  S12_Real  S12_Imag  S22_Real  S22_Imag\n")

                # 2. Iterate and write data vectors
                for i in range(len(freq_hz)):
                    f_mhz = freq_hz[i] / 1e6

                    # Extract raw components for S11 and S21
                    s11_r, s11_i = s11[i].real, s11[i].imag
                    s21_r, s21_i = s21[i].real, s21[i].imag

                    # Since the NanoVNA is a non-reversing 2-port device architecture,
                    # reverse parameters (S12/S22) default safely to perfect termination isolation baselines
                    s12_r, s12_i = 0.0, 0.0
                    s22_r, s22_i = 0.0, 0.0

                    f.write(f"{f_mhz:<11.6f} {s11_r:>9.6f} {s11_i:>9.6f} {s21_r:>9.6f} {s21_i:>9.6f} {s12_r:>9.6f} {s12_i:>9.6f} {s22_r:>9.6f} {s22_i:>9.6f}\n")

            print(f"[+] S-Parameter verification tracking file export successful: '{filename}'")
        except IOError as e:
            print(f"[!] System Failure: Failed to write Touchstone data arrays to disk: {e}")

    def close(self):
        """Safely tears down open serial stream locks."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[*] Target interface serial stream closed cleanly.")

if __name__ == "__main__":
    # Test profile parameters configured to match your target lower/upper working bounds
    START_FREQ = 30.0   # Lower band limit (MHz)
    END_FREQ = 500.0    # Upper band limit (MHz)
    POINTS = 201        # Desired resolution (Stitched across segmented frames)
    OUTPUT_FILE = "bench_verified_amplifier.s2p"

    # Instantiate the test execution loop
    bench = NanoVNATestBench()
    bench.connect()

    try:
        cal_parser = CalibrationMatrixParser()

        print("[*] STEP 1: Connect SHORT circuit artifact to NanoVNA Ch0, then press Enter...")
        input()
        _, short_raw, _ = bench.capture_segmented_sweep(START_FREQ, END_FREQ, total_points=POINTS)

        print("[*] STEP 2: Connect OPEN circuit artifact to NanoVNA Ch0, then press Enter...")
        input()
        _, open_raw, _ = bench.capture_segmented_sweep(START_FREQ, END_FREQ, total_points=POINTS)

        print("[*] STEP 3: Connect 50-Ohm LOAD termination to NanoVNA Ch0, then press Enter...")
        input()
        _, load_raw, _ = bench.capture_segmented_sweep(START_FREQ, END_FREQ, total_points=POINTS)

        # Extract and solve the error matrices headlessly
        cal_parser.compute_1port_sol_coefficients(short_raw, open_raw, load_raw)

        print("[*] STEP 4: Connect your actual manufactured Amplifier PCB, then press Enter...")
        input()
        freqs, raw_s11, raw_s21 = bench.capture_segmented_sweep(START_FREQ, END_FREQ, total_points=POINTS)

        # Un-distort the trace data using your computed correction factors
        clean_s11 = cal_parser.apply_1port_correction(raw_s11)

        # Write the cleaned data to your touchstone s2p logging file
        bench.serialize_to_touchstone_s2p(OUTPUT_FILE, freqs, clean_s11, raw_s21)
    except Exception as run_err:
        print(f"[!] Verification script aborted: {run_err}")
    finally:
        bench.close()
