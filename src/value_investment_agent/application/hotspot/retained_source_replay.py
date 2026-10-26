"""Explicit descriptive replay from append-only copies, never strategy admission."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from ...domain.hotspot import current_price, event_replay, price_action_plan
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from .event_replay import _availability, _bound_bytes
from .independent_admission import _contains_test_namespace


MANIFEST_SCHEMA = "hotspot-retained-source-manifest-v1"
FOLDER = "runtime/hotspot-retained-source-replays"
PUBLIC_FOLDER = "artifacts/current/dual-strategy-v5/retained-hotspot-sources"
FROZEN_RULES = {
    "src/value_investment_agent/domain/hotspot/current_price.py": current_price,
    "src/value_investment_agent/domain/hotspot/price_action_plan.py": price_action_plan,
}


def _clock(value: datetime) -> None:
    if value.utcoffset() is None:
        raise ValueError("Retained replay requires a timezone-aware clock")


def _read(root: Path, binding: dict) -> bytes:
    name = binding["path"]
    if not isinstance(name, str) or ".." in Path(name).parts or Path(name).as_posix() != name:
        raise ValueError("Retained source requires a canonical relative path")
    return _bound_bytes(root, binding)


def _document(raw: bytes, namespace: str) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Retained source must be a JSON object")
    if namespace == "ACTUAL" and _contains_test_namespace(value):
        raise ValueError("TEST_ONLY evidence cannot enter ACTUAL retained replay")
    return value


def _manifest_directory(root: Path, binding: dict, *, folders=(FOLDER, PUBLIC_FOLDER)) -> Path:
    name = binding["path"]
    if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
            or Path(name).as_posix() != name):
        raise ValueError("Retained manifest requires a canonical relative path")
    path = root / name
    directory = path.resolve().parent
    if (path.name != "manifest.json"
            or directory.parent not in {(root / name).resolve() for name in folders}
            or len(directory.name) != 32 or any(c not in "0123456789abcdef" for c in directory.name)):
        raise ValueError("Retained manifest outside append-only source directory")
    return directory


def _spec(raw: bytes, namespace: str, now: datetime, *, source_root: Path) -> dict:
    spec = _document(raw, namespace)
    event_replay.validate_spec(spec)
    registered = datetime.fromisoformat(spec["registered_at"])
    if registered.utcoffset() is None or registered > now:
        raise ValueError("Historical protocol is not yet available")
    if len(spec["cases"]) != 5 or len({row["symbol"] for row in spec["cases"]}) != 5:
        raise ValueError("Exactly five distinct retained cases required")
    rules = {row["path"]: row for row in spec["rule_bindings"]}
    for name, module in FROZEN_RULES.items():
        if name not in rules:
            raise ValueError("Running rule differs from historical protocol")
        # Archive integrity is byte-exact; only checkout CRLF/LF differences may
        # be normalized when comparing the running Python source with the archive.
        archived = _read(source_root, rules[name])
        running = Path(module.__file__).read_bytes()
        if running.replace(b"\r\n", b"\n") != archived.replace(b"\r\n", b"\n"):
            raise ValueError("Running rule differs from historical protocol")
    return spec


def _verified_case(root: Path, item: dict, namespace: str, end_date: str, now: datetime) -> tuple[dict, str]:
    binding = dict(path=item["case_path"], sha256=item["case_sha256"])
    case = _document(_read(root, binding), namespace)
    quote = case["current_reference_close"]
    bundle = _document(_read(root, dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])), namespace)
    available = _availability(case, bundle)
    acquired = datetime.fromisoformat(available)
    if acquired > now:
        raise ValueError("Retained evidence is not yet available")
    # Reverify the archived acquisition contract, never today's current close or
    # fictional historical availability. Evaluation time is recorded separately.
    verified = load_current_price_case(root=root, symbol=item["symbol"],
        case_path=Path(item["case_path"]), expected_sha256=item["case_sha256"], now=acquired)
    if verified["market_trade_date"] != end_date:
        raise ValueError("Retained case date differs from protocol end")
    return verified, available


def retain_hotspot_descriptive_sources(*, root: Path, protocol_binding: dict,
        namespace: str, now: datetime) -> dict:
    """Copy verified bytes to a fresh directory; return the externally pinnable manifest.

    The historical selection pointer is deliberately not substituted or rebound.
    This use case describes only the five identities already bound in the spec.
    """
    root = root.resolve()
    _clock(now)
    if namespace not in {"ACTUAL", "TEST_ONLY"}:
        raise ValueError("Explicit ACTUAL or TEST_ONLY namespace required")
    files = {}

    def retain(binding):
        binding = dict(path=binding["path"], sha256=binding["sha256"])
        raw = _read(root, binding)
        prior = files.get(binding["path"])
        if prior is not None and prior != raw:
            raise ValueError("Conflicting retained source bindings")
        files[binding["path"]] = raw
        return raw

    spec = _spec(retain(protocol_binding), namespace, now, source_root=root)
    for binding in spec["rule_bindings"]:
        retain(binding)
    for item in spec["cases"]:
        case = _document(retain(dict(path=item["case_path"], sha256=item["case_sha256"])), namespace)
        for source in case["source_bindings"].values():
            retain(source)
        quote = case["current_reference_close"]
        # Quote and calendar originals are embedded as raw_base64 in this bundle.
        _document(retain(dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])), namespace)
        _verified_case(root, item, namespace, spec["end_date"], now)
    for name, raw in files.items():
        _read(root, dict(path=name, sha256=sha256(raw).hexdigest()))

    directory = root / FOLDER / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    for name, raw in sorted(files.items()):
        target = directory / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        original = dict(path=name, sha256=sha256(raw).hexdigest())
        records.append(dict(original_binding=original,
            retained_binding=dict(path=target.relative_to(root).as_posix(), sha256=original["sha256"])))
    manifest = dict(schema_version=MANIFEST_SCHEMA, namespace=namespace, scope="DESCRIPTIVE",
        retained_at=now.isoformat(), historical_protocol_binding=dict(protocol_binding),
        historical_selection_status="NOT_REVALIDATED_RETAINED_CASES_ONLY",
        files=records, formal_eligibility=False, action="no_order")
    raw = (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path = directory / "manifest.json"
    with path.open("xb") as stream:
        stream.write(raw)
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())


def build_retained_descriptive_validation(*, root: Path, manifest_binding: dict, now: datetime) -> dict:
    """Reverify copies without consulting mutable config or the original runtime."""
    root = root.resolve()
    _clock(now)
    directory = _manifest_directory(root, manifest_binding)
    manifest = json.loads(_read(root, manifest_binding))
    namespace = manifest.get("namespace")
    if (manifest.get("schema_version") != MANIFEST_SCHEMA or namespace not in {"ACTUAL", "TEST_ONLY"}
            or manifest.get("scope") != "DESCRIPTIVE" or manifest.get("action") != "no_order"
            or manifest.get("formal_eligibility") is not False
            or manifest.get("historical_selection_status") != "NOT_REVALIDATED_RETAINED_CASES_ONLY"):
        raise ValueError("Invalid descriptive retained manifest")
    _document(_read(root, manifest_binding), namespace)
    retained = datetime.fromisoformat(manifest["retained_at"])
    if retained.utcoffset() is None or retained > now:
        raise ValueError("Retained copy is not yet available")
    if directory.parent == (root / PUBLIC_FOLDER).resolve():
        original = manifest["original_manifest_binding"]
        _manifest_directory(root, original, folders=(FOLDER,))
        digest = original["sha256"]
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("Invalid original manifest digest")
        exported = datetime.fromisoformat(manifest["exported_at"])
        if exported.utcoffset() is None or not retained <= exported <= now:
            raise ValueError("Public export is not yet available or predates retention")
    source_root = directory / "sources"
    originals = {}
    source_bindings = []
    for row in manifest["files"]:
        original, copy = row["original_binding"], row["retained_binding"]
        expected = (source_root / original["path"]).relative_to(root).as_posix()
        if copy != dict(path=expected, sha256=original["sha256"]) or original["path"] in originals:
            raise ValueError("Invalid retained provenance mapping")
        raw = _read(root, copy)
        _read(source_root, original)
        originals[original["path"]] = raw
        source_bindings.append(copy)
    historical = manifest["historical_protocol_binding"]
    spec = _spec(_read(source_root, historical), namespace, now, source_root=source_root)

    def required(binding):
        if binding["path"] not in originals:
            raise ValueError("Retained provenance omits a required dependency")
        return _read(source_root, binding)

    required(historical)
    for binding in spec["rule_bindings"]:
        required(binding)
    results, availability = [], []
    for item in spec["cases"]:
        case = _document(required(dict(path=item["case_path"], sha256=item["case_sha256"])), namespace)
        for source in case["source_bindings"].values():
            required(source)
        quote = case["current_reference_close"]
        required(dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"]))
        case, available = _verified_case(source_root, item, namespace, spec["end_date"], now)
        if datetime.fromisoformat(available) > retained:
            raise ValueError("Source acquisition follows retained copy")
        availability.append(available)
        results.append(dict(symbol=item["symbol"], case_binding=item, data_available_at=available,
            source_verification_at=available, historical_source_availability="NOT_CONTEMPORANEOUSLY_ARCHIVED",
            **event_replay.replay_v1(case["bars"], spec)))
    segments = [segment for row in results for segment in row["segments"].values()]
    for binding in [manifest_binding, *source_bindings]:
        _read(root, binding)
    return dict(schema_version="hotspot-retained-descriptive-validation-v1", namespace=namespace,
        scope="DESCRIPTIVE", metrics_scope="SIGNAL_PRICE_PATH_ONLY", status="PARTIAL",
        protocol_binding=dict(manifest_binding), historical_protocol_binding=historical,
        historical_selection_status=manifest["historical_selection_status"],
        rule_identity_scope="ARCHIVE_RAW_SHA256_EXACT_RUNNING_PYTHON_CRLF_TO_LF_ONLY",
        source_bindings=source_bindings, evaluated_at=now.isoformat(), retained_at=manifest["retained_at"],
        data_available_at=max(availability, key=datetime.fromisoformat),
        partitions={key: spec[key] for key in ("start_date", "development_end", "validation_start", "end_date")},
        results=results, signal_event_count=sum(s["trigger_count"] for s in segments),
        mature_five_session_count=sum(s["mature_five_session_count"] for s in segments),
        right_censored_count=sum(s["right_censored_count"] for s in segments),
        trade_count=None, execution_metrics=dict(status="UNASSESSABLE", trade_count=None,
            win_rate=None, payoff_ratio=None, net_return_distribution=None, maximum_drawdown=None,
            cost_sensitivity=None, t_plus_one_feasibility="UNKNOWN"),
        strategy_validation="NOT_PROVEN", actual_sample_accepted=False,
        strict_pit_admitted=False, strict_oos_admitted=False, prospective_oos_admitted=False,
        elapsed_real_shadow_sessions=0, formal_eligibility=False, risk_review_eligible=False,
        portfolio_eligibility=None, trade_eligible=False,
        limitations=["Historical selection and contemporaneous source availability are not revalidated",
            "Overlapping signal outcomes are price paths, not independent trades",
            "No execution, dated costs, tradability or corporate-action comparability established"],
        performance_claim_allowed=False, action="no_order")


def export_retained_descriptive_sources(*, root: Path, manifest_binding: dict, now: datetime) -> dict:
    """Publish a new immutable byte-exact copy; leave local runtime untouched.

    The original manifest binding is provenance, not a runtime dependency of the
    public copy. The new externally pinned manifest binds every exported byte.
    """
    root = root.resolve()
    _manifest_directory(root, manifest_binding, folders=(FOLDER,))
    build_retained_descriptive_validation(root=root, manifest_binding=manifest_binding, now=now)
    original = json.loads(_read(root, manifest_binding))
    sources = [(row["original_binding"], _read(root, row["retained_binding"]))
               for row in original["files"]]
    directory = root / PUBLIC_FOLDER / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    files = []
    for binding, raw in sources:
        target = directory / "sources" / binding["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        files.append(dict(original_binding=dict(binding), retained_binding=dict(
            path=target.relative_to(root).as_posix(), sha256=binding["sha256"])))
    manifest = dict(original, files=files, original_manifest_binding=dict(manifest_binding),
                    exported_at=now.isoformat())
    raw = (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path = directory / "manifest.json"
    with path.open("xb") as stream:
        stream.write(raw)
    binding = dict(path=path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())
    build_retained_descriptive_validation(root=root, manifest_binding=binding, now=now)
    return binding


def load_retained_replay_summary(*, root: Path, manifest_binding: dict, now: datetime) -> dict:
    """Root may bind this compact read model; no route or current pointer is changed."""
    report = build_retained_descriptive_validation(root=root, manifest_binding=manifest_binding, now=now)
    return {key: value for key, value in report.items() if key != "results"} | dict(
        schema_version="hotspot-retained-replay-web-summary-v1",
        status="HISTORICAL_DESCRIPTIVE_REPLAY_NOT_ADMITTED",
        reference_scope="RETAINED_CASE_PRICE_PATH_NOT_CURRENT_JUDGMENT_OR_TRADE_RETURN",
        items=[dict(symbol=row["symbol"], case_sha256=row["case_binding"]["case_sha256"],
            v1_rule_version=row["rule_version"], v1_segments=row["segments"],
            archived_v1_observation=row["last_observation"], data_available_at=row["data_available_at"])
            for row in report["results"]])
