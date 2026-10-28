#!/usr/bin/env python3
# Copyright (c) 2026 imxrt6xx-qemu contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Dump a flat register map from a CMSIS-SVD file using the cmsis-svd package.

Used to derive and to check the QEMU RT6xx device models against the pinned
MIMXRT685S CMSIS SVD (see SOURCES.md).

usage: svd-dump.py [--fields] <file.svd> <PERIPHERAL> [<PERIPHERAL> ...]
"""
import argparse
import sys

from cmsis_svd.parser import SVDParser


def hexv(v, width=8):
    return "-" if v is None else f"0x{v:0{width}x}"


ENUMS = False


def dump_register(reg, base):
    off = reg.address_offset
    dim = getattr(reg, "dim", None)
    stride = getattr(reg, "dim_increment", None) or 4
    dimtxt = f" dim={dim} stride={hex(stride)}" if dim and dim > 1 else ""
    reset = getattr(reg, "reset_value", None)
    mask = getattr(reg, "reset_mask", None)
    prot = getattr(reg, "protection", None)
    print(f"  {off:#06x} {reg.name:<32} acc={reg.access and reg.access.value or '-':<4}"
          f" size={getattr(reg, 'size', None) or '-'}"
          f" reset={hexv(reset)} mask={hexv(mask)}{dimtxt}"
          f"{' prot=' + prot.value if prot else ''}")
    for f in sorted(reg.fields or [], key=lambda f: f.bit_offset):
        facc = f.access.value if f.access else "-"
        frst = (None if reset is None else
                (reset >> f.bit_offset) & ((1 << f.bit_width) - 1))
        print(f"         {f.bit_offset:>2}+{f.bit_width:<2} {f.name:<30}"
              f" acc={facc:<4} reset={hexv(frst, max(2, (f.bit_width + 3) // 4))}")
        if ENUMS:
            for evc in f.enumerated_values or []:
                for ev in evc.enumerated_values:
                    print(f"                      {ev.name} = {ev.value}")


def walk(items, base):
    for item in items:
        kind = type(item).__name__
        if kind == "SVDRegister":
            dump_register(item, base)
        elif kind == "SVDRegisterArray":
            regs = item.registers
            print(f"  array {item.meta_register.name} n={len(regs)} "
                  f"offsets={hex(regs[0].address_offset)}.."
                  f"{hex(regs[-1].address_offset)} "
                  f"stride={hex(item.meta_register.dim_increment)}")
            dump_register(regs[0], base)
        elif kind == "SVDRegisterCluster":
            print(f"  cluster {item.name} @+{hex(item.address_offset)}")
            walk(item.registers, base)
            walk(item.clusters, base)
        elif kind == "SVDRegisterClusterArray":
            subs = item.clusters
            meta = item.meta_cluster
            print(f"  cluster-array {meta.name} n={len(subs)} "
                  f"@+{hex(meta.address_offset)} "
                  f"stride={hex(meta.dim_increment)}")
            walk(subs[0].registers, base)
            walk(subs[0].clusters, base)
        else:
            print(f"  UNHANDLED {kind}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svd")
    ap.add_argument("--enums", action="store_true", help="dump enumerated values")
    ap.add_argument("peripherals", nargs="+")
    args = ap.parse_args()
    global ENUMS
    ENUMS = args.enums

    device = SVDParser.for_xml_file(args.svd).get_device()
    by_name = {p.name: p for p in device.peripherals}
    for name in args.peripherals:
        per = by_name.get(name)
        if per is None:
            print(f"PERIPHERAL {name}: NOT FOUND", file=sys.stderr)
            continue
        blocks = per.address_blocks or []
        sizes = ", ".join(hex(b.size) for b in blocks)
        print(f"PERIPHERAL {name} base={hex(per.base_address)} "
              f"addressBlock.size=[{sizes}]")
        walk(per.registers, per.base_address)
        for irq in per.interrupts or []:
            num = getattr(irq, "interrupt_number", None)
            if num is None:
                continue
            print(f"  IRQ {num} {irq.name}")
        print()


main()
