# MIMXRT685 QEMU source manifest

## M0 baseline

- QEMU remote: `https://github.com/qemu/qemu.git`
- QEMU base commit: `b6c4b7e86dec12d07f5cac65265b986d38ee9002`
- Topic branch: `topic/imxrt685-m0-machine`
- Patch-series revision: local working tree, revision 1
- Build configuration: `arm-softmmu`, debug enabled, TCG debug enabled,
  warnings treated as errors
- CMSIS-SVD: `MIMXRT685S_cm33.xml`, device version 1.0, schema 1.3,
  copyright 2016-2026 NXP, supplied as the project-local downloaded input
- CMSIS-SVD SHA-256:
  `751c25d4fcf4986825ff8e3a1d399b43012ccd9fb6035d9e3529ced68d9bff1b`
- Register extraction: Python 3.12.14 with `cmsis-svd` 0.6; local tools
  `tools/svd-dump.py` and `tools/gen-reg-table.py`

## Deferred inputs

The MCUXpresso manifest, `mcuxsdk-examples` revision, Arm GNU toolchain,
reference-manual revision, EVK board revision, Renode/SOF reference revisions,
and firmware ELF/map hashes are M1/M2 inputs. They are not used by M0 and have
not yet been pinned.

## M1 peripheral-model baseline

- Topic branch: ``topic/imxrt685-m1-peripherals``
- Register authority: the same project-local CMSIS-SVD and extraction tools
  recorded above
- SDK source inspected: NXP ``mcuxsdk-examples`` main-branch
  ``freertos_examples/freertos_hello/freertos_hello.c`` and EVK-MIMXRT685
  ``board.c``/``clock_config.c`` as available on 2026-10-23
- Static finding: the EVK debug-console initialization selects Flexcomm 0;
  the generic FreeRTOS example creates a task, starts the scheduler and prints
  ``Hello world.`` from that task
- Firmware artifacts: no MCUXpresso SDK checkout, pinned commit, supported Arm
  embedded toolchain, ELF, map, build log, EVK trace, or UART transcript is
  present locally.  Consequently the firmware-derived MMIO census and M1
  integration exit criterion remain pending those inputs.

M1 device behavior is therefore scoped to the SVD-backed RSTCTL, IOPCTL, GPIO,
Flexcomm selector and USART/FIFO path, with qtests as the executable evidence.

## M2 FreeRTOS hello baseline

- QEMU topic head used for validation:
  `536f2768d7ba9e5e0fa48ff6f4580934fd4d9f9e`
- Firmware build recipe: `firmware/CMakeLists.txt`, using the project RAM
  linker configuration and `firmware/toolchain-gnu-arm.cmake`
- Arm GNU Toolchain: 15.3.Rel2, GCC 15.3.1, build `arm-15.181`
- `mcuxsdk-examples` source pin:
  `3151bc057b8924db54c7395d39b213c05ab94dc3`
- FreeRTOS/FreeRTOS-Kernel pin:
  `0adc196d4bd52a2d91102b525b0aafc1e14a2386`
- NXP FreeRTOS-Kernel reference pin:
  `b246a5566c9a706b32b04b399b38d8c22896c2e8`
- NXP MCU SDK CMSIS pin:
  `dc8b75b360fce9c864a12f1ccc54172e0c733805`
- Device and board packs: `NXP.MIMXRT685S_DFP.26.09.00` and
  `NXP.EVK-MIMXRT685_BSP.26.09.00`
- Reference manual identified by the pinned linker script:
  MIMXRT685 User Manual, revision 1.8, 21 November 2024
- Firmware security configuration: Cortex-M33 Security Extension retained;
  FreeRTOS `configENABLE_TRUSTZONE=0` and
  `configRUN_FREERTOS_SECURE_ONLY=1`
- Fresh-build SHA-256 values from the canonical `firmware/build` directory:
  - ELF: `65ee5fb5a7575d6f1b3ffa69860d85aacf8088ee5335b6770282844f716df215`
  - map: `0dfa5a66e89943a3c37ba84d8965b634278fb1c798b41c4b9e862dfca4cc4698`
  - binary: `1e04879fcb224cb1eb6ece5a3aad0f325ab72b2b6fcc359e4325e5d4ec2de28d`

The ELF debug information and map file embed the build directory, so their
hashes assume the recorded project layout.  The stripped binary hash is
independent of the build path.

The QEMU transcript contains two-second periodic `Hello world.` messages from
the FreeRTOS task.  The interrupt trace shows scheduler-start SVC, PendSV,
periodic SysTick, and successful Secure exception returns using
`EXC_RETURN=0xfffffffd`.  A physical-EVK UART transcript was not available in
this workspace, so hardware transcript matching remains external evidence;
the expected text and period are taken from the pinned application source.
