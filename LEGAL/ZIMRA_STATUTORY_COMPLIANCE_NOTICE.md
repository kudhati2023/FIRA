# ZIMRA & STATUTORY FISCAL COMPLIANCE POSITION MEMORANDUM

**DOCUMENT REF**: FIRA-REG-MEMO-2026-01  
**SUBJECT**: Regulatory Classification & Compliance Architecture of the FIRA Platform  
**JURISDICTION**: Republic of Zimbabwe  
**PRIMARY STATUTES**:
* Value Added Tax Act [Chapter 23:12]
* Statutory Instrument 153 of 2016 (Value Added Tax (Fiscalised Recording of Taxable Transactions) Regulations)
* Statutory Instrument 105 of 2024 (Value Added Tax (Fiscal Data Management System) Regulations)
* Cyber and Data Protection Act [Chapter 12:07]

---

## 1. EXECUTIVE SUMMARY & PLATFORM CLASSIFICATION
The **FIRA (Fiscal Invoice Reconciliation & Auditing)** platform is an enterprise internal audit, accounts payable pre-reconciliation, and statutory risk management software.

**Legal Exemption from Fiscal Device / FDMS Vendor Accreditation**:
Under Statutory Instrument 105 of 2024, only suppliers of hardware or software that **generate, electronically sign, and issue fiscal tax invoices / cash register receipts at point of sale** must undergo ZIMRA accreditation as approved FDMS Device Vendors.

FIRA does **NOT** issue tax invoices to consumers, does not act as an electronic fiscal cash register, and does not alter taxpayer accounts with the revenue authority. Instead, FIRA operates strictly as an **internal analytical pre-filing auditing tool** used by registered operators to audit their own purchase ledgers against ZIMRA-recorded claims before submitting VAT returns (Form VAT 7).

---

## 2. STATUTORY COMPLIANCE ARCHITECTURE

### 2.1. Rule-Based Non-Scraping Data Ingestion (HC-1 & HC-2)
* **Regulation**: Section 30 of the Cyber and Data Protection Act prohibits unauthorized automated querying or credential scraping of government public portals.
* **FIRA Design**: FIRA implements a strict **File-Ingestion Only** architecture. All tax authority data enters via authentic, verified `.csv` or `.xlsx` files manually exported by the authorized taxpayer from the official ZIMRA TaRMS / FDMS portal.
* **Direct Verification**: For single scanned invoices, FIRA calculates canonical verification links that open the official ZIMRA verification portal (`https://fdms.zimra.co.zw/verify/...`) directly in the operator’s authenticated browser window, ensuring zero automated scraping by the server.

### 2.2. Currency Segregation: USD vs. ZWG (FR-VAL-4)
* **Regulation**: The Finance Act and Reserve Bank monetary directives require businesses to account for VAT in the exact currency in which the underlying transaction occurred. Blending or converting VAT claims across currencies is unlawful.
* **FIRA Design**: FIRA maintains complete database and analytical segregation between `USD` and `ZWG` ledgers. VAT at risk, claim mismatches, and reconciliation summaries are computed separately per currency with zero cross-currency aggregation.

### 2.3. Dynamic Statutory VAT Rate Periods (HC-3)
* **Regulation**: Zimbabwe has experienced statutory VAT rate changes (e.g., standard rate adjustments between 14.5% and 15%).
* **FIRA Design**: FIRA enforces date-effective rate resolution through the `vat_rate_period` table. The software calculates expected VAT based on the statutory rate in force on the exact date of invoice issuance, preventing historic claim audit failures.

### 2.4. Deterministic Non-Hallucinatory Audit Trail (HC-4 & HC-5)
* **Regulation**: Tax audits require 100% mathematical reproducibility.
* **FIRA Design**: FIRA’s reconciliation engine is strictly deterministic (no randomness, deterministic sort orders, rule-based tier matching). Generative AI / Large Language Models are completely prohibited from mathematical calculation, classification, and matching pipelines.

---

## 3. SCOPE LIMITATION AND OPERATOR DUTY
FIRA generated reports, variance schedules, and exception alerts are provided to assist corporate tax teams, internal auditors, and financial controllers in identifying discrepancies before official tax submission. They do not constitute an official ZIMRA clearance, nor do they waive the taxpayer's statutory obligation to maintain original physical fiscal tax invoices as required under Section 15 of the VAT Act.
