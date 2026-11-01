# FIRA PLATFORM PRIVACY POLICY

**LAST REVISED**: October 2026  
**COMPLIANCE JURISDICTION**: Zimbabwe (Cyber and Data Protection Act [Chapter 12:07]) & International Standards

---

## 1. COMMITMENT TO DATA PRIVACY
This Privacy Policy outlines how the FIRA platform ("FIRA", "we", "us") collects, secures, and handles corporate and personal data uploaded by corporate clients and their authorized auditors.

---

## 2. INFORMATION WE COLLECT
In delivering the reconciliation and tax audit services, FIRA processes:
1. **Account Identification Information**: Corporate client name, physical business address, Business Partner Number (BPN), and Taxpayer Identification Number (TIN).
2. **Operator Credentials**: Authorized user email address, cryptographically hashed passwords, and Multi-Factor Authentication (MFA) tokens.
3. **Transaction & Invoice Records**: Scanned invoices, vendor names, invoice numbers, currency identifiers (USD / ZWG), net totals, VAT totals, fiscal device serial numbers, and verification hashes.
4. **Audit Metadata**: Immutable logs capturing user IDs, timestamps, client IP addresses, and actions taken (e.g., file upload, reconciliation run, manual match).

---

## 3. HOW WE USE YOUR INFORMATION
All data ingested into FIRA is utilized exclusively for:
* Reconciling customer internal accounts payable records against official tax claim lists.
* Validating invoice arithmetic and statutory fiscal markers.
* Generating exception audit reports and supplier variance correction drafts.
* Maintaining audit trails as required by tax and corporate governance standards.

**We never sell, monetize, or train external public machine learning models on Customer Data.**

---

## 4. SECURITY CONTROLS & DATA RESIDENCY
* **Data Isolation**: Strict multi-tenant logical database partitioning (`tenant_id`).
* **Transport Security**: Mandatory TLS 1.3 encryption across all network communication.
* **Storage Encryption**: AES-256 cryptographic protection for files and database volumes.
* **On-Premise Flexibility**: For enterprises with strict sovereign data sovereignty requirements, FIRA is available as an on-premise container deployment within the client's internal data center.

---

## 5. CONTACT & DATA PROTECTION OFFICER (DPO)
For inquiries regarding data protection, POTRAZ compliance, or exercising data subject rights under Chapter 12:07:  
* **Email**: `dpo@fira.local` (or designated enterprise contact)  
* **Postal Address**: [Company Physical Address, Harare, Zimbabwe]
