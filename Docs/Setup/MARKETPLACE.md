# Kynetic AI — Marketplace & AI Intent Router Architecture

This document details the Marketplace scheduling pipeline, intent-based AI Resource Router & Copilot, scikit-learn auto-pricing model, and transparent fallback recommendation engine.

---

## 1. Intent-Based Routing Pipeline

Unlike traditional GPU marketplaces requiring developers to manually pick GPU specs, Kynetic AI accepts natural language workload descriptions (e.g. *"Fine-tune Llama 3 8B with QLoRA under $0.50/hr"*).

```
Developer Prompt ──► [LangChain Intent Parser] ──► [Resource Requirements Extractor]
                                                          │
                                                          ▼
[External Marketplace Fallbacks] ◄── [Multi-Factor Ranking Engine] ──► [Selected Listing]
  (RunPod, Vast.ai, Lambda)            - Price (USD/INR)
                                       - 6-Factor Reputation Score
                                       - Hardware Suitability & VRAM
                                       - Security Tier (Confidential vs Standard)
```

---

## 2. Multi-Factor Host Reputation Score

Host listings are ranked using a 6-factor reputation algorithm:

$$\text{Reputation Score} = w_1 \cdot \text{Uptime} + w_2 \cdot \text{Latency} + w_3 \cdot \text{Benchmark} - w_4 \cdot \text{Disputes} + w_5 \cdot \text{SecurityTier} + w_6 \cdot \text{CompletionRate}$$

- **Uptime (25%)**: Historical hardware availability percentage over 30 days.
- **Latency (15%)**: Network ping and bandwidth throughput to nearest region.
- **Benchmark (20%)**: Measured PyTorch TFLOPS matrix multiplication score.
- **Dispute Rate (-15%)**: Penalty for host-initiated disconnections or failed jobs.
- **Security Tier (15%)**: Bonus for hardware-enforced Confidential Computing (`confidential_tier`).
- **Completion Rate (10%)**: Percentage of developer rentals completed cleanly without interruption.

---

## 3. Dynamic Auto-Pricing Algorithm

Hosts can opt into AI Auto-Pricing (`services/reputation_pricing_service/`). The service calculates real-time optimal rates using a `scikit-learn` regression model trained on market demand, supply saturation, VRAM capacity, and regional spot rates, maximizing host earnings while keeping prices competitive.
