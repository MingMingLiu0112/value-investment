# 600519 bounded independent semantic review handoff

The three mock-provider findings were independently evaluated against the actual
20261011-real-admission-neutral-v3 packet excerpts. No provider was called.
Original PDF hashes and exact page excerpts were revalidated through the existing
packet consumer in the focused actual-artifact test. The review is non-admitting:
it does not promote facts, raise confidence, record human approval or change gates.

| Finding role | Facts | Inference | Counterevidence |
| --- | --- | --- | --- |
| FUNDAMENTAL | No new fact claim | Reasonable with limits: finance-company cash movements prevent aggregate CFO from proving distributable parent cash | Limited; H1 CFO recovery is not sustainable-payout proof |
| COUNTER_EVIDENCE | No new fact claim | Insufficient excerpt support: aggregate profit/revenue declines do not establish margin/channel causation or sensitivity | Limited; operating breakdowns are absent from the cited excerpt |
| EVENT | No new fact claim | Reasonable research question; no new disclosure or event completeness asserted | Limited; no adverse-event citations is not evidence of absence |

## Root's optional preview interface

The existing callable is backward compatible:

```python
project_verified_agent_packet(
    payload,
    root=root,
    path=root / "runtime/daily-trade-assistant/20261011-real-admission-neutral-v3/agent-packet.json",
    expected_sha256="27c1171061f9d994d379120bffb18f85511503785860a2b6a5a82809363e5dd1",
    independent_review_binding={
        "path": "config/research-reviews/600519-agent-independent-20261011.json",
        "sha256": "e150055b8bf6ec41247307c6308ffc60d7cde3710db8c7c96e3b499ed0d7f0a6",
    },
)
```

Use a fresh preview payload generated after review time
2026-10-11T05:03:29+00:00, retaining research_as_of 2026-10-08. The company must
have no existing agent_research views, as required by the prior interface.
Output is under each view's semantic_review.independent_review, with status
COMPLETED_NON_ADMITTING and separate facts/inference/counterevidence verdicts.
Human confirmation, factual verification and overall semantic-review status
remain pending. An unfavorable verdict is still a completed independent review.

The consumer checks the exact externally pinned review file, packet, finding,
finding-context and complete excerpt-object digests (canonical sorted compact
UTF-8 JSON without newline), source paths/hashes, roles, symbol and research date.
Existing packet validation checks originals, availability and source locators.
Only known verdicts and exact schemas are accepted; no review fields are merged
into facts, confidence, gates or decisions. Entire projection is atomic.

Invalid or stale review bindings raise ValueError without modifying payload.
Root may report that review failure and independently project the valid research
packet without the optional binding; this leaves independent review pending.
Do not silently manufacture a completed status or rebind this review to a new packet.

Focused validation: 42 passed, including actual packet/original revalidation,
packet/source/excerpt drift, identity mismatch, unknown verdicts, duplicate/missing
findings, escalation attempts, future review dates and atomic audit-conflict failure.
The actual-artifact test skips only when the local runtime packet is absent.
PowerShell 7 and D:/APP/Python313/python.exe were used, with process-local TEMP/TMP
and pytest basetemp under repository .tmp. No daily orchestration, renderer,
paid calls, commit, publication, human approval or formal fact promotion.
