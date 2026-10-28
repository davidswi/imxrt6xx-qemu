# RT685 OS/Event Timer Design and Implementation

## Decision

The OS/Event Timer (OSTIMER) is useful infrastructure for DSP and audio
firmware, but it is not the sample clock for the current I2S emulation.  The
`rt685-audio-link` QEMU device supplies the virtual 48 kHz transfer cadence,
and the existing I2S record/playback firmware can run without OSTIMER.

OSTIMER should nevertheless be modeled before broader DSP enablement.  The
RT685 describes it as one central 64-bit counter readable from all domains,
with CPU-local capture, match, control, interrupt, and wakeup state.  SDK timer
adapters can use it for monotonic time, deadlines, and low-power wakeups.  It
therefore supports DSP/audio scheduling around a stream, rather than moving
the samples themselves.

## Hardware contract

The project-local MIMXRT685S CMSIS-SVD and MCUXpresso SDK define:

- M33 non-secure base address `0x40113000`;
- M33 interrupt `OS_EVENT_IRQn` / NVIC line 41;
- a 64-bit central counter exposed by `EVTIMERL/H`;
- per-CPU `CAPTURE_L/H`, `MATCH_L/H`, and `OSEVENT_CTRL` registers;
- Gray-encoded counter and match values on RT685;
- clock gate `CLKCTL1.PSCCTL0[27]` and reset
  `RSTCTL1.PRSTCTL0[27]`; and
- a normal SDK configuration of 1 MHz.

`OSEVENT_CTRL.OSTIMER_INTRFLAG` is set on a match and is write-one-to-clear.
`OSTIMER_INTENA` gates the interrupt/wakeup output.  `MATCH_WR_RDY` is low when
a new match may be written.

## QEMU model

The `rt6xx-ostimer` sysbus device implements the M33 non-secure register view
at `0x40113000` and connects its interrupt to NVIC input 41.  It uses the QEMU
virtual clock, so execution is deterministic under qtest and does not depend
on host wall time.

The counter advances at 1 MHz while its CLKCTL1 gate is enabled and reset is
deasserted.  Clock gating freezes and later resumes the count.  Peripheral
reset clears the count and the local match/control state.  Counter and match
registers are converted between the model's binary time and the guest-visible
Gray representation.

Writing `MATCH_L` followed by `MATCH_H`, as the SDK does, commits a one-shot
absolute deadline.  Match-register synchronization completes immediately, so
`MATCH_WR_RDY` reads zero.  Reaching the match sets the flag regardless of the
interrupt enable; the IRQ is asserted only when both flag and enable are set.
The flag remains set until software clears it.

State, including the pending QEMU timer, is migratable.  CLKCTL1 and RSTCTL1
now expose named clock/reset signals to the device.

## Scope and limitations

This increment intentionally models only the domain that exists in the QEMU
machine today:

- M33 non-secure address view only; the secure `0x50113000` alias is deferred.
- No DSP address view or DSP-local match/control bank until a DSP core/domain
  is instantiated.
- No CPU-generated capture signal is currently available in the machine, so
  `CAPTURE_L/H` retain their reset value.
- The clock selector is stored by CLKCTL1, but frequency selection and match
  synchronization latency are not timing-accurate; the functional rate is
  fixed at the SDK's 1 MHz configuration.
- Deep-sleep power-state transitions are not modeled.  IRQ 41 provides the
  event behavior needed by running M33 firmware.

## Verification

The MIMXRT685 qtest suite covers:

1. a stopped counter before the clock gate is enabled;
2. 1 MHz counter progression and Gray-code conversion;
3. an absolute match, sticky flag, IRQ 41, and write-one-to-clear handling;
4. counter freeze while clock-gated; and
5. reset of count, match, and control state.

Future DSP integration should split the local capture/match/control bank per
CPU while sharing the central counter, then map the DSP and secure aliases to
the same device.
