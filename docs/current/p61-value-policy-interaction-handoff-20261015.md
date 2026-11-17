# P6.1 Value Policy Interaction Handoff

Scope: local private user policy selection and immutable registration only.
Baseline HEAD: `35c0c4e6d7519febc66cf44e9e0280688e6fe411`.
Existing dirty files were preserved. No commit or push performed by this package.

## Root Integration

Application: `src/value_investment_agent/application/decision/value_policy_interaction.py`.
HTTP adapter: `src/value_investment_agent/presentation/web_api/value_policy_routes.py`.

```python
from value_investment_agent.application.decision.value_policy_interaction import (
    ValuePolicyInteractionService, PolicyPrincipal, PERMISSION,
)
from value_investment_agent.presentation.web_api.value_policy_routes import (
    register_value_policy_routes,
)

register_value_policy_routes(
    api,
    sessions=session_state,
    principal_resolver=resolve_policy_principal,
    get_service=get_value_policy_service,
    port=port,
)
```

Use the SAME existing `LocalOperatorSession` as private routes. The trusted
resolver returns `PolicyPrincipal(actor_id, frozenset({PERMISSION}))` only for an
authenticated local owner authorized to select their own investment policy.
`PERMISSION = "value_policy:confirm"`; this never grants a research reviewer role.
No actor, role, receipt path, root, or isolation flag is accepted from request JSON.
The factory is called only after authentication and permission checks.

The factory constructs either:

```python
ValuePolicyInteractionService(
    project,
    storage_relative=".tmp/value-policy-review/p61-ui",
    isolated=True,
)
# Local private review, outside any public publication chain:
ValuePolicyInteractionService(
    project,
    storage_relative="runtime/value-policy-review/local-owner",
    isolated=False,
)
```

Alternatively pass `service=instance`, mutually exclusive with `get_service`.
No private journal root resolution occurs. The isolated journal can remain
`.tmp/p61-ui/TEST_ONLY.jsonl`; policy records are separate immutable objects.
Both `.tmp/` and `runtime/` are already ignored by Git. No public registry pointer,
G3, event approval, portfolio journal, production store, or scheduler is modified.

## HTTP Contracts

Every endpoint uses existing `local_auth.authorize`, including session token,
loopback peer, Host and Origin checks. All responses have `Cache-Control: no-store`.
There is no anonymous endpoint for user drafts, registration, or status.
The pre-existing public GET review contains only pre-published public material.

- POST `/api/v1/value-policy-review/{symbol}/preview`: body exactly
  `effective_from`, `effective_through`, `rationale`, `dividend_coverage_risk`, `rules`.
  Each explicit rule contains `action` (`entry/add/reduce/exit`), `scenario`
  (`bear/base/bull`), `value_fraction` (decimal STRING, e.g. `0.93` for 93%),
  `comparison` (`LTE` for entry/add, `GTE` for reduce/exit), `rationale`.
  Response includes `preview_id`, `expires_at` (30 minutes), `scope`, and
  `preparation` with draft prices, policy blockers, and independent research blockers.
  Empty rules remain a blocked draft; no fraction is selected automatically.
- POST `/api/v1/value-policy-review/{symbol}/confirm`: body exactly `preview_id`,
  `acknowledged: true`, `note` (nonblank). Identity, preview hash, materials, basis,
  deadline and current permission are rechecked. A server-timestamped owner receipt,
  registry candidate and conditional plan are stored as immutable hash-addressed
  records. An OS lock plus atomic commit marker prevents duplicate registration.
  Same confirmation can be retried after restart; conflicting notes return 409.
- GET `/api/v1/value-policy-review/{symbol}/status`: reads only the current actor's
  latest committed policy. `REGISTERED` includes a freshly derived `conditional_plan`.
  `NOT_REGISTERED` and `REVIEW_REQUIRED` return `conditional_plan: null`.
  Basis, review bindings, expiry and current inputs are rechecked each read;
  obsolete latest policy never silently falls back to an older policy.

All paths preserve `action=no_order`, `formal_eligibility=false`, and
`portfolio_eligibility=null`. Registration is not research admission.
G3 is not a prerequisite to choosing/registering a user policy. Conditional
action prices can remain null when model/price prerequisites are missing.
The draft arithmetic remains separately visible and explicitly unapproved.

## Component Interface

`web/src/components/ValuePolicyReview.tsx` retains `symbol`, with optional
`transport: ValuePolicyTransport` and `onRegistered(result)` props. No transport
preserves the existing public read-only rendering. The editor uses ordinary
Chinese fields, no selected action fractions, a server-generated price preview,
an explicit owner acknowledgement and confirmation note. Any draft edit clears
the preview and acknowledgement. Mounting calls authenticated status to restore
the private plan after refresh or service restart.

`web/src/services/valuePolicy.ts` exports request/result types and:

```tsx
const transport = {
  status: api.valuePolicyStatus,
  preview: api.previewValuePolicy,
  confirm: api.confirmValuePolicy,
};
<ValuePolicyReview symbol={symbol} transport={transport} onRegistered={onRegistered} />
```

`status(symbol): Promise<PolicyStatus>`;
`preview(symbol, selection): Promise<PolicyPreview>`;
`confirm(symbol, {preview_id, acknowledged:true, note}): Promise<PolicyRegistration>`.
Root can alternatively use `createValuePolicyTransport(existingAuthenticatedHeaders)`;
the callback returns existing authenticated headers, including `X-Local-Session`.
No second authentication engine or session storage was added.

## Existing Contract Reuse

Reuses `draft_value_price_policy`, `prepare_value_price_policy`,
`confirm_value_price_policy`, `RegisteredValueActionPolicy`, and
`build_value_action_plan`; no valuation or approval formulas are duplicated.
The existing application confirmation contract gained one optional trusted
`confirmation_loader` dependency. Its default remains `bound_object` with the
unchanged public-runtime restriction. The new service supplies a hash-verifying
reader confined to its dedicated private store, enabling `.tmp` isolation.

## Validation

Tests: `tests/test_value_policy_interaction.py`, `web/tests/value-policy.test.tsx`.
Final verification: Python targeted regression **77 passed**; Web full suite
**30 files / 153 tests passed**; TypeScript `tsc --noEmit` passed after Root wired
the three-method transport; package Prettier checks and scoped `git diff --check`
passed. Full shared-tree whitespace checks report another package's generated
`config/current-daily-public-snapshot.json`; this package did not edit that file.
Python regression command (PowerShell 7, repository root):

```powershell
$env:TEMP = 'D:\GPTProject\value-investment\.tmp'
$env:TMP = $env:TEMP
python -m pytest tests/test_value_policy_interaction.py tests/test_value_price_policy.py tests/test_value_policy_review.py tests/test_value_action_plan.py --basetemp=.tmp/p61-policy-pytest -q
```

TEMP/TMP are scoped to the test process so the inherited test trust-root guard
and repository-only temporary-file requirement both hold.

Actual public 600887 material was read, previewed using a clearly synthetic 93%
test choice, confirmed in `.tmp/value-policy-review/p61-real-public-check`, and
restored through status. Result: `PREPARED_PENDING_USER_CONFIRMATION`, then
`REGISTERED`, restored `REGISTERED`; G3/event/model blockers retained,
`formal_eligibility=false`, `portfolio_eligibility=null`,
`production_published=false`, `research_approval_changed=false`.
This is an isolated engineering proof, not a real policy or research approval.
The private derived plan may have no applicable action price with present gates.

Root owns shared wiring, actual browser acceptance, Core/Web integration and
overall product readiness. This package does not claim final product acceptance.
