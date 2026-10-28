# MIMXRT685 DMA Audio Implementation Plan

Status: proposed  
Reviewed: 2026-10-26  
Scope: local MIMXRT685 hardware enablement; not intended for upstream QEMU

## Objective

Run the unmodified MCUXpresso SDK `i2s/dma_record_playback` example with continuous, audible 48 kHz stereo playback and capture, while preserving the working interrupt-driven I2S example and the existing MIMXRT685 qtests.

The implementation should model the reusable LPC-style DMA behavior exercised by the SDK rather than special-case audio buffer addresses. The initial integration only needs the two fixed requests used by the example:

- DMA0 channel 7: SRAM to Flexcomm3 I2S `FIFOWR` (playback)
- DMA0 channel 2: Flexcomm1 I2S `FIFORD` to SRAM (capture)

The register file and transfer engine should nevertheless cover all 33 DMA0 channels.

## Review conclusion

The present DMA device is a register stub, not a functioning DMA controller. It cannot run the SDK example because it neither reads descriptors nor transfers guest data. A focused rewrite is safer than extending its current transfer routine.

The main defects are:

| Area | Current behavior | Required behavior |
| --- | --- | --- |
| Device state | `hw/dma/imxrt685_dma.c` privately duplicates the public structs and constants | Keep one state definition in `include/hw/dma/imxrt685_dma.h` |
| Transfer configuration | Treats bits 0:9 as the count and bit 12 as `SWTRIG`, then stores only four bits | Decode the real `XFERCFG`: control bits 0:5, width 8:9, increments 12:15, count-minus-one 16:25 |
| Request gating | Requires `HWTRIGEN` for an I2S request and ignores the real software-trigger latch | `SWTRIG`/`SETTRIG` establishes triggered state; `PERIPHREQEN` admits normal peripheral requests; `HWTRIGEN` controls a separate trigger-input path |
| Data movement | Decrements a field but never accesses guest memory or peripheral MMIO | Perform width-correct reads and writes through the system address space |
| Descriptors | Does not read the descriptor table or follow links | Load the channel head at `SRAMBASE + channel * 16`, then reload linked 16-byte descriptors |
| DMA registers | Implements only `CTRL`, `SRAMBASE`, `CFG`, and part of `XFERCFG` | Add the common channel masks, status, interrupt, valid/trigger, abort, and `CTLSTAT` semantics used by `fsl_dma.c` |
| Interrupts | Asserts the shared IRQ directly and never models pending/enabled state or reliable deassertion | Track `INTA`, `INTB`, `ERRINT`, and `INTEN`; derive the shared IRQ from enabled pending flags |
| Timing | Allocates one 48 kHz timer per channel with null callbacks | Remove DMA timers; the audio link/I2S FIFO cadence owns timing and produces level DREQs |
| I2S DREQ | Only TX channel 7 is wired, and TX request polarity is inverted | Wire Flexcomm1 RX to channel 2 and Flexcomm3 TX to channel 7; assert requests at the correct FIFO watermarks |
| Reset/migration | Migrates only `CTRL`; reset omits operational state | Reset and migrate all architecturally visible and in-flight state |
| Address definitions | Secure and non-secure `DMA0` macros conflict, and comments incorrectly call this eDMA | Use unambiguous `_NS`/`_S` names and map the non-secure `0x40104000` instance used by this firmware |

`DMA0_IMPLEMENTATION_SUMMARY.md` currently describes several of these missing behaviors as implemented. Update it after the model works so it records verified behavior instead of intended behavior.

## SDK transaction to support

The SDK example configures 16-bit stereo audio at 48 kHz and represents each stereo frame as one 32-bit DMA transfer. Each 400-byte application buffer therefore produces 100 transfers.

The driver sequence is:

1. `DMA_Init()` writes the 512-byte-aligned descriptor table address to `SRAMBASE` and enables `CTRL`.
2. The application enables channels 2 and 7 and sets their priorities to 2 and 3 respectively.
3. `I2S_StartTransferDMA()` writes the head descriptors and queues a second descriptor for each direction.
4. TX descriptors use width 4, source increment 1, destination increment 0, and destination Flexcomm3 `FIFOWR`.
5. RX descriptors use width 4, source increment 0, destination increment 1, and source Flexcomm1 `FIFORD`.
6. The driver sets `CFGVALID`, `RELOAD`, and alternating `SETINTA`/`SETINTB`, enables the I2S DMA request, sets `PERIPHREQEN`, and writes `ENABLESET`.
7. Because `HWTRIGEN` is clear, `DMA_StartTransfer()` writes `SWTRIG`. This sets the channel trigger latch but does not bypass peripheral pacing.
8. A level DREQ transfers frames while the associated FIFO meets its watermark condition.
9. At descriptor exhaustion, DMA sets INTA or INTB, follows `linkToNextDesc`, and keeps streaming.
10. `DMA0_IRQHandler()` reads and clears the pending flag. The I2S DMA callback accounts for the completed 400-byte buffer and rewrites the retired descriptor for reuse.

`HWTRIGEN` remains clear in this path, but software writes `SWTRIG` once to put the channel into triggered state. Peripheral requests still pace the beats because `PERIPHREQEN` is set. This distinction must be covered by a regression test.

## Required design

### 1. Replace the DMA state and register model

Define the controller once in `include/hw/dma/imxrt685_dma.h`. Remove the per-channel timers and `sample_rate`. Add:

- controller state: `CTRL`, `SRAMBASE`, enable mask, active mask, busy mask, error mask, interrupt-enable mask, INTA mask, and INTB mask;
- 33 channel records containing `CFG`, programmed/current `XFERCFG`, current source and destination addresses, next descriptor address, remaining transfer count, DREQ level, valid/trigger state, and whether a descriptor is loaded;
- a guarded bottom half or equivalent deferred-service flag so an MMIO access to an I2S FIFO cannot recursively re-enter the DMA engine;
- one shared IRQ output and 33 named DREQ GPIO inputs.

Implement the SDK-visible offsets from `PERI_DMA.h`:

- `CTRL` `0x000`, `INTSTAT` `0x004`, `SRAMBASE` `0x008`
- banked `ENABLESET`/`ENABLECLR` `0x020`/`0x028`
- `ACTIVE` `0x030`, `BUSY` `0x038`, `ERRINT` `0x040`
- `INTENSET`/`INTENCLR` `0x048`/`0x050`
- `INTA` `0x058`, `INTB` `0x060`
- `SETVALID` `0x068`, `SETTRIG` `0x070`, `ABORT` `0x078`
- channel `CFG`, `CTLSTAT`, and `XFERCFG` at `0x400 + channel * 0x10`

The common registers have a second bank for channel 32. Implement their hardware access classes: W1S, W1C, read-only status, and W1C pending interrupt flags. Reserved bits should read zero and be ignored on write.

Store all SDK-relevant `CFG` fields, including priority bits 16:18. A first version may leave edge-trigger, polarity, burst wrapping, and external trigger selection behavior inactive, but it must preserve/read back valid fields and clearly diagnose unsupported active modes.

### 2. Implement descriptor loading exactly as the SDK encodes it

The descriptor is four little-endian words:

```text
word 0: xfercfg
word 1: srcEndAddr
word 2: dstEndAddr
word 3: linkToNextDesc
```

For the head transfer, obtain the address words and link from `SRAMBASE + channel * 16`; use the channel's programmed `XFERCFG` as the live configuration. For a reload, fetch all four words from `linkToNextDesc`.

NXP descriptors contain end addresses, not start addresses. For `N = XFERCOUNT + 1`, width `W`, and decoded increment multiplier `I`, initialize each current address as:

```text
current = end - (N - 1) * W * I
```

Then advance the address by `W * I` after each beat. Validate the 16-byte link alignment and descriptor access. Treat an invalid width, misaligned transfer, unmapped access, or failed descriptor fetch as a channel error: clear active/busy/valid as appropriate, set `ERRINT`, and update the shared IRQ.

Use QEMU's system address space access API with `MemTxResult` checking. This naturally handles both RAM and Flexcomm FIFO MMIO and keeps the engine reusable; do not call audio-specific FIFO internals or special-case SDK buffer addresses.

### 3. Implement transfer and completion semantics

A channel is eligible only when:

- DMA `CTRL.ENABLE` is set;
- the channel bit is set in `ENABLESET` state;
- `CFGVALID`/valid-pending is set;
- the channel is not aborted or faulted; and
- its `CTLSTAT.TRIG` latch is set by `SWTRIG`, `SETTRIG`, or a supported hardware trigger.

Once eligible, a channel with `PERIPHREQEN=1` may perform beats only while its peripheral DREQ is asserted. A channel with `PERIPHREQEN=0` may progress without DREQ and is suitable for memory-to-memory operation. Do not require `HWTRIGEN` for a peripheral DREQ, and do not let `SWTRIG` make a peripheral transfer drain its buffer without DREQ pacing.

For every transfer beat:

1. Mark the channel active/busy.
2. Read 1, 2, or 4 bytes from the current source address.
3. Write the same width to the current destination address.
4. Advance addresses according to `SRCINC` and `DSTINC`.
5. Decrement the remaining count and reflect the count-minus-one value in readable `XFERCFG` state.
6. Clear active/busy when the service pass yields or completes.

At descriptor completion:

- set the selected INTA and/or INTB pending bit;
- process `CLRTRIG`;
- if `RELOAD` is set and the link is nonzero, load the linked descriptor before accepting the next beat;
- otherwise clear valid state and stop the channel;
- recompute the shared IRQ immediately.

Service asserted level requests until their peripheral watermark deasserts or the descriptor completes. Defer work through a bottom half and use a bounded per-pass budget to prevent recursive FIFO callbacks or a malformed guest from monopolizing the main loop. If multiple channels are pending, select the lowest numeric configured priority value first (0 is highest), with channel number as a stable tie-breaker.

Writing `XFERCFG.SWTRIG` or `SETTRIG` sets `CTLSTAT.TRIG`; it is a control action rather than a persistent readable `XFERCFG` bit. `SETVALID`, disable, and abort also need enough behavior for the SDK driver and unit tests. `ABORT` must terminate the selected channel, clear busy/active, and leave it in a state from which the SDK can re-enable it.

### 4. Derive interrupt output from register state

Implement a single `dma_update_irq()` helper and call it after every operation that can change pending or enable state.

```text
normal_pending = (INTA | INTB) & INTEN
error_pending  = ERRINT & INTEN
IRQ            = normal_pending != 0 || error_pending != 0
```

`INTSTAT.ACTIVEINT` and `ACTIVEERRINT` should be derived summaries. Clearing INTA, INTB, ERRINT, or the corresponding interrupt-enable bit must deassert the line when no enabled source remains. This is required because `DMA_IRQHandle()` walks registered channel handles, clears flags, and expects the shared NVIC line to fall.

### 5. Make Flexcomm expose correct level DREQs

Replace the hard-coded callback path with QEMU GPIO outputs, one RX DREQ and one TX DREQ per I2S-capable Flexcomm instance. Centralize calculation in `rt6xx_flexcomm_i2s_update_dreq()` and invoke it whenever any relevant state changes:

- FIFO push or pop;
- audio-link sample production or consumption;
- `FIFOTRIG` watermark writes;
- `FIFOCFG` DMA-enable or FIFO-flush writes;
- I2S main enable/config changes;
- Flexcomm personality, clock, or reset changes.

For the modes used by the SDK:

- TX DREQ is asserted when I2S, `DMATX`, and `TXLVLENA` are enabled and the TX FIFO level is at or below the `TXLVL` field.
- RX DREQ is asserted when I2S, `DMARX`, and `RXLVLENA` are enabled and the RX FIFO contains at least `RXLVL + 1` entries (equivalently, its count is above the encoded `RXLVL` field).

These boundaries follow the SDK peripheral header: TX field 0 means "empty," while RX field 0 means "one entry." Lock both encodings down with qtests. DREQ must deassert as soon as a DMA FIFO access moves the level out of the requesting range.

The audio link remains the sole 48 kHz timing source. DMA should react to FIFO demand and must not schedule sample-rate timers of its own.

### 6. Wire the SoC requests

In `hw/arm/imxrt685.c`:

- connect Flexcomm1 RX DREQ to DMA0 input 2;
- connect Flexcomm3 TX DREQ to DMA0 input 7;
- retain DMA0's shared interrupt connection to external IRQ 1;
- map the instance at the non-secure base `0x40104000` used by the current firmware.

These channel numbers match the fixed `DMAC0_REQ_ENA0` Flexcomm1 RX bit 2 and Flexcomm3 TX bit 7 definitions used by this SoC. A full INPUTMUX device and DMA1 are outside the initial audio milestone. Keep the GPIO interface generic enough that INPUTMUX can be inserted later without rewriting the DMA engine.

Rename the base constants so secure and non-secure addresses cannot redefine `IMXRT685_DMA0_BASE`. Secure aliasing can be added separately if a secure firmware test requires it.

### 7. Complete reset, migration, and tracing

Reset must clear every controller/channel register, loaded descriptor, address, count, DREQ-latched service state, pending interrupt, and scheduled bottom half, then lower the IRQ. External DREQ levels should be re-evaluated safely after reset/configuration rather than causing transfers while the device is disabled.

VMState must include all guest-visible and in-flight state needed to resume a linked transfer without repeating or skipping a word. Add a post-load hook to recompute the IRQ and reschedule service for asserted eligible requests. Either migrate raw GPIO levels or reconstruct them deterministically from the saved source-device state after load.

Replace the current traces with useful events for descriptor load, request transition, beat address/width, descriptor completion, reload, abort, bus fault, and IRQ transition. Keep per-beat tracing disabled unless explicitly requested because 48 kHz stereo traffic is noisy.

## Firmware build target

Add `firmware/build/i2s_dma_record_playback.elf` as a separate target built from the pinned SDK tree. Reuse the existing interrupt example's board, clock, startup, linker, codec, I2C4 compatibility, and compile settings, and add:

- `driver_examples/i2s/dma_record_playback/i2s_dma_record_playback.c`
- that example's generated board files;
- `fsl_dma.c`
- `fsl_i2s_dma.c`

Do not patch the SDK example or drivers to fit the model. Refactor the CMake source lists into a small shared helper only if it reduces duplication without changing the working interrupt target.

## Implementation sequence

### Phase 1: register/state foundation

- Consolidate the DMA definitions and correct the base-address names.
- Implement all common and channel registers used by `fsl_dma.c` with correct masks and access semantics.
- Add shared IRQ derivation, reset, and register-focused qtests.

Exit criterion: the SDK can initialize DMA0, enable channels 2/7, set priorities, enable interrupts, and read back expected state without unimplemented accesses.

### Phase 2: generic descriptor engine

- Add head/linked descriptor fetch, end-address conversion, width/increment decoding, data movement, count updates, completion flags, reload, abort, and bus errors.
- First test memory-to-memory transfers with software trigger so the engine can be debugged independently of audio.

Exit criterion: qtests prove 8/16/32-bit copies, fixed/incrementing endpoints, count-minus-one handling, linked reload, INTA/INTB, abort, and error behavior.

### Phase 3: I2S request integration

- Add level DREQ outputs to Flexcomm and recompute them at every FIFO/config transition.
- Add DMA DREQ inputs and deferred guarded servicing.
- Wire Flexcomm1 RX/channel 2 and Flexcomm3 TX/channel 7.

Exit criterion: qtests demonstrate memory-to-Flexcomm3 and Flexcomm1-to-memory transfers, including watermark deassertion, without `HWTRIGEN`.

### Phase 4: SDK firmware bring-up

- Add and build the DMA example target unchanged.
- Boot it with DMA/Flexcomm/I2S tracing initially enabled.
- Verify descriptor table addresses, first request, count progression, A/B completion interrupts, driver callback, and reuse of both descriptors.
- Remove instrumentation once the lifecycle is understood.

Exit criterion: both channel 2 and channel 7 repeatedly complete alternating descriptors, and the application continuously recycles its buffers.

### Phase 5: lifecycle hardening and regression

- Finish reset and migration coverage.
- Update the implementation summary to match measured behavior.
- Run the complete MIMXRT685 qtest suite and the interrupt-driven audio example.

Exit criterion: all automated and manual acceptance checks below pass with a clean build.

## Test plan

Extend `tests/qtest/mimxrt685-test.c` (or add a focused DMA qtest file if the cases become large) with:

1. Reset values, reserved-bit masking, 512-byte `SRAMBASE` alignment, and channel-32 bank access.
2. W1S/W1C behavior for enable and interrupt registers.
3. `XFERCFG` field retention and `CTLSTAT.VALIDPENDING` transitions.
4. A software-triggered RAM-to-RAM transfer, including the one-transfer `XFERCOUNT == 0` case.
5. 8-, 16-, and 32-bit widths with fixed and incrementing addresses.
6. Linked descriptor reload with alternating INTA/INTB and correct IRQ assertion/deassertion.
7. Disable and abort while a channel is pending.
8. Descriptor/data bus errors and `ERRINT` clearing.
9. A software-armed peripheral transfer that remains paused without DREQ, then succeeds with `PERIPHREQEN=1`, asserted DREQ, and `HWTRIGEN=0`.
10. Flexcomm3 TX DREQ boundary and DMA FIFO fill on channel 7.
11. Flexcomm1 RX DREQ boundary and DMA FIFO drain on channel 2.
12. Reset during a pending transfer; migration during an in-flight linked transfer if the qtest infrastructure makes this practical.

Automated regression commands:

```sh
meson test -C qemu/build qtest-arm/mimxrt685-test
cmake --build firmware/build --target i2s_interrupt_record_playback.elf i2s_dma_record_playback.elf
```

Manual end-to-end acceptance should run under the same virtual-time mode that made interrupt-driven audio stable (currently `-icount auto`) and verify:

- the unchanged SDK DMA firmware reaches its running loop without a fault or interrupt storm;
- DMA channels 2 and 7 alternate INTA/INTB completions for multiple buffers;
- the recorded host output is 48 kHz, stereo, signed 16-bit audio;
- playback is audible and continuous, with no recurring underruns, descriptor gaps, or long silence;
- capture advances RX buffers rather than replaying an unchanged initial buffer;
- the existing interrupt-driven example still produces audio;
- `qtest-arm/mimxrt685-test` retains its existing 17 passing tests plus the new DMA tests.

For reproducible audio validation, capture a fixed-duration WAV and inspect its header, frame count, nonzero sample ratio, peak/RMS level, channel activity, and discontinuities at each 400-byte boundary. Audio presence alone is insufficient because a broken descriptor reload can repeat one short buffer indefinitely.

## Expected files changed during implementation

- `qemu/include/hw/dma/imxrt685_dma.h`
- `qemu/hw/dma/imxrt685_dma.c`
- `qemu/hw/dma/trace-events`
- `qemu/include/hw/char/rt6xx_flexcomm.h`
- `qemu/hw/char/rt6xx_flexcomm.c`
- `qemu/include/hw/arm/imxrt685.h`
- `qemu/hw/arm/imxrt685.c`
- `qemu/tests/qtest/mimxrt685-test.c` and possibly its Meson entry
- `firmware/CMakeLists.txt`
- `DMA0_IMPLEMENTATION_SUMMARY.md`

## Risks and decisions to verify early

- **Off-by-one counts:** `XFERCOUNT` encodes `N - 1`; zero means one transfer, not no transfer.
- **End-address descriptors:** treating descriptor addresses as starts silently reverses the effective buffer range.
- **DREQ polarity/boundary:** the current TX comparison is inverted. Preserve the asymmetric encodings: TX asserts at `count <= TXLVL`; RX asserts at `count >= RXLVL + 1`.
- **Re-entrancy:** a DMA write to `FIFOWR` or read from `FIFORD` can change DREQ while DMA is servicing it. Deferred, guarded service is mandatory.
- **Descriptor publication:** the SDK rewrites descriptors from the IRQ callback. Fetch each linked descriptor only when it becomes current so guest updates are observed.
- **Shared application buffer:** RX and TX intentionally use the same circular buffer. Correct startup ordering and FIFO pacing matter; do not hide races by copying whole descriptors instantaneously without respecting DREQ.
- **IRQ semantics:** pending flags and enables are separate. A completion must remain pending while disabled and assert later if enabled.
- **Bus failures:** ignored `MemTxResult` errors can turn an invalid descriptor into silent audio corruption or an infinite request loop.
- **Virtual-time catch-up:** keep pacing in the audio link. DMA-owned timers would double-clock the path and reproduce burst/underrun behavior.
- **Security aliases and INPUTMUX:** implement only the non-secure DMA0 address and fixed audio request wiring for this milestone; track secure aliasing, DMA1, and programmable routing as explicit follow-up work.

## Definition of done

The work is complete when the unmodified SDK DMA record/playback firmware builds and runs continuously, performs real bidirectional descriptor-based transfers through channels 2 and 7, produces valid audible host audio, services and clears alternating descriptor interrupts, survives reset, and passes the expanded qtests without regressing the interrupt-driven audio path.
