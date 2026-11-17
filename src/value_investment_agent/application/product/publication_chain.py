"""Load the hash-bound canonical publication chain shared by Web and CLI.

TL9-MVP1: the Web read API and the daily public packet builder must read the
same current publication with the same fail-closed rules, so the chain loader
lives in the application layer and both surfaces import it. The checks moved
here unchanged from the Web API: every binding is exactly ``{path, sha256}``,
must live under ``runtime/`` and must hash to the recorded digest.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
POINTER_SCHEMA = "m7-current-trial-workbook-v5"
MODEL_SCHEMA = "historical-company-read-model-preview-v1"
POINTER_PATH = "config/current-trial-workbook.json"
# Everything a broken or half-published artifact can raise while it is read.
STRUCTURE_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError,
                    AttributeError, UnicodeError, json.JSONDecodeError)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_at(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid object")
    return value


def bound_object(root: Path, binding: dict) -> dict:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("invalid binding")
    name, digest = binding["path"], binding["sha256"]
    if not isinstance(name, str) or not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
        raise ValueError("invalid binding fields")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "runtime":
        raise ValueError("invalid runtime binding")
    runtime = (root / "runtime").resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(runtime) or not path.is_file():
        raise ValueError("binding outside runtime")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("binding hash mismatch")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid bound object")
    return value


def _binding(role: str, path: object, digest: object) -> dict:
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"missing binding:{role}")
    if not HASH_RE.fullmatch(digest):
        raise ValueError(f"invalid binding digest:{role}")
    return {"role": role, "path": path, "sha256": digest}


def load_current_chain(root: Path) -> dict:
    """Return the verified chain, raising ``STRUCTURE_ERRORS`` on any defect.

    Keys: pointer, receipt, wps_receipt, sources, handoff, model, state,
    bindings (the exact ``{role, path, sha256}`` set the identity hashes over).
    """
    pointer = object_at(root / POINTER_PATH)
    if pointer.get("schema_version") != POINTER_SCHEMA or pointer.get("action") != "no_order":
        raise ValueError("unknown pointer")
    publication = pointer["current_publication"]
    if publication.get("status") != "PUBLISHED_WPS_READONLY_VERIFIED":
        raise ValueError("publication not verified")
    bindings: list[dict] = []
    receipt_binding = _binding("publication_receipt", publication["receipt"],
                               publication["receipt_sha256"])
    receipt = bound_object(root, {"path": receipt_binding["path"],
                                  "sha256": receipt_binding["sha256"]})
    bindings.append(receipt_binding)
    if (receipt.get("schema_version") != "canonical-reviewed-research-publication-v1"
            or receipt.get("canonical_written") is not True):
        raise ValueError("publication receipt invalid")
    wps_receipt = None
    if publication.get("wps_receipt") is not None:
        wps_binding = _binding("publication_wps_receipt", publication["wps_receipt"],
                               publication.get("wps_receipt_sha256"))
        wps_receipt = bound_object(root, {"path": wps_binding["path"],
                                          "sha256": wps_binding["sha256"]})
        bindings.append(wps_binding)
    sources_binding = _binding("publication_sources", receipt["source_bindings_path"],
                               receipt["source_bindings_sha256"])
    sources = bound_object(root, {"path": sources_binding["path"],
                                  "sha256": sources_binding["sha256"]})
    bindings.append(sources_binding)
    if sources.get("schema_version") != "existing-workbench-preview-bindings-v1":
        raise ValueError("unknown source ledger")
    handoff_binding = _binding("publication_handoff",
                               sources["publication_input_binding"]["path"],
                               sources["publication_input_binding"]["sha256"])
    handoff = bound_object(root, sources["publication_input_binding"])
    bindings.append(handoff_binding)
    if handoff.get("schema_version") != "research-publication-input-v1" or handoff.get("action") != "no_order":
        raise ValueError("unknown publication input")
    model_binding = _binding("read_model", handoff["read_model_binding"]["path"],
                             handoff["read_model_binding"]["sha256"])
    model = bound_object(root, handoff["read_model_binding"])
    bindings.append(model_binding)
    if model.get("schema_version") != MODEL_SCHEMA or model.get("action") != "no_order":
        raise ValueError("unknown read model")
    state = bound_object(root, pointer["daily_product_state_binding"])
    bindings.append(_binding("daily_product_state", pointer["daily_product_state_binding"]["path"],
                             pointer["daily_product_state_binding"]["sha256"]))
    if state.get("action") != "no_order" or not isinstance(state.get("content"), dict):
        raise ValueError("unknown daily state")
    if model.get("snapshot") != handoff.get("snapshot"):
        raise ValueError("publication snapshot mismatch")
    for role, binding in model.get("product_extensions", {}).items():
        if role in state["content"].get("extensions", {}):
            extension = bound_object(root, binding)
            if state["content"]["extensions"][role] != extension.get("semantic_content", extension):
                raise ValueError("daily state and published model disagree")
    return {"pointer": pointer, "receipt": receipt, "wps_receipt": wps_receipt,
            "sources": sources, "handoff": handoff, "model": model, "state": state,
            "bindings": sorted(bindings, key=lambda item: item["role"])}


def try_load_current_chain(root: Path) -> tuple[dict | None, str | None]:
    """Total variant: ``(chain, None)`` or ``(None, "TypeError: reason")``."""
    try:
        return load_current_chain(root), None
    except STRUCTURE_ERRORS as error:
        return None, f"{type(error).__name__}: {error}"
