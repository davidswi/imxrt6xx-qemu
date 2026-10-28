/* Default XEA2 exception vectors for the RT685 direct-load image. */

    .macro DEFAULT_VECTOR section, symbol
    .section \section, "ax", @progbits
    .align 4
    .global \symbol
    .type \symbol, @function
\symbol:
    j rt685_default_exception
    .size \symbol, . - \symbol
    .endm

    DEFAULT_VECTOR .Level2InterruptVector.text, Level2InterruptVector
    DEFAULT_VECTOR .Level3InterruptVector.text, Level3InterruptVector
    DEFAULT_VECTOR .DebugExceptionVector.text, DebugExceptionVector
    DEFAULT_VECTOR .NMIExceptionVector.text, NMIExceptionVector
    DEFAULT_VECTOR .KernelExceptionVector.text, KernelExceptionVector
    DEFAULT_VECTOR .UserExceptionVector.text, UserExceptionVector
    DEFAULT_VECTOR .DoubleExceptionVector.text, DoubleExceptionVector

    .section .iram0.text, "ax", @progbits
    .align 4
    .global rt685_default_exception
    .type rt685_default_exception, @function
rt685_default_exception:
1:
    j 1b
    .size rt685_default_exception, . - rt685_default_exception
