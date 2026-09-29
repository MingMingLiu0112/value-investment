"""Fail-closed, venue-aware binding of financial facts to registered issuers."""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from .research_run_contract import ResearchSourceDescriptor


ISSUER_IDENTITY_VERIFIED = "VERIFIED"
ISSUER_IDENTITY_NOT_READY = "NOT_READY"
ISSUER_IDENTITY_REJECTED = "REJECTED_ISSUER_MISMATCH"

_IDENTITY_REGISTRY = json.loads(
    files(__package__).joinpath("issuer_identity_registry.json").read_text(
        encoding="utf-8"
    )
)
_CNINFO_ORG_IDS = {
    symbol: identity["organization_id"]
    for symbol, identity in _IDENTITY_REGISTRY["cninfo"].items()
}
_CNINFO_NAMES = {
    symbol: frozenset(identity["issuer_names"])
    for symbol, identity in _IDENTITY_REGISTRY["cninfo"].items()
}
_HKEX_IDENTITIES = {
    symbol: (
        identity["security_code"],
        frozenset(identity["issuer_names"]),
    )
    for symbol, identity in _IDENTITY_REGISTRY["hkex"].items()
}
_CNINFO_HOSTS = frozenset({"www.cninfo.com.cn", "static.cninfo.com.cn"})
_HKEX_HOSTS = frozenset({"www1.hkexnews.hk", "www.hkexnews.hk"})
_DERIVED_SOURCE_KINDS = frozenset({"research_artifact"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class IssuerIdentityAssessment:
    status: str
    blockers: tuple[str, ...]
    matched_source_ids: tuple[str, ...] = ()


def _canonical_name(value: str) -> str:
    return re.sub(r"[\s\u3000·,，。:：()（）\[\]【】\-—_]", "", value).casefold()


def _source_venue(location: str) -> str | None:
    try:
        parsed = urlsplit(location)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.lower().rstrip(".")
    if host in _CNINFO_HOSTS:
        return "CNINFO"
    if host in _HKEX_HOSTS:
        return "HKEX"
    return None


def assess_issuer_identity(
    *,
    symbol: str,
    facts_symbol: str | None,
    fact_evidence_refs: Sequence[Mapping[str, Any]],
    sources: Sequence[ResearchSourceDescriptor],
) -> IssuerIdentityAssessment:
    """Assess identity only from hash-bound official-source descriptors.

    Caller-provided company names are intentionally not inputs. Registry values
    are compared against venue-specific metadata on a source whose id and hash
    exactly match a financial-facts evidence reference.
    """
    blockers: list[str] = []
    if not isinstance(facts_symbol, str) or not facts_symbol.strip():
        blockers.append("issuer_identity_unverified:financial_facts_symbol_missing")
    elif facts_symbol.strip() != symbol:
        blockers.append("issuer_identity_mismatch:financial_facts_symbol")

    if blockers and any(item.startswith("issuer_identity_mismatch:") for item in blockers):
        return IssuerIdentityAssessment(ISSUER_IDENTITY_REJECTED, tuple(blockers))

    refs: list[tuple[str, str]] = []
    hashes_by_id: dict[str, set[str]] = {}
    for index, ref in enumerate(fact_evidence_refs):
        if not isinstance(ref, Mapping):
            blockers.append(f"issuer_identity_unverified:financial_fact_ref_invalid:{index}")
            continue
        ref_id = ref.get("id")
        digest = ref.get("sha256")
        if not isinstance(ref_id, str) or not ref_id.strip():
            blockers.append(f"issuer_identity_unverified:financial_fact_ref_id_missing:{index}")
            continue
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest.lower()):
            blockers.append(
                f"issuer_identity_unverified:financial_fact_ref_sha256_missing:{ref_id.strip()}"
            )
            continue
        normalized_id = ref_id.strip()
        normalized_hash = digest.lower()
        hashes_by_id.setdefault(normalized_id, set()).add(normalized_hash)
        refs.append((normalized_id, normalized_hash))
    conflicting_ids = {
        ref_id for ref_id, digests in hashes_by_id.items() if len(digests) > 1
    }
    for ref_id in sorted(conflicting_ids):
        blockers.append(
            f"issuer_identity_unverified:financial_fact_ref_id_conflict:{ref_id}"
        )
    refs = list(dict.fromkeys(refs))
    if not refs:
        blockers.append("issuer_identity_unverified:financial_facts_refs_not_hash_bound")

    resolved_fact_ref_ids: list[str] = []
    verified_issuer_source_ids: list[str] = []
    for ref_id, digest in refs:
        exact_sources = [
            source for source in sources
            if source.id == ref_id and source.sha256.lower() == digest
        ]
        if not exact_sources:
            same_id_sources = [source for source in sources if source.id == ref_id]
            reason = "financial_source_sha256_not_bound" if same_id_sources else "financial_source_missing"
            blockers.append(f"issuer_identity_unverified:{reason}:{ref_id}")
            continue

        issuer_sources = [
            source for source in exact_sources
            if source.kind.strip().casefold() not in _DERIVED_SOURCE_KINDS
        ]
        if not issuer_sources:
            # Derived, hash-bound artifacts are not issuer originals. The full
            # fact set still needs at least one verified official issuer source.
            resolved_fact_ref_ids.append(ref_id)
            continue

        ref_verified = True
        for source in issuer_sources:
            venue = _source_venue(source.location)
            if venue is None:
                blockers.append(
                    f"issuer_identity_unverified:financial_source_not_official:{source.id}"
                )
                ref_verified = False
                continue
            identity = source.issuer_identity
            if identity is None:
                blockers.append(
                    f"issuer_identity_unverified:source_identity_missing:{source.id}"
                )
                ref_verified = False
                continue
            if identity.venue != venue:
                blockers.append(f"issuer_identity_mismatch:venue:{source.id}")
                ref_verified = False
                continue

            if venue == "CNINFO":
                expected_org = _CNINFO_ORG_IDS.get(symbol)
                expected_names = _CNINFO_NAMES.get(symbol)
                if expected_org is None or expected_names is None:
                    blockers.append(
                        f"issuer_identity_unverified:unregistered_issuer:{symbol}"
                    )
                    ref_verified = False
                    continue
                if identity.security_code is not None and identity.security_code != symbol:
                    blockers.append(f"issuer_identity_mismatch:sec_code:{source.id}")
                    ref_verified = False
                if (
                    identity.organization_id is not None
                    and identity.organization_id.casefold() != expected_org.casefold()
                ):
                    blockers.append(f"issuer_identity_mismatch:org_id:{source.id}")
                    ref_verified = False
                if (
                    identity.issuer_name is not None
                    and _canonical_name(identity.issuer_name)
                    not in {_canonical_name(name) for name in expected_names}
                ):
                    blockers.append(f"issuer_identity_mismatch:sec_name:{source.id}")
                    ref_verified = False
                missing = [
                    field
                    for field, value in (
                        ("sec_code", identity.security_code),
                        ("org_id", identity.organization_id),
                        ("sec_name", identity.issuer_name),
                    )
                    if value is None
                ]
                if missing:
                    blockers.append(
                        f"issuer_identity_unverified:cninfo_fields_missing:{source.id}:{','.join(missing)}"
                    )
                    ref_verified = False
                continue

            approved_hkex = _HKEX_IDENTITIES.get(symbol)
            if approved_hkex is None:
                blockers.append(
                    f"issuer_identity_unverified:unregistered_venue_mapping:{symbol}:HKEX"
                )
                ref_verified = False
                continue
            expected_code, expected_names = approved_hkex
            if identity.security_code is not None and identity.security_code != expected_code:
                blockers.append(f"issuer_identity_mismatch:sec_code:{source.id}")
                ref_verified = False
            if (
                identity.issuer_name is not None
                and _canonical_name(identity.issuer_name)
                not in {_canonical_name(name) for name in expected_names}
            ):
                blockers.append(f"issuer_identity_mismatch:sec_name:{source.id}")
                ref_verified = False
            missing = [
                field
                for field, value in (
                    ("sec_code", identity.security_code),
                    ("sec_name", identity.issuer_name),
                )
                if value is None
            ]
            if missing:
                blockers.append(
                    f"issuer_identity_unverified:hkex_fields_missing:{source.id}:{','.join(missing)}"
                )
                ref_verified = False

        if ref_verified:
            resolved_fact_ref_ids.append(ref_id)
            verified_issuer_source_ids.extend(
                source.id for source in issuer_sources
                if _source_venue(source.location) is not None
            )

    if any(item.startswith("issuer_identity_mismatch:") for item in blockers):
        return IssuerIdentityAssessment(
            ISSUER_IDENTITY_REJECTED,
            tuple(dict.fromkeys(blockers)),
            tuple(dict.fromkeys(verified_issuer_source_ids)),
        )
    if (
        len(resolved_fact_ref_ids) != len(refs)
        or any(item.startswith("issuer_identity_unverified:") for item in blockers)
        or not verified_issuer_source_ids
    ):
        if not blockers:
            blockers.append("issuer_identity_unverified:identity_not_established")
        return IssuerIdentityAssessment(
            ISSUER_IDENTITY_NOT_READY,
            tuple(dict.fromkeys(blockers)),
            tuple(dict.fromkeys(verified_issuer_source_ids)),
        )
    return IssuerIdentityAssessment(
        ISSUER_IDENTITY_VERIFIED,
        tuple(dict.fromkeys(blockers)),
        tuple(dict.fromkeys(verified_issuer_source_ids)),
    )
