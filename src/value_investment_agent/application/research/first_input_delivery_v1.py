"""Restore an explicit public first-input delivery using the existing archive."""
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile
import subprocess
import sys

from ...infrastructure.public_evidence_archive_v2 import restore_archive

KEYS = ("status", "receipt_binding", "input_fingerprint", "valuation", "annual_ledgers",
        "financial_update_observation", "action")


def _replay_projection(stage, symbol, now):
    code = (
        "import sys,json;from pathlib import Path;from datetime import datetime;"
        "root=Path(sys.argv[1]);sys.path.insert(0,str(root/'src'));"
        "from value_investment_agent.application.product.first_research_input_view_v1 import read_first_research_input;"
        "x=read_first_research_input(root=root,symbol=sys.argv[2],now=datetime.fromisoformat(sys.argv[3]));"
        "keys=json.loads(sys.argv[4]);print(json.dumps({**{k:x.get(k) for k in keys},'_diagnostic':{'reason':x.get('reason'),'blockers':x.get('blockers')}}))"
    )
    run = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(stage), symbol,
                          now.isoformat(), json.dumps(KEYS)], cwd=stage,
                         capture_output=True, timeout=180, check=True)
    return json.loads(run.stdout)


def restore_first_input_delivery(*, archive_root, manifest_sha256, destination):
    def validate(stage, manifest):
        bundle = json.loads((stage / manifest["bundle"]["path"]).read_bytes())
        if bundle.get("schema_version") != "first-input-public-delivery-v1" or bundle.get("action") != "no_order":
            raise ValueError("FIRST_INPUT_DELIVERY_INVALID")
        if not bundle.get("expected") or any(
            value.get("status") != "SOURCE_BOUND_FIRST_INPUT_COMPILED" or value.get("action") != "no_order"
            for value in bundle["expected"].values()
        ):
            raise ValueError("FIRST_INPUT_SUCCESSFUL_PUBLIC_RESULTS_REQUIRED")
        source = bundle["source_zip"]
        if not any(row["original_path"] == source["path"] and row["sha256"] == source["sha256"]
                   for row in manifest["items"]):
            raise ValueError("FIRST_INPUT_SOURCE_ARCHIVE_UNBOUND")
        with zipfile.ZipFile(stage / source["path"]) as archive:
            for entry in archive.infolist():
                name = PurePosixPath(entry.filename)
                if (name.is_absolute() or ".." in name.parts or "\\" in entry.filename or
                        not (entry.filename.startswith(("src/", "config/")) or entry.filename == "pyproject.toml") or
                        (entry.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError("FIRST_INPUT_SOURCE_ARCHIVE_PATH_INVALID")
            archive.extractall(stage)
        for name, record in bundle["configs"].items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or not name.startswith("config/") or not name.endswith(".json"):
                raise ValueError("FIRST_INPUT_CONFIG_PATH_INVALID")
            raw = base64.b64decode(record["bytes_base64"], validate=True)
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("FIRST_INPUT_CONFIG_HASH_MISMATCH")
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        now = datetime.fromisoformat(bundle["evaluated_at"])
        if now.utcoffset() is None:
            raise ValueError("FIRST_INPUT_DELIVERY_CLOCK_REQUIRED")
        for symbol, expected in bundle["expected"].items():
            actual = _replay_projection(stage, symbol, now)
            if {key: actual.get(key) for key in KEYS} != expected:
                differences = {key: {'expected': expected.get(key), 'actual': actual.get(key)}
                               for key in KEYS if actual.get(key) != expected.get(key)}
                raise ValueError("FIRST_INPUT_RESTORED_RESULT_MISMATCH:" + symbol + ":" +
                                 json.dumps({'differences': differences, 'diagnostic': actual.get('_diagnostic')},
                                            ensure_ascii=True, default=str))
    packet = restore_archive(archive_root=archive_root, manifest_sha256=manifest_sha256,
                             destination=destination, validate=validate)
    return {"status": "ISOLATED_RESTORE_REPLAY_PASSED", "manifest_sha256": manifest_sha256,
            "files": len(packet["items"]), "action": "no_order",
            "scope": "E2_READ_MODEL_ONLY_NOT_FULL_API_OR_PRICE_PUBLICATION"}
