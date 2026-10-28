# RT685 I2S Interrupt Record/Playback Design and Implementation Plan

**Target:** local `mimxrt685-evk` QEMU machine  
**Example:** `NXP.EVK-MIMXRT685_BSP.26.09.00/boards/evkmimxrt685/driver_examples/i2s/interrupt_record_playback/i2s_interrupt_record_playback.c`  
**Accuracy target:** deterministic functional emulation, not bit- or cycle-accurate audio  
**Status:** implementation in progress; I2C4 firmware build complete  
**Date:** 2026-10-26

> **Repository policy:** `qemu/AGENTS.md` and
> `qemu/docs/devel/code-provenance.rst` prohibit contributing AI-generated or
> AI-derived content to upstream QEMU. This work is explicitly for the local
> hardware-enablement project and must not be submitted upstream.

## 1. Outcome

Add the remaining models needed to build and run the unmodified SDK example
through codec initialization and continuous interrupt-driven record/playback.
The completed increment will provide:

- Flexcomm I2S TX and RX register/FIFO/interrupt behavior;
- a paced, deterministic audio data path for the EVK wiring;
- the existing Flexcomm4 I2C controller as the board codec control bus;
- a functional WM8904 control-register target at I2C address `0x1a`;
- unit-level qtests for each model and its integration; and
- a firmware test that uses the SDK drivers and proves repeated I2S callback
  progress and sample movement.

The example is an infinite service loop, so “support” means more than reaching
its last `PRINTF`: codec transactions must complete, the RX and TX FIFO IRQs
must continue to fire, and buffers must be recycled without FIFO lockup.

### 1.1 Implementation status

The current local QEMU work contains the Flexcomm I2S FIFO/IRQ model, the
paced audio link, the WM8904 model, and EVK wiring. The QEMU system binary
builds successfully. A bounded firmware smoke run reaches `Configure codec`,
`Configure I2S`, and `Setup digital loopback`, then remains alive with an empty
`unimp,guest_errors` log. Focused I2S/audio-link qtests and the finite callback
harness remain to be completed.

The firmware build deliberately selects the BSP's I2C4 fallback by defining
`SDK_I2C_BASED_COMPONENT_USED=1` and `SDK_I3C_BASED_COMPONENT_USED=0`. It builds
the pinned SDK sources into `firmware/build/i2s_interrupt_record_playback.elf`
and `.bin`. Because generated `hardware_init.c` unconditionally asks for the
I3C clock even in the fallback configuration, a source-local forced-include
shim redirects that call to `CLOCK_GetFlexCommClkFreq(4U)` without modifying
the pinned BSP source.

## 2. What the example actually requires

The board setup and application establish this dependency chain:

```text
CLKCTL1/RSTCTL1/SYSCTL1
       |              \
       |               +-- I2S shared SCK/WS routing and MCLK registers
       |
       +-- Flexcomm4 I2C @ 0x40122000, IRQ 18
       |      \
       |       +-- legacy I2C @ 0x1a --> WM8904 control registers
       |
       +-- Flexcomm1 @ 0x40107000, IRQ 15 --> I2S RX, clock master
       |
       +-- Flexcomm3 @ 0x40109000, IRQ 17 --> I2S TX, clock slave
                         \
                          +-- shared 48 kHz stereo frame cadence
```

The physical data path is not a direct Flexcomm3-to-Flexcomm1 loop. Flexcomm3
sends DAC/playback data to the WM8904, and the WM8904 sends ADC/capture data to
Flexcomm1. Flexcomm1 generates SCK and WS; Flexcomm3 consumes the shared clock.
The emulation must preserve that topology even if the initial codec model uses
a synthetic capture source and discards playback samples.

The application configures 16-bit stereo samples in one 32-bit FIFO word,
48 kHz sample rate, FIFO watermark 4, RX before TX, and one 400-byte transfer
for each direction. Both callbacks immediately queue the same transfer again.

## 3. Source authority

Use the checked-in sources in this order:

1. `MIMXRT685S_cm33.xml` for register offsets, reset values, masks, and access
   types.
2. Device headers under
   `NXP.MIMXRT685S_DFP.26.09.00/devices/MIMXRT685S/periph`, especially
   `PERI_I2S.h`, `PERI_I2C.h`, `PERI_FLEXCOMM.h`, `PERI_CLKCTL1.h`, and
   `PERI_SYSCTL1.h`.
3. SDK drivers `fsl_flexcomm.c`, `fsl_i2s.c`, `fsl_i2c.c`, `fsl_clock.c`, and
   `fsl_reset.c` for the exact polling and IRQ sequences used by firmware.
4. The example's `board.c`, `board.h`, `hardware_init.c`, `app.h`, and pin/clock
   sources for board integration.
5. QEMU's I2C APIs in `include/hw/i2c/i2c.h`.

The relevant fixed hardware facts are:

| Block | Address/IRQ or control |
|---|---|
| Flexcomm4 I2C | `0x40122000`, NVIC IRQ 18 |
| Flexcomm4 clock/reset gate | CLKCTL1 `PSCCTL0[12]`, RSTCTL1 `PRSTCTL0[12]` |
| Flexcomm1 I2S RX | `0x40107000`, NVIC IRQ 15 |
| Flexcomm3 I2S TX | `0x40109000`, NVIC IRQ 17 |
| WM8904 legacy I2C address | `0x1a` |
| Flexcomm I2S selections | `PSELID.PERSEL=4` TX, `5` RX |
| Flexcomm FIFO depth | 8 words |

## 4. Scope boundaries

### In scope

- I2S primary channel registers used by `fsl_i2s.c`.
- 32-bit FIFO words for the example's 16-bit stereo format.
- FIFO level/error status, W1C behavior, SET/CLR interrupt registers, and
  level-sensitive IRQ generation.
- Real virtual-time pacing at a configurable board sample rate, defaulting to
  48 kHz.
- SDK blocking I2C transfers over the existing Flexcomm4 model, including
  START, repeated START, STOP, byte TX/RX, and NACK reporting.
- WM8904 8-bit register addressing and big-endian 16-bit register values.
- Reset, migration, clock gate, peripheral reset, and deterministic tests.

### Deferred

- I2S secondary channels, 48-bit packing, mono/PDM modes, DMA requests, and
  bit-level SCK/WS/data waveforms.
- Host microphone/speaker integration and subjective audio quality.
- The standalone RT685 I3C0 controller. The example is intentionally compiled
  for its supported Flexcomm4 I2C fallback.
- A complete analog WM8904, FLL/clock-lock timing, jack detection, GPIOs,
  interrupts, and host audio backend.
- Electrical pin-mux enforcement. IOPCTL remains register storage.

Unsupported modes must retain safe masked register values where appropriate,
log `LOG_UNIMP` when enabled, and never silently behave as a supported mode.

## 5. Architecture

### 5.1 Keep I2S inside the composite Flexcomm device

The current `rt6xx-flexcomm` is correctly one MMIO device with a shared IRQ.
Extend its `PSELID` dispatcher rather than adding overlapping I2S MMIO
devices. The relevant windows are:

| Window | Registers |
|---|---|
| `0xc00` | `CFG1`, `CFG2`, `STAT`, `DIV` and primary I2S configuration |
| `0xe00` | shared `FIFOCFG`, `FIFOSTAT`, `FIFOTRIG`, interrupt and FIFO data |
| `0xff8` | common `PSELID` |

Add a named I2S sub-structure to `Rt6xxFlexcommState` containing configuration,
FIFO control, sticky errors, and independent eight-word TX and RX FIFOs. Do
not alias the USART/SPI FIFO arrays: selection changes and reset behavior are
easier to reason about when each personality owns its state.

`FLEXCOMM_PeripheralIsPresent()` requires capability bit 7 for both I2S
directions, while `PERSEL` distinguishes TX (4) from RX (5). The existing
`RT6XX_FLEXCOMM_CAP_I2S` capability therefore remains one silicon capability,
but both selections must be accepted by the dispatcher.

### 5.2 Add a board audio-link object

Add a small non-MMIO `rt685-audio-link` device owned by the SoC. It represents
the EVK's shared I2S wires and is the only owner of the audio cadence timer.
Use explicit typed links or a small internal endpoint interface to connect:

- Flexcomm1 RX;
- Flexcomm3 TX; and
- the WM8904 digital audio endpoint.

At each timer tick, in a fixed order, the link will:

1. consume one word from the Flexcomm3 TX FIFO, or use zero when
   `TXEMPTYZERO` is set;
2. deliver that word to the WM8904 playback sink;
3. obtain one deterministic capture word from the WM8904 source; and
4. push it into the Flexcomm1 RX FIFO.

Each FIFO mutation recomputes the owning Flexcomm IRQ. The timer runs only
when the RX master and TX slave are selected, clocked, out of reset, enabled,
and configured compatibly. It stops when the master is disabled or reset.
This avoids an always-running timer and makes tests deterministic.

The link has a `sample-rate` property, set to 48000 by the EVK. Its period is
`NANOSECONDS_PER_SECOND / sample_rate`; remainder accumulation should be used
if needed to avoid long-term drift. The model stores `CFG1`, `CFG2`, and `DIV`
and validates master/slave and frame-format compatibility, but this increment
does not derive the cadence from a cycle-accurate AUDIO PLL model.

This object is preferable to transmitting audio words through `qemu_irq`:
audio words are data, not interrupt levels, and a typed endpoint makes FIFO
backpressure and migration behavior explicit.

### 5.3 I2S register behavior

Implement only documented bits and apply masks from `PERI_I2S.h`/the SVD.
The required derived behavior is:

- `FIFOSIZE` reports depth 8.
- `TXNOTFULL` is high while TX count is less than 8.
- `TXEMPTY` is high when TX count is zero.
- `RXNOTEMPTY` is high while RX count is nonzero.
- `RXFULL` is high when RX count is 8.
- `TXLVL` is asserted when its trigger is enabled and TX count is at or below
  the programmed threshold.
- `RXLVL` is asserted when its trigger is enabled and RX count is above the
  programmed threshold, matching the SDK handler's drain loop.
- TX overflow and RX overflow set their sticky error bits; W1C writes clear
  sticky errors.
- `FIFOINTSTAT` is raw active conditions AND the interrupt-enable register.
- `FIFOINTENSET` and `FIFOINTENCLR` update one stored enable mask.
- `FIFOWR` enqueues one 32-bit word; `FIFORD` dequeues one word; NOPOP reads
  return the head without consuming it.
- FIFO empty bits in `FIFOCFG` flush their respective FIFOs and self-clear.

Level conditions must be recomputed after MMIO, timer, clock, reset, or
selection changes. A firmware W1C of a level flag may acknowledge the sampled
condition, but the flag must immediately reassert while the FIFO condition is
still true. This is essential for the SDK's interrupt handler.

The common Flexcomm IRQ remains gated by the selected personality,
`clock_enabled`, `!reset_asserted`, and `CFG1.MAINENABLE` for I2S.

### 5.4 Flexcomm4 I2C codec control plane

Use the already modeled Flexcomm4 I2C controller and its QEMU `I2CBus`. The
firmware target selects the SDK's I2C component and omits the I3C adapter, so
`board.h` resolves `BOARD_CODEC_I2C_BASEADDR` to `I2C4` and
`BOARD_CODEC_I2C_INSTANCE` to 4. Attach the WM8904 at address `0x1a` to
`s->flexcomm[4].i2c_bus`.

No standalone I3C MMIO device is required for this increment. The generated
pin and clock setup still writes harmless I3C-related IOPCTL/CLKCTL storage,
but codec traffic must be observed at Flexcomm4. The firmware build's
source-local clock shim ensures `codecI2CSourceClock` also reflects Flexcomm4.

### 5.5 WM8904 control and digital endpoint

Add `TYPE_WM8904` under `hw/audio` as a legacy `I2CSlave` plus the internal
audio endpoint interface. Board code creates it with
`i2c_slave_new(TYPE_WM8904, 0x1a)` and realizes it on Flexcomm4's bus.

The control protocol is:

- first write byte selects an 8-bit register;
- the next two bytes form one big-endian 16-bit value;
- a repeated START followed by a read returns the selected register high byte
  then low byte; and
- register selection persists across the repeated START.

Use a 256-entry 16-bit register map. Populate documented reset values for the
registers the SDK reads, preserve ordinary writes, and make a write of zero to
`WM8904_RESET` restore the reset map. The write sequencer may complete
immediately: `WM8904_WRT_SEQUENCER_4` bit 0 must read clear after the SDK
starts the sequencer, otherwise `WM8904_Init()` spins forever.

For deterministic tests, the digital capture endpoint generates a repeating
stereo ramp or PRBS-like sequence with a documented seed. The playback
endpoint records at least the last word and cumulative frame count. Expose
read-only QOM diagnostic properties for capture/playback frame counts and the
last playback word; these are observability aids, not guest-visible hardware.
Do not open a host audio backend in this increment.

### 5.6 Clock, reset, SYSCTL, and board wiring

Flexcomm4 already receives its clock and reset signals from CLKCTL1
`PSCCTL0[12]` and RSTCTL1 `PRSTCTL0[12]`, and its shared interrupt is connected
to NVIC input 18. Retain functional storage for the generated I3C and MCLK
clock writes, but they do not control codec traffic in this configuration.

The SYSCTL1 registers used by `fsl_i2s_bridge.h` (`FCCTRLSEL`, shared control
sets, and `MCLKPINDIR`) already have masked storage. Keep them and add qtests
for the exact example values. The EVK instantiates the fixed audio-link
topology only when those blocks exist; the first implementation need not make
the stored bridge mux dynamically rewire QOM links. If firmware programs an
incompatible route, the link should stop and log an unimplemented/guest error
rather than silently transferring on the wrong route.

### 5.7 Reset and migration

Reset must:

- stop the audio timer;
- empty all I2S FIFOs and preserve the existing Flexcomm I2C reset behavior;
- end an active legacy-I2C transaction;
- clear sticky status and IRQs;
- restore documented configuration/reset values; and
- reset the WM8904 register map and deterministic stream seed.

Bump the Flexcomm VMState version and migrate I2S registers, FIFO contents and
indices, error state, and any timer deadline needed by the link. Add VMState
for WM8904 and the audio link. Post-load hooks must recompute all derived
status/IRQ levels instead of migrating them as independent truth.

## 6. Expected file changes

Names may be adjusted to match local conventions, but the intended ownership
is:

```text
qemu/include/hw/char/rt6xx_flexcomm.h       I2S state and endpoint helpers
qemu/hw/char/rt6xx_flexcomm.c               I2S MMIO/FIFO/IRQ behavior
qemu/include/hw/audio/wm8904.h               codec type/endpoint interface
qemu/hw/audio/wm8904.c                       I2C register map/audio endpoint
qemu/include/hw/audio/rt685_audio_link.h     board audio-link type
qemu/hw/audio/rt685_audio_link.c             frame timer and routing
qemu/hw/arm/imxrt685.c                       device creation and wiring
qemu/include/hw/arm/imxrt685.h               child state and addresses
qemu/hw/misc/rt6xx_syscon.c                  generated clock-register storage
qemu/hw/{audio,char}/meson.build             build integration
qemu/hw/{audio,char}/Kconfig                 configuration dependencies
qemu/tests/qtest/mimxrt685-test.c            register/integration qtests
firmware/CMakeLists.txt                      SDK example/test target
firmware/app/i2s_i2c4_override.h             generated clock-query adaptation
firmware/app/i2s_record_playback_test.c       finite functional harness
```

The Flexcomm files currently contain uncommitted SPI-slave work. I2S changes
must be layered onto that working tree without reverting, reformatting, or
otherwise obscuring those edits.

## 7. Test plan

### 7.1 Flexcomm I2S qtests

Add focused tests for:

1. I2S TX/RX `PSELID` capability and selection, including lock behavior.
2. Primary register masks and reset values.
3. FIFO depth, fill/drain order, full/empty/not-full/not-empty status.
4. FIFO flush and sticky TX/RX error W1C behavior.
5. Watermark boundary behavior at counts 4 and 5.
6. SET/CLR interrupt enables and shared NVIC assertion/deassertion.
7. IRQ suppression while clock-gated, reset, unselected, or MAINENABLE clear.
8. Timer pacing: virtual time advances one frame at a time, not an entire
   application buffer in one MMIO callback.
9. Reset during an active stream and migration with partially filled FIFOs.

### 7.2 I2C4/WM8904 qtests

Exercise the controller through guest MMIO, not private helper calls:

1. clock/reset gate behavior and reset values;
2. START to `0x1a`, register-select byte, two-byte big-endian write, STOP;
3. write-register-address followed by repeated START and two-byte read;
4. Flexcomm I2C pending/status transitions and idle/active state changes;
5. missing-address NACK status clearing;
6. interrupt enable/disable and masked status;
7. WM8904 reset and immediate write-sequencer completion; and
8. clock/reset gating through the existing Flexcomm4 wiring.

### 7.3 Audio-link integration qtests

Configure Flexcomm1 RX and Flexcomm3 TX exactly as the SDK does, enqueue a
known TX pattern, advance the virtual clock, and verify:

- the codec receives words in order;
- RX receives the codec's deterministic capture pattern;
- both watermark IRQs transition at the correct counts;
- no RX overflow occurs when the handler drains at the intended cadence; and
- disabling the master, gating either Flexcomm, or asserting reset stops the
  corresponding data movement.

### 7.4 Firmware tests

Add two firmware targets:

1. **Exact-example smoke target.** Build the unmodified BSP example sources
   with the required SDK I2S, I2C, codec adapter, WM8904, clock, GPIO, and
   debug-console sources. A bounded run must print `Configure codec`,
   `Configure I2S`, and `Setup digital loopback`, remain alive, and produce no
   unimplemented MMIO or guest-error messages.
2. **Finite functional target.** Use the same board setup and SDK drivers, but
   callbacks count completions. After at least three complete RX and TX
   buffers, validate the deterministic capture sequence, write a PASS marker
   (and print `PASS`), then stop. This proves continuing IRQ/FIFO behavior that
   the infinite stock example cannot self-report.

The firmware build must consume sources directly from the pinned BSP/DFP; do
not patch or copy altered SDK drivers into the test.

### 7.5 Regression commands

The implementation phase should finish with, at minimum:

```sh
cmake -S firmware -B firmware/build -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=firmware/toolchain-gnu-arm.cmake
ninja -C firmware/build

ninja -C qemu/build qemu-system-arm tests/qtest/mimxrt685-test
QTEST_QEMU_BINARY="$PWD/qemu/build/qemu-system-arm" \
  qemu/build/tests/qtest/mimxrt685-test
```

Also run the repository's existing RT685 test invocation if Meson supplies a
named test wrapper, and run both firmware images under a bounded timeout with
`-d unimp,guest_errors` captured and checked.

## 8. Implementation sequence

Keep each stage independently testable and do not start with the full firmware
run.

### Stage 1: Flexcomm4 I2C control path

1. Select `SDK_I2C_BASED_COMPONENT_USED` and disable the I3C component.
2. Build the SDK Flexcomm I2C adapter and driver.
3. Attach the WM8904 to Flexcomm4 at `0x1a`.
4. Add controller/codec qtests through guest MMIO.

**Exit criterion:** SDK-style blocking write/read register sequences complete,
including repeated START and NACK paths.

### Stage 2: WM8904 control plane

1. Add the codec register-map I2C target and reset map.
2. Attach it to Flexcomm4's I2C bus at `0x1a`.
3. Test codec reset, write/readback, byte order, and sequencer completion.
4. Run a minimal codec-init firmware probe.

**Exit criterion:** `CODEC_Init()` and `CODEC_SetVolume()` return success.

### Stage 3: Flexcomm I2S data plane

1. Add I2S TX/RX selection and register dispatch.
2. Add FIFOs, status, trigger logic, IRQs, reset, and migration.
3. Add direct qtests for register and watermark semantics.

**Exit criterion:** an MMIO-driven test can fill TX, drain RX, and observe the
same IRQ transitions expected by `fsl_i2s.c`.

### Stage 4: Paced board audio link

1. Add the typed codec/Flexcomm endpoint contract.
2. Add the 48 kHz virtual timer and EVK topology.
3. Add deterministic codec capture and playback diagnostics.
4. Test pacing, backpressure, reset, clock gating, and stream migration.

**Exit criterion:** advancing virtual time moves exactly the expected number
of frames and repeatedly services both SDK IRQ handlers without overflow.

### Stage 5: Firmware acceptance and cleanup

1. Add the exact-example and finite-harness build targets.
2. Fix only behavior demonstrated missing by tests or logs.
3. Run the full qtest and firmware matrix.
4. Confirm no new `unimp`/`guest_errors`, sanitizer failures, hangs, or
   regressions in the existing USART/I2C/SPI tests.
5. Update project documentation with run commands and the deliberately
   deferred features.

## 9. Acceptance criteria

This increment is complete when all of the following are true:

- The SDK example builds from the pinned local BSP/DFP without source edits.
- Codec initialization and volume programming complete over Flexcomm4 I2C.
- The example reaches `Setup digital loopback` and continues running.
- Flexcomm1 and Flexcomm3 generate paced RX/TX FIFO interrupts indefinitely.
- The finite harness completes at least three buffers in both directions and
  verifies deterministic captured data.
- Clock gating and reset quiesce every new device and deassert its IRQ.
- Migration preserves active transfers/FIFO contents or explicitly quiesces
  them in a documented, tested manner.
- Existing RT685 tests, including the in-progress SPI-slave tests, still pass.
- A bounded example run is clean under `-d unimp,guest_errors`.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Immediate FIFO processing causes interrupt recursion or RX overflow | One board-owned virtual timer transfers one frame per tick. |
| Level IRQ never clears or never reasserts | Derive level flags from FIFO counts after every mutation; test exact watermark boundaries. |
| Codec init hangs in polling | Exercise the existing Flexcomm4 I2C state machine and complete the WM8904 write sequencer immediately. |
| A direct TX-to-RX shortcut hides board mistakes | Route both streams through a WM8904 endpoint with separate capture/playback behavior. |
| Fixed audio timing is mistaken for PLL accuracy | Make the 48 kHz rate an explicit board property and document that PLL registers are functional storage. |
| New work overwrites the SPI-slave changes | Treat the current dirty Flexcomm/test files as the baseline and inspect diffs before each patch. |
| The infinite example gives a false positive after startup | Require the finite callback/data-integrity harness in addition to the stock smoke run. |

