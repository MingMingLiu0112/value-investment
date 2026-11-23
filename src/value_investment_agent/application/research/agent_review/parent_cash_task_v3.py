"""Nine bounded D1 stages: operating, cash policy and terminal per scenario."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
import sys
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .task_execution_v1 import ResearchTaskService, _bytes, _hash, _now
from .operating_task_v2 import LiveOperatingTaskService, model_configuration
def read_parent_cash_agent_facts_v2(**kwargs):
    from ..direct_owner_cash_agent_facts_v2 import read_parent_cash_agent_facts_v2 as reader
    return reader(**kwargs)

from ..direct_owner_cash_staged_v2 import (
    STAGES, parse_staged_parent_cash_response,
)
from .. import direct_owner_cash_operating_wire_v1 as operating_wire
from .. import direct_owner_cash_terminal_wire_v1 as terminal_wire
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
                           request, compiler, compiler_numbered, unnumbered, unnumbered_native, operating_wire, terminal_wire)} | {
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
    def _wire(spec, stage, request):
        if stage == "operating" and operating_wire.__name__ in spec["implementation_sha256"]:
            wire = operating_wire.operating_wire_request(request)
            if spec.get("operating_series_wire") == "INPUTS_ONLY_V1":
                return replace(wire, system=wire.system.replace(
                    "Keep operating_cash distinct from the required other_operating_cash component.",
                    "The application computes total operating cash. Do not emit operating_cash or CFO.",
                ), transport_output_contract=wire.transport_output_contract +
                    " Output only revenue, cost and other_operating_cash inside series; "
                    "never emit operating_cash, even as an explanatory series.")
            return wire
        if stage == "terminal" and terminal_wire.__name__ in spec["implementation_sha256"]:
            return terminal_wire.terminal_wire_request(request)
        return request

    def _parse_stage(self, spec, stage, response, request, source_fingerprint):
        parse = (operating_wire.parse_operating_wire
                 if stage == "operating" and operating_wire.__name__ in spec["implementation_sha256"]
                 else parse_staged_parent_cash_response)
        return parse(response, request=request, source_fingerprint=source_fingerprint)

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
                    _hash(_bytes(self._wire(spec, stage, request).__dict__)) or packet.get("source_fingerprint") !=
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
                              implementation_sha256=_implementation())
            if replay_from_stage == "bear.operating":
                trial_spec["operating_series_wire"] = "INPUTS_ONLY_V1"
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
        spec = dict(schema_version=VERSION, task_id=task_id, mode="TEST_ONLY_PARENT_CASH_V3"
            if self.test_provider is not None else "LIVE_PARENT_CASH_V3", spec_binding=spec_binding,
            source_fingerprint=context["input_fingerprint"], config=cfg,
            shared_budget_root=str(self.shared_budget_root),
            implementation_sha256=_implementation(),
            created_at=seed_created_at, action="no_order")
        if seed is not None and replay_from_stage == "bear.operating":
            spec["operating_series_wire"] = "INPUTS_ONLY_V1"
        if seed is not None:
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

    def resume(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, binding = self._load(task_id, recover=True)
            if state["status"] in {"SUCCEEDED", "CANCELLED"}:
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
                    wire_request = self._wire(spec, stage, request)
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
                try:
                    provider = self.test_provider or OpenAICompatibleChatProvider(**{k:cfg[k]
                        for k in ("endpoint", "model_id", "api_key_env", "timeout_seconds",
                                  "max_completion_tokens_cap", "response_format_mode", "thinking_mode") if k in cfg})
                    response = provider.complete(wire_request)
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
                                and (re.fullmatch(r"PARENT_V3_[A-Z0-9_]{1,90}", detail)
                                     or (re.fullmatch(r"PARENT_V3_POLICY_CNY_WIRE_INVALID:20[0-9]{2}:[a-z_]+", detail)
                                         and detail.rsplit(":", 1)[-1] in POLICY))
                                else "PARENT_DRAFT_REJECTED_OR_UNPUBLISHED")
                    elif isinstance(error, TimeoutError):
                        code = "PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
                    elif isinstance(error, ValueError) and "completion token cap" in str(error):
                        code = "PARENT_PROVIDER_COMPLETION_CAP_REACHED"
                    elif isinstance(error, ValueError) and "truncated" in str(error):
                        code = "PARENT_PROVIDER_RESPONSE_INCOMPLETE"
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
