#!/usr/bin/env python3
# Copyright (c) 2026 imxrt6xx-qemu contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate a storage-backed QEMU peripheral model from CMSIS-SVD.

The generated C model is deliberately a starting point: SVD describes a
register interface, not the behaviour of a peripheral.  Reset values,
read/write permissions, register and field masks, arrays, clusters, and
modifiedWriteValues are represented.  Device-specific side effects must be
added by hand.

Examples:

    .venv/bin/python tools/svd_to_qemu.py \
        --svd=MIMXRT685S_cm33.xml --peripheral=CTIMER
    .venv/bin/python tools/svd_to_qemu.py \
        --svd=MIMXRT685S_cm33.xml --peripheral=CTIMER0 \
        --output=rt6xx_ctimer.c
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Iterable, Sequence, TextIO

from cmsis_svd.parser import SVDParser


ACCESS_READABLE = {"read-only", "read-write", "read-writeOnce"}
ACCESS_WRITABLE = {"write-only", "read-write", "writeOnce", "read-writeOnce"}
WRITE_MODES = {
    None: "SVD_WRITE_NORMAL",
    "modify": "SVD_WRITE_NORMAL",
    "oneToClear": "SVD_WRITE_ONE_TO_CLEAR",
    "oneToSet": "SVD_WRITE_ONE_TO_SET",
    "oneToToggle": "SVD_WRITE_ONE_TO_TOGGLE",
    "zeroToClear": "SVD_WRITE_ZERO_TO_CLEAR",
    "zeroToSet": "SVD_WRITE_ZERO_TO_SET",
    "zeroToToggle": "SVD_WRITE_ZERO_TO_TOGGLE",
    "clear": "SVD_WRITE_CLEAR",
    "set": "SVD_WRITE_SET",
}


class GeneratorError(ValueError):
    """An SVD construct cannot be represented safely by the generator."""


@dataclass(frozen=True)
class Register:
    name: str
    offset: int
    size: int
    reset: int
    read_mask: int
    write_mask: int
    write_mode: str


def enum_value(value: object | None) -> str | None:
    """Return a cmsis-svd enum value without depending on its enum classes."""
    if value is None:
        return None
    return getattr(value, "value", str(value))


def c_identifier(value: str, *, upper: bool = False) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    if not value:
        raise GeneratorError("the selected peripheral has no usable C name")
    if value[0].isdigit():
        value = "p_" + value
    return value.upper() if upper else value.lower()


def comment_text(value: str) -> str:
    """Keep SVD-controlled names from terminating a generated C comment."""
    return " ".join(value.replace("*/", "* /").split())


def flatten_registers(items: Iterable[object]) -> list[object]:
    """Expand cmsis-svd register/cluster arrays into concrete registers."""
    result: list[object] = []
    for item in items:
        kind = type(item).__name__
        if kind == "SVDRegister":
            result.append(item)
        elif kind == "SVDRegisterArray":
            result.extend(item.registers)
        elif kind == "SVDRegisterCluster":
            result.extend(flatten_registers(item.registers or []))
            result.extend(flatten_registers(item.clusters or []))
        elif kind == "SVDRegisterClusterArray":
            for cluster in item.clusters:
                result.extend(flatten_registers(cluster.registers or []))
                result.extend(flatten_registers(cluster.clusters or []))
        else:
            raise GeneratorError(f"unsupported cmsis-svd item {kind}")
    return result


def flatten_fields(items: Iterable[object]) -> list[object]:
    result: list[object] = []
    for item in items:
        kind = type(item).__name__
        if kind == "SVDField":
            result.append(item)
        elif kind == "SVDFieldArray":
            result.extend(item.fields)
        else:
            raise GeneratorError(f"unsupported cmsis-svd field {kind}")
    return result


def bit_mask(offset: int, width: int, register_size: int) -> int:
    if offset < 0 or width <= 0 or offset + width > register_size:
        raise GeneratorError(
            f"invalid field range {offset}+{width} in {register_size}-bit register"
        )
    return ((1 << width) - 1) << offset


def register_masks(reg: object, size: int) -> tuple[int, int]:
    full_mask = (1 << size) - 1
    fields = flatten_fields(reg.fields or [])
    reg_access = enum_value(reg.access) or "read-write"

    if not fields:
        described = reg.reset_mask if reg.reset_mask is not None else full_mask
        described &= full_mask
        return (
            described if reg_access in ACCESS_READABLE else 0,
            described if reg_access in ACCESS_WRITABLE else 0,
        )

    read_mask = 0
    write_mask = 0
    for field in fields:
        access = enum_value(field.access) or reg_access
        mask = bit_mask(field.bit_offset, field.bit_width, size)
        if access in ACCESS_READABLE:
            read_mask |= mask
        if access in ACCESS_WRITABLE:
            write_mask |= mask
    return read_mask & full_mask, write_mask & full_mask


def convert_register(reg: object, default_size: int) -> Register:
    size = reg.size or default_size
    if size not in (8, 16, 32, 64):
        raise GeneratorError(
            f"register {reg.name} has unsupported size {size}; expected 8/16/32/64"
        )
    if reg.address_offset is None:
        raise GeneratorError(f"register {reg.name} has no addressOffset")

    full_mask = (1 << size) - 1
    read_mask, write_mask = register_masks(reg, size)
    modified = enum_value(reg.modified_write_values)
    field_modes = {
        enum_value(field.modified_write_values)
        for field in flatten_fields(reg.fields or [])
        if field.modified_write_values is not None
    }
    if modified is None and len(field_modes) == 1:
        modified = field_modes.pop()
    elif field_modes and (len(field_modes) != 1 or modified not in (None, *field_modes)):
        raise GeneratorError(
            f"register {reg.name} mixes modifiedWriteValues modes; "
            "device-specific write handling is required"
        )
    if modified not in WRITE_MODES:
        raise GeneratorError(
            f"register {reg.name} has unsupported modifiedWriteValues={modified}"
        )

    return Register(
        name=reg.name,
        offset=reg.address_offset,
        size=size,
        reset=(reg.reset_value or 0) & full_mask,
        read_mask=read_mask,
        write_mask=write_mask,
        write_mode=WRITE_MODES[modified],
    )


def collect_registers(peripheral: object, default_size: int) -> list[Register]:
    expanded = [
        convert_register(reg, default_size)
        for reg in flatten_registers(peripheral.registers or [])
    ]
    expanded.sort(key=lambda reg: (reg.offset, reg.size, reg.name))

    # SVD commonly gives one address separate read and write names. Coalesce
    # compatible views into one storage entry; preserve both names in comments.
    aliases: dict[tuple[int, int], Register] = {}
    for reg in expanded:
        key = (reg.offset, reg.size)
        previous = aliases.get(key)
        if previous is None:
            aliases[key] = reg
            continue

        if (previous.write_mask and reg.write_mask and
                previous.write_mode != reg.write_mode):
            raise GeneratorError(
                f"alternate registers {previous.name} and {reg.name} have "
                "incompatible modifiedWriteValues modes"
            )
        if (previous.read_mask and reg.read_mask and
                previous.reset != reg.reset):
            raise GeneratorError(
                f"alternate registers {previous.name} and {reg.name} have "
                "incompatible reset values"
            )

        aliases[key] = Register(
            name=f"{previous.name} / {reg.name}",
            offset=reg.offset,
            size=reg.size,
            reset=reg.reset if reg.read_mask else previous.reset,
            read_mask=previous.read_mask | reg.read_mask,
            write_mask=previous.write_mask | reg.write_mask,
            write_mode=(reg.write_mode if reg.write_mask
                        else previous.write_mode),
        )

    registers = sorted(
        aliases.values(), key=lambda reg: (reg.offset, reg.size, reg.name)
    )

    occupied: dict[int, Register] = {}
    for reg in registers:
        for byte in range(reg.offset, reg.offset + reg.size // 8):
            previous = occupied.get(byte)
            if previous is not None:
                raise GeneratorError(
                    f"registers {previous.name} and {reg.name} overlap at {byte:#x}; "
                    "alternate register views need device-specific handling"
                )
            occupied[byte] = reg
    return registers


def select_peripherals(device: object, requested: str) -> tuple[object, list[object]]:
    exact = [p for p in device.peripherals if p.name == requested]
    if exact:
        return exact[0], exact

    grouped = [p for p in device.peripherals if p.group_name == requested]
    if grouped:
        # Prefer a non-derived definition as the template.
        representative = next(
            (p for p in grouped if not p.derived_from), grouped[0]
        )
        return representative, grouped

    available = sorted(
        {p.name for p in device.peripherals}
        | {p.group_name for p in device.peripherals if p.group_name}
    )
    close = [name for name in available if requested.lower() in name.lower()][:8]
    hint = f"; close matches: {', '.join(close)}" if close else ""
    raise GeneratorError(f"peripheral or group {requested!r} not found{hint}")


def peripheral_size(peripheral: object, registers: Sequence[Register]) -> int:
    blocks = [
        block
        for block in (peripheral.address_blocks or [])
        if enum_value(block.usage) in (None, "registers")
    ]
    if blocks:
        return max(block.offset + block.size for block in blocks)
    if not registers:
        raise GeneratorError(f"peripheral {peripheral.name} has no registers")
    return max(reg.offset + reg.size // 8 for reg in registers)


def format_u64(value: int) -> str:
    return f"UINT64_C(0x{value:016x})"


def render_model(
    *,
    svd_path: Path,
    device: object,
    requested: str,
    peripheral: object,
    instances: Sequence[object],
    qom_type: str | None = None,
) -> str:
    default_size = peripheral.size or device.size or 32
    registers = collect_registers(peripheral, default_size)
    if not registers:
        raise GeneratorError(f"peripheral {peripheral.name} has no registers")

    signature = [
        (reg.offset, reg.size, reg.reset, reg.read_mask, reg.write_mask,
         reg.write_mode)
        for reg in registers
    ]
    for instance in instances:
        instance_size = instance.size or device.size or 32
        instance_signature = [
            (reg.offset, reg.size, reg.reset, reg.read_mask, reg.write_mask,
             reg.write_mode)
            for reg in collect_registers(instance, instance_size)
        ]
        if instance_signature != signature:
            raise GeneratorError(
                f"group {requested} contains incompatible register layouts "
                f"({peripheral.name} and {instance.name}); select an exact "
                "peripheral name"
            )

    model_name = peripheral.group_name if len(instances) > 1 else peripheral.name
    model_name = model_name or requested
    stem = c_identifier(model_name)
    macro = c_identifier(model_name, upper=True)
    state = "".join(part.capitalize() for part in stem.split("_")) + "State"
    type_string = qom_type or stem.replace("_", "-")
    iosize = peripheral_size(peripheral, registers)
    endian = enum_value(getattr(device.cpu, "endian", None))
    device_endian = (
        "DEVICE_BIG_ENDIAN" if endian == "big" else "DEVICE_LITTLE_ENDIAN"
    )

    instance_lines = []
    for instance in instances:
        irqs = ", ".join(
            f"{irq.name}={irq.value}" for irq in (instance.interrupts or [])
        ) or "none"
        instance_lines.append(
            f" *   {comment_text(instance.name)}: base={instance.base_address:#x}, "
            f"IRQs={comment_text(irqs)}"
        )

    table_lines = []
    for reg in registers:
        table_lines.append(
            "    { "
            f"{reg.offset:#06x}, {reg.size:2d}, {reg.write_mode}, "
            f"{format_u64(reg.reset)}, {format_u64(reg.read_mask)}, "
            f"{format_u64(reg.write_mask)} "
            f"}}, /* {comment_text(reg.name)} */"
        )

    return f'''/*
 * QEMU storage model for {comment_text(model_name)}.
 *
 * Generated by tools/svd_to_qemu.py from {comment_text(svd_path.name)}
 * ({comment_text(device.name)}). Do not edit this register table by hand.
 *
 * SVD describes register layout, not peripheral behaviour. Add timer/DMA/I/O
 * side effects, IRQ updates, and clock/reset inputs before treating this as a
 * complete hardware model. This generated source is for local experimentation
 * and must not be submitted upstream as AI-generated QEMU code.
 *
 * Instances represented by this model:
{chr(10).join(instance_lines)}
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/core/sysbus.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "qom/object.h"

#define TYPE_{macro} "{type_string}"
OBJECT_DECLARE_SIMPLE_TYPE({state}, {macro})

#define {macro}_IOSIZE {iosize:#x}
#define {macro}_NUM_REGS {len(registers)}

typedef enum SvdWriteMode {{
    SVD_WRITE_NORMAL,
    SVD_WRITE_ONE_TO_CLEAR,
    SVD_WRITE_ONE_TO_SET,
    SVD_WRITE_ONE_TO_TOGGLE,
    SVD_WRITE_ZERO_TO_CLEAR,
    SVD_WRITE_ZERO_TO_SET,
    SVD_WRITE_ZERO_TO_TOGGLE,
    SVD_WRITE_CLEAR,
    SVD_WRITE_SET,
}} SvdWriteMode;

typedef struct SvdRegisterInfo {{
    uint32_t offset;
    uint8_t size;
    uint8_t write_mode;
    uint64_t reset;
    uint64_t read_mask;
    uint64_t write_mask;
}} SvdRegisterInfo;

struct {state} {{
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    uint64_t regs[{macro}_NUM_REGS];
}};

static const SvdRegisterInfo {stem}_registers[{macro}_NUM_REGS] = {{
{chr(10).join(table_lines)}
}};

static int {stem}_find_register(hwaddr offset, unsigned size,
                                unsigned *shift)
{{
    for (int i = 0; i < {macro}_NUM_REGS; i++) {{
        const SvdRegisterInfo *info = &{stem}_registers[i];
        unsigned bytes = info->size / 8;

        if (offset >= info->offset && offset + size <= info->offset + bytes) {{
            *shift = (offset - info->offset) * 8;
            return i;
        }}
    }}
    return -1;
}}

static uint64_t {stem}_read(void *opaque, hwaddr offset, unsigned size)
{{
    {state} *s = {macro}(opaque);
    unsigned shift;
    int index = {stem}_find_register(offset, size, &shift);

    if (index < 0) {{
        qemu_log_mask(LOG_GUEST_ERROR,
                      TYPE_{macro} ": invalid %u-byte read at 0x%" HWADDR_PRIx
                      "\\n", size, offset);
        return 0;
    }}

    return ((s->regs[index] & {stem}_registers[index].read_mask) >> shift) &
           MAKE_64BIT_MASK(0, size * 8);
}}

static void {stem}_write(void *opaque, hwaddr offset, uint64_t value,
                         unsigned size)
{{
    {state} *s = {macro}(opaque);
    unsigned shift;
    int index = {stem}_find_register(offset, size, &shift);
    const SvdRegisterInfo *info;
    uint64_t access_mask;
    uint64_t written;
    uint64_t old;

    if (index < 0) {{
        qemu_log_mask(LOG_GUEST_ERROR,
                      TYPE_{macro} ": invalid %u-byte write at 0x%" HWADDR_PRIx
                      " value 0x%" PRIx64 "\\n", size, offset, value);
        return;
    }}

    info = &{stem}_registers[index];
    access_mask = MAKE_64BIT_MASK(shift, size * 8) & info->write_mask;
    written = (value << shift) & access_mask;
    old = s->regs[index];

    switch (info->write_mode) {{
    case SVD_WRITE_ONE_TO_CLEAR:
        s->regs[index] = old & ~written;
        break;
    case SVD_WRITE_ONE_TO_SET:
        s->regs[index] = old | written;
        break;
    case SVD_WRITE_ONE_TO_TOGGLE:
        s->regs[index] = old ^ written;
        break;
    case SVD_WRITE_ZERO_TO_CLEAR:
        s->regs[index] = old & ~(~(value << shift) & access_mask);
        break;
    case SVD_WRITE_ZERO_TO_SET:
        s->regs[index] = old | (~(value << shift) & access_mask);
        break;
    case SVD_WRITE_ZERO_TO_TOGGLE:
        s->regs[index] = old ^ (~(value << shift) & access_mask);
        break;
    case SVD_WRITE_CLEAR:
        s->regs[index] = old & ~access_mask;
        break;
    case SVD_WRITE_SET:
        s->regs[index] = old | access_mask;
        break;
    case SVD_WRITE_NORMAL:
    default:
        s->regs[index] = (old & ~access_mask) | written;
        break;
    }}
}}

static const MemoryRegionOps {stem}_ops = {{
    .read = {stem}_read,
    .write = {stem}_write,
    .endianness = {device_endian},
    .valid.min_access_size = 1,
    .valid.max_access_size = 8,
    .impl.min_access_size = 1,
    .impl.max_access_size = 8,
}};

static void {stem}_reset(DeviceState *dev)
{{
    {state} *s = {macro}(dev);

    for (int i = 0; i < {macro}_NUM_REGS; i++) {{
        s->regs[i] = {stem}_registers[i].reset;
    }}
}}

static const VMStateDescription vmstate_{stem} = {{
    .name = TYPE_{macro},
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {{
        VMSTATE_UINT64_ARRAY(regs, {state}, {macro}_NUM_REGS),
        VMSTATE_END_OF_LIST()
    }},
}};

static void {stem}_init(Object *obj)
{{
    {state} *s = {macro}(obj);

    memory_region_init_io(&s->iomem, obj, &{stem}_ops, s,
                          TYPE_{macro}, {macro}_IOSIZE);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->iomem);
}}

static void {stem}_class_init(ObjectClass *klass, const void *data)
{{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->vmsd = &vmstate_{stem};
    device_class_set_legacy_reset(dc, {stem}_reset);
}}

static const TypeInfo {stem}_info = {{
    .name = TYPE_{macro},
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof({state}),
    .instance_init = {stem}_init,
    .class_init = {stem}_class_init,
}};

static void {stem}_register_types(void)
{{
    type_register_static(&{stem}_info);
}}

type_init({stem}_register_types)
'''


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="generate a storage-backed QEMU model from CMSIS-SVD"
    )
    parser.add_argument("--svd", required=True, type=Path, help="CMSIS-SVD XML file")
    parser.add_argument(
        "--peripheral",
        required=True,
        help="exact peripheral name or SVD groupName (for example CTIMER)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, help="write C source here (default: stdout)"
    )
    parser.add_argument(
        "--qom-type", help="override the generated QOM type string"
    )
    return parser


def generate(args: argparse.Namespace) -> str:
    if not args.svd.is_file():
        raise GeneratorError(f"SVD file not found: {args.svd}")
    device = SVDParser.for_xml_file(str(args.svd)).get_device()
    peripheral, instances = select_peripherals(device, args.peripheral)
    return render_model(
        svd_path=args.svd,
        device=device,
        requested=args.peripheral,
        peripheral=peripheral,
        instances=instances,
        qom_type=args.qom_type,
    )


def main(argv: Sequence[str] | None = None, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        source = generate(args)
        if args.output:
            args.output.write_text(source, encoding="utf-8")
        else:
            stdout.write(source)
    except (GeneratorError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
