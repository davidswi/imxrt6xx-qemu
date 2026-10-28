#!/usr/bin/env python3
# Copyright (c) 2026 imxrt6xx-qemu contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate QEMU register tables from a CMSIS-SVD file.

Emits one C array per peripheral, containing offset / reset value / write mask
and SET/CLR aliasing, ready to paste into a hw/misc device model.

usage: gen-reg-table.py <file.svd> <PERIPHERAL> <c-identifier-prefix>
"""
import argparse
import sys

from cmsis_svd.parser import SVDParser


def collect(items, out):
    for item in items:
        kind = type(item).__name__
        if kind == "SVDRegister":
            out.append(item)
        elif kind == "SVDRegisterArray":
            out.extend(item.registers)
        elif kind == "SVDRegisterCluster":
            collect(item.registers, out)
            collect(item.clusters, out)
        elif kind == "SVDRegisterClusterArray":
            for c in item.clusters:
                collect(c.registers, out)
                collect(c.clusters, out)
        else:
            print(f"UNHANDLED {kind}", file=sys.stderr)


def base_name(name):
    for suf in ("_SET", "_CLR", "_TOG"):
        if name.endswith(suf):
            return name[: -len(suf)], suf[1:]
    return name, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svd")
    ap.add_argument("peripheral")
    ap.add_argument("prefix")
    args = ap.parse_args()

    device = SVDParser.for_xml_file(args.svd).get_device()
    per = {p.name: p for p in device.peripherals}[args.peripheral]
    regs = []
    collect(per.registers, regs)
    regs.sort(key=lambda r: r.address_offset)

    # Strip array indices so that SET/CLR aliases find their base register.
    def plain(name):
        return name.replace("[0]", "")

    index = {}
    for i, r in enumerate(regs):
        n, alias = base_name(plain(r.name))
        if alias is None:
            index[n] = i

    print(f"/* {args.peripheral}: generated from {per.name} in "
          f"MIMXRT685S_cm33.svd; do not edit by hand. */")
    print(f"static const Rt6xxRegInfo {args.prefix}_regs[] = {{")
    for i, r in enumerate(regs):
        name, alias = base_name(plain(r.name))
        acc = r.access.value if r.access else "read-write"
        mask = r.reset_mask if r.reset_mask is not None else 0
        reset = r.reset_value if r.reset_value is not None else 0
        wmask = 0 if acc == "read-only" else (0 if acc == "write-only" else mask)
        alias_idx = index.get(name, -1) if alias else 255
        if alias and alias_idx == i:
            alias_idx = 255
        wmode = {"read-write": "RT6XX_WM_MASKED",
                 "read-only": "RT6XX_WM_IGNORE",
                 "write-only": f"RT6XX_WM_{alias}",
                 "read-set": f"RT6XX_WM_{alias}"}.get(acc, "RT6XX_WM_MASKED")
        if acc == "write-only" and not alias:
            wmode = "RT6XX_WM_MASKED"
        if alias:
            wmode = f"RT6XX_WM_{alias}"
        print(f"    [{i:<3}] REG({r.address_offset:#06x}, {reset:#010x}, "
              f"{wmask:#010x}, {wmode}, {alias_idx}), /* {r.name} acc={acc} */")
    print("};")


main()
