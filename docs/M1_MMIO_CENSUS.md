# M1 provisional MMIO census

This census records the M1 implementation scope available from the local
`MIMXRT685S_cm33.xml` and the public MCUXpresso example sources inspected on
2026-10-23. It is provisional: this checkout has no pinned SDK build, ELF,
linker map, disassembly, hardware trace, or supported Arm embedded toolchain.
Those inputs are required before this can be called the final firmware-derived
census.

| Address/range | Width | Access | Owner and register path | Reset/expected behavior | Static call path or reason |
|---|---:|---|---|---|---|
| `0x40001000-0x40001fff` | 32 | R/W | CLKCTL0 | SVD reset values; SET/CLR aliases; M33 root-clock mux/divide | `BOARD_BootClockRUN()` and SDK clock driver |
| `0x40002000-0x40002fff` | 32 | R/W | SYSCTL0 | SVD reset values/masks; FFRO enable feeds CLKCTL0 | `BOARD_BootClockRUN()` and SDK clock driver |
| `0x40021010`, `0x40021040`, `0x40021070` | 32 | R/W, W1S, W1C | CLKCTL1 `PSCCTL0` and aliases | Bits 8-15 gate Flexcomm 0-7 | `BOARD_InitDebugConsole()` selects the Flexcomm 0 clock |
| `0x40021014`, `0x40021044`, `0x40021074` | 32 | R/W, W1S, W1C | CLKCTL1 `PSCCTL1` and aliases | Bits 0-7 gate GPIO ports 0-7 | SDK pin/GPIO initialization when used |
| `0x40000000-0x4000007f` | 32 | R/W | RSTCTL0 | SVD reset values/masks and SET/CLR aliases | SDK reset driver/startup support |
| `0x40020010`, `0x40020040`, `0x40020070` | 32 | R/W, W1S, W1C | RSTCTL1 `PRSTCTL0` and aliases | Bits 8-15 reset Flexcomm 0-7 | Flexcomm initialization/reset path |
| `0x40020014`, `0x40020044`, `0x40020074` | 32 | R/W, W1S, W1C | RSTCTL1 `PRSTCTL1` and aliases | Bits 0-7 reset GPIO ports 0-7 | SDK pin/GPIO initialization when used |
| `0x40004000-0x40004407` | 32 | R/W | IOPCTL pin registers | SVD reset values, writable bits 0-11 | `BOARD_InitPins()`; exact touched pins await pinned build/disassembly |
| `0x40100000-0x4010279f` | 8/32 | R/W | GPIO ports 0-7 | Pin aliases, direction/mask/output and A/B interrupt state | Board initialization if the selected configuration uses GPIO |
| `0x40106ff8` | 32 | R/W | FLEXCOMM0 `PSELID` | `0x00101000`; select USART with `PERSEL=1`, optional lock | `BOARD_InitDebugConsole()` uses Flexcomm 0 |
| `0x40106000-0x4010602f` | 32 | R/W | USART0 configuration/status/baud | SVD reset values and writable masks | SDK debug-console USART initialization |
| `0x40106e00-0x40106e48` | 32 | R/W | USART0 FIFO | Reset empty/not-full; polling TX/RX and RX-level IRQ | SDK debug-console transfer path |
| `0xe000e010-0xe000e01f` | 32 | R/W | Architectural SysTick | Existing Armv7M model | FreeRTOS tick setup after `vTaskStartScheduler()` |
| `0xe000e100-0xe000efff` | 32 | R/W | NVIC/system-control space | Existing Armv7M model | Flexcomm IRQ 14; GPIO IRQs 2/3 when used; PendSV/SVC scheduler path |

The remaining Flexcomm instances are modeled at their SVD addresses because
they share one SoC IP integration and clock/reset wiring. The official example
uses Flexcomm 0 for its debug console. ANACTRL, PMC, cache-control, and ROM-call
requirements remain unresolved until an exact SDK revision and firmware image
are supplied and traced.
