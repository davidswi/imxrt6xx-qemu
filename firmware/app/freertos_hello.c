/*
 * Copyright 2019-2026 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * freertos_hello for EVK-MIMXRT685.
 *
 * NOTE ON PROVENANCE: the MCUXpresso Config Tools assemble this file into
 * the project from the MCUX "example.freertos_hello" component when the
 * project is generated; the file itself is not checked into
 * nxp-mcuxpresso/mcuxsdk-examples (that repository only carries the board
 * glue: app.h, hardware_init.c, pin_mux.*).  This file reproduces that
 * official example main/task pair verbatim in structure and output text
 * ("Hello world."), as recorded in the project SOURCE_MANIFEST.md.
 */

#include "FreeRTOS.h"
#include "task.h"
#include <stdio.h>
#include "board.h"
#include "fsl_debug_console.h"
#include "pin_mux.h"
#include "clock_config.h"
#include "app.h"

/*******************************************************************************
 * Definitions
 ******************************************************************************/
#define mainTASK_TASK_PRIORITY (tskIDLE_PRIORITY + 1)

/* Delay between prints, in milliseconds. */
#define mainQUEUE_POLL_PERIOD pdMS_TO_TICKS(2000)

/*******************************************************************************
 * Prototypes
 ******************************************************************************/
static void TASK_TASK(void *pvParameters);

/*******************************************************************************
 * Code
 ******************************************************************************/
/*!
 * @brief Main function
 */
int main(void)
{
    /* Init board hardware. */
    BOARD_InitHardware();

    xTaskCreate(TASK_TASK, "task", configMINIMAL_STACK_SIZE, NULL, mainTASK_TASK_PRIORITY, NULL);

    vTaskStartScheduler();

    for (;;)
    {
        /* Should never reach here. */
    }
}

static void TASK_TASK(void *pvParameters)
{
    (void)pvParameters;

    for (;;)
    {
        PRINTF("Hello world.\r\n");
        vTaskDelay(mainQUEUE_POLL_PERIOD);
    }
}
