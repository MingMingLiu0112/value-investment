"""Deterministic sales/cost sensitivity, never valuation or investment eligibility."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from itertools import product

VERSION = "operating-driver-bridge-v1"
FIELDS = ("revenue", "cost", "surcharges", "selling", "admin", "research", "pre_tax_profit")
DRIVERS = ("volume_change", "realization_mix_change", "unit_cost_change",
           "fixed_cogs_share", "opex_change", "surcharge_ratio", "other_pretax_cny")


def _num(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("EXACT_DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("FINITE_DECIMAL_REQUIRED") from None
    if not number.is_finite() or abs(number) > Decimal("1e24"):
        raise ValueError("FINITE_BOUNDED_DECIMAL_REQUIRED")
    return number


def _amount(value):
    if not value.is_finite() or abs(value) > Decimal("1e24"):
        raise ValueError("ECONOMIC_AMOUNT_UNSUPPORTED")
    return str(value.quantize(Decimal(".01")))


def build_basis(context):
    """Only scoped, explicitly labelled original periods may form baselines."""
    groups = {}
    for row in context["evidence"]:
        if (row.get("field") not in FIELDS or row.get("scope") != "consolidated"
                or row.get("unit") != "CNY" or "value" not in row):
            continue
        groups.setdefault(row["period"], {}).setdefault(row["field"], []).append(row)
    baselines, gaps = {}, {}
    for period, rows in sorted(groups.items()):
        if any(len(rows.get(field, [])) != 1 for field in FIELDS):
            gaps[period] = "MISSING_OR_DUPLICATE_SAME_PERIOD_FIELDS"
            continue
        selected = {field: rows[field][0] for field in FIELDS}
        kinds = {row.get("period_basis") for row in selected.values()}
        if len(kinds) != 1 or not kinds <= {"FY", "H1"}:
            gaps[period] = "OFFICIAL_PERIOD_BASIS_NOT_PROVEN"
            continue
        kind = next(iter(kinds))
        if not period.endswith("-12-31" if kind == "FY" else "-06-30"):
            gaps[period] = "PERIOD_HEADER_AND_DATE_CONFLICT"
            continue
        values = {field: _num(row["value"]) for field, row in selected.items()}
        if values["revenue"] <= 0 or any(values[field] < 0 for field in FIELDS[1:-1]):
            gaps[period] = "NONPOSITIVE_REVENUE_OR_NEGATIVE_COST_NOT_SUPPORTED"
            continue
        with localcontext() as arithmetic:
            arithmetic.prec = 38
            other = (values["pre_tax_profit"] - values["revenue"] + values["cost"]
                     + values["surcharges"] + values["selling"] + values["admin"]
                     + values["research"])
            baselines[period] = dict(period=period, period_basis=kind, scope="consolidated",
                currency="CNY", fields={field: dict(value=row["value"], evidence_id=row["id"])
                                       for field, row in selected.items()},
                opex_cny=_amount(sum((values[k] for k in ("selling", "admin", "research")), Decimal(0))),
                other_pretax_cny=_amount(other),
                other_pretax_definition="Reported pretax less listed operating rows; includes unmodelled financial/nonoperating effects; NOT normalized recurring income",
                pretax_margin=str(values["pre_tax_profit"] / values["revenue"]),
                surcharge_ratio=str(values["surcharges"] / values["revenue"]),
                evidence_ids=[row["id"] for row in selected.values()])
    comparisons = []
    for period, current in baselines.items():
        prior_period = str(int(period[:4])-1)+period[4:]
        prior = baselines.get(prior_period)
        if prior is None or prior["period_basis"] != current["period_basis"]:
            continue
        for field in FIELDS:
            now = _num(current["fields"][field]["value"])
            before = _num(prior["fields"][field]["value"])
            comparisons.append(dict(field=field, current_period=period, prior_period=prior_period,
                period_basis=current["period_basis"], scope="consolidated", currency="CNY",
                current_value=str(now), prior_value=str(before),
                change_ratio=str(now/before-1) if before > 0 else None,
                status="COMPARABLE" if before > 0 else "NONPOSITIVE_BASE_NOT_ASSESSABLE",
                evidence_ids=[current["fields"][field]["evidence_id"], prior["fields"][field]["evidence_id"]]))
    return dict(version=VERSION, baselines=baselines, comparisons=comparisons, gaps=gaps,
        action="no_order", scope="CONDITIONAL_NONFINANCIAL_SALES_COST_SENSITIVITY_NOT_VALUATION")


def calculate_path(basis, path):
    baseline = basis["baselines"].get(path["baseline_period"])
    if baseline is None:
        raise ValueError("VERIFIED_BASELINE_REQUIRED")
    start, end = date.fromisoformat(path["period_start"]), date.fromisoformat(path["period_end"])
    if start <= date.fromisoformat(baseline["period"]):
        raise ValueError("FORECAST_MUST_FOLLOW_BASELINE")
    expected_end = "-12-31" if baseline["period_basis"] == "FY" else "-06-30"
    if (start.year != end.year or not path["period_start"].endswith("-01-01")
            or not path["period_end"].endswith(expected_end)):
        raise ValueError("FORECAST_BASELINE_PERIOD_MISMATCH")
    drivers = path["drivers"]
    if set(drivers) != set(DRIVERS):
        raise ValueError("EXPLICIT_SEVEN_OPERATING_DRIVERS_REQUIRED")
    ranges = {}
    for key in DRIVERS:
        lo, hi = _num(drivers[key]["lower"]), _num(drivers[key]["upper"])
        if lo > hi:
            raise ValueError("DRIVER_LOWER_EXCEEDS_UPPER")
        if key in ("volume_change", "realization_mix_change") and lo <= -1:
            raise ValueError("NONPOSITIVE_SALES_ACTIVITY_NOT_SUPPORTED")
        if key in ("unit_cost_change", "opex_change") and lo < -1:
            raise ValueError("NEGATIVE_COST_MULTIPLIER")
        if key in ("fixed_cogs_share", "surcharge_ratio") and not 0 <= lo <= hi <= 1:
            raise ValueError("INVALID_COST_SHARE_OR_SURCHARGE_RATIO")
        ranges[key] = (lo, hi)
    values = {key: _num(row["value"]) for key, row in baseline["fields"].items()}
    cases = []
    with localcontext() as arithmetic:
        arithmetic.prec = 38
        for point in product(*(ranges[key] for key in DRIVERS)):
            v, mix, level, fixed, opex_delta, surcharge, other = point
            revenue = values["revenue"]*(1+v)*(1+mix)
            cost = values["cost"]*(fixed+(1-fixed)*(1+v))*(1+level)
            opex = _num(baseline["opex_cny"])*(1+opex_delta)
            tax = revenue*surcharge
            pretax = revenue-cost-opex-tax+other
            cases.append(dict(revenue_cny=_amount(revenue), cogs_cny=_amount(cost),
                opex_cny=_amount(opex), surcharges_cny=_amount(tax),
                other_pretax_cny=_amount(other), pretax_profit_cny=_amount(pretax),
                growth=revenue/values["revenue"]-1, margin=pretax/revenue,
                drivers={key: str(value) for key, value in zip(DRIVERS, point)}))
    low_g, high_g = min(cases, key=lambda c:c["growth"]), max(cases, key=lambda c:c["growth"])
    low_m, high_m = min(cases, key=lambda c:c["margin"]), max(cases, key=lambda c:c["margin"])
    def serialize(case):
        return {key: str(value) if isinstance(value, Decimal) else value for key, value in case.items()}
    yearly_comparable = start.year == int(baseline["period"][:4])+1
    return dict(version=VERSION, baseline=baseline, period_start=path["period_start"],
        period_end=path["period_end"], period_basis=baseline["period_basis"], scope="consolidated",
        growth_range=dict(lower=str(low_g["growth"]), upper=str(high_g["growth"])),
        margin_range=dict(lower=str(low_m["margin"]), upper=str(high_m["margin"])),
        comparison_basis="PROJECTED_YOY_SAME_PERIOD" if yearly_comparable else "CUMULATIVE_RELATIVE_TO_BASELINE_NOT_YOY",
        corner_count=len(cases), evidence_ids=baseline["evidence_ids"],
        extrema=dict(growth_lower=serialize(low_g), growth_upper=serialize(high_g),
                     margin_lower=serialize(low_m), margin_upper=serialize(high_m)),
        formula="R=R0*(1+activity)*(1+realization_mix); C=C0*(fixed+(1-fixed)*(1+activity))*(1+cost_level); OPEX=OPEX0*(1+opex_change); pretax=R-C-OPEX-R*surcharges_ratio+explicit_other",
        limitations=["Activity is an index for covered revenue, not wine tonnes",
          "Realization includes price/product/channel mix; not pure pricing power",
          "COGS sensitivity is not proven fixed-cost accounting; inventory absorption omitted",
          "Other pretax residual is not normalized recurring income",
          "Independent-driver corner envelope, not probability or a set of jointly feasible forecasts",
          "Not shareholder cash, net income, valuation, approval or a trade"],
        action="no_order", formal_eligibility=False)


def build_thresholds(derivedscenarios):
    conditions = []
    for scenario, result in derivedscenarios.items():
        for metric, key in (("revenue_growth", "growth_range"), ("pretax_margin", "margin_range")):
            for direction, edge in (("BELOW", "lower"), ("ABOVE", "upper")):
                conditions.append(dict(scenario=scenario, metric=metric, direction=direction,
                    threshold=result[key][edge], period_start=result["period_start"],
                    period_end=result["period_end"], period_basis=result["period_basis"],
                    scope=result["scope"], baseline_period=result["baseline"]["period"],
                    comparison_basis=result["comparison_basis"],
                    meaning="REOPEN_RESEARCH_ONLY_NOT_AUTOMATIC_REVISION", action="no_order"))
    return conditions


def evaluate_condition(condition, observation, *, observed_at):
    """Equality is inside; only comparable available observations can reopen."""
    for key in ("metric", "period_start", "period_end", "period_basis", "scope", "baseline_period", "comparison_basis"):
        if condition.get(key) != observation.get(key):
            return dict(status="NOT_ASSESSABLE", reason="OBSERVATION_BASIS_MISMATCH", action="no_order")
    available = datetime.fromisoformat(observation["available_at"])
    if available.utcoffset() is None or observed_at.utcoffset() is None or available > observed_at:
        return dict(status="NOT_ASSESSABLE", reason="OBSERVATION_NOT_AVAILABLE", action="no_order")
    value, edge = _num(observation["value"]), _num(condition["threshold"])
    if condition["direction"] not in ("BELOW", "ABOVE"):
        raise ValueError("INVALID_THRESHOLD_DIRECTION")
    outside = value < edge if condition["direction"] == "BELOW" else value > edge
    return dict(status="REOPEN_RESEARCH" if outside else "WITHIN_CONDITION",
                automatic_revision=False, action="no_order")
