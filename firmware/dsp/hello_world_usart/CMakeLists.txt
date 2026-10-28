cmake_minimum_required(VERSION 3.20)

project(hello_world_usart_hifi4 LANGUAGES C ASM)

get_filename_component(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(LEGACY_SDK_DIR "${REPO_ROOT}/legacy-mcux-sdk" CACHE PATH
    "Path to the legacy MCUXpresso SDK")

if(NOT CMAKE_C_COMPILER_ID STREQUAL "GNU")
    message(FATAL_ERROR
        "This target requires Xtensa GCC. Configure with "
        "-DCMAKE_TOOLCHAIN_FILE=${CMAKE_CURRENT_SOURCE_DIR}/toolchain-rt600-gcc.cmake")
endif()

add_executable(hello_world_usart.elf
    main_dsp.c
    board_hifi4.c
    pin_mux.c
    startup_vectors.S
    stubs.c
    ${LEGACY_SDK_DIR}/drivers/common/fsl_common.c
    ${LEGACY_SDK_DIR}/drivers/common/fsl_common_dsp.c
    ${LEGACY_SDK_DIR}/drivers/lpc_gpio/fsl_gpio.c
    ${LEGACY_SDK_DIR}/drivers/flexcomm/fsl_flexcomm.c
    ${LEGACY_SDK_DIR}/drivers/flexcomm/usart/fsl_usart.c
    ${LEGACY_SDK_DIR}/components/uart/fsl_adapter_usart.c
    ${LEGACY_SDK_DIR}/utilities/debug_console_lite/fsl_debug_console.c
    ${LEGACY_SDK_DIR}/utilities/str/fsl_str.c
    ${LEGACY_SDK_DIR}/utilities/assert/fsl_assert.c
    ${LEGACY_SDK_DIR}/devices/MIMXRT685S/drivers/fsl_clock.c
    ${LEGACY_SDK_DIR}/devices/MIMXRT685S/drivers/fsl_reset.c
)

target_include_directories(hello_world_usart.elf PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${LEGACY_SDK_DIR}/devices/MIMXRT685S
    ${LEGACY_SDK_DIR}/devices/MIMXRT685S/drivers
    ${LEGACY_SDK_DIR}/drivers/common
    ${LEGACY_SDK_DIR}/drivers/flexcomm/usart
    ${LEGACY_SDK_DIR}/drivers/flexcomm
    ${LEGACY_SDK_DIR}/drivers/lpc_gpio
    ${LEGACY_SDK_DIR}/drivers/lpc_iopctl
    ${LEGACY_SDK_DIR}/components/uart
    ${LEGACY_SDK_DIR}/utilities/debug_console_lite
    ${LEGACY_SDK_DIR}/utilities/assert
    ${LEGACY_SDK_DIR}/utilities/str
)

target_compile_definitions(hello_world_usart.elf PRIVATE
    CPU_MIMXRT685SFVKB_dsp
    MCUXPRESSO_SDK
    $<$<CONFIG:Debug>:DEBUG>
    $<$<NOT:$<CONFIG:Debug>>:NDEBUG>
)

target_compile_options(hello_world_usart.elf PRIVATE
    -mabi=windowed
    -mtext-section-literals
    -fsigned-char
    -ffunction-sections
    -fdata-sections
    $<$<CONFIG:Debug>:-O0;-g3>
    $<$<NOT:$<CONFIG:Debug>>:-Os>
)

set(RT685_LINKER_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/MIMXRT685S_dsp_gcc.ld")
set(RT685_MAP_FILE "${CMAKE_CURRENT_BINARY_DIR}/hello_world_usart.map")

target_link_options(hello_world_usart.elf PRIVATE
    -mabi=windowed
    -T${RT685_LINKER_SCRIPT}
    -Wl,-Map=${RT685_MAP_FILE}
    -Wl,--gc-sections
    -Wl,--fatal-warnings
)

target_link_libraries(hello_world_usart.elf PRIVATE m)
set_target_properties(hello_world_usart.elf PROPERTIES LINK_DEPENDS "${RT685_LINKER_SCRIPT}")

add_custom_command(TARGET hello_world_usart.elf POST_BUILD
    COMMAND ${CMAKE_READELF} -h -l -S -s $<TARGET_FILE:hello_world_usart.elf>
            > "${CMAKE_CURRENT_BINARY_DIR}/hello_world_usart.elf.txt"
    COMMAND ${CMAKE_OBJDUMP} -drwC $<TARGET_FILE:hello_world_usart.elf>
            > "${CMAKE_CURRENT_BINARY_DIR}/hello_world_usart.dis"
    COMMAND ${CMAKE_NM} -n $<TARGET_FILE:hello_world_usart.elf>
            > "${CMAKE_CURRENT_BINARY_DIR}/hello_world_usart.symbols"
    VERBATIM
)
