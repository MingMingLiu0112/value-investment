# Pending Candidate Replay Handoff

Engineering: 101 related tests passed. Actual 600519 exact-input replay and a
fresh-process independent publication verification passed. Economic admission,
G3, current prices and positions are unchanged; action=no_order.

The new product implementation is `pending_candidate_replay.py`. It keeps the
entire old package byte-identical, runs the ordinary workbench and scoped review
scheduler, requires the original descriptor and valuation, and creates a new
receipt bound to current implementation bytes. It retains old sources, policy,
review groups, dates and predecessor receipt. It rejects input/implementation
drift, backdating, changed output, economic admission and stopped research.
Neither old producer code nor old receipt/publication verifiers were modified.

`pending_replay_publication.py` adds the independently verified Web supplement
manifest and `load_current_pending_replay(root=root, symbol=symbol)`. It follows
the separate version-registry pattern used by bound drafts. It does not route
through the Excel publication or pretend a stale pending candidate is a v3
source-bound draft. A registered entry must pass the entire immutable lineage;
invalid entries raise, while an absent symbol returns None.

Root integration uses the exact proposed registry document in the adjacent
JSON handoff, then calls this adapter from the existing company/decision detail
assembly. Treat its result as pending research context, leaving current
valuation, eligibility and action unchanged. Existing review intake accepts the
verified new candidate. Product integration tests verify this path; actual Web
assembly and browser acceptance remain root-owned. No canonical workbook,
canonical pointer or old publication record may be changed.

Final actual 600519 manifest:
`runtime/pending-candidate-replay-v5-final-20261021/600519/publication.json`
SHA256 `9420dbbc50a95eba349157fe099b679587000b12e2b8ff3e429e2b7dc816542e`.
The original package SHA is unchanged. Its research and valuation dates remain
2026-10-11. This deliberately does not merge the later 88.89% income enrichment
into the old economic scenarios.

600887 remains rejected before output creation: two legacy source rows record
2026-09-23 retrieval but 2026-10-11 availability. The existing source contract
correctly rejects this order. The original producer's missing-availability
fallback (lines 93-101) retained older retrieval metadata. See the JSON handoff
for exact rows and paths. A separate evidence-backed metadata correction would
need a new package version; it cannot be disguised as this frozen-input replay.

000333's current bound draft independently validates. The JSON handoff contains
a hash-guarded, three-field registry correction and evidence additions for root;
it preserves PENDING_RESEARCH and all economic approval boundaries. Shared
config/ledger changes were proposed, not applied. No hotspot/worker/Web,
sharedbatch/queue/income, Git HEAD/index or existing records were changed by this
work package. Runtime artifacts are local evidence and require preservation for
the root-owned publication; these files do not claim deployed Web acceptance.

CLI: `python scripts/current/replay_pending_candidate.py --predecessor <old receipt>
--predecessor-sha256 <old hash> --output runtime/<new unique directory>`.
The CLI never writes the current registry. Replays must use a new directory.
