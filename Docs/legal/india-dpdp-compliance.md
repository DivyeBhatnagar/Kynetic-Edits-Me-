# Kynetic AI — India Regulatory & DPDP Act Compliance Review

**Last Updated**: July 24, 2026

This document certifies Kynetic AI's compliance with Indian regulatory, tax, and data protection frameworks.

---

## 1. Digital Personal Data Protection Act 2023 (DPDP Act 2023)

Kynetic AI adheres to the obligations imposed on **Data Fiduciaries** under India's DPDP Act:

1. **Notice & Consent**: Clear, itemised consent notices in English and Hindi presented during onboarding.
2. **Data Minimization**: Collecting only data required for marketplace matching, billing, and security (no access to private developer code/data).
3. **Data Principal Rights**: Right to access, correct, update, and erase personal data via self-serve dashboard or `privacy@kynetic.ai`.
4. **Data Protection Officer (DPO)**: Appointed internal DPO reachable at `dpo@kynetic.ai`.

---

## 2. Data Residency Statement

- All database records, user authentication profiles, audit logs, and invoice storage for Indian users and hosts reside in **AWS region `ap-south-1` (Mumbai, India)**.
- No personal data of Indian residents is transferred to foreign servers without explicit consent.

---

## 3. GST Registration & Tax Compliance

- Kynetic AI is registered under the Central Goods and Services Tax Act (CGST / SGST / IGST).
- **18% GST** is collected on all developer wallet top-ups and compute rentals within India.
- Sequential B2B/B2C GST Tax Invoices (`KYN/2024-25/XXXXXX`) with row-level locked sequence generation (`invoice_sequences`).
- Section 194O Tax Deducted at Source (TDS) calculated and deposited monthly for Indian host payouts.
