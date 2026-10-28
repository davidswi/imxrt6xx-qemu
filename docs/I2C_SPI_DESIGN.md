# i.MX RT685 Flexcomm I2C and SPI Design and Implementation Handoff

**Target:** local `mimxrt685-evk` QEMU machine  
**Audience:** implementation agent familiar with QEMU QOM, qdev, qtest, I2C, and SSI  
**Accuracy target:** deterministic functional emulation, not bit- or cycle-accurate serial timing  
**Status:** design ready for implementation  
**Date:** 2026-10-24

> **Repository policy:** `qemu/AGENTS.md` and
> `qemu/docs/devel/code-provenance.rst` prohibit contributing AI-generated or
> AI-derived content to upstream QEMU. This document is for the repository's
> stated local hardware-enablement experiments. Do not use this document or an
> agent-authored implementation in an upstream submission.

## 1. Outcome

Extend the existing RT6xx Flexcomm model so MIMXRT685S firmware can use the
MCUXpresso polling and interrupt-driven **I2C master** and **SPI master** APIs
against normal QEMU I2C and SSI peripherals.

The completed increment shall:

- retain existing USART behavior and its tests;
- expose correct Flexcomm capability bits and function selection;
- expose one QEMU I2C bus and one QEMU SSI bus per capable Flexcomm;
- implement the I2C master transaction state machine, NACK behavior, and IRQ;
- implement SPI master transfers, RX FIFO, chip selects, status, and IRQ;
- instantiate Flexcomm 14 (SPI-only) and Flexcomm 15 (I2C-only), which are
  present in the silicon but absent from the current SoC model;
- preserve reset, clock-gate, shared-IRQ, and migration behavior; and
- add qtests and driver-level firmware tests that cover both polling and IRQ
  transfers.

This increment deliberately does not claim complete Flexcomm support. The
following remain out of scope:

- I2C slave and monitor modes;
- I2C multi-master arbitration, high-speed master code, clock stretching, and
  elapsed-time timeout generation;
- SPI slave mode;
- DMA request outputs and DMA-driven transfers;
- pin mux electrical enforcement through IOPCTL;
- serial bit timing, baud-rate delays, and clock phase/polarity waveform
  simulation;
- I2S; and
- secure/non-secure peripheral aliases not already modeled by the machine.

Configuration registers for deferred functions may retain masked values, but
enabling an unsupported operating mode must log `LOG_UNIMP` and must not
silently perform a different operation.

## 2. Evidence and source authority

Use the checked-in sources in this order:

1. `MIMXRT685S_cm33.xml` for offsets, access types, masks, and reset values.
2. Device headers:
   - `NXP.MIMXRT685S_DFP.26.09.00/devices/MIMXRT685S/periph/PERI_FLEXCOMM.h`
   - `.../PERI_I2C.h`
   - `.../PERI_SPI.h`
   - `.../MIMXRT685S_cm33_COMMON.h`
   - `.../MIMXRT685S_cm33_features.h`
3. MCUXpresso drivers `fsl_flexcomm.c`, `fsl_i2c.c`, and `fsl_spi.c` for the
   register sequences firmware actually performs.
4. QEMU's `include/hw/i2c/i2c.h`, `hw/i2c/core.c`,
   `include/hw/ssi/ssi.h`, and `hw/ssi/ssi.c` for bus semantics.
5. Existing RT685 model and tests under `qemu/hw`, `qemu/include/hw`, and
   `qemu/tests/qtest/mimxrt685-test.c`.

The local SVD is known to report zero for the Flexcomm `*PRESENT` reset bits,
even though the feature header and SDK instance tables establish the actual
capabilities. Continue the current model's practice of correcting these bits,
but correct all functions rather than USART alone.

Useful extraction command:

```sh
bin/python tools/svd-dump.py MIMXRT685S_cm33.xml \
    FLEXCOMM0 I2C0 SPI0 CLKCTL1 RSTCTL1
```

Record any discovered disagreement between the SVD, headers, SDK, and physical
hardware in this document or a successor evidence note. Do not resolve a
disagreement with firmware-specific magic values.

## 3. Existing implementation and constraints

The current implementation is a single `rt6xx-flexcomm` SysBus device in
`qemu/hw/char/rt6xx_flexcomm.c` with:

- one 4 KiB MMIO region;
- shared Flexcomm `PSELID` handling at `0xff8`;
- one NVIC output;
- clock-enable and reset GPIO inputs;
- USART registers at `0x000` and shared FIFO registers at `0xe00`;
- a character backend per instance; and
- VMState version 1.

`qemu/hw/arm/imxrt685.c` currently creates only Flexcomm 0 through 7. Their
bases and IRQs are already correct:

| Hardware instance | Base | NVIC IRQ |
|---:|---:|---:|
| 0 | `0x40106000` | 14 |
| 1 | `0x40107000` | 15 |
| 2 | `0x40108000` | 16 |
| 3 | `0x40109000` | 17 |
| 4 | `0x40122000` | 18 |
| 5 | `0x40123000` | 19 |
| 6 | `0x40124000` | 43 |
| 7 | `0x40125000` | 44 |
| 14 | `0x40126000` | 20 |
| 15 | `0x40127000` | 21 |

CLKCTL1 and RSTCTL1 use `PSCCTL0`/`PRSTCTL0` bits 8 through 15 for instances
0 through 7, bit 22 for Flexcomm 14, and bit 23 for Flexcomm 15. Both
controllers currently expose only eight Flexcomm GPIO lines, so they must be
extended as part of this work.

## 4. Architectural decisions

### 4.1 Keep one composite Flexcomm device

Do not instantiate overlapping standalone USART, I2C, and SPI MMIO devices.
Keep a single Flexcomm QOM object and dispatch register accesses according to
`PSELID.PERSEL`:

| `PERSEL` | Function | Register window |
|---:|---|---|
| 0 | none | only common registers |
| 1 | USART | `0x000` and `0xe00` windows already modeled |
| 2 | SPI | `0x400` and `0xe00` windows |
| 3 | I2C | `0x800` window |
| 4, 5 | I2S TX/RX | deferred; log unimplemented accesses |
| 6, 7 | reserved | reject functional accesses |

`PSELID` and `PID` remain accessible regardless of selection. Access to an
inactive function window returns zero/ignores the write and logs a guest error,
matching the existing USART-selection policy.

The current source location under `hw/char` is no longer a good conceptual
fit. Prefer a first, behavior-neutral commit that moves:

- `hw/char/rt6xx_flexcomm.c` to `hw/misc/rt6xx_flexcomm.c`; and
- `include/hw/char/rt6xx_flexcomm.h` to
  `include/hw/misc/rt6xx_flexcomm.h`.

Update Meson, Kconfig, and includes in the same commit. If minimizing churn is
more important for this local branch, leaving the files in `hw/char` is
acceptable; do not split the MMIO dispatcher across three independently
realized devices.

### 4.2 Represent protocol state separately

Refactor `Rt6xxFlexcommState` so common, USART, I2C, and SPI state are visibly
separate. Named sub-structures are preferred over one undifferentiated set of
register fields:

```text
Rt6xxFlexcommState
  common: iomem, irq, instance, capabilities, pselid, clock/reset
  usart:  existing registers, RX FIFO, chardev
  i2c:    registers, master phase/direction, transaction-active, I2CBus
  spi:    registers, RX FIFO, selected-CS mask, SSIBus
```

This is a C layout recommendation, not a required public type hierarchy. The
protocol helpers should remain internal unless another RT6xx model needs them.

### 4.3 Synchronous transfers are intentional

QEMU I2C slave and SSI peripheral calls complete synchronously. Model one bus
operation during the MMIO write that commands it. The guest observes the next
pending state immediately after the write. Do not add host timers merely to
make a transfer look asynchronous.

This matches the existing synchronous USART TX approach, is deterministic,
and supports both polling and NVIC-driven SDK drivers. Baud dividers and delay
registers are stored and masked but do not advance virtual time in this
increment.

### 4.4 Preserve a single hardware IRQ

USART, I2C, and SPI share the instance IRQ. Compute the level only from the
selected function, and gate it with `clock_enabled && !reset_asserted`.
Every operation that can change raw status, enable state, FIFO level, clock,
reset, or selection must call one `rt6xx_flexcomm_update_irq()` function.

### 4.5 Expose normal QEMU buses

Create named buses during instance initialization:

- `i2c_init_bus(dev, "i2c")` on I2C-capable instances;
- `ssi_create_bus(dev, "spi")` on SPI-capable instances.

This allows board code or command-line devices to attach beneath paths such as
`/machine/soc/flexcomm0/i2c` and `/machine/soc/flexcomm0/spi`. Bus existence is
a silicon capability and does not change when `PERSEL` changes; only the
controller's ability to initiate a transaction changes.

## 5. Flexcomm topology and common registers

Represent the silicon instances with a descriptor table rather than parallel
arrays. Each descriptor contains the hardware number, base, IRQ, CLKCTL/RSTCTL
bit, and capability mask.

| Instances | Capabilities | Required `PSELID` value after reset |
|---|---|---:|
| 0-7 | USART, SPI, I2C, I2S | `0x001010f0` |
| 14 | SPI only | `0x00101020` |
| 15 | I2C only | `0x00101040` |

The low `PERSEL` and `LOCK` bits reset to zero. Writes may change only bits
0-3. Once `LOCK` becomes one, later writes cannot change either `PERSEL` or
`LOCK` until peripheral or system reset. Capability and ID bits are read-only.

Continue to return zero for `PID`/function `ID` unless a primary source gives
the silicon value. Do not synthesize an ID from an unrelated LPC part.

Changing an unlocked `PERSEL` must:

1. end any active I2C bus transaction when leaving I2C;
2. deassert every SPI chip select when leaving SPI;
3. preserve protocol register banks until hardware reset; and
4. recompute the shared IRQ.

Preserving banks avoids invented reset-on-selection behavior. Hardware reset
clears all banks.

## 6. I2C master design

### 6.1 Register subset

Implement the full documented register map so probing and SDK configuration do
not hit unimplemented offsets, but only the master path has active behavior.

| Offset | Register | Required behavior |
|---:|---|---|
| `0x800` | `CFG` | Mask `0x3f`; `MSTEN` activates master. Store slave/monitor bits and log unsupported enable. |
| `0x804` | `STAT` | Reset `0x00000801`; dynamic master pending/state plus sticky W1C flags. |
| `0x808` | `INTENSET` | W1S, mask `0x030b8951`. |
| `0x80c` | `INTENCLR` | W1C corresponding interrupt enables; reads return zero. |
| `0x810` | `TIMEOUT` | Reset `0xffff`; low nibble reads as `0xf`; store upper 12 bits. No timer generation yet. |
| `0x814` | `CLKDIV` | Store low 16 bits. |
| `0x818` | `INTSTAT` | `(STAT & INTENSET)` for implemented sources. |
| `0x820` | `MSTCTL` | Command bits plus stored `MSTDMA`; commands execute synchronously. |
| `0x824` | `MSTTIME` | Reset `0x77`; writable mask `0x77`. |
| `0x828` | `MSTDAT` | Low-byte transmit latch or current received byte. |
| `0x840` | `SLVCTL` | Masked storage only; log attempts to operate as slave. |
| `0x844` | `SLVDAT` | Low-byte storage only. |
| `0x848-0x854` | `SLVADR[0..3]` | Reset each to `1`; masked storage. |
| `0x858` | `SLVQUAL0` | Masked storage. |
| `0x880` | `MONRXDAT` | Return zero; monitor mode is deferred. |
| `0xffc` | `ID` | Return zero pending primary-source evidence. |

Only aligned 32-bit accesses are valid, consistent with the SVD and current
Flexcomm `MemoryRegionOps`.

### 6.2 Master state machine

Internally track one of:

```text
IDLE -> TX_READY -> TX_READY ... -> IDLE
  |         |             |
  |         +-> NACK_DATA +-> repeated START
  +-> RX_READY -> RX_READY ... -> IDLE
  +-> NACK_ADDRESS
```

Map it into `STAT` exactly as the SDK expects:

| Internal state | `MSTPENDING` | `MSTSTATE` |
|---|---:|---:|
| idle | 1 | 0 |
| receive ready | 1 | 1 |
| transmit ready | 1 | 2 |
| address NACK | 1 | 3 |
| data NACK | 1 | 4 |

Transactions execute as follows:

1. **Enable:** clearing `CFG.MSTEN` ends an active QEMU I2C transfer and
   returns the master to idle. Setting it makes the idle/pending state visible.
2. **START/repeated START:** firmware writes address plus R/W to `MSTDAT`, then
   writes `MSTCTL.MSTSTART`. Call `i2c_start_transfer(bus, address, is_recv)`.
   QEMU treats a second start without an intervening end as a repeated start.
   On failure select address-NACK. On write success select TX-ready. On read
   success immediately fetch the first byte with `i2c_recv()`, latch it in
   `MSTDAT`, and select RX-ready.
3. **Transmit CONTINUE:** in TX-ready, send latched `MSTDAT` through
   `i2c_send()`. ACK returns to TX-ready; NACK selects data-NACK.
4. **Receive CONTINUE:** in RX-ready, fetch and latch the next byte with
   `i2c_recv()` and remain RX-ready.
5. **STOP:** if receiving, call `i2c_nack()` before `i2c_end_transfer()`;
   otherwise call only `i2c_end_transfer()`. Return to idle.
6. **Invalid command/state:** set `MSTSTSTPERR`, leave the bus in a safe state,
   and log a guest error. Do not abort QEMU.

QEMU's I2C core does not model arbitration or a slave stretching SCL. Do not
set `MSTARBLOSS`, `EVENTTIMEOUT`, or `SCLTIMEOUT` spontaneously. Their W1C and
interrupt plumbing should still be correct so later work can add sources.

`MSTCTL.MSTDMA` may be stored, but DMA requests are out of scope. Log when it
is enabled and continue exposing software-visible pending status; suppressing
`MSTPENDING` without a DMA engine would deadlock the guest.

### 6.3 I2C IRQ

The I2C contribution to the shared IRQ is:

```text
i2c_selected && clock_enabled && !reset_asserted &&
((effective_stat & inten_set & 0x030b8951) != 0)
```

Gate master status with `CFG.MSTEN`. Deferred slave and monitor sources must
not assert merely because their configuration bits were stored.

### 6.4 I2C reset and migration

Reset must call `i2c_end_transfer()` if the controller owns an active
transaction, then restore all documented values and clear internal phase and
direction. Include every stored register and internal state flag in VMState.
The QEMU I2C bus already migrates its selected address; after load, recompute
the IRQ without replaying a bus operation.

## 7. SPI master design

### 7.1 Register subset

| Offset | Register | Required behavior |
|---:|---|---|
| `0x400` | `CFG` | Reset 0; mask `0x0fbd`. Master, loopback, bit order, CPHA/CPOL, and SSEL polarity are stored. |
| `0x404` | `DLY` | Store low 16 bits; no timing delay. |
| `0x408` | `STAT` | Reset `MSTIDLE`; `SSA`/`SSD` are W1C, `ENDTRANSFER` is a command, `STALLED`/`MSTIDLE` are dynamic. |
| `0x40c` | `INTENSET` | W1S mask `0x130`. |
| `0x410` | `INTENCLR` | W1C mask `0x130`. |
| `0x424` | `DIV` | Store low 16 bits. |
| `0x428` | `INTSTAT` | Enabled peripheral status. |
| `0xe00` | `FIFOCFG` | Shared FIFO layout; implement enable and empty commands. Store DMA/wake bits but log DMA use. |
| `0xe04` | `FIFOSTAT` | Dynamic empty/full/levels plus sticky W1C TX/RX errors and `PERINT`. |
| `0xe08` | `FIFOTRIG` | Mask `0x000f0f03`. |
| `0xe10` | `FIFOINTENSET` | W1S low four bits. |
| `0xe14` | `FIFOINTENCLR` | W1C low four bits. |
| `0xe18` | `FIFOINTSTAT` | Raw FIFO conditions plus `PERINT`; IRQ enable is applied separately. |
| `0xe20` | `FIFOWR` | Execute one master frame synchronously. |
| `0xe30` | `FIFORD` | Pop one RX entry; empty read sets `RXERR` and returns zero. |
| `0xe40` | `FIFORDNOPOP` | Peek one RX entry. |
| `0xe48` | `FIFOSIZE` | Return 16. |
| `0xffc` | `ID` | Return zero pending primary-source evidence. |

Use a 16-entry RX FIFO of 32-bit values so data and receive metadata can be
returned together. A separate modeled TX FIFO is unnecessary for this
synchronous implementation: a valid `FIFOWR` is consumed immediately, so
`TXEMPTY=1`, `TXNOTFULL=1`, and `TXLVL=0` after the write. This is the same
functional abstraction already used by USART TX.

### 7.2 Frame execution

A `FIFOWR` is accepted only when Flexcomm is selected as SPI, clock/reset allow
activity, `CFG.ENABLE=1`, `CFG.MASTER=1`, and `FIFOCFG.ENABLETX=1`. Otherwise
set `TXERR` where appropriate and do not call the SSI bus.

For an accepted frame:

1. Decode `LEN` as `number_of_bits - 1` (1 through 16 bits) and mask TX/RX
   data to that width.
2. Decode `TXSSEL[3:0]_N`. A zero selects that SSEL for the frame.
3. Drive each attached SSI peripheral's `SSI_GPIO_CS` input to the physical
   level implied by selection and `CFG.SPOLn`. Initialize and reset every
   attached target to its inactive level.
4. Set sticky `SSA` when any SSEL transitions inactive-to-active and sticky
   `SSD` when an asserted SSEL is deasserted.
5. If `CFG.LOOP=1`, use masked TX data as RX data. Otherwise call
   `ssi_transfer(spi_bus, tx_data)` once. The QEMU SSI contract supports a
   transfer word; ordinary attached devices are expected to use the SDK's
   default 8-bit frames.
6. Unless `RXIGNORE=1`, push RX data and the selected-SSEL metadata when
   `FIFOCFG.ENABLERX=1`. If the RX FIFO is full, set sticky `RXERR` and drop
   the new entry.
7. `EOF` ends a frame but retains asserted SSEL. `EOT` deasserts all SSELs
   after the frame. `STAT.ENDTRANSFER` performs the same deassertion after
   already-completed synchronous activity.
8. Leave `MSTIDLE=1` after the MMIO write; there is no modeled elapsed
   transfer interval.

`TXIGNORE`, SPI slave signaling, and externally driven SCK/MOSI/SSEL are
deferred. If `CFG.MASTER=0`, do not reinterpret a write as a master transfer.

### 7.3 FIFO conditions and IRQ

Calculate status from state rather than storing derived bits:

- `TXEMPTY = 1` and `TXNOTFULL = 1` in the synchronous model;
- `RXNOTEMPTY = (rx_count != 0)`;
- `RXFULL = (rx_count == 16)`;
- `TXLVL = 0`; and
- `RXLVL = rx_count`.

Raw FIFO interrupt conditions are:

- `TXERR` and `RXERR`: corresponding sticky status bits;
- `TXLVL`: `FIFOTRIG.TXLVLENA && tx_count <= TXLVL`;
- `RXLVL`: `FIFOTRIG.RXLVLENA && rx_count > RXLVL`; and
- `PERINT`: nonzero enabled SPI peripheral status.

The IRQ contribution is the OR of enabled peripheral and enabled FIFO
conditions, gated by SPI selection, clock, reset, and `CFG.ENABLE`.

The default SDK configuration enables both trigger comparators, then the
nonblocking driver enables TXLVL/RXLVL interrupts. With an empty TX FIFO this
must assert immediately, allowing the ISR to write the first frame. Each FIFO
read/write and interrupt-enable update must recompute the IRQ.

### 7.4 SPI reset and migration

Reset clears registers and RX FIFO, restores `STAT.MSTIDLE`, deasserts all
chip selects, and lowers the IRQ. Migrate registers, sticky flags, RX FIFO
contents/head/count, and active SSEL mask. In `post_load`, restore chip-select
levels and recompute IRQ; do not replay SSI transfers.

### 7.5 VMState compatibility

The existing Flexcomm VMState is version 1. Preserve its USART field order and
meaning. Introduce version 2 for the new state, retain `minimum_version_id = 1`,
and append I2C/SPI fields with version guards (or versioned subsections). A
version-1 incoming stream must initialize the new protocol banks to hardware
reset state before `post_load` recomputes outputs.

Do not migrate bus pointers, IRQ handles, immutable instance/capability
properties, or derived FIFO/status bits. Migrate only guest-visible registers,
sticky flags, FIFO payload/index/count, transaction phase, direction, and SSEL
state. If active-I2C migration proves inconsistent with the I2C bus's own
VMState ordering, install a migration blocker only while a transaction is
active and document that narrower limitation; do not make the whole machine
non-migratable.

## 8. Clock, reset, and SoC integration

Replace eight-element assumptions with ten logical entries while retaining
the real hardware numbers. A descriptor-to-output-index mapping avoids sparse
16-element arrays:

```text
logical index:  0 1 2 3 4 5 6 7 8  9
hardware FC:    0 1 2 3 4 5 6 7 14 15
control bit:    8 9 10 11 12 13 14 15 22 23
```

Required changes:

- `Rt6xxSysconState.flexcomm_clock[10]` and its named GPIO count;
- `Rt6xxRstctlState.flexcomm_reset[10]` and its named GPIO count;
- table-driven extraction of bits 8-15, 22, and 23 in both controllers;
- `IMXRT685State.flexcomm[10]` plus descriptor-driven child initialization,
  realization, MMIO mapping, IRQ connection, clock, and reset wiring;
- set an `instance` or `capabilities` property before realization; and
- assign chardevs only to USART-capable instances 0-7. Do not consume serial
  backends for Flexcomm 14 or 15.

Use child names `flexcomm0` through `flexcomm7`, `flexcomm14`, and
`flexcomm15`. Preserve the existing names for 0-7 so command lines and qtests
remain compatible.

The device's bus activity and IRQ are disabled while its clock is gated or
reset is asserted. Avoid changing established register-access behavior during
clock gating in this increment unless primary hardware evidence requires it;
SDK initialization deasserts reset and enables the clock before use.

## 9. Build-system changes

The current `RT6XX_FLEXCOMM` Kconfig entry selects unrelated legacy devices.
Replace those selections with the actual dependencies:

```text
config RT6XX_FLEXCOMM
    bool
    select I2C
    select SSI
```

If the tests use a concrete pluggable I2C or SSI peripheral, select its config
from `MIMXRT685_SOC` only when it is also a legitimate board capability;
otherwise use a test configuration already built for ARM rather than adding a
production dependency solely for a qtest.

Update Meson paths if the Flexcomm source is moved. No new public command-line
option is required.

### 9.1 Expected file impact

At minimum, expect to modify:

| File | Purpose |
|---|---|
| `qemu/hw/char/rt6xx_flexcomm.c` and `qemu/include/hw/char/rt6xx_flexcomm.h` (or their new `hw/misc` locations) | Composite register dispatch, buses, protocol state, IRQ, reset, VMState |
| `qemu/hw/char/Kconfig` and `qemu/hw/char/meson.build` (or `hw/misc` equivalents) | Select I2C/SSI and compile the moved device |
| `qemu/hw/arm/imxrt685.c` and `qemu/include/hw/arm/imxrt685.h` | Ten-instance topology and wiring |
| `qemu/hw/misc/rt6xx_syscon.c` and `qemu/include/hw/misc/rt6xx_syscon.h` | FC14/FC15 clock outputs |
| `qemu/hw/misc/rt6xx_rstctl.c` and `qemu/include/hw/misc/rt6xx_rstctl.h` | FC14/FC15 reset outputs |
| `qemu/hw/arm/Kconfig` | Any SoC-level dependency adjustment |
| `qemu/tests/qtest/mimxrt685-test.c` | Register, transaction, IRQ, and reset tests |
| `qemu/hw/misc/trace-events` or the owning subsystem's `trace-events` | Transfer and state-transition observability |
| `firmware/CMakeLists.txt` plus new project-side fixture sources | SDK-driver integration tests |

Do not edit the checked-in NXP pack. It is evidence and build input, not the
implementation surface.

### 9.2 Trace points

Add concise trace events for:

- Flexcomm function-selection changes;
- I2C START/repeated START with address and direction;
- I2C TX/RX byte, ACK/NACK, STOP, and state transition;
- SPI frame TX/RX value, length, SSEL mask, EOF/EOT, and loopback flag; and
- shared IRQ level with the selected function and pending-source mask.

Do not use unconditional logging for normal transfers. Reserve
`LOG_GUEST_ERROR` for invalid guest operations and `LOG_UNIMP` for explicitly
deferred modes.

## 10. Implementation sequence

Keep each step buildable and testable:

1. **Mechanical cleanup:** optionally move the Flexcomm source/header and fix
   Kconfig dependencies. No behavior changes.
2. **Topology:** add descriptors, capability property, correct `PSELID`, and
   instantiate/wire Flexcomm 14 and 15. Add reset/topology qtests.
3. **State refactor:** separate existing USART state without behavior changes;
   keep all USART tests green.
4. **I2C bus and registers:** add bus creation, masks/reset values, master state
   machine, IRQ, reset, and VMState.
5. **I2C tests:** cover ACK/NACK, write, read, repeated start, STOP, interrupt,
   reset, and function gating.
6. **SPI bus and registers:** add bus creation, synchronous frames, chip
   selects, RX FIFO, IRQ, reset, and VMState.
7. **SPI tests:** cover loopback, FIFO/error behavior, SSEL/EOT, interrupt,
   reset, and function gating.
8. **Driver fixtures:** boot small Cortex-M33 programs using the pinned NXP
   polling and nonblocking master drivers. Run with guest-error/unimplemented
   logging enabled.
9. **Regression and cleanup:** run all RT685 tests, relevant I2C/SSI tests,
   functional FreeRTOS hello, debug/release builds, and migration smoke tests.

Do not combine the state refactor with protocol behavior in one large change;
that makes USART regressions unnecessarily hard to isolate.

## 11. Test plan

### 11.1 Flexcomm/common qtests

Extend `qemu/tests/qtest/mimxrt685-test.c` to verify:

- instances 0-7 report USART/SPI/I2C/I2S present;
- instance 14 reports only SPI and instance 15 only I2C;
- FC14/FC15 bases, IRQs, clock bits, and reset bits are wired correctly;
- `PERSEL` dispatch blocks inactive function windows;
- `LOCK` prevents later selection changes until reset;
- peripheral reset restores every function bank and capability value; and
- existing UART TX/RX/IRQ behavior remains unchanged after the refactor.

Update the old expected FC0 reset value from `0x00101010` to `0x001010f0`.

### 11.2 I2C qtests

Attach a deterministic existing QEMU I2C target to `flexcomm0/i2c`, or add a
small local test-only target if no existing target gives observable ACK/read
data. Cover:

- documented reset values and write masks;
- no transaction before clock, reset, selection, and `MSTEN` are valid;
- absent address produces state 3/address-NACK;
- address ACK produces TX-ready or RX-ready;
- transmitted data ACK and data-NACK paths;
- received byte visibility in `MSTDAT`;
- write-subaddress, repeated-start, read sequence used by
  `I2C_MasterTransferBlocking()`;
- STOP ends the QEMU bus transaction and returns idle;
- `INTENSET`/`INTENCLR` and NVIC line 14;
- W1C master error flags;
- disabling master, changing `PERSEL`, and reset terminate an active transfer;
  and
- FC15 performs the same transaction and drives NVIC line 21.

### 11.3 SPI qtests

Use internal loopback for deterministic data-path coverage. Also attach one
existing SSI peripheral for a bus/chip-select smoke test if available in the
configured ARM binary. Cover:

- reset values and masks;
- 8-bit and 16-bit loopback frames;
- `FIFORDNOPOP` versus `FIFORD`;
- RX FIFO count, full condition, overflow `RXERR`, empty-read `RXERR`, and W1C;
- FIFO empty commands;
- trigger threshold boundary (`rx_count > RXLVL`);
- initial TXLVL interrupt with an empty synchronous TX FIFO;
- `INTENSET`/`INTENCLR`, `FIFOINTENSET`/`FIFOINTENCLR`, `INTSTAT`,
  `FIFOINTSTAT`, and NVIC line 14;
- SSEL assertion retained across frames and deasserted by `EOT` or
  `ENDTRANSFER`;
- active-high `SPOL` output level;
- disabling SPI, changing `PERSEL`, and reset deassert all SSELs; and
- FC14 transfers and drives NVIC line 20.

### 11.4 Driver-level firmware fixtures

Add small project-side firmware targets rather than depending only on raw
MMIO qtests:

- I2C polling write/read with subaddress and repeated start;
- I2C nonblocking transfer completed by Flexcomm IRQ;
- SPI polling full-duplex loopback;
- SPI nonblocking full-duplex loopback completed by FIFO IRQ; and
- negative probe of an absent I2C address.

Use the pinned `fsl_i2c.c`, `fsl_spi.c`, and `fsl_flexcomm.c` unchanged. Each
fixture should print a unique PASS marker or write a qtest-visible result word.
Run QEMU with `-d guest_errors,unimp`; a passing fixture must produce neither
unknown MMIO nor unimplemented-operation messages for the supported path.

### 11.5 Regression commands

Use the existing build directory and test names where available:

```sh
ninja -C qemu/build
qemu/build/run meson test -C qemu/build --setup thorough \
    qemu:qtest-arm/mimxrt685-test --print-errorlogs

MIMXRT685_FREERTOS_ELF="$PWD/firmware/build/freertos_hello.elf" \
    qemu/build/run meson test -C qemu/build --setup thorough \
    qemu:func-arm-mimxrt685 --print-errorlogs
```

Confirm the exact focused qtest name with `meson test -C qemu/build --list`
because Meson may prefix it differently. Also run the relevant generic I2C and
SSI qtests selected in the build.

## 12. Acceptance criteria

The increment is complete only when all of the following are true:

- QOM exposes I2C and SPI child buses for all capable instances.
- Flexcomm 0-7, 14, and 15 exist at the documented bases and IRQs.
- Capability bits match the feature header and dedicated-instance topology.
- Existing USART qtests and the FreeRTOS hello functional test still pass.
- Raw qtests pass for all common, I2C, SPI, IRQ, reset, and selection behavior
  listed above.
- Unmodified pinned MCUXpresso polling and interrupt master drivers complete
  the driver fixtures.
- NACK and FIFO error paths terminate without guest hangs.
- System reset during or after a transaction leaves the I2C bus idle, all SPI
  chip selects inactive, FIFOs empty, and IRQs low.
- Save/restore at idle and with populated SPI RX FIFO preserves guest-visible
  state and IRQ level; an active I2C transaction either migrates consistently
  with the QEMU I2C bus or is explicitly rejected by a documented migration
  blocker.
- A debug `-Werror` build and an optimized ARM build pass.
- Supported fixtures generate no `unimplemented`, `unassigned`, or guest-error
  trace messages.
- Deferred modes are documented and emit a clear diagnostic when requested.

## 13. Known risks and mitigations

| Risk | Mitigation |
|---|---|
| Existing monolithic USART state makes protocol additions error-prone | Refactor into named state groups before adding behavior; keep USART tests green after each step. |
| QEMU I2C has a synchronous, simplified bus and limited multi-master behavior | Scope this increment to one master and synchronous targets; explicitly test repeated start. |
| SSI has no negotiated word width | Treat one `FIFOWR` as one SSI word; validate common 8-bit targets and loopback 16-bit behavior. |
| Multiple SSEL and polarity handling can leave targets selected | Centralize CS-level calculation; call it on frame, selection change, reset, post-load, and unrealize if needed. |
| Level-triggered TX-empty IRQ can cause an interrupt storm | Match hardware condition and SDK flow; ensure clearing FIFO interrupt enables lowers IRQ immediately. |
| SVD capability and ID reset data are incomplete | Use the NXP feature header for presence, keep unknown IDs zero, and document the override. |
| Adding FC14/15 exposes sparse hardware numbering | Use descriptor tables and logical indices; never assume array index equals hardware instance. |
| Migration of an active external bus is subtle | Test it; rely on QEMU I2C bus VMState where valid and never replay transfers in `post_load`. |

## 14. Definition of the handoff boundary

This document chooses the device architecture, initial feature boundary,
transaction semantics, topology changes, and verification gates. The
implementing agent should still confirm individual field descriptions against
the pinned headers while coding. If physical-EVK traces contradict the
synchronous state transitions, preserve the bus-visible results and adjust
only the ordering needed by real firmware, recording the evidence.

Do not broaden the change into DMA, target/slave operation, I2S, or pin-level
simulation merely because those registers share the Flexcomm aperture. Land
those as separately designed increments after the master-mode acceptance
criteria above are satisfied.
