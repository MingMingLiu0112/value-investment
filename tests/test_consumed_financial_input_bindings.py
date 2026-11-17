"""Synthetic successor bindings; historical v1/v2 identities stay unchanged."""
from copy import deepcopy
from decimal import Decimal

import pytest

from test_d2_source_bound_package_contract import source_package
from value_investment_agent.application.product.source_bound_inputs import source_catalog_sha256
from value_investment_agent.m1_valuation_package_builder import build_descriptor


@pytest.fixture
def consumed_package(source_package):
    root, original = source_package
    package = deepcopy(original)
    source = package["sources"][0]
    source["kind"] = "official_issuer_filing"
    contract = package["source_contract"]
    contract.update(schema_version="source-bound-research-inputs-v3",
        share_basis="issued_ordinary_shares",
        source_catalog_sha256=source_catalog_sha256(package["sources"]))
    summary = package["research_case"]["financial_summary"]
    summary.update(parent_equity_cny="1000", issued_ordinary_shares="100")
    contract["fact_anchors"] = [dict(field=field, source_id=source["id"],
        physical_page=7, source_value=summary[field], unit=unit, scope=scope,
        period_end=package["facts"]["as_of"], sha256=source["sha256"])
        for field, unit, scope in (
            ("parent_equity_cny", "CNY", "consolidated_parent_equity"),
            ("issued_ordinary_shares", "shares", "issued_ordinary_shares"))]
    contract["consumed_fact_bindings"] = [
        dict(field_path="operating_inputs.start_book_equity", anchor_field="parent_equity_cny"),
        dict(field_path="operating_inputs.ordinary_shares", anchor_field="issued_ordinary_shares"),
    ]
    return root, package


def build(fixture):
    root, package = fixture
    return build_descriptor(package, root=root)


@pytest.mark.parametrize("operation", [None, "DIRECT"])
def test_complete_direct_bindings_match_summary_anchors_and_consumed_values(consumed_package, operation):
    _, package = consumed_package
    if operation:
        for binding in package["source_contract"]["consumed_fact_bindings"]:
            binding["operation"] = operation
    before = deepcopy(package)
    descriptor = build(consumed_package)
    assert descriptor.facts.operating_inputs == {
        "start_book_equity": Decimal("1000"), "ordinary_shares": Decimal("100")}
    assert descriptor.source_contract.as_policy() == package["source_contract"]
    assert package == before


@pytest.mark.parametrize("field", ["start_book_equity", "ordinary_shares"])
def test_consumed_value_drift_cannot_hide_behind_unchanged_anchors(consumed_package, field):
    _, package = consumed_package
    package["facts"]["operating_inputs"][field] = "2000" if field == "start_book_equity" else "200"
    with pytest.raises(ValueError):
        build(consumed_package)


@pytest.mark.parametrize("mutation", [
    "missing_bindings", "empty_bindings", "missing_anchors", "empty_anchors",
    "partial", "duplicate", "unknown_target", "unknown_anchor", "missing_target",
    "missing_anchor_field", "duplicate_anchor", "swapped_anchors",
])
def test_required_exact_coverage_and_unique_targets(consumed_package, mutation):
    contract = consumed_package[1]["source_contract"]
    bindings = contract["consumed_fact_bindings"]
    if mutation == "missing_bindings":
        del contract["consumed_fact_bindings"]
    elif mutation == "empty_bindings":
        contract["consumed_fact_bindings"] = []
    elif mutation == "missing_anchors":
        del contract["fact_anchors"]
    elif mutation == "empty_anchors":
        contract["fact_anchors"] = []
    elif mutation == "partial":
        bindings.pop()
    elif mutation == "duplicate":
        bindings.append(deepcopy(bindings[0]))
    elif mutation == "unknown_target":
        bindings[0]["field_path"] = "operating_inputs.unconsumed"
    elif mutation == "unknown_anchor":
        bindings[0]["anchor_field"] = "absent"
    elif mutation == "missing_target":
        del bindings[0]["field_path"]
    elif mutation == "missing_anchor_field":
        del bindings[0]["anchor_field"]
    elif mutation == "duplicate_anchor":
        contract["fact_anchors"].append(deepcopy(contract["fact_anchors"][0]))
    else:
        bindings[0]["anchor_field"], bindings[1]["anchor_field"] = (
            bindings[1]["anchor_field"], bindings[0]["anchor_field"])
    with pytest.raises(ValueError):
        build(consumed_package)


@pytest.mark.parametrize("index,key,value", [
    (0, "unit", "CNY_thousands"), (0, "scope", "consolidated_total_equity"),
    (1, "unit", "thousand_shares"), (1, "scope", "weighted_average_shares"),
    (0, "period_end", "2025-12-31"), (1, "period_end", "2025-12-31"),
    (0, "physical_page", 0), (0, "source_id", "unbound"), (0, "sha256", "0" * 64),
    (0, "source_value", "2000"), (1, "source_value", "200"),
])
def test_financial_metadata_and_anchor_values_are_enforced(consumed_package, index, key, value):
    consumed_package[1]["source_contract"]["fact_anchors"][index][key] = value
    with pytest.raises(ValueError):
        build(consumed_package)


@pytest.mark.parametrize("index,value", [(0, "0"), (0, "-1"), (1, "0"), (1, "-1"), (1, "100.5")])
def test_matching_but_invalid_financial_values_rejected(consumed_package, index, value):
    package = consumed_package[1]
    anchor = package["source_contract"]["fact_anchors"][index]
    field = "start_book_equity" if index == 0 else "ordinary_shares"
    anchor["source_value"] = value
    package["research_case"]["financial_summary"][anchor["field"]] = value
    package["facts"]["operating_inputs"][field] = value
    with pytest.raises(ValueError):
        build(consumed_package)


@pytest.mark.parametrize("operation", ["MULTIPLY", "SUM", "SCALE", "direct", "", None])
def test_unsupported_explicit_operations_rejected(consumed_package, operation):
    consumed_package[1]["source_contract"]["consumed_fact_bindings"][0]["operation"] = operation
    with pytest.raises(ValueError):
        build(consumed_package)


def test_no_arbitrary_scaling_even_with_direct_operation(consumed_package):
    binding = consumed_package[1]["source_contract"]["consumed_fact_bindings"][0]
    binding.update(operation="DIRECT", scale="1000")
    with pytest.raises(ValueError):
        build(consumed_package)


def test_basis_date_controls_anchors_instead_of_facts_as_of(consumed_package):
    package = consumed_package[1]
    package["facts"]["valuation_timing"] = dict(
        basis_at="2026-06-30T23:59:59+08:00", valuation_at="2026-09-22T16:00:00+08:00",
        evidence_refs=deepcopy(package["facts"]["evidence_refs"]))
    for anchor in package["source_contract"]["fact_anchors"]:
        anchor["period_end"] = "2026-06-30"
    assert build(consumed_package).facts.valuation_timing.basis_at.date().isoformat() == "2026-06-30"
    package["source_contract"]["fact_anchors"][1]["period_end"] = package["facts"]["as_of"]
    with pytest.raises(ValueError):
        build(consumed_package)


def test_existing_v2_input_and_fingerprint_are_unchanged(source_package):
    root, package = source_package
    before = deepcopy(package)
    first = build_descriptor(package, root=root)
    second = build_descriptor(deepcopy(package), root=root)
    assert first.as_policy() == second.as_policy()
    assert first.input_sha256 == second.input_sha256
    assert package == before
    assert package["source_contract"]["schema_version"] == "source-bound-research-inputs-v2"
    assert "consumed_fact_bindings" not in package["source_contract"]


def test_v3_reuses_source_catalog_and_local_bytes_checks(consumed_package):
    root, package = consumed_package
    package["sources"][0]["kind"] = "research_artifact"
    package["source_contract"]["source_catalog_sha256"] = source_catalog_sha256(package["sources"])
    with pytest.raises(ValueError):
        build_descriptor(package, root=root)


def test_explicit_shares_excluding_treasury_basis_is_supported(consumed_package):
    contract = consumed_package[1]["source_contract"]
    contract["share_basis"] = "ordinary_shares_excluding_treasury"
    contract["fact_anchors"][1]["scope"] = "ordinary_shares_excluding_treasury"
    assert build(consumed_package).facts.operating_inputs["ordinary_shares"] == Decimal("100")


@pytest.mark.parametrize("basis", ["ordinary_shares_excluding_treasury", "weighted_average_shares", None])
def test_missing_unknown_or_mismatched_share_basis_rejected(consumed_package, basis):
    contract = consumed_package[1]["source_contract"]
    if basis is None:
        del contract["share_basis"]
    else:
        contract["share_basis"] = basis
    with pytest.raises(ValueError):
        build(consumed_package)


def test_treasury_anchor_cannot_use_issued_share_basis(consumed_package):
    consumed_package[1]["source_contract"]["fact_anchors"][1]["scope"] = "ordinary_shares_excluding_treasury"
    with pytest.raises(ValueError):
        build(consumed_package)


def add_derivation(package, rule):
    """Declare raw component facts independently of the canonical consumed fact."""
    contract = package["source_contract"]
    target = contract["fact_anchors"][1 if rule == "SUM_COMPONENTS" else 0]
    summary = package["research_case"]["financial_summary"]
    components = []
    values = (("a_shares_ex_treasury", "80"), ("h_shares_ex_treasury", "20")) if rule == "SUM_COMPONENTS" else (("parent_equity_thousand_cny", "1"),)
    if rule == "SUM_COMPONENTS":
        contract["share_basis"] = target["scope"] = "ordinary_shares_excluding_treasury"
    for field, value in values:
        component = {key: deepcopy(value) for key, value in target.items() if key != "derivation"}
        component.update(field=field, source_value=value,
            unit="shares" if rule == "SUM_COMPONENTS" else "CNY_thousand")
        summary[field] = value
        components.append(component)
    target["derivation"] = dict(rule=rule, component_fields=[row["field"] for row in components])
    contract["fact_anchors"].extend(components)
    return target, components


@pytest.mark.parametrize("rule", ["SUM_COMPONENTS", "CNY_THOUSANDS_TO_CNY"])
def test_source_derived_canonical_fact_matches_direct_consumed_binding(consumed_package, rule):
    package = consumed_package[1]
    target, _ = add_derivation(package, rule)
    before = deepcopy(package)
    descriptor = build(consumed_package)
    key = "ordinary_shares" if rule == "SUM_COMPONENTS" else "start_book_equity"
    assert descriptor.facts.operating_inputs[key] == Decimal(target["source_value"])
    assert descriptor.source_contract.as_policy()["fact_anchors"] == package["source_contract"]["fact_anchors"]
    assert package == before


@pytest.mark.parametrize("rule", ["SUM_COMPONENTS", "CNY_THOUSANDS_TO_CNY"])
@pytest.mark.parametrize("mutation", [
    "wrong_total", "duplicate", "self", "unknown", "nested", "wrong_source",
    "wrong_page", "wrong_period", "wrong_scope", "wrong_unit", "arbitrary_rule",
    "empty", "wrong_arity", "unconsumed_target",
])
def test_derivation_requires_exact_direct_compatible_components(consumed_package, rule, mutation):
    package = consumed_package[1]
    target, components = add_derivation(package, rule)
    component = components[0]
    derivation = target["derivation"]
    if mutation == "wrong_total":
        # Keep component summary and anchor mutually consistent: only the
        # deterministic reconciliation can detect this changed raw amount.
        component["source_value"] = "81" if rule == "SUM_COMPONENTS" else "2"
        package["research_case"]["financial_summary"][component["field"]] = component["source_value"]
    elif mutation == "duplicate":
        derivation["component_fields"].append(component["field"])
    elif mutation == "self":
        derivation["component_fields"][0] = target["field"]
    elif mutation == "unknown":
        derivation["component_fields"][0] = "missing_raw_fact"
    elif mutation == "nested":
        component["derivation"] = dict(rule="SUM_COMPONENTS", component_fields=[target["field"], component["field"]])
    elif mutation == "wrong_source":
        # A second valid, consumed official source isolates same-source checks.
        second = package["sources"][1]
        second["kind"] = "official_issuer_filing"
        package["facts"]["evidence_refs"].append(dict(id=second["id"], sha256=second["sha256"]))
        package["source_contract"]["source_catalog_sha256"] = source_catalog_sha256(package["sources"])
        component["source_id"] = second["id"]
    elif mutation == "wrong_page":
        component["physical_page"] += 1
    elif mutation == "wrong_period":
        component["period_end"] = "2025-12-31"
    elif mutation == "wrong_scope":
        component["scope"] = "unrelated_financial_scope"
    elif mutation == "wrong_unit":
        component["unit"] = "thousand_shares" if rule == "SUM_COMPONENTS" else "CNY"
    elif mutation == "arbitrary_rule":
        derivation["rule"] = "MULTIPLY_BY_USER_FACTOR"
    elif mutation == "empty":
        derivation["component_fields"] = []
    elif mutation == "wrong_arity":
        if rule == "SUM_COMPONENTS":
            derivation["component_fields"] = [component["field"]]
        else:
            extra = deepcopy(component)
            extra["field"] = "another_thousand_cny"
            package["source_contract"]["fact_anchors"].append(extra)
            package["research_case"]["financial_summary"][extra["field"]] = extra["source_value"]
            derivation["component_fields"].append(extra["field"])
    else:
        # The derived target must itself be a directly consumed canonical fact.
        del target["derivation"]
        component["derivation"] = derivation
    with pytest.raises(ValueError):
        build(consumed_package)


def test_both_normalizations_can_coexist_in_one_model_input(consumed_package):
    package = consumed_package[1]
    add_derivation(package, "SUM_COMPONENTS")
    add_derivation(package, "CNY_THOUSANDS_TO_CNY")
    descriptor = build(consumed_package)
    assert descriptor.facts.operating_inputs == {
        "start_book_equity": Decimal("1000"), "ordinary_shares": Decimal("100")}


def test_v3_official_exchange_share_source_accepts_bound_components(consumed_package):
    package = consumed_package[1]
    target, components = add_derivation(package, "SUM_COMPONENTS")
    exchange = package["sources"][1]
    exchange["kind"] = "official_exchange_filing"
    package["facts"]["evidence_refs"].append(dict(id=exchange["id"], sha256=exchange["sha256"]))
    for anchor in (target, *components):
        anchor.update(source_id=exchange["id"], sha256=exchange["sha256"])
    package["source_contract"]["source_catalog_sha256"] = source_catalog_sha256(package["sources"])
    descriptor = build(consumed_package)
    assert descriptor.facts.operating_inputs["ordinary_shares"] == Decimal("100")
    assert descriptor.source_contract.as_policy()["share_basis"] == "ordinary_shares_excluding_treasury"
