# Agent Operating Guidelines (AGENTS.md)

Welcome to the FIRA platform repository. As an agent working on this codebase, you must adhere strictly to the following architectural rules and constraints:

## Hard Constraints
1. **No ZIMRA Automation (HC-1)**: Do not write code that authenticates to, scrapes, or interacts live with any ZIMRA portal or API. All ZIMRA data enters through manually uploaded files.
2. **File Ingestion Only (HC-2)**: The system relies solely on files exported by taxpayers. No live connection.
3. **No Hardcoded VAT Rates (HC-3)**: Rates must be resolved from the `vat_rate_period` table based on the invoice date.
4. **Deterministic Matching Engine (HC-4)**: The core reconciliation engine must be fully deterministic. Sort matching lists, candidates, and loops. No use of `random`, Python set iteration ordering, or time-dependent calculations.
5. **No LLM calls in Match/Calculation Path (HC-5)**: Calculations, matching, and classifications must remain rule-based and transparent. LLMs may only be used for drafts of supplier correspondence in Phase 3.
6. **Tenant Query Isolation (HC-6)**: Ensure every query includes a `tenant_id` filter.
7. **No Tax Advice Presentation (HC-7)**: Display the mandatory scope-limitation notice on every generated report and PDF.
8. **Clarify Ambiguities (HC-8)**: Never guess or invent tax rules. If a requirement is ambiguous, stop and ask.

## Milestone Integrity
Always verify code changes with tests. Do not proceed to milestone N+1 before milestone N is verified, fully functional, and all tests pass.
