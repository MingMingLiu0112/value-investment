"""Load the current independently authorized hotspot evidence, never value G3."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ...domain.hotspot.independent_admission import HotspotGateEvidence, evaluate_independent_hotspot
from ...infrastructure.evidence.trust_root_registry import require_pinned_trust_root

POINTER = "config/current-hotspot-independent-admission-v1.json"
PURPOSE = b"value-investment:independent-hotspot-release:v1\x00"
SOURCE_SCHEMA = "independent-hotspot-source-evidence-v1"
_KNOWLEDGE_TIMES = frozenset({"available_at", "known_at", "retrieved_at", "fetched_at",
    "generated_at", "evaluated_at", "registered_at", "computed_at", "reviewed_at"})


def _source_semantics(document, *, source, gate, payload) -> bool:
    """A signature authenticates a claim; it cannot override its cited evidence."""
    cutoff = _time(source["available_at"])
    def inspect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in _KNOWLEDGE_TIMES and item is not None:
                    if not isinstance(item, str) or _time(item) > cutoff:
                        raise ValueError("Source internal availability exceeds declared availability")
                if gate["gate"] == "strategy_validation" and gate["status"] == "PASS":
                    if key in {"strict_pit_admitted", "strict_oos_admitted", "actual_sample_accepted"} and item is not True:
                        raise ValueError("Source contradicts strategy validation admission")
                    if key == "strategy_validation" and (not isinstance(item, str) or item not in {"PASS", "PASSED"}):
                        raise ValueError("Source contradicts strategy validation admission")
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
    inspect(document)
    if not isinstance(document, dict):
        return False
    for name in ("symbol", "rule_version"):
        if name in document and document[name] != payload[name]:
            raise ValueError("Source security or rule context mismatch")
    if document.get("schema_version") != SOURCE_SCHEMA:
        return False
    references = document.get("evidence_bindings")
    declared = {(row["path"], row["sha256"]) for row in gate["source_bindings"]
                if row["path"] != source["path"]}
    if (not isinstance(references, list) or not references
            or any(not isinstance(row, dict) or set(row) != {"path", "sha256"}
                   or (row["path"], row["sha256"]) not in declared for row in references)):
        raise ValueError("Typed evidence must cite the gate's independently bound raw sources")
    if (document.get("action") != "no_order" or document.get("namespace") != payload["namespace"]
            or document.get("symbol") != payload["symbol"]
            or document.get("rule_version") != payload["rule_version"]
            or document.get("gate") != gate["gate"] or document.get("status") != gate["status"]
            or _time(document.get("available_at")) > cutoff
            or _time(document.get("expires_at")) < _time(gate["expires_at"])):
        raise ValueError("Typed source gate context or validity mismatch")
    if gate["gate"] == "strategy_validation" and gate["status"] == "PASS":
        if any(document.get(name) is not True for name in
               ("strict_pit_admitted", "strict_oos_admitted", "actual_sample_accepted")):
            raise ValueError("Strategy source requires verified PIT, OOS and accepted sample")
        if document.get("strategy_validation") not in ("PASS", "PASSED"):
            raise ValueError("Strategy source is not validated")
    return True


def canonical_payload(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _read_bytes(root: Path, binding: dict) -> bytes:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("Independent hotspot requires an exact file binding")
    name = binding["path"]
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Independent hotspot evidence requires a relative path")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Independent hotspot evidence escapes repository")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("Independent hotspot evidence hash mismatch")
    return raw


def _read(root: Path, binding: dict) -> dict:
    value = json.loads(_read_bytes(root, binding))
    if not isinstance(value, dict):
        raise ValueError("Independent hotspot evidence requires an object")
    return value


def _time(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Independent hotspot time requires ISO text")
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("Independent hotspot time requires timezone")
    return stamp


def _contains_test_namespace(value) -> bool:
    if isinstance(value, dict):
        return (value.get("namespace") in {"TEST_ONLY", "SIMULATED"}
                if isinstance(value.get("namespace"), str) else False) or any(
                    _contains_test_namespace(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_test_namespace(item) for item in value)
    return False


def load_independent_admission(root: Path, *, symbol: str, now: datetime,
        allow_test_only: bool = False) -> dict:
    """Resolve only the server-owned current release, rechecking every read.

    A signed gate assessment is an accountable research claim, not proof of
    economic advantage. Source bindings and current release authorization must
    remain valid; personal sizing and execution permission are never granted.
    """
    path = root / POINTER
    if not path.is_file():
        return evaluate_independent_hotspot(symbol=symbol,
            strategy_rule_version="UNREGISTERED", evidence=(), now=now,
            authorization_status="MISSING")
    pointer = json.loads(path.read_bytes())
    if (not isinstance(pointer, dict) or set(pointer) != {"schema_version", "action", "items"}
            or pointer["schema_version"] != "current-hotspot-independent-admission-v1"
            or pointer["action"] != "no_order" or not isinstance(pointer["items"], list)):
        raise ValueError("Independent hotspot current release registry invalid")
    seen = set()
    for row in pointer["items"]:
        if (not isinstance(row, dict) or set(row) != {"symbol", "release", "trust"}
                or not isinstance(row["symbol"], str) or row["symbol"] in seen):
            raise ValueError("Independent hotspot current release identity invalid")
        seen.add(row["symbol"])
    row = next((item for item in pointer["items"] if item["symbol"] == symbol), None)
    if row is None:
        return evaluate_independent_hotspot(symbol=symbol,
            strategy_rule_version="UNREGISTERED", evidence=(), now=now,
            authorization_status="MISSING")
    envelope, trust = _read(root, row["release"]), _read(root, row["trust"])
    require_pinned_trust_root(trust)
    if (set(envelope) != {"payload", "signature"}
            or set(trust) != {"schema_version", "reviewer_id", "public_key", "scopes",
                              "symbols", "valid_from", "valid_until"}
            or trust["schema_version"] != "independent-hotspot-trust-root-v1"
            or trust["scopes"] != ["independent_hotspot_strategy_release"]
            or not isinstance(trust["symbols"], list) or symbol not in trust["symbols"]):
        raise ValueError("Independent hotspot trust purpose or scope invalid")
    payload = envelope["payload"]
    if (not isinstance(payload, dict) or set(payload) != {"schema_version", "action", "symbol",
            "namespace", "rule_version", "reviewer_id", "reviewed_at", "expires_at", "gates"}
            or payload["schema_version"] != "independent-hotspot-release-v1"
            or payload["action"] != "no_order" or payload["symbol"] != symbol
            or payload["reviewer_id"] != trust["reviewer_id"]
            or not isinstance(payload["gates"], list)):
        raise ValueError("Independent hotspot release context invalid")
    if payload["namespace"] not in ({"ACTUAL", "TEST_ONLY"} if allow_test_only else {"ACTUAL"}):
        raise ValueError("Test-only independent release cannot enter actual admission")
    reviewed, expiry = _time(payload["reviewed_at"]), _time(payload["expires_at"])
    if not (_time(trust["valid_from"]) <= reviewed <= now < expiry <= _time(trust["valid_until"])):
        raise ValueError("Independent hotspot release is future, expired or outside authority")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust["public_key"])).verify(
            bytes.fromhex(envelope["signature"]), PURPOSE + canonical_payload(payload))
    except (InvalidSignature, ValueError, TypeError) as error:
        raise ValueError("Independent hotspot release signature invalid") from error
    evidence, gate_sources = [], {}
    for binding in payload["gates"]:
        gate = _read(root, binding)
        if (set(gate) != {"schema_version", "action", "namespace", "symbol", "rule_version",
                         "gate", "status", "available_at", "expires_at", "source_bindings"}
                or gate["schema_version"] != "independent-hotspot-gate-assessment-v1"
                or gate["action"] != "no_order" or gate["symbol"] != symbol
                or gate["namespace"] != payload["namespace"]
                or gate["rule_version"] != payload["rule_version"]
                or not isinstance(gate["source_bindings"], list) or not gate["source_bindings"]
                or _time(gate["available_at"]) > reviewed):
            raise ValueError("Independent hotspot gate context or provenance invalid")
        typed_source = False
        source_documents = []
        for source in gate["source_bindings"]:
            if (not isinstance(source, dict)
                    or set(source) != {"path", "sha256", "namespace", "available_at"}
                    or source["namespace"] != payload["namespace"]
                    or _time(source["available_at"]) > _time(gate["available_at"])):
                raise ValueError("Independent source requires matching namespace and availability provenance")
            raw_source = _read_bytes(root, {key: source[key] for key in ("path", "sha256")})
            try:
                source_document = json.loads(raw_source)
            except (ValueError, UnicodeDecodeError):
                source_document = None
            if payload["namespace"] == "ACTUAL" and _contains_test_namespace(source_document):
                raise ValueError("Test-only source cannot enter actual admission")
            typed_source = _source_semantics(source_document, source=source,
                gate=gate, payload=payload) or typed_source
            source_documents.append(source_document)
        if payload["namespace"] == "ACTUAL" and gate["status"] == "PASS" and not typed_source:
            raise ValueError("Actual gate PASS requires typed applicable source evidence")
        if (payload["namespace"] == "ACTUAL" and gate["status"] == "PASS"
                and gate["gate"] == "strategy_validation"):
            from .independent_validation import verify_strategy_admission_sources
            verify_strategy_admission_sources(root=root, documents=source_documents,
                symbol=symbol, rule_version=payload["rule_version"],
                cutoff=_time(gate["available_at"]))
        evidence.append(HotspotGateEvidence(gate["gate"], gate["status"],
            _time(gate["available_at"]), _time(gate["expires_at"]), binding["sha256"]))
        gate_sources[gate["gate"]] = [
            {key: source[key] for key in ("path", "sha256")} for source in gate["source_bindings"]]
    result = evaluate_independent_hotspot(symbol=symbol, strategy_rule_version=payload["rule_version"],
        evidence=tuple(evidence), now=now, authorization_status="VERIFIED", namespace=payload["namespace"])
    result["authorization_binding"] = row["release"].copy()
    result["gate_source_bindings"] = gate_sources
    return result
