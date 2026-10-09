# Architecture consolidation and bounded agent research pilot

## Authority and current state

This is an engineering work-package record, not a new investment goal or an
authorization receipt. `docs/current-stage-goal.md`, `docs/execution-status.md`,
`AGENTS.md`, the evidence policy, and frozen-path manifests remain authoritative.
D2 financial/economic admission is still open; D5 satellite is synthetic-only.
Canonical Excel, private portfolio, production database and PTA are untouched.

Baseline audit: `main` and `origin/main` both resolved to
`cc5b5461eee5531bf7f0561f0b6461a0b519fe39` before this work;
`git ls-files` counted 1,960 tracked paths. The worktree was not clean:
three goal documents and 29 untracked `docs/current/` research files belonged
to other work and were excluded from this package. `.gitignore` already covers
`runtime/`, `.tmp/`, caches, `.env`, dumps and backups; this pilot writes only
to ignored `runtime/`. The script inventory covers the existing script tree;
the v2 registry distinguishes product and engineering entrypoints. The GitHub
Core Research Gates on the baseline commit were green, but that does not
validate any new local changes.

The existing layered package, CLI registries v1/v2, script inventory, growth
baseline and frozen-path tests already provide useful governance. Wholesale
migration of scripts, historical files or root modules would break consumers or
path/hash-bound receipts. This work package leaves those paths in place.

| Candidate | Class | Binding/consumer | Action now |
| --- | --- | --- | --- |
| Frozen legacy root modules and M2-M7 evidence | HISTORICAL_FROZEN / COMPATIBILITY | Hash/path manifests and replay | Keep bytes and paths |
| `scripts/current/build_stage3_product_preview.py` | ENGINEERING | Stage-3 preview runner | Register through existing inventory; retain CLI |
| New `scripts/current/run_agent_research_pilot.py` | ENGINEERING | Explicit offline pilot | Register in CLI v2 and inventory |
| Dated `docs/current/` reports | RESEARCH_CASE / REFERENCE | Goal/status citations | Preserve; navigate through index |
| `runtime/agent-research-pilot-20261009/` | GENERATED / TEMPORARY | Local preview only | Keep ignored, do not push |

This is a prioritized migration ledger, not a claim that every tracked path is
safe to move. No legacy path was deleted or relocated in this batch. The safe
governance changes are a corrected README entry, a current-doc warning,
registration of the bounded CLI and a new dependency-boundary test.

## Ownership map

| Concern | Owner | Rule |
| --- | --- | --- |
| Research/valuation/decision facts | Existing domain and application contracts | Agent text cannot write them |
| AgentFinding schema | `domain/agent_research/contracts.py` | Non-admitted, `no_order`, pending review |
| Pinned snapshot and bounded three-role run | `application/research/agent_review/` | Read verified case and original bytes only |
| Product projection | `application/product/agent_research_surface.py` | Replays every finding before display |
| User-facing rendering | Existing read model and Excel publisher | No investment-rule recomputation |
| Pilot CLI | `scripts/current/run_agent_research_pilot.py` | Thin, explicit hash/path/output |

Dependency direction: verified evidence and ResearchCase -> read-only research
snapshot -> Fundamental/Counter-Evidence/Event findings -> replay verifier ->
Product Read Model -> noncanonical Excel preview. The formal ResearchGate,
ValuationResult, ModelValidity, PriceBridge, DecisionRecommendation and portfolio
policy remain on their existing independent path. No reverse edge is permitted.

The pilot uses `OfflineCaseReplayModel`: it republishes already source-cited
ResearchCase statements as three different review prompts. This is a runnable
orchestration/contract pilot, **not** fresh AI analysis, live event discovery or
independent validation of the underlying investment thesis. No new LLM/provider
dependencies were added. Deep Agents/LangGraph remain isolated evaluation
candidates, not production dependencies. No external project code was copied.

## Safe run

With a locally verified workbench under `runtime/`, calculate its SHA-256 and
run `python scripts/current/run_agent_research_pilot.py --symbol SYMBOL
--workbench runtime/PATH.json --workbench-sha256 HASH
--output runtime/agent-research-pilot/FINDINGS.json`.
The output is ignored by Git, source-pinned, idempotent only when the full prior
packet still matches deterministic replay, and never a formal fact or approval.
The optional `--agent-research-packet` and `--agent-research-packet-sha256`
arguments to `scripts/current/build_stage3_product_preview.py` render pending
lines only into a noncanonical preview. They do not publish to `WORKBOOK_PATH`.

For the 2026-10-08 600519 verified workbench v10, the pilot reproduced three
pending lines with `action=no_order`; packet SHA-256 is
`af6828bcee8d6ab9fbe7d7497833552802eefc04f6c5463dcf31034eca5ce83d`.
This is a local runtime observation, not an admitted production output.

## Governance backlog

- Keep frozen/hash-bound artifacts at their existing paths. Index historical
  cases before considering any move. A file-count reduction is not a goal.
- The v2 CLI registry is the supported-entry classification; v1 remains frozen
  compatibility. Regenerate the script inventory when adding a CLI.
- A future live LLM adapter needs its own isolation, cost budget, tool allowlist,
  transcript retention, licensing/security review and human evaluation before
  even a pilot result can be described as new research. No default network use.
- A verified human adjudication workflow is separate future work. This pilot
  deliberately has no promote/approve method.
