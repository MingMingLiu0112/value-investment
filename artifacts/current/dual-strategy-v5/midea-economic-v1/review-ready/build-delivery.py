"""Bounded delivery of unregistered Midea research using the existing archive."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src/value_investment_agent").is_dir())
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.application.product.common import load_json_object, sha256_file, write_new_bytes, write_new_json
from value_investment_agent.application.product.source_bound_inputs import source_catalog_sha256, verify_package_local_sources
from value_investment_agent.application.product.research_case import build_research_case_for_symbol
from value_investment_agent.application.product.workbench import build_current_workbench_for_symbol
from value_investment_agent.application.product.research_review_packet import build_research_review_packet
from value_investment_agent.application.product.research_reviews import build_research_review_model_context, prepare_pending_review_intake
from value_investment_agent.application.product.pending_research_candidate import verify_pending_research_candidate
from value_investment_agent.application.product.research_draft import _validate_draft, _verify_bound_draft
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.application.product.research_review_wizard import preview_pending_review_response
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.m1_valuation_package_builder import build_descriptor, build_research_case
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.valuation_models.residual_income import ResidualIncomeEquityValuationModel
from value_investment_agent.infrastructure.public_evidence_archive import restore_public_archive

BASE = ROOT / "artifacts/current/dual-strategy-v5/midea-economic-v1"
OUT = BASE / "review-ready"
EXISTING_ARCHIVES = [
    "artifacts/current/dual-strategy-v5/retained-research-sources/public-evidence/manifest.json",
    "artifacts/current/tl11-p4-20261014/public-evidence/manifest.json",
]


def bind(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha256_file(path))


def absolute_metadata(value, field=""):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(absolute_metadata(item, field + "." + key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(absolute_metadata(item, field + "[" + str(index) + "]"))
    elif isinstance(value, str) and (re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", value)
            or value.startswith("\\\\")):
        found.append(field)
    return found


def check_clean(runtime, archive_path, external_artifacts):
    clean = ROOT / ".tmp" / ("midea-economic-clean-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    clean.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / "src", clean / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    archive = load_json_object(archive_path, "bounded archive")
    copied = set(external_artifacts) | {archive_path.relative_to(ROOT).as_posix()}
    copied.update(item["archive_path"] for item in archive["items"])
    for name in sorted(copied):
        path = ROOT / name
        target = clean / name
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new_bytes(target, path.read_bytes())
    assert not (clean / "runtime").exists()
    clean_manifest = clean / archive_path.relative_to(ROOT)
    restored = restore_public_archive(clean, clean_manifest, clean)
    repeated = restore_public_archive(clean, clean_manifest, clean)
    assert repeated == restored
    draft_binding = bind(OUT / "public-draft.json")
    candidate_binding = bind(runtime / "candidate.json")
    # These registry files exist only in the disposable restore fixture.
    write_new_json(clean / "config/current-research-drafts.json", dict(
        schema_version="current-research-drafts-v1", action="no_order", drafts={"000333": draft_binding}))
    code = r'''
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
r=Path.cwd(); sys.path.insert(0,str(r/'src'))
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.research_draft import load_current_research_draft
from value_investment_agent.application.product.bound_draft_review import verify_bound_draft_review_candidate
from value_investment_agent.application.product.research_review_packet import project_research_review_packet
from value_investment_agent.application.product.research_reviews import prepare_pending_review_intake
from value_investment_agent.m1_valuation_package_builder import build_descriptor
b=json.loads(sys.argv[1]); path=r/b['path']; rt=path.parent
c=verify_bound_draft_review_candidate(root=r,symbol='000333',binding=b)
d=load_current_research_draft(r,'000333')
assert d is not None and d['input_verification']['economic_approval'] is False
p=json.loads((rt/'package.json').read_text(encoding='utf-8'))
desc=build_descriptor(p,root=r)
assert desc.input_sha256==c['model_context']['input_descriptor_sha256']
assert desc.as_policy()==json.loads((r/sys.argv[2]).read_text(encoding='utf-8'))['descriptor']
packet=project_research_review_packet(root=r,package_path=rt/'package.json',
 package_sha256=sha256_file(rt/'package.json'),workbench_path=rt/'workbench.json',workbench_sha256=sha256_file(rt/'workbench.json'))
assert packet==json.loads((rt/'consumed-review.json').read_text(encoding='utf-8'))
intake=prepare_pending_review_intake(root=r,candidate_path=path,candidate_sha256=b['sha256'])
assert intake['whole_model_decision'] is None
assert c['execution_status']=='NO_ACTION' and d['gates']['results']['G3_估值门'] is False
print(json.dumps(dict(status='CLEAN_RUNTIME_RESTORE_AND_BOUND_INPUT_VERIFICATION_PASS',
 descriptor_input_sha256=desc.input_sha256,candidate_sha256=b['sha256'],g3_approved=False,action='no_order')))
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, json.dumps(candidate_binding),
        (OUT / "descriptor.json").relative_to(ROOT).as_posix()], cwd=clean, capture_output=True,
        text=True, encoding="utf-8", check=False, timeout=90)
    if result.returncode:
        diagnostic = ROOT / ".tmp" / (clean.name + "-failure.txt")
        write_new_bytes(diagnostic, (result.stdout + result.stderr).encode("utf-8"))
        raise ValueError("clean restore verification failed; diagnostic retained only in .tmp")
    return dict(restore=restored, idempotent_restore=True, verification=json.loads(result.stdout),
        isolated_fixture=clean.relative_to(ROOT).as_posix(),
        source_scope="Current implementation copied into empty-runtime fixture; no original runtime fallback and no global registry changes.")


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    day = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    runtime = ROOT / "runtime" / ("midea-economic-review-ready-" + now.strftime("%Y%m%dT%H%M%S%fZ"))
    runtime.mkdir(parents=True, exist_ok=False)
    write_new_bytes(OUT / "build-delivery.py", Path(__file__).read_bytes())
    previous = load_json_object(BASE / "verification.json", "first candidate verification")
    config_before = {p: sha256_file(ROOT / p) for p in (
        "config/current-research-drafts.json", "config/user-research-workflow-v1.json",
        "config/current-company-research-registry.json", "config/research-evidence-stop-ledger-v1.json")}
    package = load_json_object(BASE / "package.json", "unregistered first package")
    original = load_json_object(ROOT / package["supersedes"]["path"], "frozen predecessor")
    # Only new redundant direct bindings are removed. The original historical receipt,
    # its classifications and all original sources/timestamps remain byte-identical.
    removed = [bind(ROOT / s["local_path"]) for s in package["sources"] if s["id"].startswith("midea-economic-history-")]
    package["sources"] = [s for s in package["sources"] if not s["id"].startswith("midea-economic-history-")]
    version = "midea-economic-review-ready-" + now.strftime("%Y%m%dT%H%M%S%fZ")
    package.update(package_version=version, descriptor_version=version, run_id=version)
    package["point_in_time"].update(research_as_of=day, computed_at=stamp, available_at=stamp)
    package["source_contract"].update(cutoff_at=stamp, source_catalog_sha256=source_catalog_sha256(package["sources"]))
    package["research_case"].update(as_of=day, generated_at=stamp, run_id=version, research_version=version)
    assert package["facts"] == original["facts"]
    assert package["sources"][:len(original["sources"])] == original["sources"]
    package_path = OUT / "package.json"
    write_new_json(package_path, package)
    local_sources = verify_package_local_sources(ROOT, package)
    desc = build_descriptor(package, root=ROOT)
    build_research_case(package["research_case"])
    write_new_json(OUT / "research-case-source.json", dict(research_case=package["research_case"]))
    build_research_case_for_symbol(root=ROOT, symbol="000333", source_path=OUT / "research-case-source.json",
        output_path=OUT / "research-case.json")
    write_new_json(OUT / "descriptor.json", dict(action="no_order", input_sha256=desc.input_sha256, descriptor=desc.as_policy()))
    model = ResidualIncomeEquityValuationModel()
    old_desc = build_descriptor(original, root=ROOT)
    old_value, new_value = model.value(old_desc.facts, old_desc.research_case), model.value(desc.facts, desc.research_case)
    for key in ("bear_value", "base_value", "bull_value", "valuation_date", "model_version"):
        assert getattr(old_value, key) == getattr(new_value, key)
    write_new_json(OUT / "shared-model-check.json", dict(action="no_order",
        original_value=json.loads(old_value.to_json()), research_candidate_value=json.loads(new_value.to_json())))
    old_runtime = ROOT / previous["runtime_directory"]
    request = load_json_object(old_runtime / "schedule-request.json", "economic scope")
    write_new_bytes(runtime / "package.json", package_path.read_bytes())
    write_new_json(runtime / "schedule-request.json", request)
    work = build_current_workbench_for_symbol(root=ROOT, symbol="000333", package_path=runtime / "package.json",
        output_path=runtime / "workbench.json", schedule_request=request,
        schedule_request_sha256=sha256_file(runtime / "schedule-request.json"))["result"]
    assert work["suggested_state"] == "NO_ACTION" and work["input_descriptor_sha256"] == desc.input_sha256
    assert work["schedule_gate"]["status"] == "ALLOW_NORMAL_RESEARCH"
    objects = verify_current_decision_workbench(work).dependency_objects
    build_research_review_packet(root=ROOT, package_path=runtime / "package.json",
        package_sha256=sha256_file(runtime / "package.json"), workbench_path=runtime / "workbench.json",
        workbench_sha256=sha256_file(runtime / "workbench.json"), output_path=runtime / "consumed-review.json")
    draft = load_json_object(BASE / "public-draft.json", "first draft")
    draft.update(run_id=version, research_version=version, research_as_of=day, available_at=stamp,
        model_input_binding=dict(package=bind(package_path), input_sha256=desc.input_sha256),
        gates=artifact_payload(objects["research_gate"])[1])
    draft["limitations"] = [v for v in draft["limitations"] if not v.startswith("新研究可得时间为")] + [
        "新版本研究可得时间为" + stamp + "，旧来源时间未改；不代表事实/事件/市场数据更新至现在。",
        "历史分配回执保留为候选研究证据；clean restore不重抽全部2014-2024年报，不证明未来分配能力。"]
    _validate_draft(draft, "000333", datetime.now(timezone.utc))
    _verify_bound_draft(ROOT, draft, datetime.now(timezone.utc))
    write_new_json(OUT / "public-draft.json", draft)
    scope = load_json_object(old_runtime / "review-scope.json", "unchanged review questions")
    write_new_json(runtime / "review-scope.json", scope)
    context = build_research_review_model_context(descriptor=desc, spec=build_research_run_spec(desc))
    input_bindings = dict(draft=bind(OUT / "public-draft.json"), package=bind(package_path), input_sha256=desc.input_sha256)
    candidate = dict(schema_version="pending-research-candidate-v1", symbol="000333", status="PENDING_REVIEW",
        action="no_order", generated_at=datetime.now(timezone.utc).isoformat(), candidate_research_as_of=day,
        financial_period=package["point_in_time"]["report_period"], model_context=context,
        model_context_scope="ACTUALLY_CONSUMED", candidate_valuation=work["valuation"],
        execution_status=work["suggested_state"], research_blockers=work["research_blockers"], schedule_gate=work["schedule_gate"],
        economic_policy_binding=bind(runtime / "review-scope.json"), review_groups=scope["human_review_groups"],
        bound_draft_inputs=input_bindings, preparation_mode="UNREGISTERED_SOURCE_BOUND_ECONOMIC_RESEARCH_REVIEW",
        approval_changed=False, research_admitted=False, price_admitted=False, canonical_written=False,
        registered_current_case_changed=False, position_guidance=None, strict_contemporaneous_pit="NOT_PROVEN",
        source_bindings=list({p.relative_to(ROOT).as_posix(): bind(p) for p in [package_path, OUT / "public-draft.json",
            ROOT / package["supersedes"]["path"], ROOT / previous["public_draft_binding"]["path"],
            *[runtime / n for n in ("package.json", "workbench.json", "consumed-review.json", "schedule-request.json", "review-scope.json")],
            *[p for p, _ in local_sources]]}.values()),
        implementation_bindings=[v for v in load_json_object(old_runtime / "candidate.json", "first candidate")["implementation_bindings"]
            if not v["path"].endswith("/build-inputs.py")] + [bind(OUT / "build-delivery.py")])
    write_new_json(runtime / "candidate.json", candidate)
    verify_pending_research_candidate(root=ROOT, path=runtime / "candidate.json", expected_sha256=sha256_file(runtime / "candidate.json"))
    write_new_json(runtime / "review-intake.json", prepare_pending_review_intake(root=ROOT, candidate_path=runtime / "candidate.json",
        candidate_sha256=sha256_file(runtime / "candidate.json")))
    write_new_json(runtime / "review-preview.json", preview_pending_review_response(root=ROOT, candidate_path=runtime / "candidate.json",
        candidate_sha256=sha256_file(runtime / "candidate.json")))
    public_objects = {}
    for name in EXISTING_ARCHIVES:
        archive = load_json_object(ROOT / name, "existing public archive")
        assert archive["private_data"] is False
        for item in archive["items"]:
            public_objects.setdefault(item["sha256"], item["archive_path"])
    archive_dir = OUT / "public-evidence"
    archive_dir.mkdir()
    needed = {v["path"]: v for v in candidate["source_bindings"] if v["path"].startswith("runtime/")}
    for path in runtime.glob("*.json"):
        needed[path.relative_to(ROOT).as_posix()] = bind(path)
    items, new_files, reused_files, inherited_metadata = [], [], [], []
    for name, item in sorted(needed.items()):
        source = ROOT / name
        assert sha256_file(source) == item["sha256"]
        if source.suffix.lower() == ".json":
            paths = absolute_metadata(load_json_object(source, "public runtime object"))
            if paths and source.parent == runtime:
                raise ValueError("absolute metadata in new runtime object " + name + ": " + str(paths))
            if paths:
                inherited_metadata.append(dict(path=name, fields=paths, original_bytes_unchanged=True))
        archived = public_objects.get(item["sha256"])
        if archived:
            assert sha256_file(ROOT / archived) == item["sha256"]
            reused_files.append(archived)
        else:
            object_path = archive_dir / "objects" / (item["sha256"] + ".bin")
            if not object_path.exists():
                write_new_bytes(object_path, source.read_bytes())
                new_files.append(object_path.relative_to(ROOT).as_posix())
            archived = object_path.relative_to(ROOT).as_posix()
        items.append(dict(original_path=name, archive_path=archived, sha256=item["sha256"], size_bytes=source.stat().st_size))
    archive_path = archive_dir / "manifest.json"
    write_new_json(archive_path, dict(schema_version="tl11-p4-public-evidence-archive-v1", action="no_order", private_data=False,
        scope="New candidate runtime plus exact directly read dependencies; no site-wide historical closure",
        items=items, originals_retained=True))
    artifacts = {v["path"] for v in candidate["source_bindings"] + candidate["implementation_bindings"]
        if v["path"].startswith("artifacts/")}
    artifacts.add((OUT / "descriptor.json").relative_to(ROOT).as_posix())
    clean = check_clean(runtime, archive_path, sorted(artifacts))
    for name, digest in config_before.items():
        assert sha256_file(ROOT / name) == digest
    pointers = dict(action="no_order", registration_performed=False,
        current_research_drafts=dict(config="config/current-research-drafts.json", key="drafts.000333", binding=bind(OUT / "public-draft.json")),
        bound_draft_review_candidates=dict(config="config/user-research-workflow-v1.json", key="bound_draft_review_candidates.000333", binding=bind(runtime / "candidate.json")))
    write_new_json(OUT / "root-registration-proposal.json", pointers)
    verification = dict(action="no_order", status="BOUNDED_PUBLIC_ARCHIVE_CLEAN_RESTORE_PASS", candidate_binding=bind(runtime / "candidate.json"),
        public_draft_binding=bind(OUT / "public-draft.json"), archive_binding=bind(archive_path), clean_restore=clean,
        descriptor_input_sha256=desc.input_sha256, new_runtime_file_count=len(list(runtime.glob("*.json"))),
        new_runtime_bytes=sum(p.stat().st_size for p in runtime.glob("*.json")), archive_restored_files=len(items),
        new_object_count=len(new_files), new_object_bytes=sum((ROOT / p).stat().st_size for p in new_files),
        reused_object_count=len(set(reused_files)), reused_object_bytes=sum((ROOT / p).stat().st_size for p in set(reused_files)),
        removed_redundant_direct_history_bindings=removed, original_case_and_first_candidate_unmodified=True,
        public_runtime_absolute_metadata_fields=[], config_pointers_changed=False, economic_parameters_validated=False,
        inherited_source_path_metadata=inherited_metadata,
        g3_approved=False, price_admitted=False, public_valuation_changed=False, scenario_inputs_unchanged=True,
        coverage="INCOMPLETE; no new event approval or current-data assertion",
        review_boundary="Root and independent review required before registering the two proposed pointers.")
    write_new_json(OUT / "verification.json", verification)
    write_new_json(OUT / "candidate-binding.json", dict(action="no_order", candidate_binding=bind(runtime / "candidate.json")))
    existing_public = load_json_object(BASE / "upload-allowlist.json", "first public allowlist")["public_files"]
    public = set(existing_public) | artifacts | set(new_files) | set(reused_files)
    public.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    public.add(archive_path.relative_to(ROOT).as_posix())
    public.update((OUT / n).relative_to(ROOT).as_posix() for n in ("delivery-allowlist.json", "delivery-manifest.json"))
    for name in public:
        assert not name.startswith("runtime/") and "build-error" not in name and "build-start" not in name
    write_new_json(OUT / "delivery-allowlist.json", dict(action="no_order", private_data=False,
        public_files=sorted(public), local_only_exclusions=load_json_object(BASE / "upload-allowlist.json", "exclusions")["local_only_exclusions"],
        required_byte_rule="artifacts/current/dual-strategy-v5/midea-economic-v1/** -text whitespace=cr-at-eol",
        note="Exact allowlist; no runtime originals, tracebacks or private credentials. Existing retained objects are reused by SHA; no implicit whole-tree upload."))
    write_new_json(OUT / "delivery-manifest.json", dict(action="no_order", private_data=False, status=verification["status"],
        pointers=pointers, archive_binding=bind(archive_path), verification_binding=bind(OUT / "verification.json"),
        files=[bind(ROOT / name) for name in sorted(public) if name != (OUT / "delivery-manifest.json").relative_to(ROOT).as_posix()]))
    return dict(status=verification["status"], pointers=pointers, archive=bind(archive_path),
        manifest=bind(OUT / "delivery-manifest.json"), new_object_bytes=verification["new_object_bytes"],
        new_object_count=len(new_files), reused_object_count=verification["reused_object_count"])


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
