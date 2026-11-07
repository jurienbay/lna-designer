## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

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


def serialize_markdown_report(output_filename, f_min, f_max, f_center, z0):
    """
    Builds and saves a verified procurement design document graph to disk.
    """
    doc = MarkdownDocument()
    doc.add_header("Automated RF Hardware Design Report", level=1)
    doc.add_paragraph("Generated Profile Analysis Suite for Mini-Circuits `.s2p` Device Networks.")

    doc.add_header("1. Operating Frequency Band Parameters", level=2)
    doc.add_bullet("Minimum Lower Bound", f"{f_min:.2f} MHz")
    doc.add_bullet("Maximum Upper Bound", f"{f_max:.2f} MHz")
    doc.add_bullet("Calculated Center Band Point", f"{f_center:.2f} MHz")
    doc.add_bullet("Reference Port Line Match Target", f"{z0} Ohms")
    doc.add_paragraph("")

    doc.add_header("2. Mandatory Component Sourcing Bill of Materials (BOM)", level=2)

    headers = ["Circuit Location Block", "Component Specified Value / Design Constraint Target"]
    rows = [
        ["RF Coupling Bias Choke Inductor", "Sized relative to target operating band SRF safety windows"],
        ["Input/Output DC Blocks", "High-Q microwave ceramic caps optimized for band center resonance"],
        ["DC Biasing Resistor (Rbias)", "Heavy surface-area package to safely survive case thermal margins"],
        ["Controlled Transmission Track", "Trace trace width dimensions adjusted dynamically to lamination choices"]
    ]
    doc.add_table(headers, rows)

    # --- STRUCTURAL TELEMETRY SPATIAL LOGGING MATRIX ---
    if tdr_distance is not None and tdr_impedance is not None:
        doc.add_header("3. PCB Spatial Impedance Mismatch Analysis (TDR Log)", level=2)

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
        doc.add_header("4. Down-Sampled Spatial Transmission Checkpoints", level=3)
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
