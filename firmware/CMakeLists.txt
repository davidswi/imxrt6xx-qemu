# MIMXRT685-EVK FreeRTOS hello — M1/M2 firmware build
#
# Builds the official EVK-MIMXRT685 freertos_hello example sources against
# the NXP MCUXpresso SDK content from the locally installed Keil device
# family / board support packs, for the "RAM" (single security state)
# official linker configuration, using the Arm GNU toolchain.
# The project FreeRTOS configuration selects the port's supported Secure-only
# mode; the Cortex-M33 TrustZone implementation remains enabled in QEMU.
#
# Pin record (see ../SOURCE_MANIFEST.md):
#   DFP:      NXP.MIMXRT685S_DFP.26.09.00
#   BSP:      NXP.EVK-MIMXRT685_BSP.26.09.00
#   examples: nxp-mcuxpresso/mcuxsdk-examples @ 3151bc057b8924db54c7395d39b213c05ab94dc3
#   kernel:   FreeRTOS/FreeRTOS-Kernel @ 0adc196d4bd52a2d91102b525b0aafc1e14a2386
#             (workspace pin "freertos-kernel-upstream", rtos.yml)
#   kernel:   nxp-mcuxpresso/FreeRTOS-Kernel @ b246a5566c9a706b32b04b399b38d8c22896c2e8
#             (workspace pin "freertos-kernel"; IAR asm only, kept for reference)
#   cmsis:    nxp-mcuxpresso/mcu-sdk-cmsis @ dc8b75b360fce9c864a12f1ccc54172e0c733805
#
# Configure/build:
#   cmake -B build -S . -G Ninja \
#       -DCMAKE_TOOLCHAIN_FILE=toolchain-gnu-arm.cmake
#   ninja -C build

cmake_minimum_required(VERSION 3.22)

if(NOT DEFINED MCUX_DFP_ROOT)
    set(MCUX_DFP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../NXP.MIMXRT685S_DFP.26.09.00")
endif()
if(NOT DEFINED MCUX_BSP_ROOT)
    set(MCUX_BSP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../NXP.EVK-MIMXRT685_BSP.26.09.00")
endif()

set(DEV     "${MCUX_DFP_ROOT}/devices/MIMXRT685S")
set(BOARD   "${MCUX_BSP_ROOT}/boards/evkmimxrt685/demo_apps/hello_world")
set(EXAMPLE "${CMAKE_CURRENT_SOURCE_DIR}/example")
set(APP     "${CMAKE_CURRENT_SOURCE_DIR}/app")
set(FREERTOS "${CMAKE_CURRENT_SOURCE_DIR}/vendor/freertos-kernel-upstream")
set(CMSIS    "${CMAKE_CURRENT_SOURCE_DIR}/vendor/mcu-sdk-cmsis/Core/Include")

project(freertos_hello_evkmimxrt685 C ASM)

# Adapted official RAM script (LMA==VMA, no FlexSPI boot-config section);
# see the header comment in the script for the exact deviation rationale.
set(LINKER_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/linker/MIMXRT685Sxxxx_cm33_ram_lda.ld")

add_executable(freertos_hello.elf)

target_sources(freertos_hello.elf PRIVATE
    # ---- application / example (MCUXpresso example + board glue) ----
    "${APP}/freertos_hello.c"
    "${EXAMPLE}/hardware_init.c"
    "${EXAMPLE}/pin_mux.c"
    "${BOARD}/board.c"
    "${BOARD}/clock_config.c"

    # ---- device startup / system ----
    "${DEV}/gcc/startup_MIMXRT685S_cm33.S"
    "${DEV}/system_MIMXRT685S_cm33.c"

    # ---- SDK drivers (devices/MIMXRT685S/drivers) ----
    "${DEV}/drivers/fsl_common.c"
    "${DEV}/drivers/fsl_common_arm.c"
    "${DEV}/drivers/fsl_clock.c"
    "${DEV}/drivers/fsl_power.c"
    "${DEV}/drivers/fsl_reset.c"
    "${DEV}/drivers/fsl_cache.c"
    "${DEV}/drivers/fsl_flexcomm.c"
    "${DEV}/drivers/fsl_usart.c"
    "${DEV}/drivers/fsl_flexspi.c"

    # ---- SDK utilities / debug console ----
    "${DEV}/utilities/str/fsl_str.c"
    "${DEV}/utilities/debug_console/fsl_debug_console.c"
    "${MCUX_DFP_ROOT}/components/serial_manager/fsl_component_serial_manager.c"
    "${MCUX_DFP_ROOT}/components/serial_manager/fsl_component_serial_port_uart.c"
    "${MCUX_DFP_ROOT}/components/uart/fsl_adapter_usart.c"

    # ---- FreeRTOS kernel (upstream pin) ----
    "${FREERTOS}/croutine.c"
    "${FREERTOS}/event_groups.c"
    "${FREERTOS}/list.c"
    "${FREERTOS}/queue.c"
    "${FREERTOS}/stream_buffer.c"
    "${FREERTOS}/tasks.c"
    "${FREERTOS}/timers.c"
    "${FREERTOS}/portable/MemMang/heap_4.c"
    "${FREERTOS}/portable/GCC/ARM_CM33_NTZ/non_secure/port.c"
    "${FREERTOS}/portable/GCC/ARM_CM33_NTZ/non_secure/portasm.c"
)

target_include_directories(freertos_hello.elf PRIVATE
    "${APP}"
    "${EXAMPLE}"
    "${BOARD}"
    "${DEV}"
    "${DEV}/drivers"
    "${DEV}/periph"
    "${DEV}/utilities/debug_console"
    "${DEV}/utilities/debug_console/config"
    "${DEV}/utilities/str"
    "${MCUX_DFP_ROOT}/components/serial_manager"
    "${MCUX_DFP_ROOT}/components/uart"
    "${CMSIS}"
    "${FREERTOS}/include"
    "${FREERTOS}/config"
    "${FREERTOS}/portable/GCC/ARM_CM33_NTZ/non_secure"
)

target_compile_definitions(freertos_hello.elf PRIVATE
    CPU_MIMXRT685SFVKB_cm33
    DEBUG_CONSOLE_TRANSFER_BLOCKING
    SERIAL_PORT_TYPE_UART=1
    SERIAL_MANAGER_NON_BLOCKING_MODE=0
    __STARTUP_CLEAR_BSS
)

target_compile_options(freertos_hello.elf PRIVATE
    -mcpu=cortex-m33
    -mthumb
    -g3
    -Og
    -ffunction-sections
    -fdata-sections
    -Wall
    -Wno-unused-parameter
)

set_property(TARGET freertos_hello.elf APPEND PROPERTY LINK_DEPENDS "${LINKER_SCRIPT}")

target_link_options(freertos_hello.elf PRIVATE
    -mcpu=cortex-m33
    -mthumb
    -T "${LINKER_SCRIPT}"
    --specs=nano.specs
    --specs=nosys.specs
    -Wl,--gc-sections
    -Wl,-Map=$<TARGET_FILE_DIR:freertos_hello.elf>/freertos_hello.map
    -Wl,--print-memory-usage
)

add_custom_command(TARGET freertos_hello.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary
            $<TARGET_FILE:freertos_hello.elf>
            $<TARGET_FILE_DIR:freertos_hello.elf>/freertos_hello.bin
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:freertos_hello.elf>
    COMMENT "Generating freertos_hello.bin and reporting size"
)

# Unmodified SDK I2S interrupt record/playback example, deliberately built
# with the board's supported Flexcomm4 I2C fallback instead of I3C0.  The
# forced-include shim only corrects the generated hardware_init.c clock query;
# all example, board, driver and codec implementation sources remain pinned SDK
# sources.
set(I2S_EXAMPLE
    "${MCUX_BSP_ROOT}/boards/evkmimxrt685/driver_examples/i2s/interrupt_record_playback")
set(COMPONENTS "${MCUX_DFP_ROOT}/components")

add_executable(i2s_interrupt_record_playback.elf)

target_sources(i2s_interrupt_record_playback.elf PRIVATE
    "${I2S_EXAMPLE}/i2s_interrupt_record_playback.c"
    "${I2S_EXAMPLE}/hardware_init.c"
    "${I2S_EXAMPLE}/pin_mux.c"
    "${I2S_EXAMPLE}/board.c"
    "${I2S_EXAMPLE}/clock_config.c"

    "${DEV}/gcc/startup_MIMXRT685S_cm33.S"
    "${DEV}/system_MIMXRT685S_cm33.c"
    "${DEV}/drivers/fsl_common.c"
    "${DEV}/drivers/fsl_common_arm.c"
    "${DEV}/drivers/fsl_clock.c"
    "${DEV}/drivers/fsl_power.c"
    "${DEV}/drivers/fsl_reset.c"
    "${DEV}/drivers/fsl_cache.c"
    "${DEV}/drivers/fsl_flexcomm.c"
    "${DEV}/drivers/fsl_usart.c"
    "${DEV}/drivers/fsl_i2c.c"
    "${DEV}/drivers/fsl_i2s.c"
    "${DEV}/drivers/fsl_i2s_bridge.c"
    "${DEV}/drivers/fsl_gpio.c"
    "${DEV}/drivers/fsl_flexspi.c"

    "${DEV}/utilities/str/fsl_str.c"
    "${DEV}/utilities/debug_console/fsl_debug_console.c"
    "${COMPONENTS}/serial_manager/fsl_component_serial_manager.c"
    "${COMPONENTS}/serial_manager/fsl_component_serial_port_uart.c"
    "${COMPONENTS}/uart/fsl_adapter_usart.c"
    "${COMPONENTS}/i2c/fsl_adapter_flexcomm_i2c.c"
    "${COMPONENTS}/codec/i2c/fsl_codec_i2c.c"
    "${COMPONENTS}/codec/fsl_codec_common.c"
    "${COMPONENTS}/codec/port/wm8904/fsl_codec_wm8904_adapter.c"
    "${COMPONENTS}/codec/wm8904/fsl_wm8904.c"
)

target_include_directories(i2s_interrupt_record_playback.elf PRIVATE
    "${APP}"
    "${I2S_EXAMPLE}"
    "${DEV}"
    "${DEV}/drivers"
    "${DEV}/periph"
    "${DEV}/utilities/debug_console"
    "${DEV}/utilities/debug_console/config"
    "${DEV}/utilities/str"
    "${COMPONENTS}/serial_manager"
    "${COMPONENTS}/uart"
    "${COMPONENTS}/i2c"
    "${COMPONENTS}/codec"
    "${COMPONENTS}/codec/i2c"
    "${COMPONENTS}/codec/port"
    "${COMPONENTS}/codec/port/wm8904"
    "${COMPONENTS}/codec/wm8904"
    "${CMSIS}"
)

target_compile_definitions(i2s_interrupt_record_playback.elf PRIVATE
    CPU_MIMXRT685SFVKB_cm33
    DEBUG_CONSOLE_TRANSFER_BLOCKING
    SERIAL_PORT_TYPE_UART=1
    SERIAL_MANAGER_NON_BLOCKING_MODE=0
    SDK_I2C_BASED_COMPONENT_USED=1
    SDK_I3C_BASED_COMPONENT_USED=0
    BOARD_USE_CODEC=1
    CODEC_WM8904_ENABLE=1
    __STARTUP_CLEAR_BSS
)

target_compile_options(i2s_interrupt_record_playback.elf PRIVATE
    -mcpu=cortex-m33
    -mthumb
    -g3
    -Og
    -ffunction-sections
    -fdata-sections
    -Wall
    -Wno-unused-parameter
)

# These are source-local generated-project adaptations, not global driver
# defines: the version header belongs to the example main and the I2C4 clock
# redirect belongs only to hardware_init.c.
set_source_files_properties(
    "${I2S_EXAMPLE}/i2s_interrupt_record_playback.c"
    PROPERTIES COMPILE_OPTIONS "-include;${I2S_EXAMPLE}/mcuxsdk_version.h")
set_source_files_properties(
    "${I2S_EXAMPLE}/hardware_init.c"
    PROPERTIES COMPILE_OPTIONS "-include;${APP}/i2s_i2c4_override.h")

set_property(TARGET i2s_interrupt_record_playback.elf APPEND PROPERTY
    LINK_DEPENDS "${LINKER_SCRIPT}")
target_link_options(i2s_interrupt_record_playback.elf PRIVATE
    -mcpu=cortex-m33
    -mthumb
    -T "${LINKER_SCRIPT}"
    --specs=nano.specs
    --specs=nosys.specs
    -Wl,--gc-sections
    -Wl,-Map=$<TARGET_FILE_DIR:i2s_interrupt_record_playback.elf>/i2s_interrupt_record_playback.map
    -Wl,--print-memory-usage
)

# Unmodified SDK I2S DMA record/playback example.
# Uses the same board glue, codec config, clock init and linker script as
# the interrupt-driven variant but exercises descriptor-based transfers via
# channels 7 (TX) and 2 (RX).  The forced-include shim only corrects the
# generated hardware_init.c clock query; all example sources remain SDK.
set(DMA_I2S_EXAMPLE
    "${MCUX_BSP_ROOT}/boards/evkmimxrt685/driver_examples/i2s/dma_record_playback")

add_executable(i2s_dma_record_playback.elf)

target_sources(i2s_dma_record_playback.elf PRIVATE
    # ---- example application ----
    "${DMA_I2S_EXAMPLE}/i2s_dma_record_playback.c"
    "${DMA_I2S_EXAMPLE}/hardware_init.c"
    "${DMA_I2S_EXAMPLE}/pin_mux.c"
    "${DMA_I2S_EXAMPLE}/board.c"
    "${DMA_I2S_EXAMPLE}/clock_config.c"

    # ---- device startup / system ----
    "${DEV}/gcc/startup_MIMXRT685S_cm33.S"
    "${DEV}/system_MIMXRT685S_cm33.c"

    # ---- SDK drivers (DMA + I2S variants) ----
    "${DEV}/drivers/fsl_common.c"
    "${DEV}/drivers/fsl_common_arm.c"
    "${DEV}/drivers/fsl_clock.c"
    "${DEV}/drivers/fsl_power.c"
    "${DEV}/drivers/fsl_reset.c"
    "${DEV}/drivers/fsl_cache.c"
    "${DEV}/drivers/fsl_flexcomm.c"
    "${DEV}/drivers/fsl_usart.c"
    "${DEV}/drivers/fsl_i2c.c"
    "${DEV}/drivers/fsl_i2s.c"
    "${DEV}/drivers/fsl_i2s_bridge.c"
    "${DEV}/drivers/fsl_i2s_dma.c"
    "${DEV}/drivers/fsl_dma.c"
    "${DEV}/drivers/fsl_gpio.c"
    "${DEV}/drivers/fsl_flexspi.c"

    # ---- SDK utilities / codec ----
    "${DEV}/utilities/str/fsl_str.c"
    "${DEV}/utilities/debug_console/fsl_debug_console.c"
    "${COMPONENTS}/serial_manager/fsl_component_serial_manager.c"
    "${COMPONENTS}/serial_manager/fsl_component_serial_port_uart.c"
    "${COMPONENTS}/uart/fsl_adapter_usart.c"
    "${COMPONENTS}/i2c/fsl_adapter_flexcomm_i2c.c"
    "${COMPONENTS}/codec/i2c/fsl_codec_i2c.c"
    "${COMPONENTS}/codec/fsl_codec_common.c"
    "${COMPONENTS}/codec/port/wm8904/fsl_codec_wm8904_adapter.c"
    "${COMPONENTS}/codec/wm8904/fsl_wm8904.c"
)

target_include_directories(i2s_dma_record_playback.elf PRIVATE
    "${APP}"
    "${DMA_I2S_EXAMPLE}"
    "${DEV}"
    "${DEV}/drivers"
    "${DEV}/periph"
    "${DEV}/utilities/debug_console"
    "${DEV}/utilities/debug_console/config"
    "${DEV}/utilities/str"
    "${COMPONENTS}/serial_manager"
    "${COMPONENTS}/uart"
    "${COMPONENTS}/i2c"
    "${COMPONENTS}/codec"
    "${COMPONENTS}/codec/i2c"
    "${COMPONENTS}/codec/port"
    "${COMPONENTS}/codec/port/wm8904"
    "${COMPONENTS}/codec/wm8904"
    "${CMSIS}"
)

target_compile_definitions(i2s_dma_record_playback.elf PRIVATE
    CPU_MIMXRT685SFVKB_cm33
    DEBUG_CONSOLE_TRANSFER_BLOCKING
    SERIAL_PORT_TYPE_UART=1
    SERIAL_MANAGER_NON_BLOCKING_MODE=0
    SDK_I2C_BASED_COMPONENT_USED=1
    SDK_I3C_BASED_COMPONENT_USED=0
    BOARD_USE_CODEC=1
    CODEC_WM8904_ENABLE=1
    __STARTUP_CLEAR_BSS
)

target_compile_options(i2s_dma_record_playback.elf PRIVATE
    -mcpu=cortex-m33
    -mthumb
    -g3
    -Og
    -ffunction-sections
    -fdata-sections
    -Wall
    -Wno-unused-parameter
)

set_source_files_properties(
    "${DMA_I2S_EXAMPLE}/i2s_dma_record_playback.c"
    PROPERTIES COMPILE_OPTIONS "-include;${DMA_I2S_EXAMPLE}/mcuxsdk_version.h")
set_source_files_properties(
    "${DMA_I2S_EXAMPLE}/hardware_init.c"
    PROPERTIES COMPILE_OPTIONS "-include;${APP}/i2s_i2c4_override.h")

set_property(TARGET i2s_dma_record_playback.elf APPEND PROPERTY
    LINK_DEPENDS "${LINKER_SCRIPT}")
target_link_options(i2s_dma_record_playback.elf PRIVATE
    -mcpu=cortex-m33
    -mthumb
    -T "${LINKER_SCRIPT}"
    --specs=nano.specs
    --specs=nosys.specs
    -Wl,--gc-sections
    -Wl,-Map=$<TARGET_FILE_DIR:i2s_dma_record_playback.elf>/i2s_dma_record_playback.map
    -Wl,--print-memory-usage
)

add_custom_command(TARGET i2s_dma_record_playback.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary
            $<TARGET_FILE:i2s_dma_record_playback.elf>
            $<TARGET_FILE_DIR:i2s_dma_record_playback.elf>/i2s_dma_record_playback.bin
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:i2s_dma_record_playback.elf>
    COMMENT "Generating i2s_dma_record_playback.bin and reporting size"
)
