# Phase 1 – JIRA Workflow Configuration

> Prerequisites: Phase 0 checklist committed. JIRA deployment model selected.
> Read only the Implementation Path that matches your Phase 0 selection.

---

## 1. Workflow Statuses and Transitions

All three deployment models share the same logical workflow. The difference is in *how* sequence enforcement is implemented.

### Status Definitions

| Status | Meaning | Allowed Actors |
|---|---|---|
| **Open** | Issue created; work not yet started | Any team member |
| **In Progress** | Active development; branch created | Assignee |
| **In Review** | Pull request open; peer review underway | Assignee, Reviewer |
| **Approved** | PR approved by qualified approver; ready to merge | jira-approvers group only |
| **Merged** | PR merged to target branch; code integrated | CI automation / Assignee |
| **Closed** | Issue resolved; evidence archived | Any team member |

### Required Transitions

```
Open          --> In Progress   (manual; any team member)
In Progress   --> In Review     (manual; assignee; requires open GitHub PR linked)
In Review     --> Approved      (manual; jira-approvers group only)
In Review     --> In Progress   (manual; reviewer sends back)
Approved      --> Merged        (automated via CI webhook; or manual fallback)
Approved      --> In Review     (manual; re-review triggered by approver)
Merged        --> Closed        (manual or automated)
Any status    --> Open          (admin only; for rejection/re-open)
```

### Certification Rationale

IEC 62304 clause 5.5 and ISO 26262-8 clause 9 both require that software items pass through a documented review and approval state before integration. The status sequence above creates the traceable state history required by those clauses. Skipping **In Review** before reaching **Approved** must be mechanically impossible, not merely policy.

---

## 2. Implementation Path A — Cloud Company-Managed

> Use this path if Phase 0 Section 1 = "Cloud Company-Managed".

Cloud Company-Managed projects do not expose the native Status History Validator. Sequence enforcement is achieved through a combination of:
1. Workflow transition conditions (limit visibility of transitions)
2. Workflow transition validators (block execution with an error)
3. Automation Rules (detect and roll back invalid state changes)

The Automation Rules layer is the primary enforcement mechanism because conditions and validators in Cloud projects have limited expressiveness compared to Data Center.

---

### 2.1 Create the Workflow in the JIRA Workflow Editor

1. Navigate to **JIRA Settings > Issues > Workflows**.
2. Click **Add workflow > Create new**.
3. Name it `Software-Change-Controlled-v1`. Add description: `Regulated workflow for IEC 62304 / ISO 26262 evidence. Do not modify without CCB approval.`
4. Add statuses in order: `Open`, `In Progress`, `In Review`, `Approved`, `Merged`, `Closed`.
   - For each status, set **Category**:
     - Open → To Do
     - In Progress → In Progress
     - In Review → In Progress
     - Approved → In Progress
     - Merged → Done
     - Closed → Done
5. Add transitions as listed in Section 1. For each transition:
   - Click the transition line > **Edit**.
   - Set **Name** to match the transition label (e.g., `Submit for Review`).
   - Set **Screen**: use `Default Screen` for transitions that require a comment; use `No screen` for automated transitions.
6. On the transition **In Review → Approved**:
   - Add **Condition**: `User is in group` → group name: `jira-approvers`
   - This hides the transition from non-approvers entirely.
7. On the transition **In Progress → In Review**:
   - Add **Validator**: `Field Required` → field: `GitHub PR URL` (custom field, see Section 2.2)
   - This blocks the transition if no PR URL is entered.
8. Click **Publish** and associate the workflow with your project scheme.

---

### 2.2 Custom Field: GitHub PR URL

1. **JIRA Settings > Issues > Custom Fields > Add custom field**.
2. Type: `URL Field`.
3. Name: `GitHub PR URL`.
4. Description: `Link to the GitHub Pull Request associated with this issue. Required before moving to In Review.`
5. Add to the screen used by the `Submit for Review` transition screen.
6. Add to the **Detail View** screen so it appears on the issue panel.

---

### 2.3 Automation Rule — Rollback-Based Sequence Enforcement

Cloud Company-Managed does not support pre-transition blocking via Status History in the workflow editor. Instead, the following Automation Rule detects an invalid transition *after* it executes and immediately rolls it back, posting a comment explaining the violation.

#### Rule 1 (Path A version): Enforce In Review Before Approved

Navigate to **Project Settings > Automation > Create rule**.

```
TRIGGER
  Issue transitioned
  From status: (any)
  To status:   Approved

CONDITION
  Advanced compare condition
  Field:    {{issue.status.name}}           [this fires after transition, so status IS Approved]
  Operator: equals
  Value:    Approved

  AND

  JQL Condition:
    issue = {{issue.key}}
    AND NOT status was "In Review"

  [Explanation: "status was" uses JIRA's historical status predicate.
   If the issue never passed through In Review, this JQL matches
   and the rule fires the rollback action.]

ACTION (execute if condition is TRUE, meaning In Review was skipped)
  Transition issue
    To status: In Progress
    Comment:   |
      [AUTOMATED ENFORCEMENT] Transition to Approved was rolled back.
      Reason: Issue must pass through "In Review" before reaching "Approved".
      Certification requirement: IEC 62304 §5.5 / ISO 26262-8 §9.
      Attempted by: {{initiator.displayName}} at {{now.format("yyyy-MM-dd HH:mm:ss z")}}.
      Action required: Open a GitHub PR, link it in the "GitHub PR URL" field,
      then submit for review via the "Submit for Review" transition.

  Create audit log comment:
      SEQUENCE_VIOLATION | issue={{issue.key}} | attempted_by={{initiator.accountId}}
      | from={{issue.previousStatus.name}} | to=Approved | rolled_back_to=In Progress
      | timestamp={{now.format("yyyy-MM-dd'T'HH:mm:ssXXX")}}
```

#### Rule 2 (Path A version): Enforce Approved Before Merged

```
TRIGGER
  Issue transitioned
  To status: Merged

CONDITION
  JQL Condition:
    issue = {{issue.key}}
    AND NOT status was "Approved"

ACTION (if condition TRUE)
  Transition issue
    To status: In Review
    Comment:   |
      [AUTOMATED ENFORCEMENT] Transition to Merged was rolled back.
      Reason: Issue must reach "Approved" status before merging.
      Attempted by: {{initiator.displayName}} at {{now.format("yyyy-MM-dd HH:mm:ss z")}}.

  Create audit log comment:
      SEQUENCE_VIOLATION | issue={{issue.key}} | attempted_by={{initiator.accountId}}
      | attempted_to=Merged | rolled_back_to=In Review
      | timestamp={{now.format("yyyy-MM-dd'T'HH:mm:ssXXX")}}
```

---

### 2.4 Acceptance Criteria (Path A)

See Section 5 for the unified acceptance criteria checklist.

---

## 3. Implementation Path B — Data Center

> Use this path if Phase 0 Section 1 = "Data Center".

Data Center exposes the full validator framework including the native **Status History Validator** and **ScriptRunner** for custom Groovy validators. Pre-transition blocking is the primary enforcement mechanism; no rollback is needed.

---

### 3.1 Create the Workflow

Follow the same steps as Section 2.1 with one difference: in Data Center the workflow editor exposes a **Validators** tab on each transition in addition to Conditions.

---

### 3.2 Status History Validators

#### On the transition "In Review → Approved"

1. Open the workflow in the **Diagram** view.
2. Click the **In Review → Approved** transition arrow.
3. Select the **Validators** tab > **Add validator**.
4. Choose **Previous Status Validator** (built-in).
   - Required previous status: `In Review`
   - Error message: `Transition to Approved is not permitted. The issue must have passed through "In Review". Open a PR, link it, and submit for review first.`
5. Click **Add**.

#### On the transition "Approved → Merged"

1. Click the **Approved → Merged** transition.
2. **Validators** tab > **Add validator** > **Previous Status Validator**.
   - Required previous status: `Approved`
   - Error message: `Transition to Merged is not permitted. The issue must have been Approved before merging.`
3. Click **Add**.

> **Note on "Previous Status" vs "Status History":** The built-in Data Center validator checks that the issue's *immediately preceding* status matches the required value. If your workflow allows any status to transition to Approved (e.g., via an admin shortcut), use the **Status History Validator** instead, which checks that the required status appears anywhere in the issue's history. For maximum regulatory compliance, use Status History Validator on both transitions.

---

### 3.3 Permission Validator — Approve Transition

This ensures only members of `jira-approvers` can execute the **In Review → Approved** transition, providing the segregation of duties required by IEC 62304 §5.5.5 and ISO 26262-8 §7.

1. On the **In Review → Approved** transition, **Validators** tab > **Add validator**.
2. Choose **Permission Validator**.
   - Permission: `Transition Issue` scoped to group `jira-approvers`
   - Alternatively: choose **User Is In Group** validator (available in some DC versions).
   - Group name: `jira-approvers`
   - Error message: `Only members of the jira-approvers group may approve issues. Contact your quality lead to request approval.`
3. Click **Add**.

**Creating the jira-approvers group:**
1. **JIRA Settings > User Management > Groups > Create group**.
2. Name: `jira-approvers`.
3. Add qualified approvers. Document membership in your Quality Management System.

---

### 3.4 ScriptRunner Custom Validator — Linked GitHub PR Check

This validator runs before the **In Progress → In Review** transition and blocks it if the `GitHub PR URL` custom field is empty.

1. Install ScriptRunner for JIRA (Data Center) from Atlassian Marketplace.
2. On the **In Progress → In Review** transition, **Validators** tab > **Add validator** > **Script Validator** (ScriptRunner).
3. Paste the following Groovy script:

```groovy
import com.atlassian.jira.component.ComponentAccessor
import com.atlassian.jira.issue.fields.CustomField

// Retrieve the custom field by name
def customFieldManager = ComponentAccessor.getCustomFieldManager()
CustomField prUrlField = customFieldManager.getCustomFieldObjects(issue)
    .find { it.name == "GitHub PR URL" }

if (prUrlField == null) {
    // Field not found on this issue type — fail safe
    invalidField("Configuration error: 'GitHub PR URL' custom field not found on this issue.")
    return
}

def prUrl = issue.getCustomFieldValue(prUrlField)

if (prUrl == null || prUrl.toString().trim().isEmpty()) {
    invalidField(
        "Transition to 'In Review' requires a linked GitHub Pull Request. " +
        "Enter the PR URL in the 'GitHub PR URL' field before submitting for review."
    )
    return
}

// Optional: validate URL format matches expected GitHub PR pattern
def pattern = ~/https:\/\/github\.com\/[^\/]+\/[^\/]+\/pull\/\d+/
if (!(prUrl.toString() ==~ pattern)) {
    invalidField(
        "The value in 'GitHub PR URL' does not appear to be a valid GitHub PR URL. " +
        "Expected format: https://github.com/<org>/<repo>/pull/<number>"
    )
    return
}

// All checks passed — validator succeeds (no invalidField call = success)
```

4. Set **Error message** (fallback): `A valid GitHub PR URL is required before moving to In Review.`
5. Click **Add**.

---

### 3.5 Audit Log Configuration (Data Center)

Data Center writes workflow transition events to `atlassian-jira.log` and the built-in audit log.

1. **JIRA Settings > System > Audit log**.
2. Ensure **Workflow** category events are enabled.
3. Configure log retention to meet your certification requirement (minimum 7 years for IEC 62304 Class C).
4. If using a SIEM, configure `log4j` appender or syslog forwarding to ship `atlassian-jira.log` to your log aggregator.

---

### 3.6 Acceptance Criteria (Path B)

See Section 5 for the unified acceptance criteria checklist.

---

## 4. Implementation Path C — Cloud Team-Managed

> Use this path if Phase 0 Section 1 = "Cloud Team-Managed".

### Strong Recommendation: Migrate to Company-Managed

Cloud Team-Managed projects do not support:
- Workflow editor (status transitions are simplified and non-configurable)
- Permission Validators
- Transition Conditions
- Custom validators of any kind

For IEC 62304 Class B/C or ISO 26262 ASIL C/D, a Team-Managed project **cannot** provide the mechanical sequence enforcement required by those standards. An auditor will not accept Automation Rules alone as equivalent to workflow-enforced gating when the workflow itself has no enforcement capability.

**Recommended action:** Convert the project to Company-Managed before implementing any workflow controls.

To convert:
1. **Project Settings > General**.
2. Under **Project type**, click **Switch to company-managed project**.
3. Note: this action is irreversible. Back up all issue data first.
4. After conversion, follow Implementation Path A.

---

### 4.1 Fallback: Automation Rules Only (Team-Managed)

If conversion is not immediately possible, implement the same Automation Rules as Path A (Section 2.3, Rules 1 and 2). This provides rollback-based enforcement with the following documented limitations:

| Limitation | Impact |
|---|---|
| Brief window between invalid transition and rollback | A user can read "Approved" status for seconds before rollback |
| No transition conditions (non-approvers see all transitions) | Relies entirely on automation for enforcement |
| No custom field validators on transitions | PR URL can be empty when submitting for review |
| Automation Rules can be disabled by project admins | Requires access control on automation settings |

**Document these limitations in your Software Development Plan and obtain sign-off from your quality lead before proceeding.**

---

## 5. Acceptance Criteria Checklist

Complete this checklist after implementing your chosen path. Each item must be tested with evidence (screenshot or test run log) attached to the commissioning issue.

### Workflow Structure

- [ ] All six statuses (Open, In Progress, In Review, Approved, Merged, Closed) exist in the project
- [ ] Status categories are set correctly (To Do / In Progress / Done)
- [ ] All required transitions are present and named consistently with this document

### Sequence Enforcement — In Review Before Approved

- [ ] Test: Create issue. Attempt to transition directly from In Progress to Approved.
  - Path A/C: Transition executes then rolls back within 30 seconds; comment posted with SEQUENCE_VIOLATION message
  - Path B: Transition is blocked before execution; error message displayed
- [ ] Test result recorded: `___________________________` (pass/fail + date)
- [ ] Evidence artifact committed: [ ] Yes (commit: `_______`)

### Sequence Enforcement — Approved Before Merged

- [ ] Test: Create issue. Transition to In Review. Attempt to transition directly to Merged (skipping Approved).
  - Path A/C: Rolls back with comment
  - Path B: Blocked before execution
- [ ] Test result recorded: `___________________________`
- [ ] Evidence artifact committed: [ ] Yes (commit: `_______`)

### Approver Group Enforcement

- [ ] `jira-approvers` group exists and is populated
- [ ] Test: Log in as a user NOT in jira-approvers. Attempt the In Review → Approved transition.
  - Path A: Transition is hidden (condition) OR rolls back if executed via API
  - Path B: Blocked by Permission Validator
  - Path C: Rolls back via Automation Rule
- [ ] Test result recorded: `___________________________`

### GitHub PR URL Enforcement

- [ ] `GitHub PR URL` custom field exists and appears on the transition screen
- [ ] Test: Attempt to move issue from In Progress to In Review with empty PR URL field.
  - Path A: Blocked by Field Required validator
  - Path B: Blocked by ScriptRunner validator
  - Path C: Automation Rule rolls back or comment posted
- [ ] Test result recorded: `___________________________`

### Audit Trail

- [ ] Transition events appear in JIRA audit log (or Automation Rule history for Cloud)
- [ ] Audit log entries include: issue key, actor, from-status, to-status, timestamp
- [ ] Log retention period configured and documented: `_______` years
- [ ] (Data Center only) Log forwarding to SIEM verified: [ ] Yes [ ] N/A

### Sign-Off

| Name | Role | Date | Signature |
|---|---|---|---|
| | Quality Lead | | |
| | JIRA Administrator | | |
| | Development Lead | | |

---

> After all checklist items are complete and signed, proceed to `phase1-jira/automation-rules-reference.md` for full rule specifications, then continue to Phase 2 (GitHub branch protection and CI pipeline configuration).
