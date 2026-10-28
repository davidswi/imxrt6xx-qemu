# Root Cause Analysis: No Audio Output from i2s_interrupt_record_playback

**Date:** 2026-10-27  
**Board:** mimxrt685-evk  
**Firmware:** `i2s_interrupt_record_playback.elf` (NXP SDK interrupt-driven example)  
**QEMU command:**
```bash
qemu/build/qemu-system-arm -M mimxrt685-evk \
  -kernel firmware/build/i2s_interrupt_record_playback.elf \
  -nographic \
  -audiodev coreaudio,id=rt685
```

---

## Executive Summary

**Root cause:** The QEMU Flexcomm I2S TX model does not implement **interrupt-driven FIFO filling**. When the SDK's interrupt handler (`I2S_TxHandleIRQ()`) runs, it writes audio samples from guest memory into the FIFOWR register (offset 0xe20). However, either:

1. The NVIC is not delivering I2S interrupts to the CPU, or  
2. The QEMU event loop timing prevents timely interrupt processing relative to audio-link ticks

The result is that the TX FIFO remains empty (or contains only zeros), and the `rt685_audio_link_tick()` callback receives zero samples for playback through CoreAudio.

---

## 1. Firmware Behavior Analysis

### What `i2s_interrupt_record_playback.c` Does

```c
int main(void) {
    // Initialize codec (WM8904 over I2C on Flexcomm4)
    CODEC_Init(&codecHandle, &boardCodecConfig);
    
    // Configure and initialize I2S TX/RX
    I2S_TxInit(DEMO_I2S_TX, &s_TxConfig);   // Flexcomm3 TX
    I2S_RxInit(DEMO_I2S_RX, &s_RxConfig);   // Flexcomm1 RX
    
    StartDigitalLoopback();  // Sets up callbacks and starts transfers
    
    while (1) { /* spin */ }
}

static void TxCallback(I2S_Type *base, i2s_handle_t *handle, ...) {
    I2S_TxTransferNonBlocking(base, handle, *transfer);  // Re-queue buffer
}
```

### SDK Driver Flow (`fsl_i2s.c`)

**`I2S_TxTransferNonBlocking()` does NOT fill the FIFO:**
1. Queues buffer pointer and size in `handle->i2sQueue[]`
2. Sets watermark via `FIFOTRIG = ... | I2S_FIFOTRIG_TXLVL(handle->watermark)`
3. Enables TX transmitter: `I2S_TxEnable(base, true)`
4. Returns immediately — FIFO is still empty!

**`I2S_TxHandleIRQ()` (interrupt handler) does the actual work:**
```c
void I2S_TxHandleIRQ(I2S_Type *base, i2s_handle_t *handle) {
    // When TX level interrupt fires:
    while (((base->FIFOSTAT & I2S_FIFOSTAT_TXNOTFULL_MASK) != 0UL) && (dataSize > 0U)) {
        data = *((volatile uint32_t *)(dataAddr));
        base->FIFOWR = data;   // <-- Writes to FIFO at offset 0xe20
        dataAddr += sizeof(uint32_t);
    }
}
```

**Key insight:** The SDK driver **never fills the TX FIFO until an interrupt fires**. If interrupts don't reach the CPU, no samples ever enter the FIFO.

---

## 2. QEMU Device Model Chain

### Data Flow (What Should Happen)

```
Guest memory (s_Buffer with music data)
    |
    v
[SDK I2S_TxHandleIRQ runs] → writes to FIFOWR (0xe20)
    |
    v
[qemu/hw/char/rt6xx_flexcomm.c:1070] i->tx_fifo[tail] = val;  // FIFO filled
    |
    v
[hw/audio/rt685_audio_link.c:43] rt685_audio_endpoint_pop(s->tx, &word)
    |
    v
[CoreAudio playback] → word sent to speaker/headphone output
```

### What Actually Happens (Problematic Path)

```
Guest memory (s_Buffer with music data)
    |
    X [SDK I2S_TxHandleIRQ NEVER runs — interrupt not delivered?]
    |
    v
FIFO remains empty or contains only zeros from memset()
    |
    v
[rt685_audio_link_tick()] calls rt6xx_flexcomm_endpoint_pop()
    |
    v
[i->tx_count == 0] → returns false, word = 0
    |
    v
Zero samples sent to CoreAudio (inaudible)
```

---

## 3. Potential Failure Points

### Point A: NVIC Interrupt Delivery

**Location:** `hw/char/rt6xx_flexcomm.c` line ~1294

```c
static void rt6xx_flexcomm_update_irq(Rt6xxFlexcommState *s) {
    // ... 
    case RT6XX_FLEXCOMM_PERIPH_I2S_TX:
    case RT6XX_FLEXCOMM_PERIPH_I2S_RX:
        if (s->i2s.cfg1 & I2S_CFG1_MAINENABLE) {
            sources = rt6xx_flexcomm_i2s_fifointstat(s);  // Check interrupt sources
            level = sources != 0;
        }
        break;
    // ...
    qemu_set_irq(s->irq, level);  // Set NVIC line
}
```

**Issue:** The NVIC must be configured to:
1. Unmask the I2S interrupt (enabled in NVIC_ISER)
2. Have priority lower than current execution level
3. Be pending when we call `qemu_set_irq(s->irq, true)`

If any of these conditions fail, the SDK's ISR never runs and the FIFO is never filled.

### Point B: Interrupt Acknowledgment Timing

**Location:** `hw/char/rt6xx_flexcomm.c` line 908-923

```c
static uint32_t rt6xx_flexcomm_i2s_fifointstat(Rt6xxFlexcommState *s) {
    // Returns: raw conditions ANDed with enable mask
    if ((i->fifotrig & I2S_FIFOTRIG_TXLVLENA) &&
        i->tx_count <= tx_trigger) {     // TX level when count <= watermark (4)
        raw |= I2S_FIFOINT_TXLVL;
    }
    return raw & i->fifointenset;  // AND with interrupt enables
}
```

**Issue:** The SDK writes `FIFOSTAT = I2S_FIFOSTAT_TXERR(1U)` to clear error flags, but **TX level is a level-triggered condition**. Even after the ISR runs and fills the FIFO, if `tx_count <= watermark`, the interrupt stays asserted. This should work for level-triggered interrupts in NVIC, but could cause issues if:
- QEMU's event loop processes audio ticks faster than interrupt delivery
- The CPU returns from ISR before the NVIC sees updated IRQ state

### Point C: Audio Link Tick Timing vs Interrupt Processing

**Location:** `hw/audio/rt685_audio_link.c` line 30-52

```c
static void rt685_audio_link_tick(void *opaque) {
    // Called every ~20.8μs at 48kHz
    
    /* Playback: Flexcomm TX -> codec */
    rt685_audio_endpoint_pop(s->tx, &word);  // Pops from FIFO
    rt685_audio_endpoint_push(s->codec, word);  // Sends to CoreAudio
    
    // Schedules next tick at absolute deadline (drift-free)
    s->next_deadline += s->frame_ns;
    timer_mod(s->frame_timer, s->next_deadline);
}
```

**Issue:** The audio link ticks **48kHz = every 20.8μs**, but QEMU's event loop processes guest interrupts at the CPU instruction granularity. If:
- Guest memory access is slow (no MMU mapping, etc.)
- NVIC interrupt processing takes many cycles
- The FIFO empties faster than SDK can refill it

Then we get zeros being sent to audio output.

### Point D: SDK Callback Re-entry

**Location:** `i2s_interrupt_record_playback.c` line 103

```c
static void TxCallback(I2S_Type *base, i2s_handle_t *handle, status_t completionStatus, void *userData) {
    I2S_TxTransferNonBlocking(base, handle, *transfer);  // Re-queue buffer
}
```

**Issue:** The callback is called when the **entire transfer completes** (all 400 bytes sent). If our QEMU model doesn't properly track transfer completion or trigger the callback at the right time, the SDK never re-queues the buffer and playback stops after the first 8 samples (FIFO depth).

---

## 4. Diagnostic Steps to Confirm Root Cause

### Step 1: Verify IRQ Line is Asserted

Add tracing in `rt6xx_flexcomm_update_irq()`:
```c
trace_rt6xx_flexcomm_i2s_irq_asserted(s->irq, level);
qemu_set_irq(s->irq, level);
```

Then check if the NVIC executes any I2S interrupt:
```bash
-d guest_errors,int -d cpu_reset -d unimp  # QEMU debug flags
```

### Step 2: Check Guest Memory Access

The SDK reads from `s_Buffer` (400 bytes, aligned to 8-byte boundary). If this memory isn't mapped in the emulated MMU/MPU, the CPU will fault before reaching FIFOWR writes.

Verify with:
```c
// In rt6xx_flexcomm_i2s_write() at offset 0xe20 (FIFOWR):
if (val != 0) {
    trace_rt6xx_flexcomm_i2s_fifo_sample(sample);
}
```

If we see `sample == 0` always, the SDK never writes to FIFOWR.

### Step 3: Check Transfer Completion Interrupt

The SDK expects completion interrupts when all bytes are sent. Our model doesn't implement this yet (we removed eDMA). The SDK's ISR might be waiting for an interrupt that never comes.

---

## 5. Recommended Fixes (Priority Order)

### Fix 1: Add FIFO Fill Trace (Diagnostic)
```c
case 0xe20:  // FIFOWR
    if (i->tx_count < RT6XX_FLEXCOMM_I2S_FIFO_SIZE && 
        i->fifocfg & FIFOCFG_ENABLETX) {
        trace_flexcomm_i2s_tx_fifo_write(val);
        // ... push to FIFO ...
    }
```

### Fix 2: Implement SDK Transfer Completion Tracking
The SDK driver tracks transfer progress via `handle->transferCount`. We need to detect when all queued bytes have been consumed and trigger the callback.

**Implementation approach:**
1. Store queue buffer metadata in Flexcomm state (pointer, size remaining)
2. Decrement on each FIFO pop/word sent  
3. When count reaches zero, assert completion interrupt
4. SDK's ISR runs and re-queues via `I2S_TxTransferNonBlocking()`

### Fix 3: Verify NVIC Interrupt Routing
Ensure Flexcomm IRQ lines are properly connected to NVIC in `imxrt685.c`:
```c
// Check that I2S TX/RX IRQs map to correct NVIC vectors
sysbus_connect_irq(SYS_BUS_DEVICE(&soc->flexcomm[3]), 0,
                   qdev_get_gpio_in(armv7m, I2S3_IRQ_NUMBER));
```

### Fix 4: Add Software Trigger for Testing
For diagnostic purposes, add a mechanism to pre-fill the TX FIFO from host memory (bypass SDK interrupts). This would confirm whether the audio path works if data is present.

---

## 6. Conclusion

The **primary failure mode** is that the SDK's interrupt-driven I2S model requires timely interrupt delivery and proper transfer completion signaling, neither of which our current QEMU implementation handles correctly for non-DMA transfers.

The **secondary issue** is that when interrupts do fire (if they do), we lack a mechanism to track multi-buffer transfers and trigger the SDK's callback at completion time, causing playback to stop after the initial FIFO drain (~8 samples).

**Next steps:**
1. Add trace points to confirm whether FIFOWR writes occur (SDK ISR running?)
2. Fix NVIC IRQ routing if interrupts aren't reaching CPU
3. Implement transfer completion tracking and callback invocation
4. Test with pre-filled FIFO to verify audio path is functional
