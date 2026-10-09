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
path/hash-bound receipts. This work package therefore moves only three verified,
unfrozen implementations and retains their old import paths as forwarding shims.

| Candidate | Class | Binding/consumer | Action now |
| --- | --- | --- | --- |
| Frozen legacy root modules and M2-M7 evidence | HISTORICAL_FROZEN / COMPATIBILITY | Hash/path manifests and replay | Keep bytes and paths |
| `scripts/current/build_stage3_product_preview.py` | ENGINEERING | Stage-3 preview runner | Register through existing inventory; retain CLI |
| `scripts/current/run_agent_research_pilot.py` | ENGINEERING | Explicit offline/mock/opt-in provider pilot | Keep registered in CLI v2 and inventory |
| Dated `docs/current/` reports | RESEARCH_CASE / REFERENCE | Goal/status citations | Preserve; navigate through index |
| `runtime/agent-research-pilot-20261009/` | GENERATED / TEMPORARY | Local preview only | Keep ignored, do not push |

This is a prioritized migration ledger, not a claim that every tracked path is
safe to move. The prior `cdb713d` batch corrected README navigation and
registered the CLI; the present batch migrates three implementations while
preserving their compatibility imports and adds dependency-boundary tests.

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

The original `OfflineCaseReplayModel` still republishes existing ResearchCase
statements for deterministic regression; it is **not** fresh AI analysis.
The additional three-role LLM path uses distinct tasks and a replaceable
`LLMProvider` contract. `MockLLMProvider` proves the workflow without network
use. An opt-in HTTPS Chat Completions adapter uses Python's standard library,
strict JSON-schema response formatting, a bounded timeout, three sequential
requests, no tools, explicit secret environment variable and configured token/
cost ceilings. Live mode requires an explicit per-run flag and pinned config;
this work package did not invoke it or spend API credits. Deep Agents/LangGraph
would add runtime and checkpoint dependencies without improving this bounded
read-only pilot, so neither was installed. No external project code was copied.

The 2026-10-09 incremental migration moved `evidence_dependencies.py` into
`domain/research/` and `provider_scope.py` / `roe_scope.py` into
`infrastructure/market_data/`. Root modules now forward only, with identity
tests; frozen modules, path/hash-bound evidence and older script paths remain.
Architecture tests reject domain I/O imports, agent Excel/DB/shell imports and
new root business implementations. They run in the existing Core test suite.

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

For a no-network model rehearsal, add `--mode mock --mock-responses
tests/fixtures/agent_research_mock_600519.json --mock-responses-sha256 HASH`
and use a **new** runtime output path. The fixture must contain three distinct
role objects. The producer validates JSON, evidence IDs, original bytes,
available-at dates and optional expiry, then stores raw responses and their
validated pending findings. The product projection revalidates those bytes and
findings without expecting identical regenerated wording. An existing output is
reused only when its research and provider-input fingerprints match.

`--mode live` additionally requires `--provider-config PATH
--provider-config-sha256 HASH --authorize-paid-api` and a dedicated secret in
the configured environment variable. `config/agent-research-provider.example.json`
shows the fields, not current pricing or an approved model. The user must review
provider terms, actual model support, rate card and public-source transmission
before authorizing any real call. Configured cost caps are estimates, not a
provider billing guarantee. Neither model output nor the mock preview is an
admitted fact, ResearchGate pass, decision upgrade or order.

For the 2026-10-08 600519 verified workbench v10, the pilot reproduced three
pending lines with `action=no_order`; packet SHA-256 is
`af6828bcee8d6ab9fbe7d7497833552802eefc04f6c5463dcf31034eca5ce83d`.
This is a local runtime observation, not an admitted production output.

## Governance backlog

- Keep frozen/hash-bound artifacts at their existing paths. Index historical
  cases before considering any move. A file-count reduction is not a goal.
- The v2 CLI registry is the supported-entry classification; v1 remains frozen
  compatibility. Regenerate the script inventory when adding a CLI.
- Before a real-provider trial, confirm external-data licensing, source-data
  transmission policy, model/schema compatibility, cost rate card, transcript
  retention and human evaluation. No default network use or current authorization.
- A verified human adjudication workflow is separate future work. This pilot
  deliberately has no promote/approve method.
