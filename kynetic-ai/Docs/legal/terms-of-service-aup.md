# Kynetic AI — Terms of Service & Acceptable Use Policy (AUP)

**Last Updated**: July 24, 2026

Welcome to **Kynetic AI** ("Platform", "we", "us", or "our"). By accessing or using our compute marketplace, APIs, or Host Agent software, you agree to be bound by these Terms of Service and Acceptable Use Policy.

---

## 1. Description of Service
Kynetic AI provides a resource-agnostic compute marketplace connecting hardware Hosts ("Hosts") who monetize idle compute capacity (GPUs, CPUs, RAM, NVMe storage) with developers ("Developers") renting compute capacity for AI/ML, 3D rendering, and general computational workloads.

---

## 2. Acceptable Use Policy (AUP) & Prohibited Workloads

Developers and Hosts are strictly prohibited from utilizing Kynetic AI compute resources for any of the following prohibited workloads:

1. **Cryptocurrency Mining**: Unauthorised or silent background mining of Proof-of-Work cryptocurrencies (e.g. Bitcoin, Monero, Ethereum Classic) is strictly forbidden.
2. **Malware & Botnets**: Hosting, distributing, or executing ransomware, spyware, command-and-control (C2) servers, botnets, or automated exploit frameworks.
3. **Unauthorised Scanning & DDoS**: Conducting port scanning, vulnerability probing, packet sniffing, or Distributed Denial of Service (DDoS) attacks against third-party networks.
4. **Illegal Content**: Generating, storing, or transmitting Child Sexual Abuse Material (CSAM), non-consensual imagery, or violent extremism content.
5. **Infringement**: Infringing upon third-party intellectual property, patents, trademarks, or trade secrets.

---

## 3. Enforcement & Security Controls

To protect our network, Hosts, and Developers, Kynetic AI enforces automated security controls:

- **Workload & Image Scanning**: Pre-launch static and container image scanning (`POST /security/scan`) via ClamAV and Trivy engine rules.
- **Runtime Anomaly Detection**: eBPF-based kernel monitoring for privilege escalation, unauthorised outbound connections, or unapproved binary execution.
- **Emergency Kill-Switch**: Administrative authority (`POST /admin/kill-switch`) to immediately halt and terminate any workload violating this AUP without prior notice.
- **Account Suspension & Wallet Forfeiture**: Accounts engaging in prohibited activity will be permanently suspended, and wallet balances forfeit.

---

## 4. Wallet & Usage-Based Billing

- Compute rentals are billed on a **per-second basis** deducted from the Developer's prepaid wallet balance.
- Developers must maintain a positive wallet balance. If the wallet balance reaches zero, active instances will enter a 15-minute grace period before automatic termination.
- All prices are listed in USD or INR (inclusive of 18% GST for Indian registrants).

---

## 5. Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW, KYNETIC AI SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS OR REVENUES, ARISING OUT OF OR IN CONNECTION WITH THE USE OF RENTED COMPUTE HARDWARE OR HOST DISRUPTIONS.
