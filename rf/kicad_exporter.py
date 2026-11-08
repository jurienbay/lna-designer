## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math
from termcolor import colored


def serialize_pcb_layout(output_filename, trace_width_mils, stub_engine_instance=None):
    """
    Generates a native KiCad PCB board file from scratch using the object-oriented
    data structures inside the pycbnew library.
    """
    try:
        from pycbnew.primitives.project import KProject
        from pycbnew.primitives.layer import Layer
        from pycbnew.primitives.footprint import KFootprint, KFootprintProperty, KPad
        from pycbnew.primitives.net import KNet
        from pycbnew.primitives.zone import KZone
        from pycbnew.utils.geometry import Point
    except ImportError:
        raise ImportError(
            "[!] Critical Dependency Error: 'kicad-pycbnew' library is missing or cannot be imported.\n"
            "    Please run: .venv/bin/pip install kicad-pycbnew"
        )

    print("\n" + "=" * 75)
    print(" 10. STRUCTURAL KICAD PCB PRODUCTION LAYOUT GENERATOR (VIA PYCBNEW)")
    print("=" * 75)

    proj = KProject(filename=output_filename, copper_layers=2)

    net1 = KNet(1, "one")
    net2 = KNet(2, "two")
    net3 = KNet(3, "three")
    net4 = KNet(4, "bias_stub")  # Dedicated net reference mapping for the etched stub copper node
    proj.add(net1)
    proj.add(net2)
    proj.add(net3)
    proj.add(net4)

    fp = KFootprint("Package_TO_SOT_SMD:SOT-89-3",
                    at=Point(0.0, 0.0),
                    side=KFootprint.Side.Front,
                    default_net=None)

    KFootprintProperty(fp, data=[], type="Description", value="SOT-89 MMIC Package with Integrated Thermal Matrix")

    KPad(fp, data = ["pad", "", KPad.Type.Smd, KPad.Shape.Rect, ['at', -1.5, 2.0], ['size', 0.65, 1.5] ])
    KPad(fp, data = ["pad", "", KPad.Type.Smd, KPad.Shape.Rect, ['at', 0.0, 1.0], ['size', 1.8, 3.5] ])
    KPad(fp, data = ["pad", "", KPad.Type.Smd, KPad.Shape.Rect, ['at', 1.5, 2.0], ['size', 0.65, 1.5] ])

    for x_pos in [-0.4, 0.4]:
        for y_pos in [-0.3, 0.7, 1.7]:
            KPad(fp,
                data = ["pad", "", KPad.Type.Thru_hole, KPad.Shape.Circle, ['at', x_pos, y_pos],
                ['size', 0.6, 0.6], ['drill', '0.3'], ['net', net1] ]
            )

    proj.add(fp)

    # --- PLANAR RADIAL STUB DISTRIBUTED LAYER GENERATOR ---
    if stub_engine_instance is not None:
        # 1. Fetch characterization geometry via the active engine instance math hooks
        z_high = 100.0
        w_high, _ = stub_engine_instance.calculate_microstrip_w_and_eff(z_high)

        f_target = stub_engine_instance.loader.f_center_mhz * 1e6
        _, er_eff_stub = stub_engine_instance.calculate_microstrip_w_and_eff(stub_engine_instance.z0)
        lambda_g = stub_engine_instance.c0 / (f_target * math.sqrt(er_eff_stub))
        radius_r_mm = (lambda_g / 4) * 1000

        # 2. Establish a placement anchor point relative to the device's pins
        # Injection point located right above the SOT-89 footprint center
        throat_x, throat_y = 0.0, -5.0
        angle_rad = math.radians(60.0)

        # 3. Derive absolute geometric multi-vertex wedge boundary nodes via coordinate rotation
        stub_points = [
            Point(throat_x - (w_high / 2.0), throat_y),  # Base Left Throat corner
            Point(throat_x - (radius_r_mm * math.sin(angle_rad / 2.0)), throat_y - radius_r_mm),  # Arc Top-Left boundary
            Point(throat_x + (radius_r_mm * math.sin(angle_rad / 2.0)), throat_y - radius_r_mm),  # Arc Top-Right boundary
            Point(throat_x + (w_high / 2.0), throat_y)   # Base Right Throat corner
        ]

        # 4. Instantiate and push the physical etched polygon zone structure onto the object array
        stub_zone = KZone(net=net4, layer="F.Cu")
        stub_zone.add_points(stub_points)
        proj.add(stub_zone)
        print(f"[+] Appended Planar Wedge Zone: {radius_r_mm:.2f}mm Radius Stub added at coordinate ({throat_x}, {throat_y})")

    # --- CONTROLLED 50 OHM TRACK COUPLING IN/OUT STRUCTURES ---
    in_zone = KZone(net=net2, layer="F.Cu")
    in_zone.add_points([
        Point(-40.0, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        Point(-1.5, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        Point(-1.5, 2.0 + (trace_width_mils * 0.0254 / 2.0)),
        Point(-40.0, 2.0 + (trace_width_mils * 0.0254 / 2.0))
    ])

    out_zone = KZone(net=net3, layer="F.Cu")
    out_zone.add_points([
        Point(1.5, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        Point(40.0, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        Point(40.0, 2.0 + (trace_width_mils * 0.0254 / 2.0)),
        Point(1.5, 2.0 + (trace_width_mils * 0.0254 / 2.0))
    ])

    proj.add(in_zone)
    proj.add(out_zone)

    proj.save()
    proj.export_svg()

    print(colored(f"[+] KiCad PCB Generation via pycbnew Complete! Saved to '{output_filename}'", "green", attrs=["bold"]))
    return f"[+] KiCad PCB generated: {output_filename}"


def serialize_schematic(output_filename):
    """
    Generates a native KiCad schematic file from scratch using pycbnew's schema objects.
    """
    try:
        import pycbnew.schematic as ksch
    except ImportError:
        raise ImportError(
            "[!] Critical Dependency Error: 'kicad-pycbnew' schematic interfaces are missing.\n"
            "    Please run: .venv/bin/pip install kicad-pycbnew"
        )

    print("\n" + "=" * 75)
    print(" 11. AUTOMATED KICAD SCHEMATIC GENERATOR (VIA PYCBNEW)")
    print("=" * 75)

    sch = ksch.Schematic()
    sch.set_paper("A4")
    sch.set_title("PHA-13HLN+ Active Core Component Application Schematic")
    sch.set_company("Automated Python RF Designer Suite")

    def create_rf_symbol(lib_id, ref, val, pos, rot=0, fp=None, mpn=None, dk=None, ms=None):
        sym = ksch.Symbol(lib_id=lib_id, position=pos, rotation=rot)
        sym.add_property(ksch.Property("Reference", ref, visible=True))
        sym.add_property(ksch.Property("Value", val, visible=True))
        if fp:
            sym.add_property(ksch.Property("Footprint", fp, visible=False))
        if mpn:
            sym.add_property(ksch.Property("MPN", mpn, visible=False))
        if dk:
            sym.add_property(ksch.Property("DigiKey", dk, visible=False))
        if ms:
            sym.add_property(ksch.Property("Mouser", ms, visible=False))
        return sym

    sch.add_symbol(create_rf_symbol(
        "Device:C", "C1", "DC_BLOCK_IN", (50.8, 50.8), rot=90,
        mpn="GJM1555C1H101JB01D", dk="490-11721-1-ND", ms="81-GJM1555C1H101JB1D"
    ))

    sch.add_symbol(create_rf_symbol(
        "Amplifier_RF:GALI-74+", "U1", "PHA-13HLN+", (76.2, 50.8),
        fp="Package_TO_SOT_SMD:SOT-89-3", mpn="PHA-13HLN+", dk="PHA-13HLN+-ND", ms="Mini-Circuits PHA-13HLN+"
    ))

    sch.add_symbol(create_rf_symbol(
        "Device:C", "C2", "DC_BLOCK_OUT", (101.6, 50.8), rot=90,
        mpn="GJM1555C1H101JB01D", dk="490-11721-1-ND", ms="81-GJM1555C1H101JB1D"
    ))

    sch.add_symbol(create_rf_symbol(
        "Device:L", "L1", "RF_CHOKE", (88.9, 31.75),
        mpn="0603HP-R10XJLU", dk="0603HP-R10XJLU-ND", ms="613-0603HP-R10XJLU"
    ))

    sch.add_symbol(create_rf_symbol(
        "Device:R", "R1", "R_BIAS", (88.9, 19.05),
        mpn="WK73R3ATTE18R0F", dk="638-WK73R3ATTE18R0FCT-ND", ms="660-WK73R3ATTE18R0F"
    ))

    sch.add_wire(ksch.Wire(start=(53.34, 50.8), end=(71.12, 50.8)))
    sch.add_wire(ksch.Wire(start=(81.28, 50.8), end=(88.9, 50.8)))
    sch.add_wire(ksch.Wire(start=(88.9, 50.8), end=(99.06, 50.8)))
    sch.add_wire(ksch.Wire(start=(88.9, 50.8), end=(88.9, 34.29)))
    sch.add_wire(ksch.Wire(start=(88.9, 29.21), end=(88.9, 21.59)))

    sch.serialize(output_filename)
    print(colored(f"[+] KiCad Schematic Generation via pycbnew Complete! Saved to '{output_filename}'", "green", attrs=["bold"]))
    return f"[+] KiCad Schematic generated: {output_filename}"
