"""Replay explicitly reviewed full issuer chapters from official acquisition receipts."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re

from . import company_profile_sources_v1 as legacy

REGISTRY = Path("config/company-profile-sources-v2")


def reviewed_registration(project, symbol):
    if not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("Invalid reviewed profile symbol")
    return Path(project) / REGISTRY / (symbol + ".json")


def _chapter(text, review):
    lines = [re.sub(r"\s+", "", line) for line in text.splitlines()]
    if lines.count(review["start"]) != 1 or lines.count(review["end"]) != 1:
        raise ValueError("Reviewed business chapter boundaries changed")
    section = "".join(lines[lines.index(review["start"]):lines.index(review["end"])])
    if sha256(section.encode()).hexdigest() != review["section_sha256"]:
        raise ValueError("Reviewed business chapter changed")
    return section


def load_registered_source_profile(*, root, symbol, now):
    if reviewed_registration(root, symbol).is_file():
        return read_reviewed_profile(project=root, root=root, symbol=symbol, now=now)
    return legacy.load_source_company_profile(root=root, symbol=symbol, now=now)


def read_reviewed_profile(*, project, root, symbol, now):
    registry = reviewed_registration(project, symbol)
    raw = registry.read_bytes()
    config = json.loads(raw)
    if (config["schema_version"] != "reviewed-company-business-sections-v2"
            or config["symbol"] != symbol or config["action"] != "no_order"
            or config["profile_id"] != "quality_compounder"):
        raise ValueError("Invalid reviewed profile registration")
    refs, closure = [], []
    for review in config["reports"]:
        pin = review["receipt_binding"]
        packet = legacy.acquisition.load_retained_official_report(
            root=root, receipt_binding=pin, symbol=symbol, issuer_name=config["issuer_name"],
            period=review["period"])
        for key in ("started_at", "fetched_at", "completed_at"):
            legacy._available(packet[key], now)
        source = packet["source"]
        legacy._available(source["available_at"], now)
        pages = legacy.extract_pages(root / source["path"], limit=review["page"])
        section = _chapter(pages[review["page"] - 1], review)
        refs.append(legacy._ref(packet, review["page"], section, "REVIEWED_COMPLETE_OWN_BUSINESS_SECTION"))
        closure += [pin, *[{k: item[k] for k in ("path", "sha256")}
                           for item in [source, *packet["index_bindings"]]]]
    if (len(refs) != 2 or not refs[0]["period"].endswith("-12-31")
            or refs[1]["period"] != f"{int(refs[0]['period'][:4])+1}-06-30"):
        raise ValueError("Consecutive annual and interim business reviews required")
    activities = []
    for ref in refs:
        activity = re.findall(r"经营范围主要是[^。；]{2,100}的生产、销售。", ref["excerpt"])
        products = re.findall(r"主要产品[^，。；]{2,90}", ref["excerpt"])
        if (len(activity) != 1 or len(products) != 1 or legacy.inherited.NEGATED_ACTIVITY.search(products[0])
                or not any(term in products[0] for term in legacy.inherited.BUSINESS_TERMS["consumer_products"])):
            raise ValueError("Reviewed issuer activity differs from the consumer-products route")
        activities.append(activity[0])
    if activities[0] != activities[1]:
        raise ValueError("Reviewed issuer production and sales scope changed")
    profile = config["profile_id"]
    route = legacy.route_profile(profile).as_policy()
    contract = legacy.contract_for_profile(profile)
    if route["status"] != "SUPPORTED" or route["selected_model"] != contract["primary_model"]:
        raise ValueError("Reviewed profile route mismatch")
    latest = refs[-1]
    result = legacy._empty(symbol)
    result.update(schema_version="source-company-profile-v2", status="SOURCE_BOUND_ROUTE_ONLY",
        company_name=config["issuer_name"], as_of=latest["period"], report_period=latest["period"],
        available_at=latest["available_at"], retrieved_at=latest["retrieved_at"],
        published_date=latest["published_date"], evidence_refs=refs,
        business_model=activities[-1],
        classification_method="REVIEWED_COMPLETE_OFFICIAL_BUSINESS_SECTIONS_V2",
        classification_reason="REPORTED_BUSINESS_TEMPLATE_CANDIDATE",
        profile=asdict(legacy.PROFILES[profile]), route=route, applicability_contract=contract,
        reported_business_family=legacy.inherited.PROFILE_FAMILY[profile],
        economic_type=legacy.inherited.PROFILE_FAMILY[profile], template_candidate=profile,
        applicability_conditions=contract["applicability_conditions"], refusal_conditions=contract["refusal_conditions"],
        missing_inputs=list(route["required_inputs"]), missing_economic_inputs=list(contract["required_economic_inputs"]),
        blockers=["VALUATION_INPUTS_PENDING", "ECONOMIC_QUALITY_AND_DISTRIBUTABLE_CASH_NOT_VERIFIED"],
        route_qualification=dict(status="SOURCE_ONLY_CONDITIONAL_ROUTE_NOT_MODEL_REPLAY",
                                 approved=False, economic_quality_proven=False, required_inputs=route["required_inputs"]),
        source_verification=dict(status="COMPLETE_REVIEWED_CHAPTERS_REPLAYED", strict_historical_pit=False),
        registration_binding=dict(path=registry.relative_to(project).as_posix(), sha256=sha256(raw).hexdigest()))
    for binding in closure:
        legacy._bound(root, binding)
    if registry.read_bytes() != raw:
        raise ValueError("Reviewed registration changed during replay")
    result["source_bindings"] = [result["registration_binding"], *closure]
    result["implementation_sha256"] = legacy._implementation_hashes() | {__name__: legacy.sha256_file(Path(__file__))}
    result["input_fingerprint"] = result["profile_input_sha256"] = legacy._fingerprint(result)
    return result
