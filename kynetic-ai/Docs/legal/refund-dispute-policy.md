# Kynetic AI — Refund & Dispute Resolution Policy

**Last Updated**: July 24, 2026

This policy outlines developer wallet refund eligibility, dispute resolution flows, and chargeback procedures.

---

## 1. Developer Wallet Top-Up Refunds

- **Unused Wallet Credit**: Developers may request a full refund of unspent prepaid wallet credit within 14 days of top-up.
- **Refund Method**: Refunds will be issued to the original payment method (Stripe card or Razorpay UPI/Netbanking).
- **Processing Time**: Approved refunds are processed within 5 to 7 business days.

---

## 2. Compute Rental Service Quality Guarantee

If a compute rental instance fails due to host disconnection, hardware failure, or platform error:
- The developer will **not be billed** for any time following the last valid host heartbeat.
- Automated credit compensation will be applied to the developer's wallet for lost setup time.

---

## 3. Dispute & Chargeback Handling

- **Internal Support Resolution**: Developers and Hosts agree to contact `support@kynetic.ai` before filing formal payment gateway disputes.
- **Automated Freeze on Chargebacks**: When a formal payment chargeback or dispute event (`charge.dispute.created`) is received from Stripe or Razorpay:
  1. Relevant developer wallet funds are frozen automatically pending investigation (`chargebacks` status=`opened`).
  2. If the dispute is resolved in Kynetic's favor (`won`), frozen funds are unfrozen.
  3. If the dispute is resolved against Kynetic (`lost`), frozen funds are forfeited and the account is reviewed for fraud.

---

## 4. GST Credit Notes & Invoice Adjustments

- For Indian registrants, approved refunds generate an official **GST Credit Note** matching the original GST Tax Invoice (`invoices`) to ensure tax compliance with Indian GST regulations.
