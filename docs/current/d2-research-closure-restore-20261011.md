# D2 H research closure restore: actual results

2026-10-11. Latest successor-v3: publication-contract recovery and consumption PASS; full historical semantic closure NOT PASSED. First frozen run and successor-v2 failures remain preserved. Action `no_order`; NO_ACTION and all approval/admission scopes remain unchanged. No ResearchApplication run or candidate regeneration occurred.

## Snapshot and recovery scope

New artifacts only: `runtime/d2-research-closure-restore-20261011-v1/execute.py`, `isolated-validation.py`, `snapshot.json`, `research-closure.aesgcm`, `validation.json`, `receipt.json`, plus this document and fresh private `.tmp` source/restore folders. Existing H key was reused without printing or regenerating material. Its directory ACL was rechecked: protected DACL, only current owner, SYSTEM and Administrators FullControl.

The snapshot contains **757 source files / 135,499,655 bytes**. AESGCM archive contains **760 inventory entries**: source files plus two config inventory copies and one release Excel copy. All source files passed exact byte comparison against the frozen private stage. All 760 restored inventory hashes passed an independent PowerShell check, with zero failures.

Included in the first run: latest actual C-drive Canonical Excel; current publication pointer and publication receipt; recursively discovered hash-bound union; publication preservation/readability/visual proofs; native receipt and seven PDF exports; prior Canonical backup required by publication validation; original A responses and both event closures; financial/event raw evidence, v5/v7 candidate/package/workbench and quote dependencies; complete `src` code/data snapshot and pyproject metadata. Correction from independent audit: this first union omitted the publication source-bindings sidecar, publication input and 51 other publication sources because the traversal did not handle `source_bindings_path/source_bindings_sha256`. It was not complete publication closure. The omission is repaired only in successor-v3 below. No `.env`, private key or unrelated dataset was packaged. Python dependency binaries were not archived: existing host Python/runtime dependencies were reused.

Canonical SHA is `83908b2513e1d9cf7dbdc17f0ad6f56b7a213e94f52a3bb0398af60339ab5b29`, publication `20261011T113627Z-860eef98`. The previous `6c90…` Excel is retained as the publication-bound backup, not mislabeled as current. Restored current Excel SHA matches the restored pointer.

Shared code and dependency bytes were frozen with no source drift at snapshot completion, and Hsnapshotdone was reported before further validation. Root may edit original shared code subsequently; validation depends on frozen restored code, not later original bytes.

## Isolated validation

Child cwd and PYTHONPATH were set to the fresh restored `source` root and `source/src`; imports excluded original repo paths. Python audit hooks reject external file opens outside the restored root and Python installation, network connect/name lookup, subprocess and shell execution. This is Python application-layer enforcement, NOT OS-level isolation. No `.env` or original C-drive file was read by the child. Receipt records the actual isolated path and validator results.

**19 checks passed, 3 failed**:

| Existing validator | Actual result |
| --- | --- |
| Four S1/S5 v5/v7 candidate verifiers | 4 PASS; all PENDING_REVIEW |
| Typed ResearchCase snapshot validators | 6 PASS; 2 FAIL on old S5 registered workbenches |
| Decision artifact dependency replay | 8 PASS; all no_order |
| Publication verifier | FAIL: CANONICAL_PUBLICATION_EVIDENCE_MISMATCH |
| Actual restored Canonical bytes vs pointer | PASS |

The two old S5 workbenches have `source_verification.status=NO_LOCAL_BINDING_METADATA`; `load_research_snapshot` requires LOCAL_BYTES_VERIFIED. Their corresponding pending-candidate workbenches pass typed snapshot validation. This is an existing evidence-contract limitation, not a recovery byte mismatch. Neither old package nor status was changed.

Publication failure is a concrete portability blocker: native receipt contains seven original `D:/GPTProject/value-investment/runtime/...` absolute PDF paths. PDF bytes were recovered at equivalent relative locations, but `verify_workbook_publication` correctly rejects references outside restored-root/runtime before attempting file reads. External file denial list is empty because the validator rejected first. The receipt was not normalized, rebound or approved. Publication validation stops at this first failure; downstream publication/quote-floor checks are NOT claimed passed.

There are **605 absolute bound-reference occurrences** recorded, including provenance/lineage references. Candidate verifiers passed without original-root access; this does not prove every historical absolute reference is operative or portable.

## Remaining hash-bound closure

The recursive audit records **50 findings, 7 distinct kind/path groups**, without overwriting expected hashes:

- 39 historical references expect old Yili `cninfo-index.json` SHA `f68b7e83d77c4c1d09c8d033a6e0054c97c0ce93c9f383349388bbc2d815ceea`; actual restored snapshot is `1b2674025780741befbddb0fd4fb5e0ae309f6d8efdbb50a033bd2d8d2a6cc98`.
- Ten occurrences across five implementation files differ from older v7 daily receipt hashes: application daily_trade_assistant/daily_assets, presentation daily_trade_assistant, research_supplement_comparison and renderer. Current frozen bytes were saved exactly. Candidate-specific implementation contracts still pass; historical daily-receipt implementation identity is not fully reconstructed.
- One unresolved lineage reference: `runtime/d2-source-bound-current-20261008/package-v2-current-model.json` has `supersedes.path=package-v2.json` and hash `cbecbc59f2c615e0e82d873ed0a174b212bce87678dca38072c067b2cc9f6c5b`. Root-relative resolution finds no such file. Its intended relative base is not inferred or silently changed.

Thus current available bytes can be restored, but every historical hash expectation cannot be satisfied. No indefinite search, old-version reconstruction, binding mutation or new candidate was attempted. Full detailed origins/expected/actual hashes remain in snapshot.json.

## Actual timing

| Component operation | Seconds |
| --- | ---: |
| Source/code/dependency snapshot | 11.787939 |
| AESGCM encryption | 6.994325 |
| Private isolated decrypt/extract/hash verification | 9.419568 |
| Exact source byte comparison | 0.320820 |
| Existing validators in isolated child | 2.091325 |
| Total component run | 31.756388 |

No per-file decrypt time is invented. `system_rto_seconds=null`, `system_rpo_seconds=null`; production, database and offsite are false. This is neither economics/materiality/validity approval nor price admission, production DB recovery, 20-session evidence or user acceptance.

## Exact artifact hashes

| Artifact | SHA-256 |
| --- | --- |
| receipt.json | `65dde45580f2f1f7505a4bf759aef9e098906ea265f404c9ebb9076795a865fa` |
| snapshot.json | `827a28e2105b867fc7dc16c670ca089136179140a2788f9547583a3f780b854f` |
| validation.json | `b7daddc664f9fb8b2b37c7f45a6d0cd3972aee5c2ba927ec39a1ee859fe6c67a` |
| research-closure.aesgcm | `6ac4604b1a02e7eb97afb75a74b9e33a5230fbaa6385fcfd610ef92d2506f903` |
| Authenticated archive manifest | `090d8b1a27784a9526168b4a4493e91c91325a1ae9a4ca9f220404efe0303791` |

Execution/validator script hashes and all inventory hashes are bound in receipt/snapshot. No shared code, existing hash-bound document, policy, Excel, approval or publication pointer was edited; no commit or production/network operation was made.

## Successor-v3: publication dependency consumption closed

The uniquely authorized shared engineering change is `src/value_investment_agent/infrastructure/evidence/workbook_publication.py`, with independent `tests/test_workbook_publication_restore_mapping.py`. It adds keyword-only `original_root` to existing validation APIs. Absolute references below that explicit lexical original prefix resolve exclusively into restored-root/runtime; canonical relative paths, hash contracts, PDF deduplication and backup containment remain enforced. There is no original-root fallback or receipt normalization. Default behavior remains unchanged. Focused tests: **46 passed, 1 skipped**; directory-symlink escape test explicitly skipped for host privilege limitations. Shared src/tests are stable and released to Root for core/CI; this agent made no commit.

`successor-v2/` preserves its own actual failure: mapping alone still lacked publication source bindings/input. `successor-v3/` adds the exact existing publication sidecar, all **355 declared source bindings**, publication input/authored-page bindings, native PDF chain and publication backup. All publication-contract expected hashes match. It adds **53 data/source paths** over v2, plus two bound validation scripts: **812 source files / 151,001,621 bytes**, **815 archive entries**. Every source byte comparison passed; independent rehash of all 815 archive items returned zero failures. Publication-contract missing/drift count is **0**.

Actual consumption results: **22 PASS, 5 FAIL**, with the failures retained and classified:

- Four candidates PASS, remain PENDING_REVIEW; six Agent ResearchCase snapshots PASS; ten decision DAG replays PASS, all no_order.
- `verify_workbook_publication(..., original_root=original_repo)` PASS with quote observation floor **2026-10-09**; actual restored Canonical bytes also PASS. This is published evidence/session consumption, not current price admission.
- Default/no-mapping publication control FAIL as expected, proving the explicit mapping is necessary.
- Four old registered/source-bound workbenches fail Agent snapshot's LOCAL_BYTES_VERIFIED requirement: old S5 v5 and v7 plus 000651/600741 financial attachment workbenches present in the publication dependency set. They are preserved historical artifacts, not Agent-usable verified snapshots. Their decision replays do not upgrade source eligibility. No metadata was fabricated.

Four actual negative probes PASS_DENIED: original repo pointer file, original C-drive Canonical Excel, socket connection and subprocess creation. The child uses restored code/root only, with Python application-layer hooks; this is not an OS sandbox claim. Validation report's `external_file_denials` was captured before deliberate probes; probe records contain the subsequently rejected paths/actions. No original file read or network/process operation succeeded.

Historical lineage corrections are bounded and explicit:

- `supersedes.path=package-v2.json` is now inventoried by owner-parent-relative rule. Existing sibling bytes match `cbecbc59f2c615e0e82d873ed0a174b212bce87678dca38072c067b2cc9f6c5b`. Original supersedes JSON was not edited.
- Known retained index `runtime/company-research/m1-event-scans/20260923T050735Z/600887/cninfo-index.json` exactly matches historical `f68b7e83d77c4c1d09c8d033a6e0054c97c0ce93c9f383349388bbc2d815ceea`; it is inventoried at that retained original location. Explicit mapping records the 39 old hash expectations' byte availability. The conflicting `20260923T051018Z` index path is not overwritten, and old artifact references are not silently rebound or declared semantically verified.
- Ten old daily-generation-code hash occurrences across five files remain outside historical regeneration scope. Current restored code cannot be labeled the exact old daily producer. No Git search, regeneration or forged historical code match was performed.

Thus current publication dependencies and publication consumption are closed; all historical artifact/source eligibility and producer identity are NOT closed. HumanReview != AgentReview; v7 judgments do not inherit into v5. No approval, economics, materiality, model-validity or price admission changed. No full system readiness, production DB recovery, offsite restore or acceptance is claimed; system RTO/RPO remain null.

| Actual v3 component operation | Seconds |
| --- | ---: |
| Bounded successor snapshot | 6.106249 |
| AESGCM encryption | 7.022833 |
| Fresh private decrypt/restore/hash verification | 13.852590 |
| Exact source-byte verification | 0.513641 |
| Isolated validation and denial probes | 2.144334 |
| Total component run | 30.606321 |

| Latest artifact | SHA-256 |
| --- | --- |
| successor-v3/receipt.json | `1e6a8c05a260ab25b3ceb1fe7b4cfdeafa31b9cf0b3d1d9fd6e9b0ac9859d819` |
| successor-v3/inventory.json | `7e9a870e859acc1918341b041e1da1df1b6558c4cabf2c59539e522410a79857` |
| successor-v3/validation.json | `d20b92d6d97a1d8c14b7f7465096c0fc29367b0cbb7fa86e0973ff74af18871c` |
| successor-v3/research-closure.aesgcm | `3923dce05c842436cce39e00348c48ad32899f5492f3141bbb2c5b2698703a62` |
| v3 authenticated manifest | `b8fb490cd260fa7015ff81cc1cd7274716eaebdd90d0a18934e492017769b118` |
| New shared publication verifier | `592b987de26a10eef2b03becc2819492913def925814c7ad652cdf7e64e7afd9` |
| Focused independent tests | `a7eb7b14612138ace8bed46d66f5c0ecba2b209ad3666dc5b4a12bcc30057dff` |

First receipt remains exactly `65dde45580f2f1f7505a4bf759aef9e098906ea265f404c9ebb9076795a865fa`; v2 failure receipt remains `86d2e70c97dd6679100705bc9f4e67be417e8da34d79a0bcb25308756e7069ef`. No previous runtime evidence was rewritten. Only the explicitly assigned shared module/tests and owned new runtime/document were changed; private keys and encrypted runtime are not intended for Root's code commit.
