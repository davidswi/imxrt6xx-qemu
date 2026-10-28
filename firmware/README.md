# MIMXRT685 FreeRTOS M2 firmware

This directory builds the pinned MCUXpresso `freertos_hello` sources for the
MIMXRT685-EVK RAM configuration used by the local QEMU machine.

The Cortex-M33 keeps its Armv8-M Security Extension and resets in Secure
state.  FreeRTOS is configured for its supported Secure-only mode:

```text
configENABLE_TRUSTZONE=0
configRUN_FREERTOS_SECURE_ONLY=1
```

The first setting disables FreeRTOS Secure-context calls; it does not remove
TrustZone from the processor model.  The second setting makes the task and
exception-return state agree with the Secure reset state.

Build with the pinned Arm GNU toolchain:

```sh
cmake -S firmware -B firmware/build -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE=toolchain-gnu-arm.cmake
cmake --build firmware/build
```

Run from the project root:

```sh
qemu/build/qemu-system-arm \
    -M mimxrt685-evk \
    -kernel firmware/build/freertos_hello.elf \
    -nographic -monitor none
```

The expected serial output is `Hello world.` every two seconds after the
FreeRTOS scheduler starts.

The firmware binary is not committed to QEMU.  Run the local gated functional
test by exporting its path:

```sh
MIMXRT685_FREERTOS_ELF="$PWD/firmware/build/freertos_hello.elf" \
    qemu/build/run meson test -C qemu/build --setup thorough \
    qemu:func-arm-mimxrt685 --print-errorlogs
```
