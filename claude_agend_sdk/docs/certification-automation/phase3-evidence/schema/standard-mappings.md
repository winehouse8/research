# Standard Clause Mappings for Certification Evidence Records

This document maps evidence record fields to applicable safety standard clauses and objectives.
Each table specifies the evidence field, the relevant clause or objective, its description, and the verification method used to demonstrate compliance.

---

## IEC 62304 Clause Mapping

IEC 62304 defines software lifecycle requirements for medical device software.
The evidence record fields below satisfy the following clauses.

| Evidence Field | IEC 62304 Clause | Clause Description | Verification Method |
|---|---|---|---|
| `jira_ticket.workflow_history` | 5.1.6 | Software development planning — activity scheduling and tracking | Confirm workflow transitions show planned activities were executed in sequence; compare transition timestamps against project plan milestones |
| `traceability.design_docs` | 5.3.1 | Software architectural design — document software architecture | Verify design document references are present and resolve to approved architecture artifacts in the document management system |
| `commits`, `ci_results.test_summary` | 5.5 | Software unit implementation and verification — implement and verify each software unit | Confirm all commits reference a JIRA ticket; verify unit test passed counts are non-zero and failed count is zero |
| `ci_results.test_summary`, `ci_results.coverage_percent` | 5.6 | Software integration and integration testing — integrate software units and verify integration | Confirm integration test results show zero failures; verify coverage meets project threshold (typically ≥ 80%) |
| `ci_results.conclusion`, `reviews` | 5.7 | Software system testing — verify the software system meets its requirements | Confirm workflow conclusion is "success"; verify at least one approved review is present |
| `approvals`, `github_pr.merged_at`, `release_tag` | 5.8 | Software release — release the software system | Confirm all required approvers have approved; verify merged_at is populated and a release_tag is assigned |
| `jira_ticket.id`, `jira_ticket.status` | 6.1 | Feedback and problem resolution — evaluate software problems | Confirm linked JIRA ticket exists; verify status reached a resolved state prior to merge |
| `record_id`, `integrity.sha256_hash`, `integrity.signed_by` | 7 | Software configuration management — identify, control, and track software items | Verify record_id is a valid UUID; confirm SHA-256 hash matches recomputed digest; confirm signed_by is a recognised CI identity |
| `jira_ticket.workflow_history`, `jira_ticket.resolved_at` | 8 | Software problem resolution process — document and resolve software problems | Verify workflow history shows a resolution transition; confirm resolved_at is populated before the merge date |

---

## ISO 26262 Part 6 Clause Mapping

ISO 26262-6 defines requirements for software-level product development in road vehicles.
The evidence record fields below satisfy clauses in Part 6 (Software level).

| Evidence Field | ISO 26262-6 Clause | Requirement | Verification Method |
|---|---|---|---|
| `ci_results.test_summary`, `reviews` | 6.4.6 | Software integration test — test that integrated software units meet the software architectural design | Verify test_summary shows zero failures; confirm reviews include at least one approval from an integration-responsible engineer |
| `ci_results.conclusion`, `ci_results.test_summary` | 6.4.7 | Software qualification test — test that the software satisfies the software requirements | Confirm workflow conclusion is "success"; verify total passed tests match expected count defined in the test plan |
| `traceability.requirements`, `ci_results.conclusion` | 6.4.8 | Software safety requirement verification — verify software safety requirements are correctly implemented | Confirm all safety requirement IDs appear in traceability.requirements; verify CI conclusion is "success" for the associated run |
| `traceability.design_docs`, `github_pr.base_branch` | 6.4.9 | Software design — specify software architectural design and detailed design | Verify design document references are non-empty; confirm PR targets the correct integration branch per branching strategy |
| `commits`, `traceability.requirements` | 6.4.10 | Software unit design and implementation — implement software units consistent with the detailed design | Confirm each commit message references a JIRA ticket traceable to a requirement; verify traceability.requirements is non-empty |
| `ci_results.test_summary`, `ci_results.coverage_percent`, `ci_results.sast_findings_count` | 6.4.11 | Software unit verification — verify software units meet unit design | Confirm unit test passed count is non-zero and failed count is zero; verify coverage meets ASIL-appropriate threshold; confirm SAST findings count is within the accepted threshold |

---

## DO-178C Objective Mapping

DO-178C defines software considerations in airborne systems and equipment certification.
The evidence record fields below satisfy objectives in the listed tables.
DAL applicability follows the standard (A = most stringent, E = least stringent).

| Evidence Field | DO-178C Table | Objective | DAL Applicability |
|---|---|---|---|
| `jira_ticket.workflow_history`, `traceability.requirements`, `traceability.design_docs` | Table A-4 | Software planning process — plans are developed that describe the software development and verification activities | DAL A, B, C, D |
| `jira_ticket.id`, `jira_ticket.summary` | Table A-4 | Software planning process — software development standards are defined | DAL A, B, C, D |
| `commits` | Table A-5 | Software development process — software is developed according to the software development plan and standards | DAL A, B, C, D |
| `traceability.requirements`, `traceability.test_cases` | Table A-5 | Software development process — source code is traceable to low-level requirements | DAL A, B, C |
| `ci_results.test_summary`, `ci_results.coverage_percent` | Table A-5 | Software development process — software is developed to satisfy high-level and low-level requirements | DAL A, B, C, D |
| `ci_results.test_summary` (failed == 0) | Table A-7 | Software verification process — test procedures are correct and test results are correct and consistent with expected results | DAL A, B, C |
| `ci_results.coverage_percent` | Table A-7 | Software verification process — test coverage of source code structure is achieved (MC/DC for DAL A) | DAL A (MC/DC), B (decision), C (statement) |
| `ci_results.sast_findings_count` | Table A-7 | Software verification process — output of the integration process is complete and correct | DAL A, B, C |
| `reviews`, `approvals` | Table A-7 | Software verification process — verification of the outputs of the software development processes is achieved | DAL A, B, C, D |
| `integrity.sha256_hash`, `integrity.signed_by`, `integrity.signature_timestamp` | Table A-7 | Software verification process — software configuration management process outputs are under configuration control | DAL A, B, C, D |
| `traceability.test_cases`, `ci_results.test_summary` | Table A-7 | Software verification process — test cases are correct and test coverage is satisfied | DAL A, B, C |
