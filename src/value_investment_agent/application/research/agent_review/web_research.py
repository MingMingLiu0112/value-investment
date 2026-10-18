"""Read a server-registered public research packet; never run or admit research."""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .snapshot import load_research_snapshot
from .llm_pilot import MOCK_SCOPE, LIVE_SCOPE
from ...product.agent_research_surface import project_verified_agent_packet


REGISTRY_PATH = "config/current-agent-research.json"
REGISTRY_SCHEMA = "web-agent-research-registry-v1"
SCHEMA = "web-agent-research-v1"
OFFLINE_SCOPE = "OFFLINE_REPLAY_NOT_NEW_LLM_RESEARCH"
MODES = {OFFLINE_SCOPE: "OFFLINE_REPLAY", MOCK_SCOPE: "MOCK", LIVE_SCOPE: "LIVE"}
CHINA = ZoneInfo("Asia/Shanghai")
MAX_JSON = 8 * 1024 * 1024
MAX_SOURCE = 32 * 1024 * 1024


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _raw(path, limit):
    if path.stat().st_size > limit:
        raise ValueError("Public research file exceeds bounds")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Public research file exceeds bounds")
    return raw


def _json(raw):
    value = json.loads(raw, object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError("Public research object required")
    return value


def _public_path(root, value, *, runtime_only=False):
    if not isinstance(value, str) or "\\" in value or ":" in value:
        raise ValueError("Canonical public relative path required")
    path = PurePosixPath(value)
    if (not value or not path.parts or path.is_absolute() or path.as_posix() != value or ".." in path.parts
            or path.parts[0] not in ({"runtime"} if runtime_only else {"runtime", "artifacts", "config", "docs"})
            or any(any(word in part.lower() for word in ("private", "credential", "secret", "journal", ".env"))
                   for part in path.parts)):
        raise ValueError("Path is not a public research artifact")
    target = root.joinpath(*path.parts)
    if target.resolve() != target:
        raise ValueError("Public research path cannot redirect through links")
    return target


def _binding(root, ref, *, runtime_only=True):
    if (not isinstance(ref, dict) or set(ref) != {"path", "sha256"}
            or not isinstance(ref["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])):
        raise ValueError("Exact public path/hash binding required")
    return _public_path(root, ref["path"], runtime_only=runtime_only)


def _time(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("Research timestamp is naive or future")
    return stamp


def _empty(symbol, status, reason):
    return {"schema_version": SCHEMA, "symbol": symbol, "status": status, "reason": reason,
            "scope": None, "mode": None, "findings": [], "sources": [],
            "action": "no_order", "eligibility": False, "admitted": False,
            "formal_fact_count": 0, "approval_count": 0, "decision_changed": False}


def read_web_agent_research(root: Path, *, symbol: str, now: datetime) -> dict:
    """Replay only exact server-owned registry bindings, with no file writes.

    Registry keys: schema_version, action, cases. Each six-digit case has exactly
    packet:{path,sha256}, workbench:{path,sha256}, scope (the existing packet scope).
    VERIFIED means local bytes/contracts, never verified economic claim semantics.
    An absent registry/case is NOT_CONNECTED; rejected evidence is UNAVAILABLE.
    """
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("Exact symbol required")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Aware server clock required")
    root = Path(root).resolve()
    try:
        registry_path = _public_path(root, REGISTRY_PATH)
        if not registry_path.exists():
            return _empty(symbol, "NOT_CONNECTED", "REGISTRY_NOT_REGISTERED")
        registry_raw = _raw(registry_path, 64 * 1024)
        registry = _json(registry_raw)
        if (set(registry) != {"schema_version", "action", "cases"}
                or registry["schema_version"] != REGISTRY_SCHEMA or registry["action"] != "no_order"
                or not isinstance(registry["cases"], dict) or len(registry["cases"]) > 100):
            raise ValueError("Invalid public Agent registry")
        for key, entry in registry["cases"].items():
            if (not re.fullmatch(r"[0-9]{6}", key) or not isinstance(entry, dict)
                    or set(entry) != {"packet", "workbench", "scope"} or entry["scope"] not in MODES):
                raise ValueError("Invalid public Agent registry case")
            _binding(root, entry["packet"])
            _binding(root, entry["workbench"])
        entry = registry["cases"].get(symbol)
        if entry is None:
            return _empty(symbol, "NOT_CONNECTED", "SYMBOL_NOT_REGISTERED")
        packet_path = _binding(root, entry["packet"])
        workbench_path = _binding(root, entry["workbench"])
        tracked = {registry_path: (hashlib.sha256(registry_raw).hexdigest(), 64 * 1024)}
        objects = []
        for ref, path in ((entry["packet"], packet_path), (entry["workbench"], workbench_path)):
            raw = _raw(path, MAX_JSON)
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                raise ValueError("Registered research byte hash mismatch")
            tracked[path] = (ref["sha256"], MAX_JSON)
            objects.append(_json(raw))
        packet, workbench = objects
        if (packet["symbol"] != symbol or packet["scope"] != entry["scope"]
                or packet["workbench_path"] != entry["workbench"]["path"]
                or packet["workbench_sha256"] != entry["workbench"]["sha256"]
                or workbench.get("symbol") != symbol or workbench.get("action") != "no_order"):
            raise ValueError("Packet and registered workbench differ")
        if any(type(packet.get(key)) is not int or packet[key] != 0
               for key in ("formal_fact_count", "approval_count")):
            raise ValueError("Packet cannot admit facts or approvals")
        _time(packet["generated_at"], now)
        if date.fromisoformat(packet["research_as_of"]) > now.astimezone(CHINA).date():
            raise ValueError("Research cutoff is in the future")
        if "generated_at" in workbench:
            _time(workbench["generated_at"], now)
        # Preflight all paths that the existing snapshot/context verifier will open.
        originals = list(workbench["source_verification"]["sources"])
        for artifact in workbench["artifact_bundle"]["artifacts"]:
            _time(artifact["identity"]["available_at"], now)
            _time(artifact["created_at"], now)
            if artifact["identity"]["artifact_type"] == "research_case":
                case = _json(artifact["canonical_payload"])
                _time(case["generated_at"], now)
                originals.extend(case["evidence_refs"])
        context = packet.get("source_context")
        if context is not None:
            originals.extend(context["excerpts"])
        total = 0
        for original in originals:
            # Existing snapshots normalize Windows source separators. Preserve
            # their original bytes; registry/packet bindings remain canonical.
            ref = {"path": original["path"].replace("\\", "/"), "sha256": original["sha256"]}
            path = _binding(root, ref, runtime_only=False)
            if path not in tracked:
                size = path.stat().st_size
                total += size
                if size > MAX_SOURCE or total > 64 * 1024 * 1024:
                    raise ValueError("Public source budget exceeded")
            elif tracked[path][0] != ref["sha256"]:
                raise ValueError("Conflicting source binding")
            tracked[path] = (ref["sha256"], MAX_SOURCE)
            if original.get("available_at") is not None:
                _time(original["available_at"], now)
        snapshot = load_research_snapshot(root=root, workbench=workbench_path,
            expected_sha256=entry["workbench"]["sha256"], symbol=symbol)
        # The existing projector dispatches offline replay vs verify_llm_packet,
        # including exact source-context verification and semantic quality checks.
        payload = {"as_of": snapshot.as_of.isoformat(), "generated_at": now.isoformat(),
                   "companies": [{"symbol": symbol}], "audit": {"evidence": []}}
        project_verified_agent_packet(payload, root=root, path=packet_path,
                                      expected_sha256=entry["packet"]["sha256"])
        views = payload["companies"][0]["agent_research"]
        counts = Counter(view["role"] for view in views)
        if set(counts) != {"FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT"} or any(n > 2 for n in counts.values()):
            raise ValueError("All three bounded roles required")
        if len(views) != len(packet["findings"]):
            raise ValueError("Packet projection differs")
        for view, finding in zip(views, packet["findings"]):
            view.update(finding_id=finding["finding_id"], confidence=finding["confidence"],
                        proposed_follow_up=finding["proposed_follow_up"])
        sources = payload["audit"]["evidence"]
        for source in sources:
            url = source.get("source_url")
            if url is not None:
                parsed = urlsplit(url)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Unsafe public source link")
        # Detect source/registry replacement during snapshot and excerpt replay.
        for path, (digest, limit) in tracked.items():
            _public_path(root, path.relative_to(root).as_posix())
            if hashlib.sha256(_raw(path, limit)).hexdigest() != digest:
                raise ValueError("Research binding changed during read")
        result = _empty(symbol, "VERIFIED", "LOCAL_BYTES_AND_CONTRACTS_VERIFIED_NOT_CLAIM_APPROVAL")
        result.update(scope=packet["scope"], mode=MODES[packet["scope"]],
            research_as_of=snapshot.as_of.isoformat(), generated_at=packet["generated_at"],
            checked_at=now.isoformat(), model_id=packet["model_id"], prompt_version=packet["prompt_version"],
            research_input_fingerprint=snapshot.input_fingerprint,
            bindings={"registry": {"path": REGISTRY_PATH, "sha256": hashlib.sha256(registry_raw).hexdigest()},
                      "packet": entry["packet"], "workbench": entry["workbench"]},
            findings=views, sources=sources)
        return deepcopy(result)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return _empty(symbol, "UNAVAILABLE", "REGISTERED_RESEARCH_VERIFICATION_FAILED")
