# DATA PROCESSING AGREEMENT (DPA)

**Pursuant to the Zimbabwe Cyber and Data Protection Act [Chapter 12:07]**

This Data Processing Agreement ("DPA") supplements the Master Subscription Agreement between **Vendor** ("Data Processor") and **Customer** ("Data Controller").

---

## 1. PURPOSE AND SCOPE
1.1. The Data Controller engages the Data Processor to provide the FIRA fiscal reconciliation platform.  
1.2. In providing the services, the Data Processor processes financial data, tax identifiers, and purchase ledgers on behalf of the Data Controller.  
1.3. Both parties agree to adhere strictly to the **Cyber and Data Protection Act [Chapter 12:07]** and guidelines issued by the Postal and Telecommunications Regulatory Authority of Zimbabwe (POTRAZ).

---

## 2. CATEGORIES OF DATA PROCESSED
* **Corporate Identifiers**: Business Partner Numbers (BPN), Taxpayer Identification Numbers (TIN), Trade Names.
* **Financial & Invoice Data**: Invoice numbers, fiscal device numbers, verification codes, net amounts, VAT values, gross values, currency codes (USD/ZWG).
* **System User Credentials**: Operator email addresses, hashed passwords, Multi-Factor Authentication (MFA) tokens, and session IP audit logs.

---

## 3. OBLIGATIONS OF THE DATA PROCESSOR
3.1. **Instructions Only**: The Data Processor shall process Personal and Financial Data strictly in accordance with documented instructions from the Data Controller.  
3.2. **Multi-Tenant Isolation**: The Data Processor shall maintain strict database-level tenant isolation ensuring no data co-mingling or cross-tenant exposure.  
3.3. **Technical & Organizational Measures**:
   * **Encryption in Transit**: TLS 1.3 encryption on all public and internal communications.
   * **Encryption at Rest**: AES-256 encryption for file storage and sensitive configuration keys.
   * **Access Controls**: Strict Role-Based Access Control (RBAC) with mandatory multi-factor authentication (MFA) options for administrative accounts.
   * **Immutability**: Tamper-evident, timestamped audit logging for all record imports and modifications.

---

## 4. SECURITY INCIDENT & BREACH NOTIFICATION
4.1. In the event of a confirmed security incident, data leakage, or unauthorized breach affecting Customer Data, the Data Processor shall:
   * Notify the Data Controller without undue delay, and in any event within **forty-eight (48) hours** of becoming aware of the breach.
   * Provide a detailed incident assessment, scope of affected records, and remedial mitigation measures taken.
   * Assist the Data Controller in fulfilling statutory reporting obligations to POTRAZ and affected data subjects where required under Chapter 12:07.

---

## 5. SUB-PROCESSORS
5.1. The Data Processor shall not engage third-party sub-processors without prior notification to the Data Controller.  
5.2. Where infrastructure hosting is subcontracted (e.g., local cloud data centers or AWS/DigitalOcean), sub-processors are bound by data protection obligations no less protective than those in this DPA.

---

## 6. DATA RETENTION, RETURN & DELETION
6.1. **Statutory Retention**: Pursuant to Section 57 of the **Value Added Tax Act [Chapter 23:12]**, taxpayers are required to retain tax invoices and ledgers for a minimum period of **six (6) years** (or as contractually configured in FIRA retention settings, minimum 24 months).  
6.2. **Return or Deletion**: Upon termination of the subscription, the Data Processor shall, at the choice of the Data Controller, either securely export all Customer Data in structured format (`.csv` / `.json`) or permanently expunge and sanitize the data within ninety (90) days.

---

## 7. GOVERNING LAW
This DPA is governed by the laws of **Zimbabwe**, including the Cyber and Data Protection Act [Chapter 12:07].
