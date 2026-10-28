# i.MX RT685 QEMU Implementation Plan

**Target:** MIMXRT685S on MIMXRT685-EVK  
**Initial CPU scope:** Cortex-M33 only  
**Baseline:** latest upstream QEMU mainline at project start  
**First firmware target:** MCUXpresso SDK `freertos_hello`

## 1. Outcome and scope

The first implementation increment will add an upstream-quality MIMXRT685-EVK machine to QEMU and boot the NXP MCUXpresso FreeRTOS hello-world application on its Cortex-M33.

The work is divided into three milestones:

| Milestone | Outcome |
|---|---|
| M0 | QEMU contains an instantiable MIMXRT685-EVK Cortex-M33 machine with the correct foundational memory and interrupt topology |
| M1 | The machine has the RT685 peripheral behavior required by the pinned FreeRTOS image, with qtests for every new device |
| M2 | An unmodified MCUXpresso `freertos_hello` application boots, schedules a FreeRTOS task, and prints its expected UART output |

M0–M2 intentionally exclude the HiFi4 process, SOF bridge integration, MU/SEMA42, audio, DMA, external-flash boot, and secure boot. Those follow once the M33 platform baseline is stable.

“Add the missing peripheral models” in M1 means **models required by the M2 firmware and its startup path**, not every peripheral present in the RT685 or on the EVK. Full-device coverage would be too broad to verify meaningfully in one milestone.

## 2. Pinned inputs and reproducibility

Before implementation, create `docs/system/arm/mimxrt685-evk.rst` in the QEMU tree and a project-side source manifest recording:

- upstream QEMU repository URL and exact base commit;
- topic-branch name and patch-series revision;
- MCUXpresso manifest and `mcuxsdk-examples` commit IDs;
- Arm GNU toolchain version;
- MIMXRT685S CMSIS header, SVD, reference-manual revision, and board revision;
- Renode and SOF QEMU reference commits; and
- firmware build command, linker configuration, ELF SHA-256, and map-file SHA-256.

QEMU's upstream default branch is currently named `master`. “Latest main” in this plan means the current upstream default/mainline head, recorded by commit ID when M0 begins—not a moving branch reference.

Recommended branch stack:

```text
upstream/master
  └── topic/imxrt685-m0-machine
        └── topic/imxrt685-m1-peripherals
              └── topic/imxrt685-m2-freertos-hello
```

Keep the stack rebaseable and split by reviewable subsystem. Do not combine the machine, all devices, tests, and firmware test into one commit.

## 3. Design principles

### SoC and board separation

Model the silicon separately from the evaluation board:

```text
MIMXRT685EVKMachineState
  └── MIMXRT685SoCState
        ├── ARMv7M container
        │     ├── Cortex-M33
        │     ├── NVIC
        │     └── SysTick
        ├── on-chip memories and aliases
        ├── clock/reset/system-control devices
        ├── IOCON/GPIO
        └── Flexcomm instances
```

The SoC owns on-chip memory and peripherals. The board owns boot configuration and later external flash, PSRAM, codec, microphones, and connectors. This avoids baking EVK-specific devices into the silicon model.

### Source authority

Use references in this order:

1. MIMXRT685S reference manual, CMSIS header, SVD, errata, and SDK drivers;
2. MCUXpresso board initialization and the pinned firmware's observed behavior;
3. physical EVK traces;
4. Zephyr's RT685 devicetree and drivers;
5. Renode RT500/LPC/NXP models where the IP revision is confirmed compatible; and
6. SOF QEMU i.MX8 models for QEMU design patterns and shared NXP IP behavior.

Renode and SOF are references, not authoritative RT685 specifications. Record any deliberate difference in the QEMU device source or documentation.

### Modeling policy

- Implement register behavior, not firmware-specific PC hooks.
- Do not return magic values merely to advance the firmware.
- Unknown registers should log `LOG_UNIMP` during bring-up.
- Invalid widths or alignment should produce QEMU guest errors where hardware would reject them.
- Use explicit reset phases and QEMU clocks where relevant.
- Add VMState descriptions for stateful devices unless the device is explicitly declared non-migratable.
- Keep source constants derived from the selected RT685 header/reference revision.

## 4. M0 — Create the MIMXRT685-EVK machine

### Goal

Create a topic branch from the pinned upstream mainline commit and add an instantiable `mimxrt685-evk` machine with correct Cortex-M33, memory, reset, and interrupt foundations. M0 does not attempt to boot the production FreeRTOS image.

### M0.1 — Baseline and build matrix

1. Fetch upstream QEMU and record the default-branch commit.
2. Create `topic/imxrt685-m0-machine` from that exact commit.
3. Configure at least:

   ```text
   --target-list=arm-softmmu
   --enable-debug
   --enable-werror
   ```

4. Establish the commands used for `ninja`, `meson test`, qtest, and functional tests.
5. Run the relevant pre-change ARM test subset and save the result as a baseline.

### M0.2 — QOM layout and build integration

Add:

- an RT685 SoC QOM type;
- an MIMXRT685-EVK machine QOM type;
- headers for device state and address/IRQ constants;
- Kconfig and Meson entries under `hw/arm`;
- machine documentation under `docs/system/arm`; and
- MAINTAINERS entries for the machine and its tests.

Use an upstream Cortex-M33 through QEMU's ARMv7M container rather than constructing the CPU/NVIC/SysTick separately. Set the exact external IRQ count and priority configuration from the MIMXRT685S source material.

### M0.3 — Foundational memory map

Create a reviewed map table before writing code. It must identify for each region:

- M33 address and size;
- physical backing store;
- secure/non-secure alias relationship;
- executable/read/write permissions;
- reset or retention domain; and
- whether the region is real storage, an alias, a device, or intentionally absent.

M0 should include only the foundational regions needed for reset and later direct ELF loading:

- M33 vector/reset-visible memory;
- M33 TCM if present in the selected configuration;
- on-chip SRAM banks and their aliases;
- system ROM as a read-only placeholder only if an image is legally available or startup requires the address range;
- Cortex-M system-control space supplied by QEMU; and
- explicitly named unimplemented ranges only when they improve diagnostics without masking missing devices.

All aliases must share the same `MemoryRegion` backing. Do not instantiate duplicate RAM for hardware aliases.

### M0.4 — Reset and image loading

- Start the M33 from the architectural vector table.
- Support `-kernel <elf>` using the normal M-profile loader path.
- Define the initial security state and document it. The first firmware configuration should be non-secure or single-state unless its official SDK build requires TrustZone.
- Reject unsupported CPU types and SMP counts with clear errors.
- Keep the DSP absent/held off; M0 is an M33-only machine.

### M0.5 — M0 tests

Add qtests for:

- machine creation and clean reset;
- expected Cortex-M33 CPU type and single-CPU limit;
- representative memory-region boundaries;
- secure/non-secure or other SRAM aliases sharing storage;
- read/write permissions and unmapped boundaries;
- reset-vector loading from a tiny test ELF; and
- repeated system reset restoring architectural and memory-reset behavior as specified.

Use a tiny project-owned test ELF or bytes generated specifically for QEMU tests—not the MCUXpresso firmware—to keep M0 independent of the SDK.

### M0 deliverables

- `qemu-system-arm -M mimxrt685-evk -machine help` exposes the machine.
- The debug and release builds pass with warnings treated as errors.
- New memory/reset qtests pass.
- Existing relevant ARM qtests remain green.
- Documentation states what is modeled and explicitly lists missing peripherals.

### M0 exit criteria

M0 is complete when a minimal Cortex-M33 image can fetch its vector table, execute from modeled on-chip memory, write a completion marker to RAM, and stop under qtest without unmodeled CPU or memory behavior.

## 5. M1 — Add M2-critical RT685 peripheral models

### Goal

Implement and unit-test the peripherals touched by the pinned MCUXpresso FreeRTOS hello image from reset through stable task execution and UART output.

M1 begins with discovery rather than a fixed assumption that every RT500 or RT600 peripheral model is reusable.

### M1.1 — Firmware dependency census

Pin and build the [MCUXpresso EVK-MIMXRT685 `freertos_hello` board application](https://github.com/nxp-mcuxpresso/mcuxsdk-examples/tree/main/_boards/evkmimxrt685/freertos_examples/freertos_hello) using an official SRAM/debug configuration where available.

Preserve:

- ELF, binary, and linker map;
- complete build log and configuration;
- disassembly from reset through `main`, scheduler start, and the hello task;
- symbols and section layout;
- SDK and toolchain versions; and
- a successful EVK UART transcript at 115200 8-N-1.

Create an MMIO census by combining static analysis of startup/board/clock/UART code with an execution trace from the EVK where practical. For every touched address, record width, access type, call site, expected reset value, and owning IP block.

The census is the scope-control artifact for M1. A peripheral joins M1 only when it is on the boot path or needed to validate correct FreeRTOS execution.

### M1.2 — Expected minimum device set

The initial expectation is:

| Device area | Required behavior for M2 | Notes |
|---|---|---|
| SYSCTL/clock control | Reset values, clock attach/divide, ready/status transitions, peripheral gates | Confirm exact SYSCTL0/1, CLKCTL0/1, ANACTRL, PMC accesses from the pinned SDK |
| Reset control | Peripheral reset assert/deassert and status | Must gate/reset affected device state consistently |
| IOCON | Pin-function, pull, and digital-mode register storage/masks used by board init | Electrical behavior is not needed for UART output |
| Flexcomm selector | Select USART function and expose correct peripheral identity/status | Do not assume a bare UART at the Flexcomm base |
| LPC USART/FIFO | Configuration, baud registers, FIFO/status, polling TX, and required interrupts | Route TX through a QEMU character backend |
| GPIO | Only register state touched by board init | External pin simulation is out of scope unless observed |
| M33 architectural timers | SysTick, PendSV, SVC and NVIC behavior | Primarily existing QEMU functionality; add integration tests rather than a new device |
| Cache/MPU control | Startup-visible enable/invalidate/status behavior if exercised | Prefer existing architectural behavior; model SoC cache control only if accessed |
| ROM/power API surface | Only if the official build calls ROM-resident routines | Prefer an official SDK build configuration that does not require unavailable proprietary ROM; never skip calls with PC hooks |

CTIMER, OS Event Timer, FlexSPI, external flash, DMA, MU, SEMA42, DSP control, USB, audio, and security blocks remain excluded unless the MMIO census proves that this exact firmware needs them.

### M1.3 — Reference matrix

For each new QEMU device, add a short design note containing:

| Field | Required content |
|---|---|
| RT685 source | Manual chapter, header/SVD identifiers, SDK driver files |
| Renode reference | Model/file and verified compatible behaviors |
| SOF QEMU reference | Device/file and reusable QEMU patterns, if any |
| Implemented subset | Registers and behaviors present in M1 |
| Deferred subset | Known omissions and the workload that would require them |
| Differences | Any behavior intentionally not copied from a reference model |

Likely reference candidates include Renode's LPC USART, LPC clock, timer, and RT500 platform models. SOF i.MX8 is most useful for QEMU device organization, logging, reset, and future MU integration; an i.MX8 register match must not be assumed.

### M1.4 — Device implementation order

Implement in boot-path order so each patch advances execution:

1. system/clock/power register blocks;
2. reset controller and device reset wiring;
3. IOCON and minimal GPIO state;
4. Flexcomm function selection;
5. LPC USART with character backend;
6. any remaining device proven necessary by the runtime trace.

Each device should be a separate reviewable patch with its tests. Wire it into the SoC only after the standalone qtest passes.

### M1.5 — Unit-test requirements

Every newly introduced device must have qtests covering, as applicable:

- documented reset values;
- legal 8/16/32-bit accesses and alignment policy;
- read-only, write-only, reserved, W1C, W1S, set/clear/toggle semantics;
- clock enable/disable effects;
- peripheral reset and system reset;
- FIFO empty/full and status transitions;
- IRQ assertion and deassertion;
- QEMU character-backend transmit/receive behavior;
- migration/save-restore state if supported; and
- accesses just outside the implemented register window.

Add negative tests for unsupported modes so omissions fail visibly. A test that merely verifies firmware-expected constants is insufficient; tests must exercise state transitions.

### M1.6 — Integration probe

Run the FreeRTOS ELF after every device patch with:

- guest-error and unimplemented logging enabled;
- instruction and MMIO tracing available on demand;
- a fixed virtual clock configuration; and
- a timeout that reports the last PC, exception state, and recent MMIO operations.

Maintain a blocker ledger:

```text
PC | symbol | address | access | device/register | observed result | required fix | test
```

Close a blocker only after the behavior has a focused qtest.

### M1 deliverables

- All devices in the final MMIO census are modeled or explicitly justified as benign storage.
- Each model has qtests and a design/reference note.
- The firmware reaches `main()` and the FreeRTOS scheduler start without PC hooks.
- There are no unexplained `LOG_UNIMP` or guest-error messages on the tested boot path.
- Existing QEMU ARM tests remain green.

### M1 exit criteria

M1 is complete when the pinned image reaches `vTaskStartScheduler()`, SysTick is running, the first task is eligible to execute, and the debug USART can transmit bytes through a QEMU character backend. Printing the final expected transcript is reserved for M2.

## 6. M2 — Boot MCUXpresso FreeRTOS hello

### Goal

Boot the pinned NXP FreeRTOS hello-world firmware without source patches or address hooks and turn it into a repeatable QEMU functional test.

The target application is the board port at:

<https://github.com/nxp-mcuxpresso/mcuxsdk-examples/tree/main/_boards/evkmimxrt685/freertos_examples/freertos_hello>

MCUXpresso describes `freertos_hello` as an SDK UART demonstration running with FreeRTOS. M2 must prove both the UART path and actual scheduler/exception behavior; printing from pre-scheduler startup code is not sufficient.

### M2.1 — Freeze the firmware contract

- Use the exact source commits and toolchain recorded in section 2.
- Prefer an official SRAM/debug linker configuration loaded with `-kernel <elf>`.
- Do not modify application, SDK driver, startup, FreeRTOS, or linker source solely for QEMU.
- A QEMU-specific build script may select an existing official configuration and package artifacts reproducibly.
- Record the expected UART transcript from the physical EVK rather than guessing it from source.
- Confirm from symbols/trace that the output occurs in the created FreeRTOS task after scheduler start.

If only a flash-linked official configuration exists, decide explicitly between adding the required FlexSPI/XIP model to M1 or adding an official RAM linker configuration upstream in the SDK. Do not relocate sections post-link in an undocumented way.

### M2.2 — QEMU launch contract

Define one canonical non-interactive command, conceptually:

```text
qemu-system-arm \
  -M mimxrt685-evk \
  -kernel <freertos_hello.elf> \
  -nographic \
  -monitor none \
  -serial stdio
```

Document any required `-semihosting`, clock, security-state, or loader options. The final test must not depend on GDB, human input, sleep-based timing, or a patched binary.

### M2.3 — Functional test

Add a QEMU functional test, for example under `tests/functional`, that:

1. launches `mimxrt685-evk` with the pinned ELF;
2. waits for the exact EVK-derived UART banner/task message;
3. verifies the process remains alive long enough for multiple SysTick interrupts or task iterations;
4. fails with useful serial and QEMU logs on timeout;
5. rejects unexpected HardFault, lockup, unimplemented MMIO, or guest-error messages; and
6. shuts QEMU down cleanly.

If the firmware binary cannot be redistributed, keep a local gated test plus a reproducible source-build recipe. Do not silently commit an artifact before reviewing NXP/FreeRTOS redistribution terms.

### M2.4 — Scheduler correctness checks

Use tracepoints or a test-only observable mechanism to verify:

- SVC starts the first task;
- SysTick becomes periodic;
- PendSV performs at least one context-switch path;
- PSP/MSP and exception-return behavior remain valid;
- the idle task does not lock virtual time; and
- UART output originates after scheduler start.

These checks distinguish a genuine FreeRTOS boot from a firmware path that merely prints during initialization.

### M2.5 — Stability and regression

- Run the functional test repeatedly, with a target of at least 20 consecutive passes.
- Run with TCG single-threaded defaults and document any dependency on instruction counting or `-icount`.
- Verify debug and optimized QEMU builds.
- Run the complete relevant `arm-softmmu` qtest/functional subset.
- Check that system reset allows the firmware to boot and print again.

### M2 deliverables

- Reproducible firmware build recipe and source lock file.
- EVK baseline transcript and QEMU transcript.
- Canonical launch command.
- Automated functional boot test.
- Documentation of modeled versus deferred RT685/EVK hardware.
- Updated gaps analysis based on observed, rather than predicted, MMIO and CPU behavior.

### M2 exit criteria

M2 is complete when the unpatched, pinned MCUXpresso FreeRTOS hello application:

1. loads through the documented QEMU command;
2. completes board and clock initialization;
3. starts the FreeRTOS scheduler;
4. executes its hello task;
5. produces the EVK-matching UART output;
6. runs without HardFault, lockup, PC hooks, unexplained MMIO fallbacks, or host-timing races; and
7. passes the automated test repeatedly.

## 7. Patch-series shape

A likely reviewable series is:

```text
01  docs: record MIMXRT685-EVK machine scope
02  hw/arm: add MIMXRT685 SoC skeleton and memory map
03  hw/arm: add MIMXRT685-EVK machine and loader
04  tests/qtest: add MIMXRT685 memory and reset tests
05  hw/misc: add RT6xx system clock/power control subset
06  tests/qtest: add RT6xx clock/power tests
07  hw/misc: add RT6xx reset control
08  tests/qtest: add RT6xx reset tests
09  hw/gpio: add RT6xx IOCON/minimal GPIO behavior
10  tests/qtest: add IOCON/GPIO tests
11  hw/misc: add LPC Flexcomm function selection
12  hw/char: add or extend LPC USART/FIFO model
13  tests/qtest: add Flexcomm USART tests
14  tests/functional: boot MIMXRT685 FreeRTOS hello
15  docs: document firmware build and supported devices
```

The actual series should follow the MMIO census. Do not create empty device models merely to match this provisional list.

## 8. Cross-milestone quality gates

Every milestone must satisfy:

- builds with the project's supported compilers and `--enable-werror`;
- `ninja test` plus relevant qtest and functional-test subsets pass;
- no unrelated regressions in `arm-softmmu`;
- new public QOM properties and machine options are documented;
- no test depends on host wall-clock sleeps;
- reset behavior is covered;
- unknown MMIO is visible during development;
- sources and generated artifacts are pinned and reproducible; and
- each deferred behavior is recorded with the firmware or later milestone that needs it.

## 9. Risks and mitigations

| Risk | Effect | Mitigation |
|---|---|---|
| SDK startup touches many clock/power registers | M1 expands unexpectedly | Build MMIO census first; implement only observed paths plus coherent register semantics |
| SDK calls ROM power APIs | Direct ELF stalls in unavailable ROM | Select an official RAM/debug configuration that uses SDK code, or model documented ROM entry behavior without PC hooks |
| Firmware is linked for FlexSPI | External-flash controller enters M1 | Prefer official SRAM/debug target; otherwise make FlexSPI an explicit scope decision |
| Clock model becomes overly detailed | Delays hello-world boot | Model software-visible selection/gating/status first; defer PLL lock timing and analog fidelity |
| Renode RT500 registers differ from RT685 | Incorrect copied behavior | Require IP-version confirmation and cross-check NXP headers/drivers for every ported behavior |
| UART output appears before scheduler | False M2 success | Verify SVC/SysTick/PendSV and task PC before accepting output |
| Firmware binary licensing blocks CI asset | Functional test cannot be public | Provide reproducible local build and hash-gated test; review redistribution before committing binaries |
| Upstream QEMU changes during development | Rebase churn | Pin M0 base SHA; rebase at milestone boundaries, not continuously |

## 10. Explicitly deferred work

The following starts after M2 unless the firmware census proves it is a hard dependency:

- HiFi4 CPU overlay and instruction semantics;
- second QEMU process and SOF bridge hardening;
- DSP power/start integration beyond register placeholders;
- MU, SEMA42, and RPMsg-Lite;
- DMA0/DMA1;
- I2S, DMIC, I3C, codec, and audio clocks;
- FlexSPI command engine, Octal flash, PSRAM, and XIP boot;
- USB, SD/eMMC, ADC, display, and other EVK devices;
- TrustZone application flows, ROM secure boot, OTFAD, PUF, and OTP; and
- cycle-accurate clocks, caches, contention, or power behavior.

## 11. Completion evidence

At the end of each milestone, publish a short evidence bundle:

| Milestone | Evidence |
|---|---|
| M0 | base SHA, patch list, machine help output, memory-map table, qtest results |
| M1 | firmware MMIO census, device reference matrices, blocker ledger, qtest results, no-unexplained-MMIO boot log |
| M2 | firmware build manifest/hashes, EVK transcript, QEMU transcript, scheduler trace, canonical command, repeated functional-test results |

M2 closes the initial Cortex-M33 platform phase. The next planning checkpoint should use the measured implementation to define the HiFi4 feasibility spike and dual-core M3 milestone.
