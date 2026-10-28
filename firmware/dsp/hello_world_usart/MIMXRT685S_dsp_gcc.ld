/* GNU layout adapted from the MCUXpresso MIMXRT685S min-rt memory map. */

ENTRY(_start)

MEMORY
{
    DSP_CORE     (rwx) : ORIGIN = 0x00200000, LENGTH = 0x00280000
    DSP_UNCACHED (rwx) : ORIGIN = 0x20060000, LENGTH = 0x00010000
    DSP_DRAM      (rw) : ORIGIN = 0x24000000, LENGTH = 0x00010000
    DSP_RESET     (rx) : ORIGIN = 0x24020000, LENGTH = 0x00000400
    DSP_VECTORS   (rx) : ORIGIN = 0x24020400, LENGTH = 0x0000fc00
}

PHDRS
{
    core    PT_LOAD FLAGS(5);
    dram    PT_LOAD FLAGS(6);
    reset   PT_LOAD FLAGS(5);
    vectors PT_LOAD FLAGS(5);
}

SECTIONS
{
    /* Reset-handler L32R operands must precede the reset code. */
    .reset.literal : ALIGN(4)
    {
        KEEP(*(.reset.literal))
    } > DSP_DRAM :dram

    .data : ALIGN(8)
    {
        __data_start = .;
        *(.data .data.*)
        *(.sdata .sdata.* .sdata2 .sdata2.*)
        *(.got .got.* .got.plt)
        __data_end = .;
    } > DSP_DRAM :dram
    __data_source = LOADADDR(.data);
    __data_size = __data_end - __data_start;
    __data_source_size = __data_size;

    .tdata : ALIGN(8)
    {
        __tdata_start = .;
        *(.tdata .tdata.*)
        __tdata_end = .;
    } > DSP_DRAM :dram

    .bss (NOLOAD) : ALIGN(8)
    {
        __bss_start = .;
        *(.dynsbss .sbss .sbss.* .scommon)
        *(.dynbss .bss .bss.* COMMON)
        __bss_end = .;
    } > DSP_DRAM :dram
    __bss_size = __bss_end - __bss_start;

    .tbss (NOLOAD) : ALIGN(8)
    {
        *(.tbss .tbss.* .tcommon)
    } > DSP_DRAM :dram

    __heap_start = ALIGN(8);
    __stack = ORIGIN(DSP_DRAM) + LENGTH(DSP_DRAM);
    __stack_size = 0x2000;
    __heap_end = __stack - __stack_size;
    ASSERT(__heap_start <= __heap_end, "DSP DRAM overflow: data/heap overlaps stack")

    .reset.entry ORIGIN(DSP_RESET) : ALIGN(4)
    {
        KEEP(*(.reset.entry))
    } > DSP_RESET :reset

    .reset.text : ALIGN(4)
    {
        KEEP(*(.reset.text))
    } > DSP_RESET :reset
    ASSERT(SIZEOF(.reset.entry) + SIZEOF(.reset.text) <= LENGTH(DSP_RESET),
           "reset handler exceeds RT685 reset-vector region")

    .window_vectors ORIGIN(DSP_VECTORS) : ALIGN(4)
    {
        KEEP(*(.vectors))
    } > DSP_VECTORS :vectors
    ASSERT(ADDR(.window_vectors) == 0x24020400,
           "window vectors must begin at reset VECBASE")
    ASSERT(SIZEOF(.window_vectors) <= 0x17c,
           "window vectors overlap the level-2 vector")

    .level2_vector 0x2402057c : { KEEP(*(.Level2InterruptVector.text)) } > DSP_VECTORS :vectors
    .level3_vector 0x2402059c : { KEEP(*(.Level3InterruptVector.text)) } > DSP_VECTORS :vectors
    .debug_vector  0x240205bc : { KEEP(*(.DebugExceptionVector.text)) } > DSP_VECTORS :vectors
    .nmi_vector    0x240205dc : { KEEP(*(.NMIExceptionVector.text)) } > DSP_VECTORS :vectors
    .kernel_vector 0x240205fc : { KEEP(*(.KernelExceptionVector.text)) } > DSP_VECTORS :vectors
    .user_vector   0x2402061c : { KEEP(*(.UserExceptionVector.text)) } > DSP_VECTORS :vectors
    .double_vector 0x2402063c : { KEEP(*(.DoubleExceptionVector.text)) } > DSP_VECTORS :vectors

    .iram0.text : ALIGN(4)
    {
        *(.iram0.literal .iram.literal .iram.text.literal)
        *(.iram0.text .iram.text)
    } > DSP_VECTORS :vectors

    NonCacheable.init : ALIGN(8)
    {
        NonCacheable_init_start = .;
        *(NonCacheable.init)
        NonCacheable_init_end = .;
    } > DSP_UNCACHED :NONE

    NonCacheable (NOLOAD) : ALIGN(8)
    {
        NonCacheable_start = .;
        *(NonCacheable)
        NonCacheable_end = .;
    } > DSP_UNCACHED :NONE
    ASSERT(SIZEOF(NonCacheable.init) + SIZEOF(NonCacheable) == 0,
           "non-cacheable data needs an explicit PT_LOAD policy")

    .text : ALIGN(16)
    {
        _text_start = .;
        *(.literal.unlikely .text.unlikely .literal.unlikely.* .text.unlikely.*)
        *(.literal.startup .text.startup .literal.startup.* .text.startup.*)
        *(.entry.text)
        KEEP(*(.init .init.*))
        *(.literal .text .literal.* .text.* .stub)
        KEEP(*(.fini .fini.*))
        _text_end = .;
    } > DSP_CORE :core

    .rodata : ALIGN(8)
    {
        _rodata_start = .;
        *(.rodata .rodata.* .srodata .srodata.*)
        *(.gnu.linkonce.r.*)
        *(.eh_frame_hdr)
        KEEP(*(.eh_frame))
        *(.gcc_except_table .gcc_except_table.*)
        *(.xt_except_table .xt_except_table.*)
        *(.xt_except_desc .xt_except_desc.* .xt_except_desc_end)

        . = ALIGN(8);
        PROVIDE_HIDDEN(__preinit_array_start = .);
        KEEP(*(.preinit_array))
        PROVIDE_HIDDEN(__preinit_array_end = .);
        PROVIDE_HIDDEN(__init_array_start = .);
        KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))
        KEEP(*(.init_array))
        PROVIDE_HIDDEN(__init_array_end = .);
        PROVIDE_HIDDEN(__fini_array_start = .);
        KEEP(*(SORT_BY_INIT_PRIORITY(.fini_array.*)))
        KEEP(*(.fini_array))
        PROVIDE_HIDDEN(__fini_array_end = .);
        _rodata_end = .;
    } > DSP_CORE :core

    . = ALIGN(8);
    _end = .;
    PROVIDE(end = .);

    .xtensa.info 0 : { KEEP(*(.xtensa.info)) }
    .xt.lit 0 : { KEEP(*(.xt.lit .xt.lit.* .gnu.linkonce.p.*)) }
    .xt.prop 0 : { KEEP(*(.xt.prop .xt.prop.* .gnu.linkonce.prop.*)) }
    .xt.insn 0 : { KEEP(*(.xt.insn .gnu.linkonce.x.*)) }

    .debug 0 : { *(.debug) }
    .debug_info 0 : { *(.debug_info .gnu.linkonce.wi.*) }
    .debug_abbrev 0 : { *(.debug_abbrev) }
    .debug_aranges 0 : { *(.debug_aranges) }
    .debug_line 0 : { *(.debug_line .debug_line.*) }
    .debug_line_str 0 : { *(.debug_line_str) }
    .debug_frame 0 : { *(.debug_frame) }
    .debug_str 0 : { *(.debug_str) }
    .debug_loc 0 : { *(.debug_loc .debug_loclists) }
    .debug_ranges 0 : { *(.debug_ranges .debug_rnglists) }
    .debug_addr 0 : { *(.debug_addr) }
    .debug_macro 0 : { *(.debug_macro .debug_macinfo) }
    .debug_pubnames 0 : { *(.debug_pubnames) }
    .debug_pubtypes 0 : { *(.debug_pubtypes) }
    .comment 0 : { *(.comment) }

    /DISCARD/ :
    {
        *(.note.GNU-stack)
        *(.gnu_debuglink)
        *(.gnu.lto_*)
    }
}

ASSERT(_start == 0x24020000, "RT685 DSP reset entry is not at 0x24020000")
