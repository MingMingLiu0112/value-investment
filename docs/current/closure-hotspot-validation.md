# Hotspot Structure Validation (W7)

`action=no_order`. Current evidence pointer:
`config/current-hotspot-structure-validation.json`.

## Frozen v3 package

- Manifest:
  `artifacts/current/hotspot-structure-validation-20261017-v3/manifest.json`
  SHA-256 `3b8e10f821d986e83c5caa0c7302638b533f994aa738162ca00b62223f05873b`.
- Validation:
  `artifacts/current/hotspot-structure-validation-20261017-v3/validation.json`
  SHA-256 `c971fb4c7a01f0d869a8322acd2bfc0b40c6b55526251730182872c0ac3d95f5`.
- Report:
  `artifacts/current/hotspot-structure-validation-20261017-v3/report.md`
  SHA-256 `97c6af9d8fe36df2b202398029b6930b2e3be908318ed7165cf4bc155cd68de0`.
- Evidence digest:
  `a65fc7002cac4b57da746ced01f7ce5a5417712e7e1a38777bc90717e4f754dd`.

v1 and v2 remain immutable historical packages and are marked superseded by the
current pointer. The v3 schema carries the bound case's
`current_reference_price` and the writer rejects a candidate close that does
not equal that case price.

## Actual result

- Selection date: 2026-10-16.
- Candidate pool: 10 symbols across 10 industries.
- Bound structure assessments: 1.
- Unassessed members: 9, all without a complete same-date daily/60-minute/15-
  minute case.
- Current structural result: 600150 is `ACTIVE_ONLY`; it is not a BUY/ADD.
- Conflict or rejected cases: 7, including the preserved 601318, 300059 and
  600030 negative cases.
- Incomplete live attempt: retained as non-evidence and marked
  `used_as_evidence=false`.

## Why strategy validation is not passed

The current source report used ranking rule v2, while the replay uses later
rule v3. The artifact therefore records
`RETROSPECTIVE_RESEARCH_EXTENSION` and
`future_rule_version_used=true`. Rule PIT and classification PIT remain
`NOT_PROVEN`; costed walk-forward, untouched OOS and natural-time shadow also
remain unfinished.

```text
STRATEGY_VALIDATION=NOT_PROVEN
FORMAL_ELIGIBILITY=false
PORTFOLIO_ELIGIBILITY=null
```

