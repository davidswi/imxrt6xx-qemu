# i.MX RT600 / MIMXRT685-EVK QEMU Emulator — Milestone 1 Gaps Analysis

**Status:** M33 M2 behavior complete locally; physical-EVK comparison pending  
**Analysis date:** 2026-10-24  
**Target:** MIMXRT685S on the MIMXRT685-EVK  
**Accuracy target:** Functional firmware emulation, not cycle accuracy

## M2 update

The Cortex-M33 platform baseline now boots the pinned MCUXpresso FreeRTOS
hello application from SRAM.  The firmware starts the scheduler, exercises
SVC, PendSV and periodic SysTick, prints from the task through Flexcomm 0, and
continues correctly after system reset.  A gated functional test completed 20
consecutive boot/reset runs under TCG defaults, passed debug and optimized
`-Werror` builds, and is backed by the 10-test MIMXRT685 qtest suite.

The Cortex-M33 retains the Armv8-M Security Extension and runs FreeRTOS in its
supported Secure-only configuration.  Secure-to-Non-secure boot, IDAU/SAU
attribution, and TrustZone application flows remain deferred.  A physical-EVK
UART transcript is still required for the plan's external hardware comparison.

**Implementation roadmap:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## 1. Executive summary

The recommended implementation base remains the user's modernized port of the Sound Open Firmware (SOF) QEMU fork, but the hardware target is now the **MIMXRT685S and MIMXRT685-EVK**.

This is a meaningful DSP-risk reduction compared with the earlier RT500 target:

- NXP identifies the RT685 DSP explicitly as a Cadence Tensilica HiFi 4 running at up to 600 MHz, rather than requiring a Fusion F1/HiFi4 equivalence assumption.
- Upstream Zephyr supports the EVK as separate `mimxrt685_evk/mimxrt685s/cm33` and `mimxrt685_evk/mimxrt685s/hifi4` targets.
- The Zephyr SDK distributes an `xtensa-nxp_rt600_adsp_zephyr-elf` GCC toolchain, so buildable, redistributable DSP test programs are readily available.
- Zephyr includes M33-side DSP power, clock, image-loading, and run-control support plus RT600 AMP audio samples.
- MCUXpresso documents the DSP boot sequence, memory placement, interrupts, MU, SEMA42, RPMsg-Lite, DMA, and peripheral use, and supplies small dual-core examples.
- The physical EVK supports independent and tandem debugging of the M33 and HiFi4, making it a practical differential-testing oracle.

The target change does **not** eliminate the principal CPU risk. A compiler configuration and generated decoder data do not provide QEMU TCG semantics for HiFi4 packed, vector, accumulator, or VFPU instructions. The first project gate is therefore an empirical one: build the Zephyr HiFi4 hello-world and IPC fixtures, run them under the imported QEMU configuration, and produce an exact unsupported-opcode census.

The recommended architecture is still two QEMU processes—one ARM and one Xtensa—connected using a hardened form of the SOF message-queue/shared-memory bridge. The first useful target should be the upstream Zephyr RT685 AMP flow, not a custom demonstration.

### Feasibility verdict

| Target | Assessment | Main reason |
|---|---|---|
| M33 Zephyr hello world from SRAM | Low-to-medium risk | QEMU has Cortex-M33; the RT685 machine and startup-visible MMIO remain |
| HiFi4 Zephyr hello world | Medium risk, strong discovery target | Exact public board/toolchain target exists; emitted instruction coverage is not yet known |
| Zephyr M33-starts-DSP AMP hello world | Medium-to-high risk | Upstream firmware provides the boot contract; QEMU still needs RT685 power/reset/memory models |
| MU polling/interrupt examples | Medium-to-high risk | NXP supplies focused examples; paired MU semantics and bridge delivery remain |
| RPMsg-Lite control-plane demo | High but bounded risk | Shared-memory layout and MU notifications are well specified by working software |
| Zephyr AMP audio output/loopback | High risk | Adds DMA, I2S, clocks, codec, and enough HiFi4 instructions for audio code |
| XAF or production DSP firmware | Very high risk | Likely exercises a much broader HiFi4/VFPU and peripheral surface |
| Full-chip or cycle-accurate replacement | Out of scope | Timing, contention, caches, security, analog, and many board devices are absent |

## 2. Decision record

### Selected platform

The concrete target is the **MIMXRT685S** mounted on the [MIMXRT685-EVK](https://www.nxp.com/products/processors-and-microcontrollers/arm-microcontrollers/i-mx-rt-crossover-mcus/i-mx-rt600-evaluation-kit:MIMXRT685-EVK).

NXP's [RT600 family fact sheet](https://www.nxp.com/docs/en/fact-sheet/IMXRT600FAMILYFS.PDF) describes:

- Cortex-M33 at up to 300 MHz;
- Cadence Tensilica HiFi 4 DSP at up to 600 MHz;
- up to 4.5 MB on-chip SRAM;
- 128 KB DSP TCM and 96 KB DSP cache;
- a Messaging Unit and hardware semaphore;
- two DMA controllers, eight FlexComm interfaces, DMIC, high-speed USB, I3C, FlexSPI, timers, and security blocks.

The EVK adds Octal SPI flash and PSRAM, an audio codec with line input/output, dual digital microphones, expansion for additional DMICs, USB, Arduino headers, and an on-board debug probe. These board devices are later milestones, not prerequisites for CPU and IPC bring-up.

### Selected emulator architecture

Use a modern QEMU tree containing the user's forward-ported SOF changes and build two target-specific system emulators:

```text
 qemu-system-arm                           qemu-system-xtensa
 +----------------------------+           +----------------------------+
 | mimxrt685-evk-cm33         |           | mimxrt685-evk-hifi4        |
 |  Cortex-M33                |           |  nxp_rt600_adsp config     |
 |  NVIC / ARMv8-M devices    |           |  DSP IRQ mux / local RAM   |
 |  DSP control + MU side A   |<--------->|  MU side B                 |
 |  shared SRAM aliases       |  bridge   |  shared SRAM aliases       |
 +----------------------------+           +----------------------------+
```

The bridge is an implementation detail. Guest software must see RT685 memory, reset, interrupt, SEMA42, and MU behavior—not generic SOF bridge registers.

### Why RT600 reduces DSP risk

The [Zephyr MIMXRT685-EVK documentation](https://docs.zephyrproject.org/latest/boards/nxp/mimxrt685_evk/doc/index.html) confirms a maintained HiFi4 board target, support for proprietary Cadence tools and the Zephyr SDK GCC toolchain, direct DSP debugging, and tandem M33/DSP debugging. Zephyr also documents the M33-side `nxp_rtxxx_adsp_ctrl` component that powers, loads, and runs the DSP.

The RT600 software ecosystem therefore supplies four things the project previously had to discover independently:

1. a named, buildable DSP compiler target;
2. linker scripts and devicetrees for both core views;
3. working M33-side boot/control software; and
4. small single-core and AMP applications suitable for regression fixtures.

It still does not supply QEMU implementations of all configured HiFi4 instructions.

## 3. Scope and definition of done

This analysis assumes:

1. MIMXRT685S is the sole initial SoC target; RT633 and RT500 compatibility are deferred.
2. The MIMXRT685-EVK is the board target; the MIMXRT685-AUD-EVK may be used later for richer audio validation.
3. Firmware is initially loaded from ELF or packaged AMP images. ROM boot, signed images, OTFAD, and production security flows are deferred.
4. Linux is the initial emulator host because the inherited SOF bridge uses POSIX message queues and shared memory.
5. Functional correctness covers architectural state, address maps, MMIO, interrupts, reset/power transitions, shared memory, and repeatable event ordering. It does not cover cycle timing or audio deadlines.

### Milestone definition of done

The milestone passes when the emulator can run unmodified or minimally board-configured upstream fixtures that:

- boot Zephyr hello world on the M33 target;
- boot Zephyr hello world on the HiFi4 target;
- start with the DSP powered/stalled as real hardware does;
- execute the M33-side DSP initialization, image-loading, and run-control path;
- exchange all four MU message channels in both directions using NXP polling and interrupt examples;
- share RPMsg-Lite memory correctly and complete a bidirectional control-plane exchange;
- produce repeatable UART and bridge event transcripts in deterministic mode; and
- diagnose every unsupported instruction and unknown MMIO access.

Audio playback is the next milestone, not part of this initial definition of done.

## 4. Evidence and executable specifications

### Primary hardware and SDK sources

- [MIMXRT685-EVK product page](https://www.nxp.com/products/processors-and-microcontrollers/arm-microcontrollers/i-mx-rt-crossover-mcus/i-mx-rt600-evaluation-kit:MIMXRT685-EVK)
- [RT600 data sheet](https://www.nxp.com/docs/en/data-sheet/RT600.pdf)
- [RT600 family fact sheet](https://www.nxp.com/docs/en/fact-sheet/IMXRT600FAMILYFS.PDF)
- [MCUXpresso HiFi4 system programming guide](https://docs.mcuxpresso.nxp.com/mcuxsdk/latest/boards/RT/mimxrt685audevk/gettingStarted/topics/hifi4_system_programming.html)
- [MCUXpresso HiFi4 boot loader and memory-map guide](https://docs.mcuxpresso.nxp.com/mcuxsdk/latest/boards/RT/mimxrt685audevk/gettingStartedXplorer/topics/hifi4_boot_loader_and_memory_map.html)
- [MCUXpresso DSP peripheral/interrupt guide](https://mcuxpresso.nxp.com/mcuxsdk/25.12.00/html/boards/RT/mimxrt685audevk/gettingStartedXplorer/topics/peripheral_drivers_and_interrupts.html)
- [MCUXpresso examples repository](https://github.com/nxp-mcuxpresso/mcuxsdk-examples)

The MCUXpresso material identifies focused `mu_polling`, `mu_interrupt`, and `sema42` DSP examples, plus XAF/RPMsg-Lite applications. It also documents that the DSP is powered off initially, that M33 performs clock/power/local-memory/image setup, and that vectors/critical code, ordinary code/data, and non-cacheable data occupy different memory classes.

### Primary open-source firmware sources

- [Zephyr MIMXRT685-EVK board documentation](https://docs.zephyrproject.org/latest/boards/nxp/mimxrt685_evk/doc/index.html)
- [Zephyr MIMXRT685-EVK board sources](https://github.com/zephyrproject-rtos/zephyr/tree/main/boards/nxp/mimxrt685_evk)
- [CM33 board devicetree](https://github.com/zephyrproject-rtos/zephyr/blob/main/boards/nxp/mimxrt685_evk/mimxrt685_evk_mimxrt685s_cm33.dts)
- [HiFi4 board devicetree](https://github.com/zephyrproject-rtos/zephyr/blob/main/boards/nxp/mimxrt685_evk/mimxrt685_evk_mimxrt685s_hifi4.dts)
- [Zephyr RTxxx AMP audio-output sample](https://docs.zephyrproject.org/latest/samples/boards/nxp/adsp/rtxxx/amp_audio_output/README.html)
- [Zephyr RTxxx AMP audio-loopback sample](https://docs.zephyrproject.org/latest/samples/boards/nxp/adsp/rtxxx/amp_audio_loopback/README.html)

The HiFi4 devicetree enables Flexcomm UART, DMA1, I2S receive/transmit, I3C-attached audio codec, GPIO, CRC, and mailbox support. This provides a concrete, versioned list of peripherals exercised by later AMP/audio tests.

### Emulator inputs

- [SOF QEMU repository](https://github.com/thesofproject/qemu), especially the [two-process I/O bridge](https://github.com/thesofproject/qemu/blob/sof-v4.2/util/qemu-io-bridge.c), [bridge protocol](https://github.com/thesofproject/qemu/blob/sof-v4.2/include/qemu/io-bridge.h), [i.MX8M DSP machine](https://github.com/thesofproject/qemu/blob/sof-v4.2/hw/adsp/dsp/imx8m.c), and [partial i.MX8 MU](https://github.com/thesofproject/qemu/blob/sof-v4.2/hw/adsp/dsp/imx8-mu.c)
- Current [QEMU Cortex-M implementation](https://github.com/qemu/qemu/blob/master/target/arm/tcg/cpu-v7m.c)
- Renode's [RT500 platform](https://github.com/renode/renode/blob/master/platforms/cpus/imxrt500.repl) and referenced LPC/NXP peripheral models as nearby-family references only

No maintained Renode or upstream QEMU RT685 machine was identified. Do not treat the RT500 Renode address map as authoritative for RT600.

Pin exact commits and SDK/toolchain releases before implementation.

## 5. HiFi4 risk-reduction plan

### What is now known

- The core is explicitly HiFi4, not merely a nearby Xtensa configuration.
- Zephyr can build `samples/hello_world` for `mimxrt685_evk/mimxrt685s/hifi4` with the Zephyr SDK's `xtensa-nxp_rt600_adsp_zephyr-elf` toolchain.
- The Zephyr and MCUXpresso linker descriptions expose the DSP memory views used by real software.
- The EVK can supply instruction-level expected results through hardware debugging.
- Small examples create a natural progression from startup to MU, RPMsg-Lite, DMA/I2S, and audio workloads.

### What remains unknown

The SOF QEMU i.MX8/i.MX8M overlays contain generated HiFi4 decoder/configuration data, but the inspected `sof-v4.2` configuration falls back to generic Xtensa opcode translators. Instructions that decode but lack handlers fault at execution. The RT600 toolchain target also does not automatically provide a QEMU CPU overlay or TCG helpers.

The RT600 configuration may differ from the SOF i.MX8M core in registers, interrupts, memory options, caches, TIE operations, and instruction availability. Reusing the i.MX8M overlay unchanged would conceal exactly the mismatch this target switch is intended to remove.

### DSP discovery spike

Before building broad peripherals:

1. Install a pinned Zephyr SDK containing `xtensa-nxp_rt600_adsp_zephyr-elf`.
2. Build HiFi4 `hello_world`, a minimal arithmetic/exception corpus, MU polling, MU interrupt, and RPMsg-Lite fixtures.
3. Extract ELF attributes, disassembly, register use, sections, vectors, and every distinct opcode/format.
4. Obtain the RT600 Xtensa configuration artifacts available with the toolchain or NXP/Cadence development package.
5. Import a dedicated QEMU CPU overlay named for `nxp_rt600_adsp`; do not alias it to `imx8m`.
6. Run the fixtures and emit structured reports for decoded-but-unimplemented instructions, unknown registers, and exception mismatches.
7. Run the same fixtures on the EVK and capture architectural checkpoints with GDB/J-Link or `xt-ocd`.

### Gate criteria

Proceed to full dual-core platform work only if:

- the exact reset/vector/interrupt/register configuration is available;
- HiFi4 hello world reaches `main` or has a finite, understood missing-opcode list;
- required instruction semantics can be implemented and tested legally;
- the chosen firmware fixtures can be retained in automated tests; and
- hardware comparison is repeatable.

If this gate fails, the project should deliver an M33-focused RT685 emulator and a documented experimental DSP subset rather than claiming HiFi4 compatibility.

## 6. SOF bridge gap analysis

### Reusable functionality

The SOF bridge connects QEMU processes of different architectures through:

- parent/child roles;
- POSIX message queues for IRQ, register, power, DMA, memory, and debugger events;
- POSIX shared-memory mappings; and
- per-machine receive callbacks.

This is the appropriate starting pattern because ARM and Xtensa QEMU system emulators are target-specific binaries.

### Required hardening

| Gap | Impact | Required action |
|---|---|---|
| No RT685 M33 endpoint | Existing SOF NXP work is DSP-oriented | Add bridge-backed DSP control, MU side A, and shared SRAM to the ARM machine |
| No shared virtual clock | Host threads and queues determine event arrival | Add a coordinator and deterministic grant/barrier protocol |
| Small fixed queues | Inherited limit is eight messages of at most 128 bytes | Make limits explicit and handle backpressure without deadlock |
| Global singleton bridge | Prevents clean multi-link tests and complicates lifecycle | Convert or wrap it as an instance-owned QEMU object |
| Weak startup/recovery | Peer order, stale queues, and crashes can poison tests | Add handshake, protocol version, session ID, timeout, cleanup, and reconnect rules |
| Uncoordinated snapshots/GDB | Processes cannot stop or snapshot atomically | Defer migration; add coordinated pause/checkpoint commands for testing |
| Linux-specific transport | POSIX mqueues are not uniformly portable | Support Linux first and isolate transport behind a backend interface |

Support two execution modes:

1. **Fast functional mode**, allowing both cores to run freely between bridge events.
2. **Deterministic test mode**, granting bounded virtual-time or instruction quanta and yielding at MU/MMIO, WFI/WAITI, interrupt, timer, reset, and explicit barrier events.

## 7. Cortex-M33 and RT685 machine gaps

Current QEMU provides Cortex-M33/ARMv8-M Mainline, NVIC, SysTick, security architecture, memory regions, QOM devices, ELF loading, GDB, tracing, and qtest. The missing work is the RT685 machine:

| Gap | Priority | Required action |
|---|---:|---|
| `mimxrt685-evk-cm33` machine | P0 | Instantiate Cortex-M33, memory regions, aliases, NVIC inputs, and board boot configuration |
| Exact M33 feature profile | P0 | Verify FPU, MPU/SAU, TrustZone, priority bits, and external interrupt count |
| SRAM/TCM and aliases | P0 | Derive from RT685 headers, linker scripts, devicetree, and reference manual |
| DSP control block | P0 | Implement registers used by `fsl_dsp` and Zephyr `nxp_rtxxx_adsp_ctrl` |
| Clock/reset/power | P0 | Implement the sequence needed to power DSP memories, clocks, resets, vector base, stall, and run |
| UART and timers | P0 | Provide Flexcomm0 UART and timers used by Zephyr bring-up |
| MU side A / SEMA42 | P0/P1 | Support NXP examples and RPMsg-Lite synchronization |
| FlexSPI/EVK flash | P1 | Add when booting board images rather than direct-loaded ELF |
| TrustZone/security boot | P2/P3 | Defer unless the selected firmware requires it |

The M33 implementation should first boot the upstream Zephyr CM33 hello-world. The next test should execute the real Zephyr DSP-control driver against a stub peer before the Xtensa process is introduced.

## 8. HiFi4 machine and interrupt gaps

Create a dedicated `mimxrt685-evk-hifi4` machine using the exact RT600 core overlay. It must model:

- DSP reset and stall state;
- vector and critical sections in DSP TCM;
- executable/data sections in shared SRAM;
- non-cacheable shared regions used for inter-core data;
- DSP cache-visible behavior or a documented initial coherent abstraction;
- 32 DSP interrupts and four interrupt levels;
- the DSP interrupt input multiplexers for sources 5–31;
- MU side B, SEMA42, DMA1, Flexcomm0 UART, and timers required by early fixtures; and
- the DSP-visible aliases of shared peripherals.

The MCUXpresso guide states that digital peripherals are accessible from both cores and that DMA1 is the intended DSP DMA controller. Shared peripheral ownership must therefore be explicit: both QEMU processes cannot independently own conflicting UART, timer, DMA, or clock state.

For the first milestone, assign each side-effecting peripheral to one process and access it from the other through bridge transactions. Shared RAM remains direct shared-memory backing. This avoids divergent duplicate device state.

## 9. Messaging Unit, SEMA42, and shared memory

RT600 software confirms that inter-core IPC uses the MU and SEMA42. MCUXpresso supplies `mu_polling`, `mu_interrupt`, and `sema42` examples; XAF uses RPMsg-Lite over shared memory with MU notifications. These are substantially better acceptance fixtures than a custom mailbox test.

### MU behavior to implement

- two core-facing register views backed by one logical state machine;
- four 32-bit transmit and receive channels in each direction;
- transmit-empty and receive-full transitions;
- per-channel interrupt enables and correct core routing;
- general interrupt request/pending/clear/retrigger behavior;
- peer reset and power indications exposed by the RT685 variant;
- correct reset values, access widths, masks, W1C/W1S, and reserved bits; and
- DSP interrupt-mux integration, including the interrupt line used by SDK/XOS examples.

The SOF i.MX8 MU code is a useful register-name and event-delivery precedent, but its implementation is incomplete: it largely stores register values and handles a subset of general-interrupt signaling. It should be adapted conceptually, not declared RT685-compatible.

### SEMA42 behavior

Implement the gate ownership, lock attempt, unlock, reset, and notification semantics used by the NXP example and RPMsg-Lite port. Include simultaneous acquisition tests in deterministic mode. SEMA42 must share one authoritative state across the two QEMU processes.

### Shared SRAM

Map the same host shared-memory object into each guest at the core-appropriate addresses. Validate:

- linker-section and alias offsets;
- RPMsg-Lite vrings and payload regions;
- atomic access assumptions;
- cacheable versus non-cacheable views;
- cross-process translation-block invalidation for executable writes;
- DSP reset and SRAM retention behavior; and
- bounds and security permissions.

Bridge semantic events rather than mirroring arbitrary side-effecting MMIO arrays. Each local MU/SEMA42 endpoint should receive sequence-numbered transitions such as message written/consumed, semaphore acquired/released, general IRQ, and peer reset.

## 10. Peripheral and EVK coverage

### Milestone ordering

| Priority | Blocks | Purpose |
|---|---|---|
| P0 | M33, HiFi4, SRAM/TCM/aliases, DSP control, clock/reset subset, IRQ mux, MU, Flexcomm0 UART, basic timer | Hello world and dual-core control plane |
| P1 | SEMA42, DMA1, I2S Flexcomm instances, I3C, WM8904 control path, audio clocks | Zephyr AMP audio output |
| P2 | DMIC, DMA0, GPIO/IOCON, CRC, FlexSPI, Octal flash/PSRAM, cache controls | Audio loopback and board-like boot |
| P3 | USB, SD/eMMC, ADC/comparator, security blocks, OTFAD/PUF/OTP, full ROM boot | Workload-specific expansion |

### Reference hierarchy

For each peripheral, use this order of authority:

1. RT600 reference manual and MIMXRT685S device headers/SVD;
2. MCUXpresso driver and example behavior;
3. Zephyr devicetree and driver behavior;
4. physical EVK traces;
5. nearby Renode RT500 model, where the IP block is demonstrably compatible.

Renode's C# devices cannot be linked into QEMU. Port behavior into QOM/sysbus devices and record the source and differences. Unknown MMIO should warn or abort during bring-up; silent read-as-zero/write-ignore behavior must be opt-in per register.

## 11. Boot and validation ladder

Use existing firmware as the specification:

1. **M33 direct-load:** upstream Zephyr hello world; validate reset/vector fetch, SRAM, UART, SysTick, and one external IRQ.
2. **DSP direct-load:** upstream Zephyr HiFi4 hello world; validate configuration, vectors, TCM/SRAM, UART routing, and opcode census.
3. **M33 control with stub DSP:** run `nxp_rtxxx_adsp_ctrl` or equivalent SDK sequence and verify register transitions.
4. **Real AMP boot:** M33 powers, loads, and starts the QEMU HiFi4 peer.
5. **Focused IPC:** NXP MU polling, MU interrupt, and SEMA42 examples.
6. **RPMsg-Lite:** bidirectional message exchange over shared SRAM.
7. **Audio output:** Zephyr RTxxx AMP audio-output sample with DMA/I2S and a simplified or real codec backend.
8. **Audio loopback/XAF:** add input timing and broader DSP instruction/peripheral coverage.
9. **Flash/security boot:** only if target firmware requires it.

Starting both guests in a running state at host launch is not acceptable for stages 4 onward; real M33-controlled DSP startup is part of the observable contract.

## 12. Testing and observability

### Required traces

- per-core PC, instruction bytes, decoded operation, register changes, exception, and virtual time;
- unsupported opcode name/encoding, format/slot, PC, ELF symbol, and execution count;
- MMIO core/security/width/address/value/device/register;
- bridge session, sequence number, sender, receiver, event, and delivery timestamp;
- interrupt source, mux selection, target, enable, pending, acknowledge, and clear;
- DSP power/clock/reset/stall/vector state transitions; and
- deterministic launch configuration and random seeds.

### Test pyramid

| Layer | Tests |
|---|---|
| Xtensa configuration | register reset, vectors, ABI, exceptions, interrupt levels, instruction corpus |
| Bridge | handshake, version, ordering, backpressure, peer loss, stale cleanup, reconnect |
| Devices | reset values, masks, widths, W1C/W1S, aliases, IRQ transitions, invalid accesses |
| Firmware drivers | Zephyr and MCUXpresso DSP control, MU, SEMA42, UART, timer, DMA/I2S |
| Dual-core | boot, shared-memory visibility, RPMsg-Lite, WFI/WAITI wake, peer reset |
| Platform | golden UART and event transcripts for each rung of the validation ladder |
| Differential | QEMU versus EVK checkpoints; Renode only for proven-compatible peripheral subsets |
| Fuzz/property | decoder robustness, MU/SEMA42 invariants, malformed bridge messages |

Use qtest for devices and a supervisor process for paired-system tests. The supervisor should launch both QEMU binaries, create a unique bridge namespace, coordinate deterministic grants, capture logs, enforce timeouts, and always clean up queues/shared-memory objects.

## 13. Recommended implementation sequence

### Phase A — freeze and audit

- Pin the modern QEMU base, SOF forward-port series, Zephyr release, Zephyr SDK, MCUXpresso release, and board revision.
- Build and run the CM33 and HiFi4 Zephyr hello-world images on the EVK.
- Audit which SOF bridge/i.MX changes survived the user's forward port.
- Extract authoritative memory, IRQ, DSP configuration, and boot-control data.

**Exit gate:** reproducible firmware binaries and EVK traces exist, and the forward-ported QEMU builds on Linux.

### Phase B — DSP feasibility spike

- Import the `nxp_rt600_adsp` QEMU CPU configuration.
- Run the HiFi4 fixture corpus and generate the opcode/register census.
- Implement the minimum missing operations required to reach Zephyr `main` and print hello world.
- Compare checkpoints against the EVK.

**Exit gate:** HiFi4 hello world completes or every remaining blocker is finite, specified, and testable. Stop broad platform work if this cannot be achieved.

### Phase C — bridge hardening

- Add session handshake, versioning, sequence numbers, lifecycle handling, and tracing.
- Add shared-memory regions with distinct ARM and DSP guest mappings.
- Implement fast and deterministic coordination modes.

**Exit gate:** minimal ARM and Xtensa machines repeatedly exchange ordered events and shared data without stale host resources.

### Phase D — M33 machine and DSP control

- Add `mimxrt685-evk-cm33`, SRAM/aliases, UART, timer, and required clocks/resets.
- Boot Zephyr CM33 hello world.
- Implement DSP power, local-memory, clock, reset, vector, stall, load, and run controls.

**Exit gate:** the real Zephyr/SDK M33 DSP-start sequence completes against a verified stub peer.

### Phase E — dual-core control plane

- Add `mimxrt685-evk-hifi4` memory and interrupt mux.
- Connect paired MU and SEMA42 endpoints.
- Run M33-controlled HiFi4 boot, NXP polling/interrupt examples, and RPMsg-Lite.

**Exit gate:** the milestone definition in section 3 passes in deterministic mode.

### Phase F — audio expansion

- Add DMA1, I2S, audio clocks, I3C control, and WM8904 behavior/backend.
- Implement HiFi4 instructions in measured workload order.
- Run Zephyr AMP audio output, then loopback, then selected XAF workloads.

## 14. Open decisions and gates

1. What modern QEMU commit and SOF patch series make up the user's existing port?
2. Which Zephyr/Zephyr SDK and MCUXpresso releases should be pinned?
3. Is the classic MIMXRT685-EVK the only validation board, or is MIMXRT685-AUD-EVK also available?
4. Can the project use the RT600 Xtensa configuration artifacts shipped with the selected toolchain/Cadence package?
5. May compiled Zephyr/MCUXpresso test fixtures and EVK traces be retained in the repository?
6. Is Linux acceptable as the first and possibly only host?
7. Is deterministic functional ordering sufficient, or are audio timing/deadline failures in scope?
8. Is the first end-user workload Zephyr AMP, MCUXpresso RPMsg-Lite/XAF, or another firmware?
9. Are TrustZone, external flash, secure boot, and encrypted images required?

Questions 1, 2, 4, 5, and 8 should be answered before claiming a fixed implementation schedule.

## 15. Milestone conclusion

Moving to MIMXRT685-EVK materially improves the project because it supplies a precise public HiFi4 target, an open GCC toolchain, dual-core Zephyr board definitions, maintained AMP samples, documented NXP boot/IPC examples, and accessible hardware validation.

The critical path is now:

1. pin the toolchain and firmware fixtures;
2. import the exact `nxp_rt600_adsp` QEMU configuration;
3. measure and close the HiFi4 opcode gap with EVK-backed tests;
4. harden the SOF bridge and shared-memory lifecycle;
5. implement the RT685 M33 machine and real DSP-control sequence;
6. implement paired MU and SEMA42 behavior; and
7. advance from RPMsg-Lite to audio peripherals only after the control plane is stable.

This target switch converts DSP configuration and firmware availability from open-ended discovery risks into concrete engineering tasks. HiFi4 execution semantics remain the decisive technical risk, but they can now be measured early using standard, buildable firmware and compared directly with the EVK.
