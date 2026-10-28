/*
 * FreeRTOSConfig.h for EVK-MIMXRT685 freertos_hello (MIMXRT685S Cortex-M33)
 *
 * Modeled on the MCUXpresso SDK freertos_hello board configuration for
 * EVK-MIMXRT685 with the "middleware.freertos-kernel.cm33_non_trustzone"
 * component selected (see the example's prj.conf).  Single security state,
 * no MPU usage, no TrustZone context save, soft-float compilation.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

#include <stdint.h>

extern uint32_t SystemCoreClock;

/*-----------------------------------------------------------
 * Application specific definitions.
 *----------------------------------------------------------*/

/* Scheduler behaviour. */
#define configUSE_PREEMPTION                     1
#define configSUPPORT_DYNAMIC_ALLOCATION         1
#define configSUPPORT_STATIC_ALLOCATION          0
#define configUSE_IDLE_HOOK                      0
#define configUSE_TICK_HOOK                      0
#define configCPU_CLOCK_HZ                       (SystemCoreClock)
#define configTICK_RATE_HZ                       ((TickType_t) 1000)
#define configMAX_PRIORITIES                     (5)
#define configMINIMAL_STACK_SIZE                 ((uint16_t) 128)
#define configTOTAL_HEAP_SIZE                    ((size_t) (32 * 1024))
#define configMAX_TASK_NAME_LEN                  (16)
#define configUSE_16_BIT_TICKS                   0
#define configUSE_MUTEXES                        1
#define configQUEUE_REGISTRY_SIZE                8
#define configUSE_PORT_OPTIMISED_TASK_SELECTION  1

/* Co-routine definitions. */
#define configUSE_CO_ROUTINES                    0
#define configMAX_CO_ROUTINE_PRIORITIES          (2)

/* Software timers (used by the SDK debug console synchronization). */
#define configUSE_TIMERS                         1
#define configTIMER_TASK_PRIORITY                (configMAX_PRIORITIES - 1)
#define configTIMER_QUEUE_LENGTH                 5
#define configTIMER_TASK_STACK_DEPTH             configMINIMAL_STACK_SIZE

/* Cortex-M33 (RT685S): 3 implemented NVIC priority bits. */
#define configPRIO_BITS                          3
#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY          0x07U
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY     0x05U

#define configKERNEL_INTERRUPT_PRIORITY \
    (configLIBRARY_LOWEST_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))
#define configMAX_SYSCALL_INTERRUPT_PRIORITY \
    (configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))

/* Mandatory for the GCC ARM_CM33_NTZ portable layer. */
#define configENABLE_FPU                         0
#define configENABLE_MPU                         0
#define configENABLE_TRUSTZONE                   0
#define configRUN_FREERTOS_SECURE_ONLY           1

/* Assertions: spin with interrupts disabled (visible in QEMU traces). */
#define configASSERT(x)                                       \
    if ((x) == 0)                                             \
    {                                                         \
        taskDISABLE_INTERRUPTS();                             \
        for (;;)                                              \
        {                                                     \
        }                                                     \
    }

/* Standard mappings used by the FreeRTOS code. */
#define INCLUDE_vTaskPrioritySet             1
#define INCLUDE_uxTaskPriorityGet            1
#define INCLUDE_vTaskDelete                  1
#define INCLUDE_vTaskCleanUpResources        0
#define INCLUDE_vTaskSuspend                 1
#define INCLUDE_vTaskDelay                   1
#define INCLUDE_xTaskDelayUntil              1
#define INCLUDE_xTaskGetSchedulerState       1

#endif /* FREERTOS_CONFIG_H */
