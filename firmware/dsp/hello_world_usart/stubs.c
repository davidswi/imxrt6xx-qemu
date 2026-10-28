/* Minimal bare-metal support required by the Zephyr RT600 Picolibc runtime. */

#include <stdint.h>
#include <stdio.h>

static int stderr_put(char c, FILE *stream)
{
    (void)c;
    (void)stream;
    return 0;
}

static FILE stderr_stream =
    FDEV_SETUP_STREAM(stderr_put, NULL, NULL, _FDEV_SETUP_WRITE);

FILE *const __attribute__((weak)) stderr = &stderr_stream;

/* Called by abort and exit paths; bare-metal firmware has nowhere to return. */
void _exit(int status)
{
    (void)status;
    for (;;)
    {
        __asm__ volatile("waiti 0");
    }
}

/* Satisfy the Zephyr-configured Picolibc errno hook without an RTOS thread. */
int *z_errno_wrap(void)
{
    static int bare_metal_errno;
    return &bare_metal_errno;
}

/* fsl_common_dsp.c uses this HAL entry point for cycle-accurate delays. */
uint32_t xthal_get_ccount(void)
{
    uint32_t count;
    __asm__ volatile("rsr.ccount %0" : "=a"(count));
    return count;
}
