## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

from termcolor import colored


def serialize_pcb_layout(output_filename, trace_width_mils):
    """
    Generates a native KiCad PCB board file from scratch using the object-oriented
    data structures inside the pycbnew library.
    """
    try:
        from pycbnew.primitives.project import KProject
        from pycbnew.primitives.layer import Layer
        from pycbnew.primitives.footprint import KFootprint
        from pycbnew.primitives.footprint import KFootprintProperty
        from pycbnew.primitives.footprint import KPad
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
                ['size', 0.6, 0.6], ['drill', '0.3'], ['net', 0]]
            )

    proj.add(fp)

    in_zone = KZone(net=1, layer="F.Cu")
    in_zone.add_points([
        (-40.0, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        (-1.5, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        (-1.5, 2.0 + (trace_width_mils * 0.0254 / 2.0)),
        (-40.0, 2.0 + (trace_width_mils * 0.0254 / 2.0))
    ])

    out_zone = KZone(net=2, layer="F.Cu")
    out_zone.add_points([
        (1.5, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        (40.0, 2.0 - (trace_width_mils * 0.0254 / 2.0)),
        (40.0, 2.0 + (trace_width_mils * 0.0254 / 2.0)),
        (1.5, 2.0 + (trace_width_mils * 0.0254 / 2.0))
    ])

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
