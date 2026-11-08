## Copyright (C) <2026>, <Edward O'Callaghan>, All rights reserved.

import math

from termcolor import colored

from .hardware_profiles import DEVICE_PROFILES, PACKAGE_FOOTPRINTS


def serialize_pcb_layout(output_filename, trace_width_mils, stub_engine_instance=None, device_name="PHA-13HLN+"):
    """
    Generates a native KiCad PCB board file from scratch using the object-oriented
    data structures inside the pycbnew library.
    """
    try:
        from pycbnew.primitives.footprint import KFootprint, KFootprintProperty, KPad
        from pycbnew.primitives.net import KNet
        from pycbnew.primitives.project import KProject
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

    # Fetch active hardware configuration characteristics from registry mapping arrays
    dev_cfg = DEVICE_PROFILES.get(device_name, DEVICE_PROFILES["PHA-13HLN+"])
    pkg_cfg = PACKAGE_FOOTPRINTS.get(dev_cfg["package"], PACKAGE_FOOTPRINTS["SOT-89-3"])
    # Instantiate the active footprint housing
    fp = KFootprint(f"Package_TO_SOT_SMD:{dev_cfg['package']}",
                    at=Point(0.0, 0.0),
                    side=KFootprint.Side.Front,
                    default_net=None)
    KFootprintProperty(fp, [], type="Description", value=f"{device_name} MMIC Package with Integrated Thermal Matrix")

    # Dynamic Pad Generation Loop
    # Parses ['at', X, Y] and ['size', W, H] settings cleanly straight from hardware profiles
    for p_idx, p_data in enumerate(pkg_cfg["pads"], start=1):
        pad_type_enum = KPad.Type.Smd if p_data[2] == "smd" else KPad.Type.Thru_hole
        pad_shape_enum = KPad.Shape.Rect if p_data[3] == "rect" else KPad.Shape.Circle

        KPad(fp, data = ["pad", str(p_idx), pad_type_enum, pad_shape_enum, p_data[4], p_data[5] ])

    # Dynamic Thermal Via Matrix Stitched array pass-through
    for x_pos, y_pos in pkg_cfg["vias"]:
        KPad(fp,
            data = ["pad", "", KPad.Type.Thru_hole, KPad.Shape.Circle, ['at', x_pos, y_pos],
            ['size', pkg_cfg["via_size"], pkg_cfg["via_size"]],
            ['drill', str(pkg_cfg["via_drill"])], ['net', net1] ]
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


def serialize_schematic(output_filename, device_name="PHA-13HLN+"):
    """
    Generates a native KiCad schematic file from scratch using pycbnew's schema objects.
    """
    try:
        from pycbnew.primitives.schematic import KProperty, KSchematic, KSymbol, KWire
        from pycbnew.utils.geometry import Point
    except ImportError:
        raise ImportError(
            "[!] Critical Dependency Error: 'kicad-pycbnew' schematic interfaces are missing.\n"
            "    Please run: .venv/bin/pip install kicad-pycbnew"
        )

    print("\n" + "=" * 75)
    print(" 11. AUTOMATED KICAD SCHEMATIC GENERATOR (VIA PYCBNEW)")
    print("=" * 75)

    # Recover active device specifications context
    dev_cfg = DEVICE_PROFILES.get(device_name, DEVICE_PROFILES["PHA-13HLN+"])
    sourcing = dev_cfg["sourcing"]

    # Initialize schematic via its primitive file context container structure
    sch = KSchematic(filename=output_filename)
    sch.set_paper("A4")
    sch.set_title(f"{device_name} Active Core Component Application Schematic")
    sch.set_company("Automated Python RF Designer Suite")

    def create_rf_symbol(lib_id, ref, val, pos, rot=0, fp=None, mpn=None, dk=None, ms=None):
        sym = KSymbol(lib_id=lib_id, at=Point(pos[0], pos[1]), rotation=rot)
        # Structural internal field properties are appended to the entity instance mapping
        sym.add(KProperty("Reference", ref, visible=True))
        sym.add(KProperty("Value", val, visible=True))
        if fp:
            sym.add(KProperty("Footprint", fp, visible=False))
        if mpn:
            sym.add(KProperty("MPN", mpn, visible=False))
        if dk:
            sym.add(KProperty("DigiKey", dk, visible=False))
        if ms:
            sym.add(KProperty("Mouser", ms, visible=False))
        return sym

    c1 = create_rf_symbol(
        "Device:C", "C1", "DC_BLOCK_IN", (50.8, 50.8), rot=90,
        mpn="GJM1555C1H101JB01D", dk="490-11721-1-ND", ms="81-GJM1555C1H101JB1D"
    )
    u1 = create_rf_symbol(
        dev_cfg["schematic_symbol"], "U1", device_name, (76.2, 50.8),
        fp=f"Package_TO_SOT_SMD:{dev_cfg['package']}",
        mpn=sourcing["mpn"],
        dk=sourcing["digikey"],
        ms=sourcing["mouser"]
    )
    c2 = create_rf_symbol(
        "Device:C", "C2", "DC_BLOCK_OUT", (101.6, 50.8), rot=90,
        mpn="GJM1555C1H101JB01D", dk="490-11721-1-ND", ms="81-GJM1555C1H101JB1D"
    )
    l1 = create_rf_symbol(
        "Device:L", "L1", "RF_CHOKE", (88.9, 31.75),
        mpn="0603HP-R10XJLU", dk="0603HP-R10XJLU-ND", ms="613-0603HP-R10XJLU"
    )
    r1 = create_rf_symbol(
        "Device:R", "R1", "R_BIAS", (88.9, 19.05),
        mpn="WK73R3ATTE18R0F", dk="638-WK73R3ATTE18R0FCT-ND", ms="660-WK73R3ATTE18R0F"
    )

    sch.add(c1)
    sch.add(u1)
    sch.add(c2)
    sch.add(l1)
    sch.add(r1)

    # Draw interconnections using primitive KWire endpoints
    sch.add(KWire(start=Point(53.34, 50.8), end=Point(71.12, 50.8)))
    sch.add(KWire(start=Point(81.28, 50.8), end=Point(88.9, 50.8)))
    sch.add(KWire(start=Point(88.9, 50.8), end=Point(99.06, 50.8)))
    sch.add(KWire(start=Point(88.9, 50.8), end=Point(88.9, 34.29)))
    sch.add(KWire(start=Point(88.9, 29.21), end=Point(88.9, 21.59)))

    sch.save()


    print(colored(f"[+] KiCad Schematic Generation via pycbnew Complete! Saved to '{output_filename}'", "green", attrs=["bold"]))
    return f"[+] KiCad Schematic generated: {output_filename}"
