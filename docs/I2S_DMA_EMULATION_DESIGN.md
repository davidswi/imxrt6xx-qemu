# Flexcomm I2S + NXP DMA0 Emulation Design (Revised)

**Target:** local `mimxrt685-evk` QEMU machine  
**Goal:** Enable SDK DMA-driven I2S audio transfers using a lightweight, targeted NXP DMA model.  
**Date:** 2026-10-26 (revised from original eDMA design)

---

## Critical Discovery: The SDK Uses NXP DMA0, NOT eDMA

The original design assumed the SDK used eDMA. **This was wrong.**

The MCUXpresso SDK's `fsl_i2s_dma.c` driver uses:
- **Header:** `fsl_dma.h` (not `fsl_edma.h`)  
- **Base address:** DMA0 at `0x40104000` (non-secure) / `0x50104000` (secure)
- **Channel:** Channel 7 for I2S TX on Flexcomm3

Reference from SDK source:
```c
// app.h in dma_transfer example:
#define DEMO_DMA                        (DMA0)
#define DEMO_I2S_TX_CHANNEL             (7)
```

From `MIMXRT685S_cm33_COMMON.h`:
```c
#define DMA0_BASE_NS                            (0x40104000u)
#define DMA0                                    ((DMA_Type *)DMA0_BASE)
```

---

## 1. NXP DMA0 Register Layout (SDK-relevant subset)

| Offset | Name | Size | Description |
|--------|------|------|-------------|
| 0x000 | CTRL | 4 bytes | Control: bit 0 = ENABLE |
| 0x008 | SRAMBASE | 4 bytes | Descriptor table base address (bits 9:31) |
| 0x400+`n*0x10` | CH`n`.CFG | 4 bytes | Channel config: PERIPHREQEN(0), HWTRIGEN(1) |
| 0x408+`n*0x10` | CH`n`.XFERCFG | 4 bytes | Transfer count (bits 0:9), SWTRIG(12) |

Channel count: **33** (SDK uses channel 7 for I2S TX)

---

## 2. SDK DMA Initialization Sequence

The `i2s_dma_transfer.c` example does:
```c
DMA_Init(DEMO_DMA);              // Sets SRAMBASE to descriptor table, enables CTRL[0]
DMA_EnableChannel(DEMO_DMA, 7);  // Enables channel 7
DMA_SetChannelPriority(DEMO_DMA, 7, kDMA_ChannelPriority3);
// ... later:
I2S_TxTransferCreateHandleDMA(...);  // Configures DMA channel via descriptor table
I2S_TxTransferSendDMA(...);           // Triggers transfer via SWTRIG or hardware request
```

The `fsl_i2s_dma.c` driver then configures each channel's XFERCFG register with the
transfer count and triggers it (via PERIPHREQEN for hardware-triggered, or SWTRIG bit).

---

## 3. Implementation Plan

### Phase A: NXP DMA0 Model Skeleton (~300 lines)

**New files:**
- `qemu/hw/dma/imxrt685_dma.c` — DMA controller model  
- Update `qemu/include/hw/arm/imxrt685.h` — Add DMA0_BASE address, remove eDMA

### Phase B: Flexcomm → DMA DREQ Integration

When the I2S TX FIFO watermark triggers and PERIPHREQEN is enabled on channel 7,
assert a signal to the DMA controller telling it to fetch the next descriptor.

### Phase C: Board Setup Wiring

Connect Flexcomm3 I2S TX (hardware instance index 3) → DMA0 channel 7 DREQ input.

---

## 4. Data Flow

```
Guest SRAM buffer (g_Music[])
       |
       v
[DMA descriptor table configures SAR, DAR, XFERCOUNT]
       |
Flexcomm3 I2S TX FIFO drops below watermark → PERIPHREQEN triggers DMA
       |
       v
eDMA receives trigger → reads next descriptor → transfers one buffer chunk
       |
       v
Write sample into Flexcomm3 TX FIFO
       |
       v
Decrement XFERCOUNT; if non-zero, wait for next watermark/trigger
       |
When XFERCOUNT == 0: assert DMA completion interrupt → SDK callback re-enqueues
```

---

## 5. Exit Criteria

- Unmodified `i2s_dma_transfer` firmware runs without crashes on DMA register access
- Data flows end-to-end: guest buffer → DMA transfer → Flexcomm TX FIFO → audio-link → codec
- WAV output contains real sample data (not zeros)  
- CoreAudio audible playback works with `-audiodev coreaudio,id=rt685`
