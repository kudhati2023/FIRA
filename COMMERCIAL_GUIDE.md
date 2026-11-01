# COMMERCIAL & SALES PLAYBOOK FOR FIRA

**Product**: FIRA — Fiscal Invoice Reconciliation & Auditing Platform  
**Target Market**: Zimbabwe and FDMS-regulated fiscal tax jurisdictions  
**Primary Customers**: Large Enterprises, FMCG Distributors, Mining Houses, Commercial Banks, and Certified Accounting/Tax Firms.

---

## 1. PRODUCT VALUE PROPOSITION & ROI

### The Problem FIRA Solves:
* **The ZIMRA Input Tax Risk**: Under ZIMRA FDMS regulations (SI 105/2024), companies claiming input VAT deductions on invoices that do not appear in ZIMRA’s fiscal database face **immediate disallowance of claims, 100% penalties, and interest charges**.
* **The Manual Audit Bottleneck**: Finance departments manually cross-check thousands of supplier invoices against ZIMRA portal exports using Excel, which takes weeks and results in costly human error.
* **The Currency Trap**: Mixing USD and ZWG calculations creates major compliance violations during tax audits.

### The Value to the Customer:
1. **Automated 5-Second Reconciliation**: Instantly compares 10,000+ AP lines against ZIMRA FDMS claims.
2. **Pre-Filing Protection**: Pinpoints fake invoices, missing fiscal device numbers, arithmetic mismatches, and unfiled supplier invoices *before* filing Form VAT 7.
3. **Automated Discrepancy Letters**: Instantly generates supplier correction notices for unrecorded invoices, saving hundreds of accounting hours.
4. **Guaranteed Return on Investment**: Finding just two or three disallowed invoices ($5,000 to $20,000 VAT risk) pays for the annual software license immediately.

---

## 2. COMMERCIAL PACKAGING & PRICING MODELS

### Option A: Cloud Multi-Tenant SaaS (Recommended for Mid-Market & SME)
* **Target**: Mid-sized companies, retail chains, logistics providers.
* **Hosting**: Hosted by you on secure cloud infrastructure.
* **Pricing Tiers**:
  * **Standard Tier**: Up to 2,500 invoices/month — **$250 - $400 / month**.
  * **Enterprise Tier**: Up to 25,000 invoices/month, multi-user, MFA, priority support — **$800 - $1,500 / month**.
  * **Annual Billing Discount**: 15% discount for upfront annual prepayment.

### Option B: On-Premise Enterprise Container (For Banks, Mining & Telcos)
* **Target**: Mining houses (e.g. Zimplats, Mimosa), Commercial Banks, Telecommunications companies that cannot export financial data to external clouds due to strict internal compliance.
* **Delivery**: Packaged Docker Compose production stack (`deploy-prod.sh` / `deploy-prod.ps1`) installed inside their private network/data center.
* **Pricing**:
  * **Annual License Fee**: **$10,000 – $25,000 / year** per enterprise entity.
  * **Installation & Integration Fee**: **$2,500 – $5,000** one-time setup and training.

### Option C: Certified Audit Firm / Tax Practitioner Partner License
* **Target**: Chartered accounting firms, tax consultancies, and independent auditors.
* **Model**: Multi-client portal where the accounting firm creates isolated client engagements and charges their corporate clients for monthly tax health checks.
* **Pricing**: **$500 – $1,200 / month** flat base fee + $50 per managed corporate client.

---

## 3. READY-TO-USE LEGAL & SALES CONTRACT PACK

All legal contracts required to sign enterprise deals are provided in the `/LEGAL` directory:
1. **`LEGAL/MASTER_SUBSCRIPTION_AGREEMENT.md`**: The binding commercial sales agreement (SaaS / on-premise license terms, SLA, payment terms, and limitation of liability).
2. **`LEGAL/DATA_PROCESSING_AGREEMENT.md`**: Compliant with the **Zimbabwe Cyber and Data Protection Act [Chapter 12:07]** and POTRAZ requirements.
3. **`LEGAL/ZIMRA_STATUTORY_COMPLIANCE_NOTICE.md`**: The formal legal position paper proving to client CFOs and legal teams that FIRA complies with SI 105/2024 and does not require point-of-sale device accreditation.
4. **`LEGAL/PRIVACY_POLICY.md`**: Corporate privacy and data handling notice.

---

## 4. HOW TO CLOSE DEALS: 3-STEP SALES PLAY

1. **Step 1: The "Free Fiscal Health Audit" Pilot**:
   * Offer the prospective CFO / Tax Manager a 1-month historical health audit.
   * Have them export their last month’s AP ledger and ZIMRA claim list.
   * Run it through FIRA. In under 2 minutes, show them the **VAT at Risk** dollar amount and the list of suppliers who failed to fiscalize invoices.
2. **Step 2: Present the Cost of Inaction**:
   * Show that ZIMRA penalties (100% penalty + interest) on those mismatched invoices far exceed the cost of FIRA.
3. **Step 3: Sign Master Agreement & Onboard**:
   * Execute the `MASTER_SUBSCRIPTION_AGREEMENT.md` and `DATA_PROCESSING_AGREEMENT.md`.
   * Deploy via Cloud login or 1-command on-premise script.
