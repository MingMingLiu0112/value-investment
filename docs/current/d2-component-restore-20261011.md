# D2 bounded H component restore, 2026-10-11

Status: VERIFIED_LOCAL_COMPONENT_RESTORE, `no_order`. This is a local component-byte recovery receipt, not production readiness, human review, investment admission or system disaster recovery. HumanReview != AgentReview. No approval was created or inherited.

## Actual restored scope

The new `runtime/d2-component-restore-20261011-v1/` contains the execution script, AES-256-GCM encrypted package, source manifest and verified receipt. It snapshots 25 files / 14,608,229 bytes:

- Both actual A editable responses in `runtime/d2-human-review-inputs-20261011-v1/`. Reviewer, reviewed date and decisions remain null; these are real response-entry artifacts, not completed human judgments.
- All five files of the 600519 event closure and all nine files of the 600887 event closure. Existing v5 candidate bindings and unapproved decisions remain byte-identical. No v7 judgment is transferred to v5.
- Shared infrastructure trust-root registry implementation, operations compatibility shim, empty pinned-root config and current research review consumer. These are actual working-tree bytes on HEAD `30f4288bef61fa08196495c815c4326ba4845077`, not a claim that uncommitted integration is an approved release.
- Existing backup implementation and security policy, current publication pointer, prior publication receipt and the actual C-drive Canonical Excel.

Referenced financial/event PDFs, candidate packages and other dependencies outside this explicit inventory were not restored. This is not a self-contained reconstruction of the whole research environment. Source manifest lists every original path, archive path, size and actual SHA.

## Canonical publication boundary

Canonical snapshot SHA: `6c90ae7a24d07f5dc3cf3e05a997db1984c85fd87820248c80528979d7166900`.

The workbook is the existing 2026-10-11 publication (`20261011T090531Z` receipt), captured on 2026-10-11 before Root's upcoming new publication. It is not the older `879e…` pre-publication workbook. Pointer `as_of=2026-10-01` is historical metadata, not the backup date. The restored pointer and workbook hashes agree. Original inputs and workbook remained unchanged at restoration and independent verification.

## Recovery and key evidence

The script reuses `backup_security.encrypt_package/decrypt_package` and existing protected-private-directory handling. The old `.tmp/restore_d2_evidence_20261011.py` was read for reference and not modified. Plaintext snapshot, separate key directory and fresh isolated restore destination are under `.tmp`; their actual paths are in the receipt. Key material is not in the encrypted-package directory or source inventory and is not printed.

Existing Windows ACL enforcement independently restricts the key directory to current owner, SYSTEM and Administrators. The key file inherits only these three FullControl rules from that protected directory; its own `AreAccessRulesProtected=false` does not mean a broad parent ACL. No offsite key separation or offsite copy is claimed.

All 25 restored files passed archive authentication, SHA and size verification, followed by exact original-versus-restored byte comparison. An independent PowerShell 7 pass then rechecked all restored hashes/lengths, all current source hashes and encrypted-package SHA. No source drift occurred.

## Measured component seconds

| Component | Snapshot seconds | Restored-byte verification seconds |
| --- | ---: | ---: |
| A responses | 0.001360 | 0.000385 |
| 600519 event closure | 0.004731 | 0.001758 |
| 600887 event closure | 0.004939 | 0.001843 |
| Shared registry/consumer | 0.002648 | 0.000471 |
| Backup implementation | 0.000470 | 0.000140 |
| Publication receipt | 0.000448 | 0.000131 |
| Publication pointer | 0.000559 | 0.000184 |
| Backup policy | 0.000343 | 0.000113 |
| Canonical Excel | 0.016777 | 0.020505 |

Actual whole-package encryption: 0.275827 seconds. Actual local decrypt/extract/hash verification: 1.733700 seconds. Total component run including private ACL setup and receipt preparation: 4.274661 seconds. Per-component measurements are actual snapshot and byte-verification operations, not invented allocations of whole-archive decrypt time.

`system_rto_seconds=null`, `system_rpo_seconds=null`; production, database and offsite are all false. No production DB restore, 20-session acceptance, user acceptance, economics, materiality/model validity or price admission is asserted. NO_ACTION remains unchanged.

## Artifact hashes

| Artifact | SHA-256 |
| --- | --- |
| receipt.json | `50c4d99c730366a3555553ecc2ff49030185aa7697781f2bbb3b2dd4b10ae59a` |
| components.aesgcm | `659ee03660f2c0924c1f249b59aab574eda42387e8dc1fb9fec51e50eb1cd10f` |
| source-manifest.json | `a12f72b1c1d636e0b504f594776f7cede3559930c8546539bac86b9008fe150b` |
| restore-components.py | `3165036d94839c0514f88ea161bdb6c17df29cc3e8a612b47948be68d0f8333f` |
| Authenticated backup manifest | `41826360a14f2ac59bc089ac9d58ac093d594aaf5c1b0c4d64d418eda59d460f` |

Only this new runtime directory, this document and authorized fresh private `.tmp` staging/key/restore directories were written. No existing hash-bound script, shared implementation, research evidence, policy, publication pointer or Excel was edited. No commit or network/production operation occurred.
