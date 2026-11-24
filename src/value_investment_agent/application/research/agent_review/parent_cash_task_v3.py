"""Nine bounded D1 stages: operating, cash policy and terminal per scenario."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, localcontext
import json
import sys
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from .task_execution_v1 import ResearchTaskService, _bytes, _hash, _now
from .operating_task_v2 import LiveOperatingTaskService, model_configuration
from . import parent_cash_financing_wire as fixed_financing
def read_parent_cash_agent_facts_v2(**kwargs):
    from ..direct_owner_cash_agent_facts_v2 import read_parent_cash_agent_facts_v2 as reader
    return reader(**kwargs)

from ..direct_owner_cash_staged_v2 import (
    STAGES, parse_staged_parent_cash_response,
)
from .. import direct_owner_cash_operating_wire_v1 as operating_wire
from .. import direct_owner_cash_terminal_wire_v1 as terminal_wire
from .. import direct_owner_cash_policy_capital_v1 as policy_capital
from .. import parent_financing_schedule_v1 as financing_schedule
from .. import direct_owner_cash_staged_v3 as staged_numbered
from ..direct_owner_cash_staged_v3 import (
    preflight_annual_cash_upper_bound_v3, merge_staged_parent_cash_v3,
    staged_parent_cash_request_v3, preflight_terminal_forecast_debt_v3,
)
from ..direct_owner_cash_agent_draft_v2 import (
    POLICY, SCENARIOS, assemble_parent_cash_drafts_v2,
)
from ....infrastructure.agent_runtime.provider import LLMResponse, OpenAICompatibleChatProvider
from ...product.common import require_inside, write_new_bytes

VERSION = "parent-cash-task-v3"
STAGE_ORDER = tuple(f"{scenario}.{stage}" for scenario in SCENARIOS for stage in STAGES)
LEGACY_WIRE_SERVICE = "74b81ab8641985ac2e641442322dc599f721f5d87352d032f74d2e3bac68d06b"
PRE_TERMINAL_WIRE_SERVICE = "c1ab9217121595980da1396cb78bfaa5df0226b53b7f58fd2bb86711439db264"
STATES = {"QUEUED", "RUNNING", "FAILED", "SUCCEEDED", "CANCELLED"}
# Hash of normalized service bytes with this one revision literal zeroed.
REVIEWED_CAPITAL_SERVICE = "3714f2400613b5d7dfb476ed40a996e91eb2165ebd3c4d57b8426fb8ee36115d"


_PRE_UNNUMBERED_HASHES = {
    "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2": "32d3052ce84815f47ccd5284b43b511e227c234992875d69e5621930c446de3d",
    "value_investment_agent.application.research.direct_owner_cash_staged_v3": "242347a19bea4369d3f8b26da14628c455773922edac94326b0d000a6a4ea5de",
    "value_investment_agent.application.research.direct_owner_cash_compilation_v2": "85e7f4fe51c022c5caa2065fef7fcdef0402258322181e927762b7822ba7e00a",
    "value_investment_agent.application.research.agent_review.parent_cash_task_v3": "128c61d0993303dbb441c30ea4423aaefc5ce24f4231ec54a0c1e559f996e12f",
}


_REVIEWED_NUMBERED_COMPATIBILITY_HASHES = {
    "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2": "03c7d1dcbdd61128e73f442727c4f22fe48abc10701e6f10170c17a5fe93e3e0",
    "value_investment_agent.application.research.direct_owner_cash_staged_v3": "7f11ce13add09c9686e389f84ee5782bbe6d14c8962be32f2cae3696827b0d5a",
    "value_investment_agent.application.research.direct_owner_cash_compilation_v2": "1a72bb69c4aa62712b6379d689a3611fa9dcbe565c0d08270561d24c46739044",
}


PRE_FINANCING_IMPLEMENTATION = {
    "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2": "03c7d1dcbdd61128e73f442727c4f22fe48abc10701e6f10170c17a5fe93e3e0",
    "value_investment_agent.application.research.direct_owner_cash_compilation_v2": "b9f4d8f98d514fa358865274b8d72073b1e0e83b42ef14ad69ebcddb628d3a5e",
    "value_investment_agent.application.research.direct_owner_cash_staged_v3": "7f11ce13add09c9686e389f84ee5782bbe6d14c8962be32f2cae3696827b0d5a",
    "value_investment_agent.application.research.parent_direct_owner_cash_unnumbered_v1": "6f5f6c6b42a8cae9545668f98bcb29a8bed012aca2a5bfcd392113b85fc74557",
    "value_investment_agent.application.research.agent_review.parent_cash_task_v3": "f72520a5d57674cce511cd0066c5650408394a333240fbf3014cfde8539d5793",
}

PRE_FINANCING_WINDOWS_OVERRIDES = {
    "value_investment_agent.application.research.agent_review.parent_cash_task_v3": "e53bc6e6c48cee0db24f21225079d21095937b1a220ffe993ca623b7283ddd89",
    "value_investment_agent.application.research.direct_owner_cash_compilation_v2": "1a72bb69c4aa62712b6379d689a3611fa9dcbe565c0d08270561d24c46739044",
    "value_investment_agent.application.research.parent_direct_owner_cash_unnumbered_v1": "fb5efbabb334369fd28515063c95cb753e8f13709edb9724fc9542fad14f88a8",
}

REVIEWED_FINANCING_IMPLEMENTATION = {
    "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2": "6633ab4499590c7a773d2ec25c7af10eba8d503e1b5f738de3d0cc2a67721643",
    "value_investment_agent.application.research.direct_owner_cash_compilation_v2": "fbb7ad124181d540def843a9877773f653ea21d04581c246551a034887f742a1",
    "value_investment_agent.application.research.direct_owner_cash_staged_v3": "33f2ede2ffadea2fc49aeb7bedb184b3fce3954223a5a2ad05982921c99b8478",
    "value_investment_agent.application.research.parent_direct_owner_cash_unnumbered_v1": "56f60cbf9cc00fc84d2fe8687c2dd5dd213186b15df17ded77d7d311202ff160",
}


PRE_QUARTER_FINANCING_IMPLEMENTATION = {
    "value_investment_agent.application.research.direct_owner_cash_staged_v3": "2b5dac58c1a56a20481661978dc1616b42555a73921cf29aa08060c7f18ff5d8",
    "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2": "d7e05f7cf18b877a2fa1828e3197b1d324114e4a29fa7dfbde211a5f1d07d1fd",
    "value_investment_agent.application.research.agent_review.parent_cash_task_v3": "69b3f187d674adc4d119088bfc810644a378d52758af93ec8450205960f01a18",
}


PRE_POLICY_MONEY_IMPLEMENTATION = {
    "value_investment_agent.application.research.agent_review.parent_cash_task_v3": "e66e9818e25867866bf8beb162a526e3444576b6729ea6e2129df84a771a1434",
    "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2": "47f9fd729b717a59ddcd3c286d60711c1945672b698531bc312a65de43454f45",
    "value_investment_agent.application.research.direct_owner_cash_staged_v3": "2b5dac58c1a56a20481661978dc1616b42555a73921cf29aa08060c7f18ff5d8",
}


def _conditional_coupon_calendar(root, schedule, *, symbol, as_of):
    from ....infrastructure.filings.operating_event_terms import parse_operating_event_terms
    from ....infrastructure.filings.pdf_text import extract_pages

    if root is None:
        raise ValueError("PARENT_COUPON_SOURCE_ROOT_REQUIRED")
    originals = {}
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for code, issue in sorted(schedule["later_issues"].items()):
            matches = []
            for binding in issue["sources"]:
                available = datetime.fromisoformat(binding["available_at"])
                if available.utcoffset() is None or available > as_of:
                    raise ValueError("PARENT_COUPON_SOURCE_NOT_AVAILABLE")
                path = require_inside(root / "runtime", root / binding["path"], "coupon original")
                if _hash(path.read_bytes()) != binding["sha256"]:
                    raise ValueError("PARENT_COUPON_SOURCE_HASH_CHANGED")
                if path not in originals:
                    event = parse_operating_event_terms(extract_pages(path), symbol=symbol)
                    originals[path] = event["financing_issues"]
                matches.extend(term for term in originals[path] if term["code"] == code)
            if not matches or any(term != matches[0] for term in matches):
                raise ValueError("PARENT_COUPON_ISSUE_NOT_UNIQUE")
            term = matches[0]
            if any(term[name] != value for name, value in issue["terms"].items()):
                raise ValueError("PARENT_COUPON_TERMS_CHANGED")
            start, due = map(date.fromisoformat, (term["interest_start"], term["maturity"]))
            days = (due - start).days
            coupon = Decimal(term["face_value_cny"]) * Decimal(term["coupon_percent"]) * days / 36500
            rows.append(dict(code=code, maturity=due.isoformat(),
                             coupon_percent=term["coupon_percent"],
                             conditional_act365_cash_cny=str(coupon.quantize(Decimal(".01"))),
                             source_sha256=sorted({ref["sha256"] for ref in issue["sources"]})))
    return dict(classification="CONDITIONAL_ACT365_NOT_CONTRACT_DAY_COUNT_OR_PAYMENT",
                cash_payment_verified=False, remaining_debt_interest_verified=False, issues=rows)


def _validate_scenario_interest(parsed, debt_path, source, calendar):
    floors = {}
    paid = source.get("annual_paid_note_interest_floor")
    if paid is not None:
        floors[paid["year"]] = Decimal(paid["minimum_cny"])
    for issue in calendar["issues"]:
        year = date.fromisoformat(issue["maturity"]).year
        floors[year] = floors.get(year, Decimal(0)) + Decimal(issue["conditional_act365_cash_cny"])
    for row, raw in zip(debt_path, parsed["series"]["interest_outside_cfo"]["values"], strict=True):
        year, amount = row["year"], Decimal(raw)
        if amount < floors.get(year, Decimal(0)):
            raise ValueError(f"PARENT_V3_POLICY_COUPON_COVERAGE_LOW:{year}")
        if (amount <= 0 and (Decimal(row["opening_debt_cny"]) > 0
                             or Decimal(row["new_borrowing_cny"]) > 0)):
            raise ValueError(f"PARENT_V3_POLICY_DEBT_INTEREST_UNSUPPORTED:{year}")


def _implementation():
    from .. import (direct_owner_cash_agent_draft_v1 as draft_prior,
                    direct_owner_cash_agent_draft_v2 as draft,
                    direct_owner_cash_agent_facts_v2 as facts,
                    parent_direct_owner_cash_sources_v2 as sources,
                    direct_owner_cash_staged_v2 as staged,
                    direct_owner_cash_staged_v3 as staged_numbered,
                    direct_owner_cash_compilation_v2 as compiler_numbered,
                    direct_owner_cash_agent_request_v1 as request,
                    direct_owner_cash_compilation_v1 as compiler,
                    parent_direct_owner_cash_unnumbered_v1 as unnumbered,
                    parent_direct_owner_cash_sources as unnumbered_native)
    return {module.__name__: _hash(Path(module.__file__).read_bytes())
            for module in (draft_prior, draft, facts, sources, staged, staged_numbered,
                           request, compiler, compiler_numbered, unnumbered, unnumbered_native, operating_wire, terminal_wire, policy_capital, financing_schedule)} | {
        __name__: _hash(Path(__file__).read_bytes())}


class ParentCashTaskServiceV3(ResearchTaskService):
    def __init__(self, root, *, test_provider=None):
        super().__init__(root)
        self.base = require_inside(self.root, self.base / VERSION, "parent cash tasks")
        self.test_provider = test_provider
        shared = os.environ.get("VALUE_AGENT_SHARED_RESEARCH_ROOT")
        self.shared_budget_root = (self.root if test_provider is not None else
            Path(shared).resolve() if shared and Path(shared).is_absolute() else None)
        # Reuse the exact ledger root used by the existing live horizon tasks.
        self.daily = (LiveOperatingTaskService(self.shared_budget_root)
            if self.shared_budget_root is not None and self.shared_budget_root.is_dir() else None)

    def _configuration(self):
        if self.daily is None:
            raise PermissionError("PARENT_SHARED_BUDGET_ROOT_REQUIRED")
        cfg = model_configuration(self.shared_budget_root)
        if cfg["model_id"] != "deepseek-flash" or Decimal(str(cfg["daily_cost_limit"])) > 10:
            raise PermissionError("PARENT_SHARED_MODEL_CONFIGURATION_INVALID")
        # The same shared D1 gateway is configured for 4096; the established
        # V19 horizon task expands only its per-request completion ceiling.
        if cfg["max_completion_tokens_cap"] != 4096:
            raise PermissionError("PARENT_SHARED_COMPLETION_CONFIG_INVALID")
        return {**cfg, "max_completion_tokens_cap": 8192}

    def _implementation_matches(self, spec):
        current = _implementation()
        pinned = spec.get("implementation_sha256")
        if not isinstance(current, dict) or not isinstance(pinned, dict):
            return False
        raw = Path(__file__).read_bytes()
        normalized = re.sub(
            rb'REVIEWED_CAPITAL_SERVICE = "[0-9a-f]{64}"',
            b'REVIEWED_CAPITAL_SERVICE = "' + b"0" * 64 + b'"',
            raw.replace(b"\r\n", b"\n"), count=1)
        reviewed = current.get(__name__) == _hash(raw) and _hash(normalized) == REVIEWED_CAPITAL_SERVICE
        # Preserve exact request reconstruction for the previous service revision.
        previous_service = {
            "2d0fc6e3dbf90043eb3406b9b67c9137d65087e7917adaf67be01fac53aa7c59",
            "bd6b85db9e181e473e50afd3fd6a78c16476f51dbc8a57e4d0dbc7d63e069005",
            "898bbeaf8c6a62b9466fc04d9b7562b17489f4054e7d86f9bfc553a2c8bca3bc",
            "2ecfbc057485bced15d3d021db6fbb27174a3b4ca5b5b5874338292f15b2be59",
            "cfa16989259b138a5c133b6e9a1273201ff75e24d772a7afb4ab80055ef15000",
            "9c6c1824a05f0588fedf72add13eef86decf0e37c267c21671239e06367f0119",
            "efb254950943325621bfc2c3326c0a398fbbfac52f69cff83b36d22179267647",
            "8cf04890cd76c7102e0c47bde9779499196e65b5b1e3ab98bbbd2c3462781fbc",
            "e2106301d5f0a6d2dd1c722ba1658ec1ec748286855938bb517fbec92f73d8ab",
            "e06f05e8c811d8a59aec6ab672e7373165aa251cd6cb1ed6199b9726efd000d3",
            "648de0ee3db959a3e54c49d854b90ae3cc04d2ff5322813e05bc8b3cd154f794",
            "f47401bbffaebf89d26ecaf011e03d18f1026b7b46af5b79a61f222f6c201d5f",
            "98f19101f67dbfa66747b0667f36829aa511fc08316222c2fee340dae4421245",
            "2d049a3e65e0b7aefd65acd156ea3a86cc895ff84f1dcbcd06d51f1ae7d542ab",
            "4607c1b46dece2c82406f1822b8054c360dc7a5bdc14b61e93f68fb7c9f42048",
            "1dca8a72779713bfc21f67e5e11d924fec54ecdbb7dde645eaac727b94ed80c2",
            "3ca0ec5018979fc0b080b2da08269b4de8ce8619d682f205fe54d194bffde9a2",
            "d765bdf379aa69498dc67e9e7c7b2fc599850feead57ab07ad2de484ee9b046a",
            "d7c211740c28a813998434fb64829693a265da6016a5c6da7d2655b5f3ba635f",
            "e2465dbb3234967208bad139ebafe6b514e5eacfcde51179d0435e20f623c9f5",
            "001fe55b377083de2e577a4bef570fba9eb2f4ce3dced927128e13d52dbe6673",
            "0a941f5287c6d786a1fa36149e09418b4cf4ef5a063190fc011c0e34290f2625",
            "788c0f698b6ac66aed9e3f6689e2009652f71ce26ddb35dc60b3fb643c697301",
            "83faf15fbc2f95a2376fb3ceb35bdd2db3101fb05992f05e75bac907d19c319b",
            "7e7adc609379ce2a67f272130906ae354e9b62557437df84d93af0247dced12e",
            "8c74402d9c0a235d9e946a54e9f4405c4146059d26fa2324841cdfac80bc4d20",
            "3774af9243786fc9d53b055deaa3cd2c2af6c9a31f7b4accba4a096827db9bed",
            "126bab52f86ebec41d690e1411a4dd7381d6e78522a597d934f7e7deb4a31984",
            "dbf7b1d76e3aa0a3c92bbbfee16df2a07a9bfee6ee12d8d165b479384f10f427",
            "4c6eb47c765ba255cfa9a3143b45c684993b1a7c2217d248a7d4abb6c303f7ea",
            "9c8955c8e3193b2a542f27795e693608ba3f794c735e7df32350e3875246fd8f",
            "31f286f615b144036173388233648b8a2413d1c5ee9da87dff1b4eab72c60812",
            "22bb04a6f97a7e38bf1c13c21339fc2639a28bc28a75fce8e03c421a38c0f608",
            "411b7a79bf683bf741302bd50b72aed2aed9a8962a6535e504525ec5733b28ce",
            "4e9790c3e6ceaaeee9058277bf3133f346fd0c78d9eb4f9ccf3fff565b47950c",
            "98096bf08faef5c7b27967be5275edc210a0eac557a1411c6f9ff539cee0df59",
            "30442d7943b4b817f6b97b41bc968e96e41a592da6843f41083470cbbcde1714",
            "f86d050459aa38d62a1c6aff927855c07fea9826720047e0827fc8e68b3b8dcf",
            "40a3d19ae65d2d41e1c40ff642ba5e402e00de70e26f5f32f39707f5a6979241",
            "f69114fbfa585e50d7e05e3218de5741eb0537b5d63116956fc1ad7467127eb3",
            "3b67006f29f92bb8715fad6be677df44193744314970f836b0aaa861b37b0955",
            "a4e4243a479e13014ce85b72ec1073265ccca5a43bcaa020f37309517ebae830",
            "28ccdd5b30d471b1c0ae1b0ddeda0d6c6affa37d484e1d926c8a3330b2560867",
            "3eada6ab1703a400969ded6ddc6fa6f94205207c99d2db79d9e733a58b376f59",
            "fa4ce1d888b9170fdc0ac7b8936a4efb7220cb084bafe8caa87d57ade02784e5",
            "fb3eb8ae12f42c63a2a57ec35a330c55721f846d45999ae70305e30c93057aac",
        }
        if reviewed and pinned.get(__name__) in previous_service:
            current[__name__] = pinned[__name__]
        if financing_schedule.__name__ not in pinned:
            current.pop(financing_schedule.__name__, None)
        if policy_capital.__name__ not in pinned:
            if spec.get("policy_capital_basis") is not None or not reviewed:
                return False
            current = {name: digest for name, digest in current.items()
                       if name != policy_capital.__name__}
            prior_service = pinned.get(__name__)
            current[__name__] = (
                prior_service if prior_service in {
                    "af998baf6d5a8192afc5218a670c2694b1d474efc7283782841546822c2ad384",
                    "38cd85ac4835bf0494e8682798d3e25903b64dd7e59ce1c1c130c26ae81e03b0",
                } else "af998baf6d5a8192afc5218a670c2694b1d474efc7283782841546822c2ad384")
        source_module = "value_investment_agent.application.research.parent_direct_owner_cash_unnumbered_v1"
        legacy_source_hashes = {
            "28eb119c1fa0f9f59a559ecf688f71c94701ee23cd5293c4c3c9f795151edfba",
            "56f60cbf9cc00fc84d2fe8687c2dd5dd213186b15df17ded77d7d311202ff160",
        }
        if pinned.get(source_module) in legacy_source_hashes and source_module in current:
            source_file = Path(sys.modules[source_module].__file__)
            revision = _hash(source_file.read_bytes().replace(b"\r\n", b"\n"))
            if revision == "4cdc7a127c81e9392851b98c01f9b3595b0433cd2b919cf1425ccc03dfad4c99":
                source = self._bound(spec["spec_binding"])
                constraint = source.get("constraint_binding")
                if not constraint or "supplemental_financing_sources_v1" not in self._bound(constraint):
                    current = current | {source_module: pinned[source_module]}
                    if pinned.get(__name__) == "4636acbdfbf639d68648be86a04c472154b36d71cb106abe6e306d95ad7a529b":
                        current = current | {__name__: pinned[__name__]}
        staged_module = "value_investment_agent.application.research.direct_owner_cash_staged_v3"
        staged_legacy = {
            "2c396c68efd948f7093f26a70e2c4c1ffa0c377adc771a568815d89a80d6658d",
            "ad3b92ce4903790b3aeab224814893418c796b7747d4262e2c000037ea0998bb",
        }
        if staged_module in current and pinned.get(staged_module) in staged_legacy:
            staged_file = Path(sys.modules[staged_module].__file__)
            if _hash(staged_file.read_bytes().replace(b"\r\n", b"\n")) == "55335d685a2045c2b33c9b3446e1eecfac4f690223427c35b079afaa4c0f135b":
                source = self._bound(spec["spec_binding"])
                constraint = source.get("constraint_binding")
                if not constraint or "supplemental_financing_sources_v1" not in self._bound(constraint):
                    current = current | {staged_module: pinned[staged_module]}
                    if pinned.get(__name__) == "975631602fcd2f41149176b2cce3cd000343f3be91559dfc24a351dcbc9bd836":
                        current = current | {__name__: pinned[__name__]}
        previous_interest_service = "7e09ef24373aeeb03231342527ca41a524705b6a924bdfd008d6f69df5cf1d16"
        if pinned == current | {__name__: previous_interest_service}:
            return True
        if pinned == current:
            return True
        source = self._bound(spec["spec_binding"]) if __name__ in pinned else {}
        if {"first_year_operating_cash_method", "first_year_cash_receipts_evidence",
            "paid_note_interest_sources"} & source.keys():
            return False
        # The compiler and forecast additions below are gated by the spec.
        # Only these reviewed source revisions may replay the former wording.
        annual_changes = {
            "direct_owner_cash_agent_facts_v2": (
                "269f3c8f2c7abadffcbb392a160041918b89c58af3681ae5380059f10ef8f529",
                "a36104edc9aea061f28b0092ff27e0509b32aee67266ffc262b5c8f0cc0178fa"),
            "direct_owner_cash_staged_v3": (
                "2c396c68efd948f7093f26a70e2c4c1ffa0c377adc771a568815d89a80d6658d",
                "ad3b92ce4903790b3aeab224814893418c796b7747d4262e2c000037ea0998bb"),
            "direct_owner_cash_compilation_v2": (
                "ba38d058b1f7de2039fe244ceb0378ea97f4bac1f12d07c0b18cbd1c4f408050",
                "fbb7ad124181d540def843a9877773f653ea21d04581c246551a034887f742a1"),
        }
        names = {name: annual_changes[name.rsplit(".", 1)[-1]] for name in current
                 if name.rsplit(".", 1)[-1] in annual_changes}
        if (len(names) != len(annual_changes)
                or any(_hash(Path(sys.modules[name].__file__).read_bytes().replace(b"\r\n", b"\n")) != pair[0]
                       for name, pair in names.items())):
            return False
        current = current | {name: pair[1] for name, pair in names.items()}
        if pinned.get(__name__) in {
            "65f8ec5352838d02a88b6dfaaa90b3cc3ad3ffa39aa137533d8aa8231ec69a8f",
            "16b636cc55a9c8641664a2e97bda779c3a1e640d2ffd9679ce5e90a0b98bb482",
            "272e9c45a4940aee0559ba4e6a75a086842b6580ee373d82582b273fb424fb2b",
            "023721d29de2415825f6650b86e9b343098066efd2ceabd08854f2165b5c9d79",
            "c9664e8f35b451f3d7f0840de189cedb0d71c491054e073ee35c1cecdeb4ab51",
        } and pinned.keys() == current.keys():
            mixed_line_endings = {
                "a36104edc9aea061f28b0092ff27e0509b32aee67266ffc262b5c8f0cc0178fa":
                    "e7f930dc07a0c0fd347fca879b19d6b049648422d7dc8eb0f13ef23b7fd9f3f9",
                "ad3b92ce4903790b3aeab224814893418c796b7747d4262e2c000037ea0998bb":
                    "429f1217495ba7a01be67f6b4f0cc6a9d69b9861aabd3ded93d7231b6d8f5e98",
                "2e83e5f7d27c379719525221c3cb04655b08500041f85648faa5df6b315fd0a1":
                    "f1a3e5b62bb442006ccaefdad51981386d9e487c7d28122361ab65d2a5908d07",
            }
            for name, digest in pinned.items():
                if name == __name__ or digest == current[name]:
                    continue
                lf = Path(sys.modules[name].__file__).read_bytes().replace(b"\r\n", b"\n")
                lf_hash = _hash(lf)
                if (digest in {lf_hash, _hash(lf.replace(b"\n", b"\r\n"))}
                        or mixed_line_endings.get(digest) == lf_hash):
                    continue
                break
            else:
                return True

        if "annual_capex_evidence" in source:
            return False
        # The capex input and policy checks are opt-in. The prior file bytes
        # remain valid for source specs that predate this contract.
        prior = {
            "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2": (
                "70f63e800f161176cc9329ad53b929e06498de8075da906c2a133cb5dffb192c",
                REVIEWED_FINANCING_IMPLEMENTATION[
                    "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2"]),
            "value_investment_agent.application.research.direct_owner_cash_staged_v3": (
                "5848b01a9b567bc193472b2fddf7b6ca048c0b058ac4fa15d75ee7a1312379b1",
                REVIEWED_FINANCING_IMPLEMENTATION[
                    "value_investment_agent.application.research.direct_owner_cash_staged_v3"]),
            __name__: (
                "7ee419c4aca91882d53b64648f0a5e514079e78636e534a013fa6e3f56aaaa7a",
                "93cf408e660e9affac70d70eb6ac4a911e58f14bcff31060d46d3cf77d3fd145"),
        }
        previous = {name: pinned.get(name) for name, hashes in prior.items()
                    if pinned.get(name) in hashes}
        if len(previous) == len(prior) and pinned.keys() == current.keys():
            for name, digest in pinned.items():
                if name in previous or digest == current[name]:
                    continue
                lf = Path(sys.modules[name].__file__).read_bytes().replace(b"\r\n", b"\n")
                if digest in {_hash(lf), _hash(lf.replace(b"\n", b"\r\n"))}:
                    continue
                if (name == terminal_wire.__name__
                        and _hash(lf) == "f1a3e5b62bb442006ccaefdad51981386d9e487c7d28122361ab65d2a5908d07"
                        and digest == "2e83e5f7d27c379719525221c3cb04655b08500041f85648faa5df6b315fd0a1"):
                    continue
                break
            else:
                return True
        current = current | {name: hashes[1] for name, hashes in prior.items() if name != __name__}
        reviewed = all(current.get(name) == digest for name, digest in REVIEWED_FINANCING_IMPLEMENTATION.items())
        if reviewed and __name__ in pinned:
            source = self._bound(spec["spec_binding"])
            historical = {}
            if pinned[__name__] in {"680690b3c064a2491b1c0b983927c7a2ec7a094e10738758ce4e8a9825eaa722", "1d412c35b83df1a1d7518c5beea03b9793daf2effae5b69e95f04b3c902152d9"}:
                staged_name = "value_investment_agent.application.research.direct_owner_cash_staged_v3"
                if pinned.get(staged_name) in {
                    "1bb262ddf5b4737b69a9c74e20f7d328ad332f3c31d225ab9422b6479d26c92c",
                    "90d458591a1e58105a163fde8704f2483c827e16fa2776f97cef019fe550a50f",
                }:
                    historical = {__name__: pinned[__name__], staged_name: pinned[staged_name]}
            elif ("policy_money_wire" not in source
                    and pinned[__name__] == PRE_POLICY_MONEY_IMPLEMENTATION[__name__]):
                historical = PRE_POLICY_MONEY_IMPLEMENTATION
            elif "quarterly_financing_source" not in source and "policy_money_wire" not in source:
                if pinned[__name__] == PRE_QUARTER_FINANCING_IMPLEMENTATION[__name__]:
                    historical = PRE_QUARTER_FINANCING_IMPLEMENTATION
                elif source.get("source_adapter_version") != "UNNUMBERED_OFFICIAL_CNINFO_V2":
                    historical = PRE_FINANCING_IMPLEMENTATION
            current = current | historical
            if historical and pinned.keys() == current.keys():
                compatible = dict(current)
                for name, digest in pinned.items():
                    if name in historical:
                        if (historical is PRE_FINANCING_IMPLEMENTATION
                                and digest == PRE_FINANCING_WINDOWS_OVERRIDES.get(name)):
                            compatible[name] = digest
                        continue
                    if (name == terminal_wire.__name__
                            and current[name] == "68819cfc23750c0120f9b73191f60ad7ffe1c5d7288bc16bc17dc582d950b540"
                            and digest == "2e83e5f7d27c379719525221c3cb04655b08500041f85648faa5df6b315fd0a1"):
                        # This historical checkout combined LF and CRLF in this file.
                        compatible[name] = digest
                        continue
                    raw = Path(sys.modules[name].__file__).read_bytes()
                    lf = raw.replace(b"\r\n", b"\n")
                    if digest in {_hash(lf), _hash(lf.replace(b"\n", b"\r\n"))}:
                        compatible[name] = digest
                if pinned == compatible:
                    return True
        before_terminal = {name: digest for name, digest in current.items()
                           if name != terminal_wire.__name__}
        before_terminal[__name__] = PRE_TERMINAL_WIRE_SERVICE
        if pinned == before_terminal:
            return True
        legacy_wire = {name: digest for name, digest in before_terminal.items()
                       if name != operating_wire.__name__}
        legacy_wire[__name__] = LEGACY_WIRE_SERVICE
        if pinned == legacy_wire:
            return True
        if any(current.get(name) != digest
               for name, digest in _REVIEWED_NUMBERED_COMPATIBILITY_HASHES.items()):
            return False
        legacy = {name: digest for name, digest in current.items()
                  if name not in {operating_wire.__name__, terminal_wire.__name__} and name.rsplit(".", 1)[-1] not in {
                      "parent_direct_owner_cash_unnumbered_v1", "parent_direct_owner_cash_sources"}}
        legacy.update(_PRE_UNNUMBERED_HASHES)
        if pinned != legacy:
            return False
        source = self._bound(spec["spec_binding"])
        return source.get("source_adapter_version") == "NUMBERED_CNINFO_V2"

    @staticmethod
    def _wire(spec, stage, request, *, root=None):
        if stage == "operating" and operating_wire.__name__ in spec["implementation_sha256"]:
            wire = operating_wire.operating_wire_request(request)
            wire_version = spec.get("operating_series_wire")
            if wire_version in {"INPUTS_ONLY_V1", "INPUTS_ONLY_V2"}:
                wire = replace(wire, system=wire.system.replace(
                    "Keep operating_cash distinct from the required other_operating_cash component.",
                    "The application computes total operating cash. Do not emit operating_cash or CFO.",
                ), transport_output_contract=wire.transport_output_contract +
                    " Output only revenue, cost and other_operating_cash inside series; "
                    "never emit operating_cash, even as an explanatory series.")
            if wire_version == "INPUTS_ONLY_V2":
                wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                    " annual_notes is exactly ten plain JSON strings in required_years order. "
                    "Each string explains that year's assumptions in at least 12 characters. "
                    "Never use objects, year keys or nested evidence_anchors in annual_notes. "
                    "Return exactly one JSON object with no trailing text or closing brace.")
            if (spec.get("replay_from_stage") == "base.operating"
                    or spec.get("base_operating_wire") in {"SOURCE_RESIDUAL_V1", "MATCHED_QUARTER_V2"}
                    or spec.get("bear_operating_wire") == "MATCHED_QUARTER_V2"):
                payload = json.loads(wire.user)
                scenario = payload.get("scenario")
                bear_rebuild = scenario == "bear" and spec.get("bear_operating_wire") == "MATCHED_QUARTER_V2"
                base_rebuild = scenario == "base" and (
                    spec.get("replay_from_stage") == "base.operating"
                    or spec.get("base_operating_wire") in {"SOURCE_RESIDUAL_V1", "MATCHED_QUARTER_V2"}
                )
                if base_rebuild or bear_rebuild:
                    source = payload["source_context"]
                    rows = [
                        row for row in source.get("parent_operating_cash_observations", [])
                        if row["period_end"] == source["valuation_date"]
                        and row["symbol"] == source["symbol"]
                        and row["scope"] == terminal_wire.SCOPE
                    ]
                    if len(rows) != 1:
                        raise ValueError("PARENT_OPERATING_RESIDUAL_SOURCE_REQUIRED")
                    row = rows[0]
                    with localcontext() as arithmetic:
                        arithmetic.prec = 48
                        residual = (Decimal(row["cfo"]) - Decimal(row["customer_cash"])
                                    + Decimal(row["supplier_cash"]))
                        ratio = residual / Decimal(row["revenue"])
                    payload["operating_residual_reference"] = {
                        "period_end": row["period_end"], "scope": row["scope"],
                        "formula": "cfo - customer_cash + supplier_cash",
                        "observed_residual_cny": str(residual),
                        "observed_residual_to_revenue": str(ratio),
                        "classification": "HISTORICAL_DIAGNOSTIC_NOT_FORECAST",
                    }
                    if bear_rebuild or spec.get("base_operating_wire") == "MATCHED_QUARTER_V2":
                        from .quarterly_parent_cash_source import replay_quarterly_parent_cash
                        from ....infrastructure.filings.pdf_text import extract_pages
                        from ....infrastructure.filings.quarterly_parent_operating_facts import (
                            build_quarterly_parent_operating_observations,
                        )
                        source_spec = staged_numbered._load_spec(root, spec["spec_binding"])
                        quarterly = source_spec["quarterly_financing_source"]
                        period_end = f"{int(source['valuation_date'][:4]) + 1}-09-30"
                        identity = dict(symbol=source["symbol"], issuer_name=source_spec["issuer_name"],
                                        period_end=period_end)
                        verified = replay_quarterly_parent_cash(root=root, source=quarterly,
                            now=datetime.fromisoformat(spec["created_at"]), **identity)
                        path = root / verified["source"]["path"]
                        pages = extract_pages(path)
                        if _hash(path.read_bytes()) != quarterly["sha256"]:
                            raise ValueError("PARENT_QUARTER_SOURCE_HASH_CHANGED")
                        observed = []
                        with localcontext() as arithmetic:
                            arithmetic.prec = 48
                            for period in build_quarterly_parent_operating_observations(pages, **identity):
                                revenue = Decimal(period["revenue"])
                                cost = Decimal(period["cost"])
                                collected = Decimal(period["customer_cash"])
                                paid = Decimal(period["supplier_cash"])
                                other = Decimal(period["cfo"]) - collected + paid
                                observed.append(dict(period_end=period["period_end"],
                                    customer_cash_to_revenue=str(collected / revenue),
                                    supplier_cash_to_cost=str(paid / cost),
                                    other_operating_cash_to_revenue=str(other / revenue)))
                        payload["matched_quarter_cash_conversion"] = dict(
                            classification="HISTORICAL_NOT_ANNUALISED_NOT_TERMINAL",
                            source_sha256=quarterly["sha256"], observations=observed)
                        wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                            " Use the matched quarter observations to challenge durable supplier "
                            "payment improvements and changes in other operating cash. Do not "
                            "annualise nine-month coefficients. Distinguish timing from recurrence.")
                    if scenario == "base" and spec.get("base_cash_transition_wire") == "FY_AFTER_OBSERVED_9M_V1":
                        wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                            " The observed-nine-month plus Q4 method applies only to the first forecast year. "
                            "Later years use full-year historical payment and collection coefficients. "
                            "Do not carry a nine-month timing effect, the revenue-minus-cost difference, "
                            "or customer/supplier cash already counted in those coefficients into the "
                            "other_operating_cash aggregate. Explain any sustained departure from the "
                            "signed full-year residual by identifying which net operating items change.")
                    if bear_rebuild:
                        wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                            " Match the actual cash collection and supplier payment basis. "
                            "Only include cash flows already classified within operating cash in "
                            "other_operating_cash. Leave note interest, financing and separately "
                            "deducted mandatory cash outside this component.")
                    wire = replace(wire, user=json.dumps(payload, ensure_ascii=False,
                        sort_keys=True, separators=(",", ":")),
                        transport_output_contract=wire.transport_output_contract +
                        " Forecast other_operating_cash as the net of staff, taxes, and other "
                        "operating receipts and payments outside customer and supplier cash. "
                        "Use the historical diagnostic as a scale check. Explain material "
                        "changes in the component drivers and why they persist; do not treat "
                        "the residual as only working capital or target a terminal value.")
            return wire
        if stage == "policy" and policy_capital.__name__ in spec["implementation_sha256"]:
            wire = policy_capital.policy_capital_request(request, spec["policy_capital_basis"])
            if financing_schedule.__name__ not in spec["implementation_sha256"]:
                return wire
            payload = json.loads(wire.user)
            schedule = financing_schedule.disclosed_schedule_from_context(payload["source_context"])
            if schedule is None:
                if "conditional_financing_stress" in spec:
                    raise ValueError("PARENT_V3_POLICY_COUPON_SOURCE_REQUIRED")
                return wire
            if (spec.get("base_policy_wire") in {"ANNUAL_EARNINGS_BRIDGE_V1", "ANNUAL_EARNINGS_BRIDGE_V2"}
                    and payload["scenario"] == "base"):
                source = payload["source_context"]
                history = [row for row in source["parent_operating_cash_observations"]
                           if row["period_end"] == source["valuation_date"]
                           and row["scope"] == terminal_wire.SCOPE and row["symbol"] == source["symbol"]]
                if len(history) != 1 or "profit_and_operating_cash" not in history[0]:
                    raise ValueError("PARENT_POLICY_ANNUAL_PROFIT_SOURCE_REQUIRED")
                row = history[0]
                scenarios = payload["prior_forecast_assumptions_not_facts"]["operating"]
                with localcontext() as arithmetic:
                    arithmetic.prec = 48
                    gross = Decimal(row["revenue"]) - Decimal(row["cost"])
                    profit = Decimal(row["profit_and_operating_cash"]["parent_profit_cny"])
                    payload["annual_earnings_bridge"] = {
                        "classification": "HISTORICAL_DIAGNOSTIC_AND_CONDITIONAL_DRIVERS",
                        "historical_period_end": row["period_end"],
                        "historical_gross_profit_cny": str(gross),
                        "historical_parent_net_profit_cny": str(profit),
                        "historical_net_less_gross_cny": str(profit - gross),
                        "scenario_gross_profit_cny": [
                            dict(year=year, amount_cny=str(Decimal(revenue) - Decimal(cost)))
                            for year, revenue, cost in zip(payload["required_years"],
                                scenarios["revenue"], scenarios["cost"], strict=True)
                        ],
                    }
                if spec["base_policy_wire"] == "ANNUAL_EARNINGS_BRIDGE_V2":
                    with localcontext() as arithmetic:
                        arithmetic.prec = 48
                        historical_revenue = Decimal(row["revenue"])
                        historical_cost = Decimal(row["cost"])
                        historical_collections = Decimal(row["customer_cash"])
                        historical_supplier_cash = Decimal(row["supplier_cash"])
                        historical_other = Decimal(row["cfo"]) - historical_collections + historical_supplier_cash
                        cash_bridge = []
                        # The first forecast year uses a separate actuals and
                        # remaining-period bridge. These coefficients are full-year only.
                        for forecast_year, revenue, cost, other in zip(
                                payload["required_years"], scenarios["revenue"], scenarios["cost"],
                                scenarios["other_operating_cash"], strict=True):
                            if forecast_year == payload["required_years"][0]:
                                continue
                            sales = Decimal(revenue)
                            collected = sales * historical_collections / historical_revenue
                            paid = Decimal(cost) * historical_supplier_cash / historical_cost
                            forecast_other = Decimal(other)
                            scaled_other = sales * historical_other / historical_revenue
                            cash_bridge.append(dict(year=forecast_year,
                                customer_cash_cny=str(collected), supplier_cash_cny=str(paid),
                                forecast_other_operating_cash_cny=str(forecast_other),
                                scenario_operating_cash_cny=str(collected - paid + forecast_other),
                                historical_intensity_other_cash_cny=str(scaled_other),
                                historical_intensity_operating_cash_cny=str(collected - paid + scaled_other)))
                    payload["operating_cash_conversion_diagnostic"] = dict(
                        classification="CONDITIONAL_SENSITIVITY_NOT_ADOPTED",
                        historical_period_end=row["period_end"], annual=cash_bridge)
                    wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                        " Review the operating cash conversion diagnostic. The historical "
                        "intensity path is only a counterfactual. Explain any long-run divergence "
                        "in payroll, taxes or other operating cash without treating it as a "
                        "separate expense or cash flow. If durable conversion cannot be explained, "
                        "the operating premise requires revision before a terminal can be adopted.")
                wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                    " Derive each year's parent_profit from the same scenario gross-profit path. "
                    "Explain expenses, finance income, investment income and taxes below gross "
                    "profit. The historical residual is a scale check, not a plug or forecast. "
                    "Separate realised gross capex from future maintenance and growth. A missing "
                    "plan does not imply zero maintenance. Do not place observed gross capex into "
                    "one component without a defensible conditional split or use it as terminal proof.")
            year, ceiling, floors = financing_schedule.disclosed_financing_limits(schedule)
            if ((spec.get("base_policy_wire") == "ANNUAL_EARNINGS_BRIDGE_V2"
                 and payload["scenario"] == "base")
                    or (spec.get("bear_financing_wire") == "MATCHED_PRINCIPAL_WINDOW_V1"
                        and payload["scenario"] == "bear")):
                with localcontext() as arithmetic:
                    arithmetic.prec = 48
                    opening = Decimal(spec["policy_capital_basis"]["amount_cny"])
                    observed = Decimal(schedule["reported_ytd_cny"]["borrowings_received_cny"])
                    repayment = floors[year]
                    payload["financing_principal_diagnostic"] = {
                        "classification": "FORECAST_ARITHMETIC_NOT_FINANCING_FACT",
                        "observed_through": schedule["period_end"],
                        "observed_borrowing_cny": str(observed),
                        "later_disclosed_gross_ceiling_increment_cny": str(ceiling - observed),
                        "closing_principal_if_only_observed_borrowing_cny": str(opening + observed - repayment),
                        "minimum_borrowing_for_nonnegative_principal_cny": str(
                            max(observed, repayment - opening)),
                        "minimum_borrowing_if_no_new_debt_through_next_year_cny": str(
                            max(observed, repayment + floors.get(year + 1, Decimal(0)) - opening)),
                        "cash_receipt_verified": False,
                    }
                wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                    " The observed borrowing is only through observed_through and excludes "
                    "later announced issues. The minimum is a diagnostic, not a funding source. "
                    "Use a separately justified conditional financing assumption or acknowledge "
                    "that the policy cannot be supported. Do not manufacture borrowing.")
            payload["disclosed_financing_limits"] = {
                "borrowing_ceiling_year": year,
                "borrowing_ceiling_cny": str(ceiling),
                "repayment_minimum_by_year_cny": {str(y): str(v) for y, v in floors.items()},
                "classification": "CONDITIONAL_NOT_ACTUAL_SETTLEMENT",
            }
            if spec.get("scenario_interest_wire") == "CONDITIONAL_COUPON_COVERAGE_V1":
                payload["conditional_issuer_note_coupon_calendar"] = _conditional_coupon_calendar(
                    root, schedule, symbol=payload["source_context"]["symbol"],
                    as_of=datetime.fromisoformat(spec["created_at"]))
                wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                    " Interest outside CFO must cover already paid interest plus the shown "
                    "conditional coupons in each applicable year, without counting either twice. "
                    "Explain the interest on residual debt or its documented repayment path. "
                    "An unknown residual interest payment cannot be entered as zero. "
                    "Use only the exact declared series properties.")
            if (spec.get("base_interest_wire") in {"ISSUER_FINANCING_INTEREST_V1", "ISSUER_FINANCING_INTEREST_V2"}
                    and payload["scenario"] == "base"):
                maturity_years = sorted({
                    int(issue["terms"]["maturity"][:4]) for issue in schedule["later_issues"].values()
                })
                payload["conditional_issuer_note_interest_years"] = maturity_years
                if "base_principal_reference" in spec:
                    payload["locked_conditional_principal"] = spec["base_principal_reference"]
                    wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                        " Use the locked conditional new_borrowing and debt_repayment arrays "
                        "exactly. They are a verified arithmetic scenario, not actual funding. "
                        "If inconsistent with the other assumptions, the policy must be reopened.")
                if spec["base_interest_wire"] == "ISSUER_FINANCING_INTEREST_V2":
                    payload["conditional_issuer_note_coupon_calendar"] = _conditional_coupon_calendar(
                        root, schedule, symbol=payload["source_context"]["symbol"],
                        as_of=datetime.fromisoformat(spec["created_at"]))
                wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                    " The selected policy models parent borrowing outside operating cash. "
                    "For later disclosed borrowing carried through contractual maturity, "
                    "provide a supported conditional cash interest estimate in maturity years "
                    "and whenever parent principal remains outstanding. Treat uncertain "
                    "interest as unresolved, not zero; do not double count it in operating cash.")
            wire = replace(wire, user=json.dumps(payload, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")), transport_output_contract=wire.transport_output_contract +
                " Use the computed disclosed_financing_limits without re-summing note amounts. "
                "The borrowing ceiling includes full gross disclosed proceeds as an upper "
                "conditional input; it does not verify actual cash receipt. Annual repayment "
                "minimums already include observed principal and applicable later maturities. "
                "Do not add those amounts again or insert balancing debt.")
            stress = spec.get("conditional_financing_stress")
            if stress is None:
                return wire
            if spec["financing_wire_sha256"] != _hash(Path(fixed_financing.__file__).read_bytes()):
                raise ValueError("PARENT_V3_FINANCING_WIRE_IMPLEMENTATION_CHANGED")
            source = payload["source_context"]
            calendar = payload.get("conditional_issuer_note_coupon_calendar")
            paid = source.get("annual_paid_note_interest_floor")
            if calendar is None or paid is None:
                raise ValueError("PARENT_V3_POLICY_COUPON_SOURCE_REQUIRED")
            terms = fixed_financing.conditional_no_refinance_terms(
                years=payload["required_years"], schedule=schedule, calendar=calendar,
                opening_principal=spec["policy_capital_basis"]["amount_cny"], paid_interest=paid,
                residual_stress_rate=stress["residual_stress_rate"], anchors=stress["evidence_anchors"])
            return fixed_financing.financing_policy_request(wire, terms)
        if stage == "terminal" and terminal_wire.__name__ in spec["implementation_sha256"]:
            payload = json.loads(request.user)
            source = payload["source_context"]
            if source.get("first_year_operating_cash_method"):
                # The terminal reference is the last forecast year. The partial-year
                # actuals method applies only to the first forecast year.
                if payload["terminal_reference_year"] <= int(source["valuation_date"][:4]) + 1:
                    raise ValueError("PARENT_TERMINAL_REFERENCE_YEAR_INVALID")
                payload["source_context"] = {
                    key: value for key, value in source.items()
                    if key != "first_year_operating_cash_method"
                }
                wire = terminal_wire.terminal_wire_request(replace(request, user=json.dumps(payload)))
                result = json.loads(wire.user)
                result["source_context"] = source
                reference = result.get("terminal_transition_reference")
                if (spec.get("replay_from_stage") == "base.terminal" and reference is not None
                        and payload.get("scenario") == "base"):
                    policy = reference["policy_cash_inputs_cny"]
                    fields = ("maintenance_capex", "growth_capex", "interest_outside_cfo",
                              "other_mandatory_cash", "commitments_outside_capex", "debt_repayment")
                    with localcontext() as arithmetic:
                        arithmetic.prec = 48
                        operating = Decimal(reference["operating_cash_cny"])
                        receipts = Decimal(policy["investment_cash_received"])
                        net = operating + receipts + Decimal(policy["new_borrowing"]) - sum(
                            Decimal(policy[field]) for field in fields
                        )
                        reference["annual_net_cash_cny"] = str(net)
                        reference["annual_cash_minus_profit_cny"] = str(net - Decimal(policy["parent_profit"]))
                    wire = replace(wire, transport_output_contract=wire.transport_output_contract +
                        " The computed bridge is the last annual forecast diagnostic only. "
                        "Year-to-date investment cash and capex floors do not establish terminal "
                        "recurrence. Explain supported changes in collection, payments, investment "
                        "remittances and reinvestment separately. If evidence cannot reconcile "
                        "stationary cash and profit, do not invent balancing cash or expenses.")
                return replace(wire, user=json.dumps(result, ensure_ascii=False,
                    sort_keys=True, separators=(",", ":")))
            return terminal_wire.terminal_wire_request(request)
        return request

    def _parse_stage(self, spec, stage, response, request, source_fingerprint):
        parse = (operating_wire.parse_operating_wire
                 if stage == "operating" and operating_wire.__name__ in spec["implementation_sha256"]
                 else parse_staged_parent_cash_response)
        if stage == "policy" and "conditional_financing_stress" in spec:
            wire = self._wire(spec, stage, request, root=self.root)
            response = fixed_financing.merge_financing_policy_response(response, wire)
        parsed = parse(response, request=request, source_fingerprint=source_fingerprint)
        if stage == "policy" and policy_capital.__name__ in spec["implementation_sha256"]:
            schedule = None
            if financing_schedule.__name__ in spec["implementation_sha256"]:
                schedule = financing_schedule.disclosed_schedule_from_context(
                    json.loads(request.user)["source_context"],
                )
                if schedule is not None:
                    financing_schedule.validate_disclosed_financing_policy(schedule, parsed)
            debt_path = policy_capital.validate_policy_debt(spec["policy_capital_basis"], parsed)
            if spec.get("scenario_interest_wire") == "CONDITIONAL_COUPON_COVERAGE_V1":
                if schedule is None:
                    raise ValueError("PARENT_V3_POLICY_COUPON_SOURCE_REQUIRED")
                source = json.loads(request.user)["source_context"]
                calendar = _conditional_coupon_calendar(self.root, schedule, symbol=source["symbol"],
                    as_of=datetime.fromisoformat(spec["created_at"]))
                _validate_scenario_interest(parsed, debt_path, source, calendar)
            locked = spec.get("base_principal_reference")
            if locked is not None and json.loads(request.user)["scenario"] == "base":
                if (parsed["years"] != locked["years"] or any(
                        list(map(Decimal, parsed["series"][field]["values"])) !=
                        list(map(Decimal, locked[field]))
                        for field in ("new_borrowing", "debt_repayment"))):
                    raise ValueError("PARENT_V3_LOCKED_CONDITIONAL_PRINCIPAL_CHANGED")
            if (spec.get("base_interest_wire") in {"ISSUER_FINANCING_INTEREST_V1", "ISSUER_FINANCING_INTEREST_V2"}
                    and json.loads(request.user)["scenario"] == "base"):
                amounts = parsed["series"]["interest_outside_cfo"]["values"]
                for row, amount in zip(debt_path, amounts, strict=True):
                    if ((Decimal(row["opening_debt_cny"]) > 0
                            or Decimal(row["new_borrowing_cny"]) > 0)
                            and Decimal(amount) <= 0):
                        raise ValueError(f"PARENT_V3_POLICY_DEBT_INTEREST_UNSUPPORTED:{row['year']}")
        return parsed

    def _context(self, spec, now):
        if (self._configuration() != spec["config"]
                or not self._implementation_matches(spec)
                or spec.get("shared_budget_root") != str(self.shared_budget_root)):
            raise PermissionError("MODEL_AUTHORIZATION_CHANGED")
        context = read_parent_cash_agent_facts_v2(root=self.root,
            spec_binding=spec["spec_binding"], now=now)
        if context["input_fingerprint"] != spec["source_fingerprint"]:
            raise ValueError("PARENT_SOURCE_CHANGED")
        return context

    def _load(self, task_id, *, recover=False):
        directory = self._directory(task_id)
        raw = (directory / "input.json").read_bytes()
        spec = json.loads(raw)
        if (spec.get("schema_version") != VERSION or spec.get("task_id") != task_id
                or spec.get("action") != "no_order" or spec.get("mode") not in
                {"LIVE_PARENT_CASH_V3", "TEST_ONLY_PARENT_CASH_V3"}):
            raise ValueError("PARENT_TASK_INPUT_INVALID")
        files = sorted((directory / "versions").glob("*.json"))
        if not 1 <= len(files) <= 128:
            raise ValueError("PARENT_TASK_CHAIN_MISSING_OR_UNBOUNDED")
        previous = None
        for number, path in enumerate(files, 1):
            binding = self._binding(path)
            row = self._bound(binding)
            if (path.name != f'{number:04d}-{binding["sha256"]}.json'
                    or row.get("schema_version") != VERSION or row.get("task_id") != task_id
                    or row.get("version") != number or row.get("previous") != previous
                    or row.get("input_sha256") != _hash(raw)
                    or row.get("status") not in STATES or row.get("action") != "no_order"
                    or row.get("formal_eligibility") is not False):
                raise ValueError("PARENT_TASK_CHAIN_INVALID")
            previous = binding
        head = directory / "current.json"
        if head.exists():
            published = json.loads(head.read_bytes())
            if published not in [self._binding(path) for path in files]:
                raise ValueError("PARENT_TASK_HEAD_INVALID")
        elif not recover:
            raise ValueError("PARENT_TASK_HEAD_MISSING_EXPLICIT_RESUME")
        if not head.exists() or published != previous:
            if not recover:
                raise ValueError("PARENT_TASK_UNPUBLISHED_EXPLICIT_RESUME")
            self._head(directory, previous)
        return spec, row, previous

    def _save(self, spec, state, previous, now, **changes):
        row = deepcopy(state)
        row.update(changes)
        row.update(schema_version=VERSION, task_id=spec["task_id"],
                   input_sha256=_hash(_bytes(spec)), previous=previous,
                   version=state.get("version", 0) + 1, updated_at=now.isoformat())
        raw = _bytes(row)
        directory = self._directory(spec["task_id"])
        path = directory / "versions" / f'{row["version"]:04d}-{_hash(raw)}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new_bytes(path, raw)
        binding = self._binding(path)
        self._head(directory, binding)
        return row, binding

    def _stage_outputs(self, spec, state, now, *, verified_context=None):
        context = verified_context if verified_context is not None else self._context(spec, now)
        self._verify_charges(state)
        seed = spec.get("seed")
        if seed is not None:
            if seed["task_id"] == spec.get("task_id"):
                raise ValueError("PARENT_SEED_SELF_REFERENCE")
            old_spec, old_state, old_head = self._load(seed["task_id"])
            if (old_head != seed["head"] or old_state["status"] != "FAILED"
                    or old_spec["source_fingerprint"] != spec["source_fingerprint"]
                    or old_spec["spec_binding"] != spec["spec_binding"]
                    or old_spec["mode"] != spec["mode"]):
                raise ValueError("PARENT_SEED_CHANGED")
            self._verify_charges(old_state)
            # Revalidate only the inherited stage bindings. A predecessor may
            # contain rejected stages that this new task deliberately re-runs.
            inherited = deepcopy(old_state)
            inherited["responses"] = {stage: binding for stage, binding in
                old_state["responses"].items() if stage in seed["responses"]}
            inherited_spec = deepcopy(old_spec)
            if inherited_spec.get("seed") is not None:
                inherited_spec["seed"]["responses"] = {stage: binding for stage, binding in
                    inherited_spec["seed"]["responses"].items()
                    if stage in inherited["responses"]}
            self._stage_outputs(inherited_spec, inherited, now, verified_context=context)
            for stage, binding in seed["responses"].items():
                if old_state["responses"].get(stage) == binding:
                    continue
                if not binding["path"].startswith(
                    self._directory(seed["task_id"]).relative_to(self.root).as_posix() + "/response-"):
                    raise ValueError("PARENT_SEED_RESPONSE_PATH_INVALID")
                if binding not in old_state.get("returned_responses", []):
                    raise ValueError("PARENT_SEED_RESPONSE_CHANGED")
                reservation = Path(binding["path"]).stem.removeprefix("response-")
                charge = old_state["reservations"].get(reservation)
                if (not charge or charge["scenario"] != stage
                        or charge["status"] != "SETTLED"):
                    raise ValueError("PARENT_SEED_RESPONSE_NOT_SETTLED")
            if any(state["responses"].get(stage) != binding
                   for stage, binding in seed["responses"].items()):
                raise ValueError("PARENT_SEED_BINDING_CHANGED")
        outputs = {scenario: {} for scenario in SCENARIOS}
        if set(state["responses"]) - set(STAGE_ORDER):
            raise ValueError("PARENT_V3_UNKNOWN_STAGE")
        for stage_id in STAGE_ORDER:
            if stage_id not in state["responses"]:
                continue
            scenario, stage = stage_id.split(".")
            prior = outputs[scenario]
            if set(prior) != set(STAGES[:STAGES.index(stage)]):
                raise ValueError("PARENT_V3_PRIOR_STAGE_MISSING")
            binding = state["responses"][stage_id]
            packet = self._bound(binding)
            request = staged_parent_cash_request_v3(root=self.root,
                spec_binding=spec["spec_binding"], scenario=scenario, stage=stage,
                prior_drafts=prior, generated_at=datetime.fromisoformat(spec["created_at"]),
                verified_context=context,
                max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
            if (packet.get("scenario") != stage_id or packet.get("request_sha256") !=
                    _hash(_bytes(self._wire(spec, stage, request, root=self.root).__dict__)) or packet.get("source_fingerprint") !=
                    context["input_fingerprint"] or packet.get("action") != "no_order"):
                raise ValueError("PARENT_RESPONSE_BINDING_INVALID")
            parsed = self._parse_stage(spec, stage,
                LLMResponse(**packet["response"]), request=request,
                source_fingerprint=context["input_fingerprint"])
            if stage == "terminal":
                preflight_terminal_forecast_debt_v3(request=request, parsed_stage=parsed)
            outputs[scenario][stage] = parsed
        return outputs

    def _drafts(self, spec, state, now):
        context = self._context(spec, now)
        outputs = self._stage_outputs(spec, state, now, verified_context=context)
        drafts = {}
        for scenario, stages in outputs.items():
            if not stages:
                continue
            if set(stages) != set(STAGES):
                continue
            requests = {}
            for stage in STAGES:
                prior = {name: stages[name] for name in STAGES[:STAGES.index(stage)]}
                requests[stage] = staged_parent_cash_request_v3(root=self.root,
                    spec_binding=spec["spec_binding"], scenario=scenario, stage=stage,
                    prior_drafts=prior, generated_at=datetime.fromisoformat(spec["created_at"]),
                    verified_context=context,
                    max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
            responses = {stage: LLMResponse(text=json.dumps(stages[stage], ensure_ascii=False),
                prompt_tokens=0, completion_tokens=0, model_id=spec["config"]["model_id"])
                for stage in STAGES}
            drafts[scenario] = merge_staged_parent_cash_v3(
                scenario=scenario, source_fingerprint=spec["source_fingerprint"],
                requests=requests, responses=responses)
        return drafts

    def _verify_charges(self, state):
        """Read the existing shared ledger before trusting any published response."""
        reserved = settled = Decimal(0)
        by_day = {}
        for reservation, charge in state["reservations"].items():
            if (not re.fullmatch(r"[0-9a-f]{64}", reservation)
                    or charge.get("scenario") not in STAGE_ORDER
                    or charge.get("status") not in {"RESERVED", "SETTLED"}
                    or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", charge.get("day", ""))):
                raise ValueError("PARENT_CHARGE_RECORD_INVALID")
            amount = Decimal(charge["cost"])
            if not amount.is_finite() or amount < 0:
                raise ValueError("PARENT_CHARGE_AMOUNT_INVALID")
            if charge["status"] == "RESERVED":
                reserved += amount
                if charge["scenario"] in state["responses"]:
                    raise ValueError("PARENT_RESPONSE_NOT_SETTLED")
            else:
                actual = Decimal(charge["actual_cost"])
                if not actual.is_finite() or not 0 <= actual <= amount:
                    raise ValueError("PARENT_CHARGE_SETTLEMENT_INVALID")
                settled += actual
            by_day.setdefault(charge["day"], []).append((reservation, charge))
        if (Decimal(state["reserved_cost"]) != reserved
                or Decimal(state["settled_cost"]) != settled):
            raise ValueError("PARENT_CHARGE_TOTAL_MISMATCH")
        for day, charges in by_day.items():
            directory = require_inside(self.daily.base,
                self.daily.base / "budget" / day, "parent cash shared budget")
            with self.daily._lock(directory):
                files = sorted((directory / "versions").glob("*.json"))
                if not 1 <= len(files) <= 512:
                    raise ValueError("PARENT_BUDGET_CHAIN_INVALID")
                previous = None
                for number, path in enumerate(files, 1):
                    pin = self.daily._binding(path)
                    row = self.daily._bound(pin)
                    if (path.name != f'{number:04d}-{pin["sha256"]}.json'
                            or row.get("previous") != previous
                            or row.get("version") != number
                            or row.get("day") != day or row.get("currency") != "CNY"):
                        raise ValueError("PARENT_BUDGET_CHAIN_INVALID")
                    previous = pin
                if (directory / "current.json").read_bytes() != _bytes(previous):
                    raise ValueError("PARENT_BUDGET_HEAD_INVALID")
                for reservation, charge in charges:
                    expected = (dict(status="RESERVED", cost=charge["cost"])
                        if charge["status"] == "RESERVED" else
                        dict(status="SETTLED", cost=charge["actual_cost"]))
                    if row["records"].get(reservation) != expected:
                        raise ValueError("PARENT_BUDGET_CHARGE_MISMATCH")

    def _view(self, spec, state, binding, now):
        view = deepcopy(state)
        view.update(record_binding=binding, mode=spec["mode"],
            spec_binding=spec["spec_binding"], source_fingerprint=spec["source_fingerprint"],
            recovery_boundary=("SOURCE_AND_REQUEST_VERIFIED_SEED_NO_AUTOMATIC_RESEND"
                if spec.get("seed") is not None else "PUBLISHED_RESPONSES_ONLY_NO_AUTOMATIC_RESEND"),
            approval_changed=False, main_range_adopted=False)
        if spec.get("seed") is not None:
            view["reused_stages"] = list(spec["seed"]["responses"])
            view["reused_from_task_id"] = spec["seed"]["task_id"]
        if "conditional_financing_stress" in spec:
            view["fixed_financing_research"] = True
        if not self._implementation_matches(spec):
            view.update(historical_status=state["status"],
                        historical_error_code=state.get("error_code"),
                        status="FAILED", error_code="PARENT_IMPLEMENTATION_CHANGED_REPLAY_REQUIRED")
            return view
        try:
            drafts = self._drafts(spec, state, now)
            view["completed_stages"] = [stage for stage in STAGE_ORDER
                if stage in state["responses"]]
            view["completed_scenarios"] = sorted(drafts)
            if state["status"] == "SUCCEEDED":
                if set(drafts) != set(SCENARIOS):
                    raise ValueError("PARENT_RESULT_INCOMPLETE")
                view["candidate"] = assemble_parent_cash_drafts_v2(root=self.root,
                    spec_binding=spec["spec_binding"], drafts=drafts, generated_at=now)
        except (ValueError, OSError, KeyError, TypeError, PermissionError):
            view.update(status="FAILED", error_code="PARENT_SOURCE_OR_CHECKPOINT_INVALID")
        return view

    def create(self, *, spec_binding, request_key, now=None, seed_task_id=None,
               replay_from_stage=None):
        now = _now(now)
        if not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key):
            raise ValueError("PARENT_REQUEST_KEY_INVALID")
        if replay_from_stage is not None and (seed_task_id is None
                                               or replay_from_stage not in STAGE_ORDER):
            raise ValueError("PARENT_REPLAY_STAGE_INVALID")
        task_id = "rt-" + _hash((VERSION + ":" + request_key).encode("utf-8"))[:32]
        directory = self._directory(task_id)
        if (directory / "input.json").exists():
            with self._lock(directory):
                old, state, binding = self._load(task_id)
                if (old["spec_binding"] != spec_binding
                        or (old.get("seed") or {}).get("task_id") != seed_task_id
                        or old.get("replay_from_stage") != replay_from_stage
                        or old["mode"] != ("TEST_ONLY_PARENT_CASH_V3"
                            if self.test_provider is not None else "LIVE_PARENT_CASH_V3")):
                    raise ValueError("PARENT_REQUEST_KEY_CONFLICT")
                return self._view(old, state, binding, now)
        cfg = self._configuration()
        if cfg["model_id"] != "deepseek-flash" or cfg["max_completion_tokens_cap"] < 1024:
            raise ValueError("PARENT_MODEL_CONTRACT_INVALID")
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context = read_parent_cash_agent_facts_v2(root=self.root, spec_binding=spec_binding, now=now)
        capital_basis = None
        seed = None
        ancestor_spend = Decimal(0)
        seed_created_at = now.isoformat()
        if seed_task_id is not None:
            old_spec, old_state, old_head = self._load(seed_task_id)
            if (old_state["status"] != "FAILED" or old_spec["spec_binding"] != spec_binding
                    or old_spec["source_fingerprint"] != context["input_fingerprint"]
                    or old_spec["config"] != cfg
                    or old_spec["mode"] != ("TEST_ONLY_PARENT_CASH_V3" if self.test_provider is not None
                                                else "LIVE_PARENT_CASH_V3")):
                raise ValueError("PARENT_SEED_INCOMPATIBLE")
            self._verify_charges(old_state)
            source_spec = staged_numbered._load_spec(self.root, spec_binding)
            capital_basis = policy_capital.opening_debt_basis(source_spec["opening"], context["facts"])
            ancestor_spend = (Decimal(old_spec.get("ancestor_spend", "0"))
                + Decimal(old_state["reserved_cost"]) + Decimal(old_state["settled_cost"]))
            if ancestor_spend >= Decimal(str(cfg["max_run_cost"])):
                raise ValueError("PARENT_TASK_BUDGET_EXHAUSTED")
            seed_created_at = old_spec["created_at"]
            seed = dict(task_id=seed_task_id, head=old_head, responses={})
            # Only stages with unchanged request bytes are reusable. A changed
            # prompt or source requires a new model response.
            trial = dict(responses={}, reservations={}, reserved_cost="0", settled_cost="0")
            trial_spec = dict(spec_binding=spec_binding, source_fingerprint=context["input_fingerprint"],
                              config=cfg, created_at=seed_created_at,
                              shared_budget_root=str(self.shared_budget_root),
                              implementation_sha256=_implementation(), policy_capital_basis=capital_basis,
                              replay_from_stage=replay_from_stage)
            if replay_from_stage == "bear.operating":
                trial_spec["operating_series_wire"] = "INPUTS_ONLY_V2"
            elif "operating_series_wire" in old_spec:
                trial_spec["operating_series_wire"] = old_spec["operating_series_wire"]
            if (replay_from_stage == "bear.policy" and old_state.get("error_code") ==
                    "BEAR_POLICY_PARENT_V3_FORECAST_DEBT_NEGATIVE"):
                trial_spec["bear_financing_wire"] = "MATCHED_PRINCIPAL_WINDOW_V1"
            elif "bear_financing_wire" in old_spec:
                trial_spec["bear_financing_wire"] = old_spec["bear_financing_wire"]
            if "scenario_interest_wire" in old_spec:
                trial_spec["scenario_interest_wire"] = old_spec["scenario_interest_wire"]
            if "conditional_financing_stress" in old_spec:
                trial_spec["conditional_financing_stress"] = old_spec["conditional_financing_stress"]
                trial_spec["financing_wire_sha256"] = old_spec["financing_wire_sha256"]
                if (replay_from_stage == "bear.operating" and old_state.get("error_code") ==
                        "BEAR_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"):
                    trial_spec["bear_operating_wire"] = "MATCHED_QUARTER_V2"
                elif "bear_operating_wire" in old_spec:
                    trial_spec["bear_operating_wire"] = old_spec["bear_operating_wire"]
            elif (replay_from_stage == "bear.policy"
                  and old_spec.get("bear_financing_wire") == "MATCHED_PRINCIPAL_WINDOW_V1"
                  and old_state.get("error_code") == "BASE_POLICY_PARENT_DRAFT_TERM_SOURCE_INVALID"
                  and any(row["source"].get("redemption_wire") == "MULTI_LAYOUT_V1"
                          for row in (context.get("annual_paid_note_interest_floor") or {}).get("evidence", ()))):
                trial_spec["scenario_interest_wire"] = "CONDITIONAL_COUPON_COVERAGE_V1"
            if "base_cash_transition_wire" in old_spec:
                trial_spec["base_cash_transition_wire"] = old_spec["base_cash_transition_wire"]
            if (replay_from_stage == "base.operating"
                    and old_spec.get("bear_operating_wire") == "MATCHED_QUARTER_V2"
                    and old_state.get("error_code") ==
                    "BASE_POLICY_PARENT_V3_ECONOMIC_DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2027"):
                trial_spec["base_cash_transition_wire"] = "FY_AFTER_OBSERVED_9M_V1"
                trial_spec["base_operating_wire"] = "MATCHED_QUARTER_V2"
            elif (replay_from_stage == "base.operating"
                    and old_spec.get("base_policy_wire") == "ANNUAL_EARNINGS_BRIDGE_V2"
                    and old_state.get("error_code") ==
                    "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"):
                trial_spec["base_operating_wire"] = "MATCHED_QUARTER_V2"
            elif (old_spec.get("replay_from_stage") == "base.operating"
                    or "base_operating_wire" in old_spec):
                trial_spec["base_operating_wire"] = old_spec.get("base_operating_wire", "SOURCE_RESIDUAL_V1")
            if replay_from_stage == "base.policy" and old_state.get("error_code") == (
                    "BASE_POLICY_PARENT_V3_FORECAST_DEBT_NEGATIVE"):
                trial_spec["base_policy_wire"] = "ANNUAL_EARNINGS_BRIDGE_V2"
            elif (old_spec.get("base_policy_wire") in {"ANNUAL_EARNINGS_BRIDGE_V1", "ANNUAL_EARNINGS_BRIDGE_V2"}
                    or (replay_from_stage == "base.policy" and old_state.get("error_code") ==
                        "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION")):
                trial_spec["base_policy_wire"] = old_spec.get("base_policy_wire", "ANNUAL_EARNINGS_BRIDGE_V1")
            if (old_spec.get("base_interest_wire") in {"ISSUER_FINANCING_INTEREST_V1", "ISSUER_FINANCING_INTEREST_V2"}
                    or (replay_from_stage == "base.policy"
                        and old_spec.get("base_operating_wire") == "MATCHED_QUARTER_V2"
                        and old_state.get("error_code") in {
                            "BASE_POLICY_PARENT_DRAFT_REJECTED_OR_UNPUBLISHED",
                            "BASE_POLICY_PARENT_FINANCING_ABOVE_DISCLOSED_PROCEEDS:2026",
                        })):
                trial_spec["base_interest_wire"] = old_spec.get("base_interest_wire", "ISSUER_FINANCING_INTEREST_V2")
            if "base_principal_reference" in old_spec:
                trial_spec["base_principal_reference"] = old_spec["base_principal_reference"]
            elif trial_spec.get("base_interest_wire") == "ISSUER_FINANCING_INTEREST_V2":
                predecessor = old_spec["seed"]
                financing_spec, financing_state, financing_head = self._load(predecessor["task_id"])
                if (financing_head != predecessor["head"]
                        or financing_spec["spec_binding"] != spec_binding
                        or financing_spec["source_fingerprint"] != context["input_fingerprint"]
                        or financing_spec.get("base_policy_wire") != "ANNUAL_EARNINGS_BRIDGE_V2"):
                    raise ValueError("PARENT_V3_LOCKED_CONDITIONAL_PRINCIPAL_SOURCE_CHANGED")
                financing = self._stage_outputs(financing_spec, financing_state, now,
                                                verified_context=context)["base"]["policy"]
                trial_spec["base_principal_reference"] = dict(
                    classification="CONDITIONAL_NOT_VERIFIED_CASH_RECEIPT",
                    task_head=financing_head, response_binding=financing_state["responses"]["base.policy"],
                    years=financing["years"],
                    new_borrowing=financing["series"]["new_borrowing"]["values"],
                    debt_repayment=financing["series"]["debt_repayment"]["values"])
            for stage_id in STAGE_ORDER:
                if replay_from_stage is not None:
                    replay_scenario, replay_stage = replay_from_stage.split(".")
                    scenario, stage = stage_id.split(".")
                    if (scenario == replay_scenario and
                            STAGES.index(stage) >= STAGES.index(replay_stage)):
                        continue
                binding = old_state["responses"].get(stage_id)
                if binding is None:
                    candidates = [item for item in old_state.get("returned_responses", [])
                                  if item["path"].startswith(
                                      self._directory(seed_task_id).relative_to(self.root).as_posix()
                                      + "/response-")
                                  and self._bound(item).get("scenario") == stage_id]
                    if len(candidates) != 1:
                        continue
                    binding = candidates[0]
                    reservation = Path(binding["path"]).stem.removeprefix("response-")
                    charge = old_state["reservations"].get(reservation)
                    if (not charge or charge["scenario"] != stage_id
                            or charge["status"] != "SETTLED"):
                        continue
                trial["responses"][stage_id] = binding
                try:
                    # Validate the original packet against the current request/parser.
                    self._stage_outputs(trial_spec, trial, now, verified_context=context)
                except (ValueError, KeyError, TypeError, OSError):
                    del trial["responses"][stage_id]
                    continue
                seed["responses"][stage_id] = binding
            # Check the predecessor head, ledger and all selected lineage now,
            # before publishing a new task or permitting another model call.
            trial_spec.update(task_id="new-task-preview", mode=old_spec["mode"], seed=seed)
            self._stage_outputs(trial_spec, trial, now, verified_context=context)
        if capital_basis is None:
            source_spec = staged_numbered._load_spec(self.root, spec_binding)
            capital_basis = policy_capital.opening_debt_basis(source_spec["opening"], context["facts"])
        spec = dict(schema_version=VERSION, task_id=task_id, mode="TEST_ONLY_PARENT_CASH_V3"
            if self.test_provider is not None else "LIVE_PARENT_CASH_V3", spec_binding=spec_binding,
            source_fingerprint=context["input_fingerprint"], config=cfg,
            shared_budget_root=str(self.shared_budget_root),
            implementation_sha256=_implementation(), policy_capital_basis=capital_basis,
            created_at=seed_created_at, action="no_order")
        if seed is None:
            spec["operating_series_wire"] = "INPUTS_ONLY_V2"
            if any(row["source"].get("redemption_wire") == "MULTI_LAYOUT_V1"
                   for row in (context.get("annual_paid_note_interest_floor") or {}).get("evidence", ())):
                spec["scenario_interest_wire"] = "CONDITIONAL_COUPON_COVERAGE_V1"
            stress = source_spec.get("conditional_financing_stress")
            if stress is not None:
                anchors = stress.get("evidence_anchors") if isinstance(stress, dict) else None
                if (not isinstance(stress, dict) or set(stress) != {"residual_stress_rate", "evidence_anchors"}
                        or not isinstance(stress["residual_stress_rate"], str)
                        or not isinstance(anchors, list) or not 1 <= len(anchors) <= 8
                        or any(not isinstance(anchor, str) or anchor not in context["facts"] for anchor in anchors)
                        or len(set(anchors)) != len(anchors)
                        or "scenario_interest_wire" not in spec):
                    raise ValueError("PARENT_V3_FINANCING_WIRE_INVALID")
                spec["conditional_financing_stress"] = stress
                spec["financing_wire_sha256"] = _hash(Path(fixed_financing.__file__).read_bytes())
        elif "operating_series_wire" in trial_spec:
            spec["operating_series_wire"] = trial_spec["operating_series_wire"]
        if seed is not None:
            if "conditional_financing_stress" in trial_spec:
                spec["conditional_financing_stress"] = trial_spec["conditional_financing_stress"]
                spec["financing_wire_sha256"] = trial_spec["financing_wire_sha256"]
            if "bear_operating_wire" in trial_spec:
                spec["bear_operating_wire"] = trial_spec["bear_operating_wire"]
            if "scenario_interest_wire" in trial_spec:
                spec["scenario_interest_wire"] = trial_spec["scenario_interest_wire"]
            if "bear_financing_wire" in trial_spec:
                spec["bear_financing_wire"] = trial_spec["bear_financing_wire"]
            if "base_cash_transition_wire" in trial_spec:
                spec["base_cash_transition_wire"] = trial_spec["base_cash_transition_wire"]
            if "base_operating_wire" in trial_spec:
                spec["base_operating_wire"] = trial_spec["base_operating_wire"]
            if "base_policy_wire" in trial_spec:
                spec["base_policy_wire"] = trial_spec["base_policy_wire"]
            if "base_interest_wire" in trial_spec:
                spec["base_interest_wire"] = trial_spec["base_interest_wire"]
            if "base_principal_reference" in trial_spec:
                spec["base_principal_reference"] = trial_spec["base_principal_reference"]
            spec.update(forked_at=now.isoformat(), seed=seed,
                        replay_from_stage=replay_from_stage,
                        ancestor_spend=str(ancestor_spend))
        with self._lock(directory):
            if (directory / "input.json").exists():
                old, state, binding = self._load(task_id)
                if ({k:v for k,v in old.items() if k not in {"created_at", "forked_at"}}
                        != {k:v for k,v in spec.items() if k not in {"created_at", "forked_at"}}):
                    raise ValueError("PARENT_REQUEST_KEY_CONFLICT")
                return self._view(old, state, binding, now)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", responses=seed["responses"] if seed else {},
                reservations={}, provider_requests=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0",
                settled_cost="0", action="no_order", formal_eligibility=False,
                error_code=None, new_llm_calls=0)
            state, binding = self._save(spec, state, None, now)
            return self._view(spec, state, binding, now)

    def read(self, task_id):
        directory = self._directory(task_id)
        if not (directory / "input.json").exists():
            raise FileNotFoundError(task_id)
        with self._lock(directory):
            return self._view(*self._load(task_id), _now())

    def cancel(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, binding = self._load(task_id)
            if state["status"] not in {"CANCELLED", "SUCCEEDED"}:
                state, binding = self._save(spec, state, binding, now,
                    status="CANCELLED", error_code="USER_CANCELLED")
            return self._view(spec, state, binding, now)

    def revalidate_interrupted_financing(self, task_id, *, now=None):
        """Record a failed policy recheck without sending a provider request."""
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory, "execution"), self._lock(directory):
            spec, state, binding = self._load(task_id)
            if (state["status"] != "RUNNING" or "bear.policy" not in state["responses"]
                    or any(row["status"] == "RESERVED" for row in state["reservations"].values())):
                return self._view(spec, state, binding, now)
            context = self._context(spec, now)
            schedule = financing_schedule.disclosed_schedule_from_context(context)
            if schedule is None:
                return self._view(spec, state, binding, now)
            policy = self._stage_outputs(spec, state, now, verified_context=context)["bear"]["policy"]
            try:
                financing_schedule.validate_disclosed_financing_policy(schedule, policy)
            except ValueError as error:
                reason = str(error)
                if not re.fullmatch(
                    r"PARENT_FINANCING_(?:ABOVE_DISCLOSED_PROCEEDS|BELOW_CONTRACTUAL_PRINCIPAL):20[0-9]{2}",
                    reason,
                ):
                    raise
                state, binding = self._save(
                    spec, state, binding, now, status="FAILED", error_code="BEAR_POLICY_" + reason,
                )
            return self._view(spec, state, binding, now)

    def resume_if_interrupted(self, task_id, *, now=None):
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            return self.resume(task_id, now=now)

    def resume(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, binding = self._load(task_id, recover=True)
            if (state["status"] in {"SUCCEEDED", "CANCELLED"}
                    or (state.get("error_code") or "").startswith("BEAR_POLICY_PARENT_FINANCING_")):
                return self._view(spec, state, binding, now)
            self._drafts(spec, state, now)
            if any(row["scenario"] not in state["responses"] for row in state["reservations"].values()):
                state, binding = self._save(spec, state, binding, now,
                    status="FAILED", error_code="PARENT_V3_AMBIGUOUS_STAGE_NO_RESEND")
                return self._view(spec, state, binding, now)
            state, binding = self._save(spec, state, binding, now, status="QUEUED", error_code=None)
            return self._view(spec, state, binding, now)

    def run(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                if state["status"] != "QUEUED":
                    return self._view(spec, state, binding, now)
                if any(row["scenario"] not in state["responses"] for row in state["reservations"].values()):
                    raise ValueError("PARENT_AMBIGUOUS_CALL_NO_RESEND")
                self._drafts(spec, state, now)
                state, binding = self._save(spec, state, binding, now, status="RUNNING")
            for stage_id in STAGE_ORDER:
                scenario, stage = stage_id.split(".")
                with self._lock(directory):
                    spec, state, binding = self._load(task_id)
                    if state["status"] == "CANCELLED":
                        return self._view(spec, state, binding, _now())
                    if stage_id in state["responses"]:
                        if stage == "policy":
                            context = self._context(spec, _now())
                            stages = self._stage_outputs(spec, state, _now(),
                                verified_context=context)[scenario]
                            try:
                                preflight_annual_cash_upper_bound_v3(root=self.root,
                                    spec_binding=spec["spec_binding"], evaluated_at=_now(),
                                    context=context, operating=stages["operating"],
                                    policy=stages["policy"])
                            except (ValueError, OSError, KeyError, TypeError) as error:
                                detail = str(error).replace("PARENT_V2_", "PARENT_V3_", 1)
                                code = ("PARENT_V3_ECONOMIC_" + detail
                                    if isinstance(error, ValueError) and re.fullmatch(
                                        r"(?:(?:DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT|PARENT_V3_ANNUAL_CAPEX_BELOW_REALISED_CASH|PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_BELOW_REALISED_CASH|PARENT_V3_ANNUAL_INTEREST_BELOW_REALISED_CASH):20[0-9]{2}|"
                                    r"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:20[0-9]{2}:"
                                    r"(?:debt_repayment|new_borrowing))", detail)
                                    else detail if isinstance(error, ValueError) and re.fullmatch(
                                        r"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:20[0-9]{2}:(?:new_borrowing|debt_repayment)", detail)
                                    else "PARENT_V3_ANNUAL_CASH_PREFLIGHT_REJECTED")
                                state, binding = self._save(spec, state, binding, _now(),
                                    status="FAILED", error_code=f"{stage_id.upper().replace('.', '_')}_{code}")
                                return self._view(spec, state, binding, _now())
                        continue
                    if any(row["scenario"] == stage_id for row in state["reservations"].values()):
                        raise ValueError("PARENT_AMBIGUOUS_CALL_NO_RESEND")
                    context = self._context(spec, _now())
                    cfg = spec["config"]
                    prior = self._stage_outputs(spec, state, _now(), verified_context=context)[scenario]
                    if set(prior) != set(STAGES[:STAGES.index(stage)]):
                        raise ValueError("PARENT_V3_STAGE_ORDER_INVALID")
                    try:
                        request = staged_parent_cash_request_v3(root=self.root,
                            spec_binding=spec["spec_binding"], scenario=scenario, stage=stage,
                            prior_drafts=prior, generated_at=datetime.fromisoformat(spec["created_at"]),
                            verified_context=context,
                            max_completion_tokens=cfg["max_completion_tokens_cap"])
                    except ValueError as error:
                        if stage != "terminal" or str(error) != "PARENT_V3_FORECAST_DEBT_NEGATIVE":
                            raise
                        state, binding = self._save(spec, state, binding, _now(), status="FAILED",
                            error_code=f"{scenario.upper()}_TERMINAL_PARENT_V3_FORECAST_DEBT_NEGATIVE")
                        return self._view(spec, state, binding, _now())
                    wire_request = self._wire(spec, stage, request, root=self.root)
                    prompt_cap = len(_bytes(wire_request.__dict__)) + 4096
                    reserve = (Decimal(prompt_cap) * Decimal(str(cfg["input_cost_per_million"])) +
                        Decimal(request.max_completion_tokens) * Decimal(str(cfg["output_cost_per_million"]))) / Decimal(1000000)
                    if (state["provider_requests"] >= len(STAGE_ORDER) or
                            Decimal(spec.get("ancestor_spend", "0")) + Decimal(state["reserved_cost"]) +
                            Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"]))):
                        state, binding = self._save(spec, state, binding, _now(),
                            status="FAILED", error_code="PARENT_TASK_BUDGET_EXHAUSTED")
                        return self._view(spec, state, binding, _now())
                    reservation = _hash(os.urandom(32))
                    day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    self.daily._daily_budget(day, reservation, reserve, cfg)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation] = dict(scenario=stage_id, status="RESERVED",
                        cost=str(reserve), day=day)
                    state, binding = self._save(spec, state, binding, _now(),
                        reservations=reservations, reserved_cost=str(Decimal(state["reserved_cost"]) + reserve),
                        provider_requests=state["provider_requests"] + 1,
                        new_llm_calls=state["new_llm_calls"] + (self.test_provider is None))
                response_recorded = False
                provider_returned = False
                try:
                    provider = self.test_provider or OpenAICompatibleChatProvider(**{k:cfg[k]
                        for k in ("endpoint", "model_id", "api_key_env", "timeout_seconds",
                                  "max_completion_tokens_cap", "response_format_mode", "thinking_mode") if k in cfg})
                    response = provider.complete(wire_request)
                    provider_returned = True
                    if (not isinstance(response, LLMResponse) or response.tool_calls
                            or type(response.prompt_tokens) is not int or type(response.completion_tokens) is not int
                            or not 0 <= response.prompt_tokens <= prompt_cap
                            or not 0 <= response.completion_tokens <= request.max_completion_tokens
                            or response.model_id != cfg["model_id"]):
                        raise ValueError("PARENT_PROVIDER_RESPONSE_INVALID")
                    actual = (Decimal(response.prompt_tokens) * Decimal(str(cfg["input_cost_per_million"])) +
                        Decimal(response.completion_tokens) * Decimal(str(cfg["output_cost_per_million"]))) / Decimal(1000000)
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        self.daily._daily_budget(day, reservation, actual, cfg, settle=True)
                        reservations = deepcopy(state["reservations"])
                        reservations[reservation].update(status="SETTLED", actual_cost=str(actual))
                        usage = {key:state["usage"][key] + getattr(response, key)
                            for key in ("prompt_tokens", "completion_tokens")}
                        state, binding = self._save(spec, state, binding, _now(), reservations=reservations,
                            usage=usage, reserved_cost=str(Decimal(state["reserved_cost"]) - reserve),
                            settled_cost=str(Decimal(state["settled_cost"]) + actual))
                        packet = dict(scenario=stage_id, request_sha256=_hash(_bytes(wire_request.__dict__)),
                            source_fingerprint=spec["source_fingerprint"], response=response.__dict__, action="no_order")
                        path = directory / ("response-" + reservation + ".json")
                        write_new_bytes(path, _bytes(packet))
                        response_recorded = True
                        response_binding = self._binding(path)
                        state, binding = self._save(spec, state, binding, _now(),
                            returned_responses=state.get("returned_responses", []) + [response_binding])
                    parsed_stage = self._parse_stage(spec, stage, response, request=request,
                        source_fingerprint=spec["source_fingerprint"])
                    if stage == "terminal":
                        preflight_terminal_forecast_debt_v3(request=request, parsed_stage=parsed_stage)
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        if state["status"] == "CANCELLED":
                            return self._view(spec, state, binding, _now())
                        responses = deepcopy(state["responses"])
                        responses[stage_id] = response_binding
                        state, binding = self._save(spec, state, binding, _now(), responses=responses)
                    if stage == "policy":
                        preflight_annual_cash_upper_bound_v3(root=self.root,
                            spec_binding=spec["spec_binding"], evaluated_at=_now(),
                            context=context,
                            operating=prior["operating"], policy=parsed_stage)
                except Exception as error:
                    if response_recorded:
                        detail = str(error).replace("PARENT_V2_", "PARENT_V3_", 1)
                        code = ("PARENT_V3_ECONOMIC_" + detail
                                if isinstance(error, ValueError) and re.fullmatch(
                                    r"(?:(?:DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT|PARENT_V3_ANNUAL_CAPEX_BELOW_REALISED_CASH|PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_BELOW_REALISED_CASH|PARENT_V3_ANNUAL_INTEREST_BELOW_REALISED_CASH):20[0-9]{2}|"
                                    r"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:20[0-9]{2}:"
                                    r"(?:debt_repayment|new_borrowing))", detail)
                                else detail if isinstance(error, ValueError)
                                and (detail == "PARENT_DRAFT_TERM_SOURCE_INVALID"
                                     or re.fullmatch(r"PARENT_V3_[A-Z0-9_]{1,90}", detail)
                                     or re.fullmatch(
                                         r"PARENT_FINANCING_(?:ABOVE_DISCLOSED_PROCEEDS|BELOW_CONTRACTUAL_PRINCIPAL):20[0-9]{2}",
                                         detail)
                                     or re.fullmatch(r"PARENT_V3_POLICY_(?:DEBT_INTEREST_UNSUPPORTED|COUPON_COVERAGE_LOW):20[0-9]{2}", detail)
                                     or (re.fullmatch(r"PARENT_V3_POLICY_CNY_WIRE_INVALID:20[0-9]{2}:[a-z_]+", detail)
                                         and detail.rsplit(":", 1)[-1] in POLICY))
                                else "PARENT_DRAFT_REJECTED_OR_UNPUBLISHED")
                    elif not provider_returned and isinstance(error, HTTPError):
                        status = error.code
                        code = (f"PARENT_PROVIDER_HTTP_{status}_UNSETTLED"
                                if type(status) is int and 100 <= status <= 599
                                else "PARENT_PROVIDER_HTTP_ERROR_UNSETTLED")
                    elif not provider_returned and isinstance(error, URLError):
                        code = ("PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
                                if isinstance(error.reason, TimeoutError)
                                else "PARENT_PROVIDER_CONNECTION_AMBIGUOUS")
                    elif provider_returned and isinstance(error, OSError):
                        code = "PARENT_RESPONSE_SETTLEMENT_OR_PERSISTENCE_FAILED"
                    elif isinstance(error, TimeoutError):
                        code = "PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
                    elif isinstance(error, ValueError) and "completion token cap" in str(error):
                        code = "PARENT_PROVIDER_COMPLETION_CAP_REACHED"
                    elif isinstance(error, ValueError) and "truncated" in str(error):
                        code = "PARENT_PROVIDER_RESPONSE_INCOMPLETE"
                    elif provider_returned and isinstance(error, ValueError) and str(error) == "PARENT_PROVIDER_RESPONSE_INVALID":
                        code = "PARENT_PROVIDER_RESPONSE_INVALID"
                    else:
                        code = "PARENT_PROVIDER_OR_SETTLEMENT_AMBIGUOUS"
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        if state["status"] != "CANCELLED":
                            state, binding = self._save(spec, state, binding, _now(),
                                status="FAILED", error_code=f"{stage_id.upper().replace('.', '_')}_{code}")
                        return self._view(spec, state, binding, _now())
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                if state["status"] == "CANCELLED":
                    return self._view(spec, state, binding, _now())
                try:
                    drafts = self._drafts(spec, state, _now())
                    if set(drafts) != set(SCENARIOS):
                        raise ValueError("PARENT_V3_INCOMPLETE_THREE_SCENARIOS")
                    assemble_parent_cash_drafts_v2(root=self.root, spec_binding=spec["spec_binding"],
                        drafts=drafts, generated_at=_now())
                except (ValueError, KeyError, TypeError, OSError) as error:
                    detail = str(error).replace("PARENT_V2_", "PARENT_V3_", 1)
                    code = ("PARENT_V3_ECONOMIC_" + detail
                            if isinstance(error, ValueError)
                            and re.fullmatch(r"(?:DIRECT_OWNER|DIRECT_INPUT|PARENT_V3)_[A-Z0-9_]{1,90}(?::20[0-9]{2})?", detail)
                            else "PARENT_V3_ECONOMIC_CONTRACT_REJECTED")
                    state, binding = self._save(spec, state, binding, _now(),
                        status="FAILED", error_code=code)
                    return self._view(spec, state, binding, _now())
                state, binding = self._save(spec, state, binding, _now(), status="SUCCEEDED")
                return self._view(spec, state, binding, _now())
