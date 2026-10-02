"""Project bounded, source-anchored explanations without investment admission."""
from datetime import datetime
from pathlib import Path

from .common import load_json_object, require_inside, sha256_file
from ..historical_validation.event_source_review import prepare_event_source_review


def read_event_followup(*, root: Path, cutoff, path: Path, expected_sha256: str):
    path = require_inside(root, path, "event followup")
    if sha256_file(path) != expected_sha256:
        raise ValueError("event followup hash mismatch")
    value = load_json_object(path, "event followup")
    if (value.get("schema_version") != "research-event-followup-v1"
            or value.get("scope") != "SOURCE_ANCHORED_EXPLANATION_ONLY"
            or value.get("action") != "no_order"):
        raise ValueError("event followup cannot authorize investment")
    point = datetime.fromisoformat(value["observed_at"])
    if point.utcoffset() is None or point.date() > cutoff:
        raise ValueError("event followup observation is outside product cutoff")
    binding = value["event_scan"]
    scan = require_inside(root, root / binding["path"], "event followup scan")
    packet = prepare_event_source_review(root=root, path=scan,
        expected_sha256=binding["sha256"], symbol=value["symbol"])
    if not packet["audit"]["evidence_integrity_verified"]:
        raise ValueError("event followup requires unchanged originals")
    events = {event["announcement_id"]: event for event in packet["events"]}
    claims = value.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("event followup requires source claims")
    rows = {}
    normalized = lambda text: "".join(text.split())
    labels = set()
    for claim in claims:
        label, summary = claim["label"], claim["summary"]
        if not isinstance(label, str) or not label.strip() or label in labels:
            raise ValueError("event followup labels must be new and unique")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("event followup summary is required")
        labels.add(label)
        event = events.get(claim["announcement_id"])
        if event is None:
            raise ValueError("event followup references unknown announcement")
        anchors = claim.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            raise ValueError("event followup requires page-specific anchors")
        for anchor in anchors:
            page = anchor["physical_page"]
            excerpt = anchor["excerpt"]
            if isinstance(page, bool) or not isinstance(page, int) or page < 1 or not excerpt.strip():
                raise ValueError("event followup requires positive pages and nonempty excerpts")
            matches = [record["text"] for source in event["sources"] for record in source["pages"]
                       if record["physical_page"] == page]
            if not any(normalized(excerpt) in normalized(text) for text in matches):
                raise ValueError("event followup anchor differs from original page")
        rows[label] = summary + "；原件：" + event["sources"][0]["source_url"]
    historical_labels = value.get("historical_labels", [])
    if len(set(historical_labels)) != len(historical_labels):
        raise ValueError("duplicate historical explanation labels")
    unresolved = value.get("unresolved_questions")
    if not isinstance(unresolved, list) or not unresolved or any(not isinstance(item, str) or not item.strip() for item in unresolved):
        raise ValueError("event followup must retain explicit unresolved questions")
    if sha256_file(path) != expected_sha256:
        raise ValueError("event followup changed during read")
    return dict(symbol=value["symbol"], observed_at=point.isoformat(), rows=rows,
                historical_labels=historical_labels, unresolved_questions=unresolved,
                path=path.relative_to(root.resolve()).as_posix(), sha256=expected_sha256,
                scope="SOURCE_ANCHORED_EXPLANATION_ONLY", action="no_order")
