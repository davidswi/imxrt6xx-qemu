# Arm GNU Toolchain (arm-none-eabi-gcc) cross toolchain for MIMXRT685S.
#
# Validated with: Arm GNU Toolchain 15.3.Rel2 (Build arm-15.181),
# arm-none-eabi-gcc 15.3.1.  Prefix may be overridden with
# -DTOOLCHAIN_PREFIX=<path>/arm-none-eabi- if the toolchain is not on PATH.

set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR cortex-m33)

if(NOT TOOLCHAIN_PREFIX)
    set(TOOLCHAIN_PREFIX arm-none-eabi-)
endif()

set(CMAKE_C_COMPILER   ${TOOLCHAIN_PREFIX}gcc)
set(CMAKE_CXX_COMPILER ${TOOLCHAIN_PREFIX}g++)
set(CMAKE_ASM_COMPILER ${TOOLCHAIN_PREFIX}gcc)
set(CMAKE_OBJCOPY      ${TOOLCHAIN_PREFIX}objcopy)
set(CMAKE_SIZE         ${TOOLCHAIN_PREFIX}size)

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

find_program(CMAKE_GDB ${TOOLCHAIN_PREFIX}gdb)
