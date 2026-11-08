## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import numpy as np
from termcolor import colored


class MarkdownDocument:
    """Programmatic document tree model mapping structural markdown elements."""
    def __init__(self):
        self.elements = []

    def add_header(self, text, level=1):
        self.elements.append({"type": "header", "text": text, "level": level})

    def add_paragraph(self, text):
        self.elements.append({"type": "paragraph", "text": text})

    def add_bullet(self, key, value):
        self.elements.append({"type": "bullet", "key": key, "value": value})

    def add_table(self, headers, rows):
        self.elements.append({"type": "table", "headers": headers, "rows": rows})

    def render(self):
        lines = []
        for el in self.elements:
            if el["type"] == "header":
                lines.append(f"{'#' * el['level']} {el['text']}\n")
            elif el["type"] == "paragraph":
                lines.append(f"{el['text']}\n")
            elif el["type"] == "bullet":
                lines.append(f"* **{el['key']}:** {el['value']}")
            elif el["type"] == "table":
                lines.append("| " + " | ".join(el["headers"]) + " |")
                lines.append("| " + " | ".join(["---"] * len(el["headers"])) + " |")
                for row in el["rows"]:
                    lines.append("| " + " | ".join(row) + " |")
                lines.append("")
        return "\n".join(lines)


def serialize_markdown_report(output_filename, f_min, f_max, f_center, z0, tdr_distance=None, tdr_impedance=None, stub_engine_instance=None):
    """
    Builds and saves a verified procurement design document graph to disk.
    Now dynamically captures planar microstrip radial stub layout clearances.
    """
    import math
    doc = MarkdownDocument()
    doc.add_header("Automated RF Hardware Design Report", level=1)
    doc.add_paragraph("Generated Profile Analysis Suite for Mini-Circuits `.s2p` Device Networks.")

    doc.add_header("1. Operating Frequency Band Parameters", level=2)
    doc.add_bullet("Minimum Lower Bound", f"{f_min:.2f} MHz")
    doc.add_bullet("Maximum Upper Bound", f"{f_max:.2f} MHz")
    doc.add_bullet("Calculated Center Band Point", f"{f_center:.2f} MHz")
    doc.add_bullet("Reference Port Line Match Target", f"{z0} Ohms")
    doc.add_paragraph("")

    # --- DYNAMIC DISTRIBUTED PLANAR STUB NETWORK TELEMETRY LOG ---
    if stub_engine_instance is not None and f_max >= 2000.0:
        doc.add_header("2. Distributed Microstrip Radial Stub Geometric Parameters", level=2)
        doc.add_paragraph("High-frequency operational ceiling requires distributed etching geometry instead of discrete coils:")

        # Pull parameters dynamically from matching synthesis equations
        z_high = 100.0
        w_high, _ = stub_engine_instance.calculate_microstrip_w_and_eff(z_high)
        _, er_eff_stub = stub_engine_instance.calculate_microstrip_w_and_eff(stub_engine_instance.z0)

        lambda_g = stub_engine_instance.c0 / ((f_center * 1e6) * math.sqrt(er_eff_stub))
        radius_r_mm = (lambda_g / 4) * 1000
        angle_deg = 60.0
        outer_arc_w_mm = 2 * radius_r_mm * math.sin(math.radians(angle_deg) / 2)

        doc.add_bullet("Stub Topology Mode", f"Cascaded {angle_deg}° Planar Sector Element")
        doc.add_bullet("High-Z Trace Width ($W_{{high}}$)", f"{w_high:.3f} mm (Targeting {z_high} \u03a9)")
        doc.add_bullet("Fundamental Radial Radius (R)", fr"{radius_r_mm:.2f} mm ($\lambda/4$ Resonant Node)")
        doc.add_bullet("Throat Opening Entrance Width", f"{w_high:.3f} mm")
        doc.add_bullet("Outer Segment Arc Span Width", f"{outer_arc_w_mm:.2f} mm")
        doc.add_paragraph("")

    # --- MANDATORY HARDWARE BOM ---
    doc.add_header("3. Mandatory Component Sourcing Bill of Materials (BOM)", level=2)

    headers = ["Circuit Location Block", "Component Specified Value / Design Constraint Target"]

    # Update BOM row text dynamically depending on layout modes
    choke_description = "Distributed Microstrip Radial Stub Wedge (Etched Front Copper Layout)" if f_max >= 2000.0 else "Sized relative to target operating band SRF safety windows"

    rows = [
        ["RF Coupling Bias Choke Inductor", choke_description],
        ["Input/Output DC Blocks", "High-Q microwave ceramic caps optimized for band center resonance"],
        ["DC Biasing Resistor (Rbias)", "Heavy surface-area package to safely survive case thermal margins"],
        ["Controlled Transmission Track", "Trace width dimensions adjusted dynamically to lamination choices"]
    ]
    doc.add_table(headers, rows)

    # --- STRUCTURAL TELEMETRY SPATIAL LOGGING MATRIX ---
    if tdr_distance is not None and tdr_impedance is not None:
        doc.add_header("4. PCB Spatial Impedance Mismatch Analysis (TDR Log)", level=2)

        # Calculate worst-case absolute layout step error boundary metrics
        dev_from_50 = np.abs(tdr_impedance - z0)
        worst_idx = np.argmax(dev_from_50)
        worst_dist = tdr_distance[worst_idx]
        worst_z = tdr_impedance[worst_idx]

        doc.add_paragraph("Real-time Time-Domain Reflectometry tracking logs captured over active workspace runs:")
        doc.add_bullet("Worst-Case Discontinuity Peak", f"{worst_z:.2f} \u03a9 at {worst_dist:.2f} mm distance footprint")
        doc.add_bullet("Maximum Structural VSWR Delta Deviation", f"{np.max(dev_from_50):.2f} \u03a9 step error bound")
        doc.add_paragraph("")

        # Programmatically sample spatial down-sampled checkpoints to prevent excessive text growth
        doc.add_header("5. Down-Sampled Spatial Transmission Checkpoints", level=3)
        headers_tdr = ["Layout Position Node (mm)", "Calculated Instantaneous Impedance (\u03a9)"]
        rows_tdr = []

        # Take 5 distinct geometric verification markers spaced equally across the 50mm trace
        sample_indices = np.linspace(0, len(tdr_distance) - 1, 5, dtype=int)
        for idx in sample_indices:
            rows_tdr.append([f"{tdr_distance[idx]:.1f} mm", f"{tdr_impedance[idx]:.2f} \u03a9"])
        doc.add_table(headers_tdr, rows_tdr)

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(doc.render())
        print(colored(f"[+] Production Design Data Export Complete: Saved report to '{output_filename}'", "green", attrs=["bold"]))
        return f"[+] Design report generated: {output_filename}"
    except OSError as e:
        print(colored(f"[!] System Failure: Could not write file destination path: {e}", "red"))
        raise
