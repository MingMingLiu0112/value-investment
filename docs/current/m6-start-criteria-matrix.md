# M6 Start-Criteria Matrix

Authoritative machine-readable form:
`config/m6-start-criteria-matrix-v1.json`.

Current decision:

```text
M6_OPERATIONAL = NOT_STARTED
production_authorization_requested = false
production_authorization_granted = false
shadow_start_allowed = false
decision = BLOCKED_PENDING_HARD_START_GATES
action = no_order
```

This matrix does not request production authorization. It records which
prerequisites block the first technical Shadow start, which can only be
satisfied by elapsed real market time, and which work is a later product gap or
is unrelated to Shadow start.

## Classification

| Classification | Meaning |
| --- | --- |
| `MACHINE_READY` | Repository code or a deterministic machine check can complete the item without new private input. |
| `USER_INPUT_REQUIRED` | A user-owned constraint, identity, acceptance, or private input is required. |
| `USER_AUTHORIZATION_REQUIRED` | A separate explicit authorization is required for a high-impact production action. |
| `NATURAL_TIME_REQUIRED` | Only elapsed real sessions, events, or contemporaneous evidence can satisfy the item. |
| `RESEARCH_EVIDENCE_REQUIRED` | New external or research evidence is required, without production authorization. |

## Shadow-Start Gate

| Gate | Meaning |
| --- | --- |
| `HARD_START_GATE` | Must pass before the first technical Shadow start. |
| `SOFT_PRODUCT_GAP` | Product-maturity work that does not block technical Shadow start. |
| `NATURAL_TIME_GATE` | A post-start observation gate, not a pre-start condition. |
| `NOT_RELEVANT_TO_SHADOW_START` | Not part of the current technical Shadow start contract. |

## Key Boundaries

- M3 strict contemporaneous PIT and M4 real private portfolio acceptance are
  individual hard gates because `LONG-TERM-GOAL.md` makes M1-M5 product
  acceptance an M6 prerequisite.
- The 20 real exchange sessions, one real event, and full M6 operational
  acceptance are natural-time gates. They cannot be satisfied before Shadow
  starts and historical or synthetic replay cannot count.
- The five scoped production approvals remain `null`. This matrix neither
  fills them nor asks for them now.
- `600519 NEED_MORE_EVIDENCE` and `600519` historical validation are not
  technical Shadow start gates. They remain company-specific research states.
- M7 Product Read Model and five-page candidate are now ready for review, but
  final user acceptance still does not block technical Shadow start.

The read-only engineering command is:

```powershell
python scripts/current/audit_m6_start_criteria.py
```
