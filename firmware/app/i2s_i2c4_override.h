/*
 * Build-time adaptation for the RT685 I2S example under QEMU.
 *
 * The BSP supports Flexcomm4 I2C when the I3C component is disabled, but its
 * generated hardware_init.c still assigns the I3C functional clock to the
 * codec configuration unconditionally.  Include the SDK clock declarations
 * first, then redirect that one generated call to the actual I2C4 source.
 */
#ifndef I2S_I2C4_OVERRIDE_H
#define I2S_I2C4_OVERRIDE_H

#include "fsl_clock.h"

#define CLOCK_GetI3cClkFreq() CLOCK_GetFlexCommClkFreq(4U)

#endif
