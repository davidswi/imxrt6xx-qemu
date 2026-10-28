# MIMXRT685 QEMU M2 evidence

**Validation date:** 2026-10-24  
**Scope:** local experimental QEMU model; not an upstream contribution

## Result

The pinned MIMXRT685 FreeRTOS hello application builds and boots on the local
`mimxrt685-evk` machine.  It starts the scheduler, runs the hello task, prints
`Hello world.` every two seconds, survives a QMP system reset, and resumes the
same behavior.

The Cortex-M33 Security Extension remains enabled.  FreeRTOS runs in its
supported Secure-only configuration, avoiding the deferred RT685 Secure boot
handoff and SAU/IDAU model.

## Reproduction

```sh
cmake -S firmware -B firmware/build -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE=toolchain-gnu-arm.cmake
cmake --build firmware/build

qemu/build/qemu-system-arm \
    -M mimxrt685-evk \
    -kernel firmware/build/freertos_hello.elf \
    -nographic -monitor none
```

Local functional test:

```sh
MIMXRT685_FREERTOS_ELF="$PWD/firmware/build/freertos_hello.elf" \
    qemu/build/run meson test -C qemu/build --setup thorough \
    qemu:func-arm-mimxrt685 --print-errorlogs
```

The test is gated by `MIMXRT685_FREERTOS_ELF` because no firmware binary is
committed to QEMU.

## Automated checks

The functional test verifies:

- two task messages before reset and two after reset;
- scheduler-start SVC (exception 11);
- PendSV context switching (exception 14);
- periodic SysTick (exception 15);
- Secure `EXC_RETURN=0xfffffffd`; and
- no failed exception return, HardFault, UsageFault, lockup, unimplemented
  MMIO, unassigned access, or guest-error message in the trace.

The complete boot/reset test passed 20 consecutive runs using TCG defaults,
without `-icount`, GDB, user input, address hooks, or host sleeps.

The functional test also passed in both the `-Werror` debug build and a
separate `-Werror`, `-O2` ARM-only build.  The focused MIMXRT685 qtest suite
passed all 10 subtests and remains the device-level regression gate.

## Artifact hashes

Fresh build in the canonical `firmware/build` directory with Arm GNU
Toolchain 15.3.Rel2:

```text
65ee5fb5a7575d6f1b3ffa69860d85aacf8088ee5335b6770282844f716df215  freertos_hello.elf
0dfa5a66e89943a3c37ba84d8965b634278fb1c798b41c4b9e862dfca4cc4698  freertos_hello.map
1e04879fcb224cb1eb6ece5a3aad0f325ab72b2b6fcc359e4325e5d4ec2de28d  freertos_hello.bin
```

The ELF debug information and map file embed the build directory, so their
hashes assume the recorded project layout.  The stripped binary hash is
independent of the build path.

## Remaining external evidence

A physical-EVK UART transcript was not present in the workspace.  The exact
message and period currently come from the pinned application source, so the
plan's hardware-transcript comparison remains an external validation item.

The RAM linker script is a documented direct-load adaptation of NXP's
official RAM layout: load addresses equal execution addresses and the
FlexSPI boot-config section is omitted.  Application, SDK driver, startup, and
FreeRTOS source files are otherwise used without QEMU-specific code hooks.
