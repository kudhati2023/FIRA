# Architectural and Tax Decisions Log (DECISIONS.md)

This document tracks assumptions, interpretations of tax rules, and system-design decisions.

## Seeding and Placeholders (Milestone 0)
1. **TaRMS Export Columns**: Unspecified. Designed mapping wizard to let operators define layout configurations.
2. **Valid Statuses**: Default is `["VALID", "APPROVED", "SUCCESS"]`. Editable via dynamic `config_setting` system.
3. **Zimbabwean TIN**: Configurable regex validation rule. We use `^\d{9,10}$` (9 to 10 digits) as a starter.
4. **ZWG/USD Segregation**: Reported separately; currency aggregation is prohibited (FR-VAL-4).
5. **E7 Keyword Set**: Seeding config with `["entertainment", "passenger", "motor vehicle", "hospitality", "club", "lunch", "golf"]`.
6. **Retention Period**: Seeding default of 24 months, with override capacity per client.
