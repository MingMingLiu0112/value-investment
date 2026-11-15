"""Explicit real operating research, existing local authorization and D1 workflow."""
from datetime import datetime,timezone
import json,os,re,subprocess
from itertools import islice
from pathlib import Path
from fastapi import FastAPI,Request,BackgroundTasks
from fastapi.responses import JSONResponse
from .local_auth import authorize,LocalAuthorizationError,AUTHORIZATION_REQUIRED
from ...application.research.agent_review.operating_task_v2 import LiveOperatingTaskService,model_status,ROLES
from ...application.research.agent_review.operating_task_v2 import LiveOperatingTaskService as _NativeLiveService
from ...operations.live_task_controller_v1 import supervise_live_task, read_pending_live_task, finalize_pending_live_task
from ...application.portfolio.private_journal_lock import LockTimeout

RESEARCH_TASK_ROOT_ENV = "VALUE_INVESTMENT_LOCAL_RESEARCH_TASK_ROOT"


def resolve_research_task_root(code_root: Path) -> Path:
    """Bind only a sibling worktree of this checkout's canonical repository.

    The selected root owns D1/D2 sources, tasks and the shared daily budget.
    It is never inferred from a task ID or supplied by an HTTP request.
    """
    code_root = Path(code_root).resolve(strict=True)
    configured = os.environ.get(RESEARCH_TASK_ROOT_ENV)
    if configured is None:
        return code_root
    candidate = Path(configured)
    if not configured or not candidate.is_absolute():
        raise ValueError("INVALID_LOCAL_RESEARCH_TASK_ROOT")
    try:
        candidate = candidate.resolve(strict=True)
        def common_dir(root: Path) -> Path:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            return Path(result.stdout.strip()).resolve(strict=True)
        common = common_dir(code_root)
        canonical = common.parent
        if (common.name != ".git" or candidate == code_root
                or candidate.parent != canonical / ".tmp"
                or common_dir(candidate) != common
                or not (candidate / ".git").is_file()):
            raise ValueError("INVALID_LOCAL_RESEARCH_TASK_ROOT")
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise ValueError("INVALID_LOCAL_RESEARCH_TASK_ROOT") from error
    return candidate


def register_live_operating_routes(api:FastAPI,*,project,sessions,port):
    code_root = Path(project).resolve()
    project = resolve_research_task_root(code_root)
    service=LiveOperatingTaskService(project)
    def enqueue(background,task_id):
        # Execution resource supervision only; frozen research inputs/providers
        # and financial implementation fingerprints remain byte-identical.
        if type(service) is _NativeLiveService and service.test_provider is None:
            background.add_task(supervise_live_task,project,task_id)
        else:
            background.add_task(service.run,task_id)

    def pending(task_id):
        if type(service) is not _NativeLiveService or service.test_provider is not None:
            return None
        value=read_pending_live_task(project,task_id)
        return value if value["status"]!="NO_PENDING_FINALIZATION" else None
    def pending_response(value):
        return reply(dict(action="no_order",status="FINALIZATION_PENDING",
            detail="工作进程已停止，状态写入尚未完成；请使用完成状态写入，不会调用模型。",
            controller_finalization=value),409)

    def reply(value,status=200):
        return JSONResponse(value,status_code=status,headers={"Cache-Control":"no-store"})
    def review_projection(value):
        # Response-only copy: never edit an immutable task or its role pins.
        projected=dict(value)
        projected.pop("independent_review_status",None)
        if "independent_review" not in value:return projected
        review=projected.pop("independent_review")
        roles=value.get("roles")
        valid=(isinstance(review,dict) and isinstance(roles,dict) and bool(roles)
            and isinstance(value.get("context_fingerprint"),str) and bool(value["context_fingerprint"])
            and review.get("source_context_fingerprint")==value["context_fingerprint"]
            and review.get("reviewed_role_responses")==roles
            and review.get("status")=="REVIEW_REQUIRED_NOT_APPROVAL"
            and isinstance(review.get("findings"),list))
        projected["independent_review_status"]=("REVIEW_REQUIRED_NOT_APPROVAL" if valid
            else "REVIEW_BINDING_INVALID")
        if valid:
            projected["independent_review"]={key:review[key] for key in
                ("source_context_fingerprint","reviewed_role_responses","status","findings")}
        return projected

    def denied(request):
        try:authorize(request,session=sessions,port=port)
        except LocalAuthorizationError as error:
            return reply(dict(action="no_order",status=error.code,detail=error.detail),
                         401 if error.code==AUTHORIZATION_REQUIRED else 403)
        return None

    # Annual supplements share source verification, authorization and the live daily budget.
    # They do not replace the existing three-role task or grant research approval.
    from ...application.research.agent_review.operating_horizon_task_v2 import OperatingHorizonTaskService
    horizon = OperatingHorizonTaskService(project)
    from ...application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService
    anchored_annual = NoticeAwareTaskService(project, kind="annual")
    # Separate task contract: v2 annual operating research never acquires a
    # shareholder-cash-policy meaning merely because this API was added.
    from ...application.research.agent_review.operating_horizon_task_v4 import OperatingHorizonTaskService as CashPolicyHorizonTaskService
    horizon_cash_policy = CashPolicyHorizonTaskService(project)
    from ...application.research.agent_review.operating_horizon_task_v5_wc import (
        OperatingHorizonTaskService as ParentWCHorizonTaskService, CONTRACT as PARENT_WC_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v6_split import (
        OperatingHorizonTaskService as SplitHorizonTaskService, CONTRACT as SPLIT_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v7_split import (
        OperatingHorizonTaskService as AnchoredSplitHorizonTaskService,
        CONTRACT as ANCHORED_SPLIT_CONTRACT)
    from ...application.research.agent_review import operating_q3_cash_source_loader_v1 as q3_cash_loader

    def parent_wc_horizon():
        return ParentWCHorizonTaskService(project, allow_live=True,
            source_loader=q3_cash_loader.load_current,
            source_loader_version=q3_cash_loader.VERSION)

    def parent_wc_test_reader():
        # Validation only. Never run or return a TEST_ONLY task as live research.
        return ParentWCHorizonTaskService(project, test_provider=object(),
            source_loader=q3_cash_loader.load_current,
            source_loader_version=q3_cash_loader.VERSION)

    def split_horizon():
        return SplitHorizonTaskService(project, allow_live=True,
            source_loader=q3_cash_loader.load_current,
            source_loader_version=q3_cash_loader.VERSION)

    def split_test_reader():
        return SplitHorizonTaskService(project, test_provider=object(),
            source_loader=q3_cash_loader.load_current,
            source_loader_version=q3_cash_loader.VERSION)

    def anchored_split_horizon():
        return AnchoredSplitHorizonTaskService(project, allow_live=True,
            source_loader=q3_cash_loader.load_current,
            source_loader_version=q3_cash_loader.VERSION)

    def anchored_split_test_reader():
        return AnchoredSplitHorizonTaskService(project, test_provider=object(),
            source_loader=q3_cash_loader.load_current,
            source_loader_version=q3_cash_loader.VERSION)

    def v5_mode(service, task_id):
        directory = service._directory(task_id)
        if not (directory / "input.json").is_file():
            raise ValueError("V5_WC_INPUT_MISSING_OR_DAMAGED")
        raw = json.loads((directory / "input.json").read_bytes())
        mode = raw.get("mode")
        if mode not in ("LIVE_OPERATING", "TEST_ONLY_LIVE_CONTRACT"):
            raise ValueError("V5_WC_MODE_INVALID")
        validator = service if mode == "LIVE_OPERATING" else parent_wc_test_reader()
        validator._load(task_id)  # includes input hash and version-chain checks
        return mode

    def list_live_parent_wc(symbol):
        service = parent_wc_horizon()
        if not service.base.exists():
            return []
        children = list(islice(service.base.iterdir(), 101))
        if len(children) > 100:
            raise ValueError("RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED: max_entries=100")
        items = []
        for path in sorted(children):
            if not path.is_dir() or not path.name.startswith("rt-"):
                continue
            if not (path / "input.json").is_file():
                raise ValueError("V5_WC_INPUT_MISSING_OR_DAMAGED:" + path.name)
            if v5_mode(service, path.name) != "LIVE_OPERATING":
                continue
            item = service.read(path.name)
            if item["symbol"] == symbol:
                items.append(item)
                if len(items) > 20:
                    raise ValueError("RESEARCH_TASK_RESULT_LIMIT_EXCEEDED: max_results=20")
        return sorted(items, key=lambda row: (row["updated_at"], row["task_id"]), reverse=True)

    def list_live_split(symbol, *, anchored=False):
        service = anchored_split_horizon() if anchored else split_horizon()
        if not service.base.exists():
            return []
        children = list(islice(service.base.iterdir(), 101))
        if len(children) > 100:
            raise ValueError("RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED: max_entries=100")
        items = []
        for path in sorted(children):
            if not path.is_dir() or not path.name.startswith("rt-"):
                continue
            raw = json.loads((path / "input.json").read_bytes())
            mode = raw.get("mode")
            if mode not in ("LIVE_OPERATING", "TEST_ONLY_LIVE_CONTRACT"):
                raise ValueError("V7_SPLIT_MODE_INVALID" if anchored else "V6_SPLIT_MODE_INVALID")
            validator = service if mode == "LIVE_OPERATING" else (
                anchored_split_test_reader() if anchored else split_test_reader())
            validator._load(path.name)
            if mode != "LIVE_OPERATING":
                continue
            item = service.read(path.name)
            if item["symbol"] == symbol:
                items.append(item)
                if len(items) > 20:
                    raise ValueError("RESEARCH_TASK_RESULT_LIMIT_EXCEEDED: max_results=20")
        return sorted(items, key=lambda row: (row["updated_at"], row["task_id"]), reverse=True)

    def cash_horizon_for(task_id):
        # Task identity alone is not a version. Never fall back to V4 when a
        # V5 artifact exists but its integrity check rejects it.
        v7 = anchored_split_horizon()
        if v7._directory(task_id).exists():
            raw = json.loads((v7._directory(task_id) / "input.json").read_bytes())
            mode = raw.get("mode")
            if mode not in ("LIVE_OPERATING", "TEST_ONLY_LIVE_CONTRACT"):
                raise ValueError("V7_SPLIT_MODE_INVALID")
            (v7 if mode == "LIVE_OPERATING" else anchored_split_test_reader())._load(task_id)
            if mode != "LIVE_OPERATING":
                raise ValueError("V7_SPLIT_TEST_ONLY_NOT_LIVE_RESEARCH")
            return v7
        v6 = split_horizon()
        if v6._directory(task_id).exists():
            raw = json.loads((v6._directory(task_id) / "input.json").read_bytes())
            mode = raw.get("mode")
            if mode not in ("LIVE_OPERATING", "TEST_ONLY_LIVE_CONTRACT"):
                raise ValueError("V6_SPLIT_MODE_INVALID")
            (v6 if mode == "LIVE_OPERATING" else split_test_reader())._load(task_id)
            if mode != "LIVE_OPERATING":
                raise ValueError("V6_SPLIT_TEST_ONLY_NOT_LIVE_RESEARCH")
            return v6
        v5 = parent_wc_horizon()
        if v5._directory(task_id).exists():
            if v5_mode(v5, task_id) != "LIVE_OPERATING":
                raise ValueError("V5_WC_TEST_ONLY_NOT_LIVE_RESEARCH")
            return v5
        return horizon_cash_policy
    compact_cash_policy = NoticeAwareTaskService(project, kind="cash")
    from ...application.research.agent_review.operating_horizon_task_v10_live import (
        OperatingHorizonTaskService as V10HorizonTaskService, CONTRACT as V10_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v11_live import (
        OperatingHorizonTaskService as V11HorizonTaskService, CONTRACT as V11_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v12_live import (
        OperatingHorizonTaskService as V12HorizonTaskService, CONTRACT as V12_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v13_live import (
        OperatingHorizonTaskService as V13HorizonTaskService, CONTRACT as V13_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v14_live import (
        OperatingHorizonTaskService as V14HorizonTaskService, CONTRACT as V14_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v15_live import (
        OperatingHorizonTaskService as V15HorizonTaskService, CONTRACT as V15_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v16_live import (
        OperatingHorizonTaskService as V16HorizonTaskService, CONTRACT as V16_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v17_cash import (
        OperatingHorizonTaskService as V17HorizonTaskService, CONTRACT as V17_CONTRACT,
        STORE as V17_STORE)
    from ...application.research.agent_review.operating_horizon_task_v18_cash import (
        OperatingHorizonTaskService as V18HorizonTaskService, CONTRACT as V18_CONTRACT,
        STORE as V18_STORE)
    from ...application.research.agent_review.operating_horizon_task_v19_generic import (
        OperatingHorizonTaskService as V19HorizonTaskService, CONTRACT as V19_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v20_staged import (
        OperatingHorizonTaskService as V20HorizonTaskService, CONTRACT as V20_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v21_flat import (
        OperatingHorizonTaskService as V21HorizonTaskService, CONTRACT as V21_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v22_native import (
        OperatingHorizonTaskService as V22HorizonTaskService, CONTRACT as V22_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v23_full_schema import (
        OperatingHorizonTaskService as V23HorizonTaskService, CONTRACT as V23_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v24_shared_budget import (
        OperatingHorizonTaskService as V24HorizonTaskService, CONTRACT as V24_CONTRACT)
    from ...application.research.agent_review.operating_horizon_task_v25_canonical import (
        OperatingHorizonTaskService as V25HorizonTaskService, CONTRACT as V25_CONTRACT)
    from ...application.research.agent_review import operating_horizon_sources_v1 as generic_horizon_sources
    from ...application.research.agent_review import operating_horizon_sources_v2_return_plan as return_plan_sources
    from ...application.research.agent_review import operating_horizon_sources_v3_parent_quarter as parent_quarter_sources
    from ...application.research.agent_review import operating_horizon_sources_v4_cash_constraints as cash_constraint_sources
    from ...application.research.agent_review import operating_horizon_sources_v5_parent_trade as trade_sources
    from ...application.research.agent_review import operating_horizon_sources_v6_industry_cost as industry_cost_sources
    from ...application.research.agent_review import operating_horizon_charter_sources_v1 as charter_sources
    from ...application.research.agent_review import operating_horizon_charter_distribution_sources as charter_distribution
    from ...application.research.agent_review import operating_horizon_sources_compact as compact_sources
    from ...application.research.agent_review import operating_horizon_sources_parent_layout as parent_layout_sources
    from ...application.research.agent_review import operating_horizon_sources_parent_layout_cost as parent_cost_sources
    from ...application.research.agent_review import operating_horizon_sources_parent_layout_income as parent_income_sources
    from ...application.research.agent_review import operating_q3_issuer_plan_loader_v8_600519 as q3_v8
    from ...application.research.agent_review import operating_q3_issuer_wc_loader_v9_600519 as wc_v9
    from ...application.research.agent_review import operating_q3_issuer_dividend_split_loader_v9_600519 as dividend_v9
    from ...application.research.agent_review.task_execution_v1 import _hash

    def sealed_v12_import_pins(task_id):
        if not isinstance(task_id, str) or re.fullmatch(r"rt-[0-9a-f]{32}", task_id) is None:
            raise ValueError("V13_IMPORT_SOURCE_TASK_ID_INVALID")
        probe = V12HorizonTaskService(project)
        raw = json.loads((probe._directory(task_id) / "input.json").read_bytes())
        if raw.get("mode") != "LIVE_OPERATING" or raw.get("task_contract") != V12_CONTRACT:
            raise ValueError("V13_IMPORT_REQUIRES_LIVE_V12")
        selected = live_2027_reader(V12_CONTRACT, raw)
        spec, state, _ = selected._load(task_id)
        packet = selected._packet(spec, state, "annual")
        if packet is None or "annual" not in state.get("stage_validated", []):
            raise ValueError("V13_IMPORT_ANNUAL_NOT_SEALED")
        intent = state["stage_intents"]["annual"]
        settlement = state["reservations"][intent["reservation"]]
        return dict(expected_source_binding=spec["source_binding"],
            expected_context_sha256=spec["context_sha256"],
            expected_annual_response_sha256=_hash(packet["response"]["text"].encode("utf-8")),
            expected_budget_day=settlement["budget_day"])

    def selected_v25_loader(symbol):
        for loader in (industry_cost_sources, trade_sources, cash_constraint_sources, parent_quarter_sources, charter_distribution, compact_sources, parent_income_sources, parent_layout_sources):
            path = project / loader.CONFIG
            if path.is_file():
                selection = json.loads(path.read_bytes())
                if not isinstance(selection, dict):
                    raise ValueError("V25_SOURCE_SELECTION_INVALID")
                if symbol in selection:
                    if loader in (compact_sources, parent_income_sources) and selection[symbol] is not True:
                        raise ValueError("V25_COMPACT_SOURCE_REQUIRES_EXPLICIT_OPT_IN")
                    return loader.VERSION
        return return_plan_sources.VERSION if return_plan_sources.configured_for(project, symbol) else None

    def live_2027_horizon(contract, *, loader_version=None, test_provider=None, compact_cash=False):
        from ...application.research.agent_review.operating_horizon_task_v25_compact_cash import CompactCashTaskService
        if contract == V25_CONTRACT:
            for loader in (industry_cost_sources, trade_sources, cash_constraint_sources, parent_quarter_sources, charter_sources, charter_distribution, compact_sources, parent_cost_sources, parent_income_sources, parent_layout_sources, return_plan_sources):
                if loader_version == loader.VERSION:
                    service_type = (CompactCashTaskService
                                    if compact_cash and loader in (industry_cost_sources, trade_sources, cash_constraint_sources, charter_sources, charter_distribution, compact_sources, parent_cost_sources, parent_income_sources, parent_layout_sources)
                                    else V25HorizonTaskService)
                    return service_type(project,
                        source_loader=loader.build_operating_horizon_source_context,
                        source_loader_version=loader.VERSION,
                        **({"test_provider": test_provider} if test_provider is not None else {}))
            if loader_version not in (None, generic_horizon_sources.VERSION):
                raise ValueError("V25_SOURCE_LOADER_VERSION_UNSUPPORTED")
            service_type = CompactCashTaskService if compact_cash else V25HorizonTaskService
            return service_type(project, **({"test_provider": test_provider}
                if test_provider is not None else {}))
        if contract == V24_CONTRACT:
            if loader_version not in (None, generic_horizon_sources.VERSION):
                raise ValueError("V24_SOURCE_LOADER_VERSION_UNSUPPORTED")
            return V24HorizonTaskService(project, **({"test_provider": test_provider}
                if test_provider is not None else {}))
        if contract == V23_CONTRACT:
            if loader_version not in (None, generic_horizon_sources.VERSION):
                raise ValueError("V23_SOURCE_LOADER_VERSION_UNSUPPORTED")
            return V23HorizonTaskService(project, **({"test_provider": test_provider}
                if test_provider is not None else {}))
        if contract == V22_CONTRACT:
            if loader_version not in (None, generic_horizon_sources.VERSION):
                raise ValueError("V22_SOURCE_LOADER_VERSION_UNSUPPORTED")
            return V22HorizonTaskService(project, **({"test_provider": test_provider}
                if test_provider is not None else {}))
        if contract == V21_CONTRACT:
            if loader_version not in (None, generic_horizon_sources.VERSION):
                raise ValueError("V21_SOURCE_LOADER_VERSION_UNSUPPORTED")
            return V21HorizonTaskService(project, **({"test_provider": test_provider}
                if test_provider is not None else {}))
        if contract == V20_CONTRACT:
            if loader_version not in (None, generic_horizon_sources.VERSION):
                raise ValueError("V20_SOURCE_LOADER_VERSION_UNSUPPORTED")
            return V20HorizonTaskService(project, **({"test_provider": test_provider}
                if test_provider is not None else {}))
        if contract == V19_CONTRACT:
            if loader_version not in (None, generic_horizon_sources.VERSION):
                raise ValueError("V19_SOURCE_LOADER_VERSION_UNSUPPORTED")
            return V19HorizonTaskService(project, **({"test_provider": test_provider}
                if test_provider is not None else {}))
        if contract == V16_CONTRACT:
            if loader_version is None or loader_version == q3_v8.VERSION:
                return V16HorizonTaskService(project, **({"test_provider": test_provider}
                    if test_provider is not None else {}))
            if loader_version == wc_v9.VERSION:
                return V16HorizonTaskService(project, source_loader=wc_v9.load_current,
                    source_loader_version=wc_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            if loader_version == dividend_v9.VERSION:
                return V16HorizonTaskService(project, source_loader=dividend_v9.load_current,
                    source_loader_version=dividend_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            raise ValueError("V16_SOURCE_LOADER_VERSION_UNSUPPORTED")
        if contract == V15_CONTRACT:
            if loader_version is None or loader_version == q3_v8.VERSION:
                return V15HorizonTaskService(project, **({"test_provider": test_provider}
                    if test_provider is not None else {}))
            if loader_version == wc_v9.VERSION:
                return V15HorizonTaskService(project, source_loader=wc_v9.load_current,
                    source_loader_version=wc_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            if loader_version == dividend_v9.VERSION:
                return V15HorizonTaskService(project, source_loader=dividend_v9.load_current,
                    source_loader_version=dividend_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            raise ValueError("V15_SOURCE_LOADER_VERSION_UNSUPPORTED")
        if contract == V14_CONTRACT:
            if loader_version is None or loader_version == q3_v8.VERSION:
                return V14HorizonTaskService(project, **({"test_provider": test_provider}
                    if test_provider is not None else {}))
            if loader_version == wc_v9.VERSION:
                return V14HorizonTaskService(project, source_loader=wc_v9.load_current,
                    source_loader_version=wc_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            raise ValueError("V14_SOURCE_LOADER_VERSION_UNSUPPORTED")
        if contract == V13_CONTRACT:
            if loader_version is None or loader_version == q3_v8.VERSION:
                return V13HorizonTaskService(project, **({"test_provider": test_provider}
                    if test_provider is not None else {}))
            if loader_version == wc_v9.VERSION:
                return V13HorizonTaskService(project, source_loader=wc_v9.load_current,
                    source_loader_version=wc_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            raise ValueError("V13_SOURCE_LOADER_VERSION_UNSUPPORTED")
        if contract == V12_CONTRACT:
            if loader_version is None or loader_version == q3_v8.VERSION:
                return V12HorizonTaskService(project, **({"test_provider": test_provider}
                    if test_provider is not None else {}))
            if loader_version == wc_v9.VERSION:
                return V12HorizonTaskService(project, source_loader=wc_v9.load_current,
                    source_loader_version=wc_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            raise ValueError("V12_SOURCE_LOADER_VERSION_UNSUPPORTED")
        if contract == V11_CONTRACT:
            if loader_version is None or loader_version == q3_v8.VERSION:
                return V11HorizonTaskService(project, **({"test_provider": test_provider}
                    if test_provider is not None else {}))
            if loader_version == wc_v9.VERSION:
                return V11HorizonTaskService(project, source_loader=wc_v9.load_current,
                    source_loader_version=wc_v9.VERSION,
                    **({"test_provider": test_provider} if test_provider is not None else {}))
            raise ValueError("V11_SOURCE_LOADER_VERSION_UNSUPPORTED")
        if loader_version not in (None, q3_v8.VERSION):
            raise ValueError("V10_SOURCE_LOADER_VERSION_UNSUPPORTED")
        return V10HorizonTaskService(project, **({"test_provider": test_provider}
            if test_provider is not None else {}))

    def live_2027_reader(contract, raw, *, test_provider=None):
        if contract in (V17_CONTRACT, V18_CONTRACT):
            source_id = raw.get("imported_annual", {}).get("source_task_id")
            if not isinstance(source_id, str) or re.fullmatch(r"rt-[0-9a-f]{32}", source_id) is None:
                raise ValueError("V17_SOURCE_TASK_ID_INVALID")
            probe = live_2027_horizon(V16_CONTRACT)
            source_raw = json.loads((probe._directory(source_id) / "input.json").read_bytes())
            source = live_2027_reader(V16_CONTRACT, source_raw, test_provider=test_provider)
            service_class = V18HorizonTaskService if contract == V18_CONTRACT else V17HorizonTaskService
            return service_class(project, source_service=source,
                **({"test_provider": test_provider} if test_provider is not None else {}))
        binding = raw.get("source_loader_binding")
        if binding is not None and not isinstance(binding, dict):
            raise ValueError("V11_SOURCE_LOADER_BINDING_INVALID")
        version = binding.get("version") if binding else None
        return live_2027_horizon(contract, loader_version=version,
                                 test_provider=test_provider,
                                 compact_cash=bool(binding and "cash_transport" in binding))

    def live_2027_for(task_id):
        # A damaged newer task must never be read through an older store.
        for contract in (V25_CONTRACT, V24_CONTRACT, V23_CONTRACT, V22_CONTRACT, V21_CONTRACT, V20_CONTRACT, V19_CONTRACT, V18_CONTRACT, V17_CONTRACT, V16_CONTRACT, V15_CONTRACT, V14_CONTRACT, V13_CONTRACT, V12_CONTRACT, V11_CONTRACT, V10_CONTRACT):
            if contract in (V17_CONTRACT, V18_CONTRACT):
                probe = live_2027_horizon(V16_CONTRACT)
                store = V18_STORE if contract == V18_CONTRACT else V17_STORE
                if not (probe.base.parent / store / task_id).exists():
                    continue
                raw = json.loads((probe.base.parent / store / task_id / "input.json").read_bytes())
                if raw.get("mode") != "LIVE_OPERATING":
                    raise ValueError("V11_TEST_ONLY_NOT_LIVE_RESEARCH")
                selected = live_2027_reader(contract, raw)
                selected._load(task_id)
                return selected
            selected = (V17HorizonTaskService(project, source_service=live_2027_horizon(V16_CONTRACT))
                if contract == V17_CONTRACT else live_2027_horizon(contract))
            if selected._directory(task_id).exists():
                raw = json.loads((selected._directory(task_id) / "input.json").read_bytes())
                if raw.get("mode") != "LIVE_OPERATING":
                    raise ValueError("V11_TEST_ONLY_NOT_LIVE_RESEARCH")
                selected = live_2027_reader(contract, raw)
                selected._load(task_id)
                return selected
        return None

    def list_live_2027(symbol, contract):
        if contract in (V17_CONTRACT, V18_CONTRACT):
            probe = live_2027_horizon(V16_CONTRACT)
            store = V18_STORE if contract == V18_CONTRACT else V17_STORE
            if not (probe.base.parent / store).exists():
                return []
            base = probe.base.parent / store
        else:
            base = None
        selected = (None if contract in (V17_CONTRACT, V18_CONTRACT)
            else live_2027_horizon(contract))
        if base is None:
            base = selected.base
        if not base.exists():
            return []
        children = list(islice(base.iterdir(), 101))
        if len(children) > 100:
            raise ValueError("RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED: max_entries=100")
        items = []
        for path in sorted(children):
            if not path.is_dir() or not path.name.startswith("rt-"):
                continue
            if not (path / "input.json").is_file():
                continue
            raw = json.loads((path / "input.json").read_bytes())
            mode = raw.get("mode")
            if mode == "TEST_ONLY_LIVE_CONTRACT":
                test_reader = live_2027_reader(contract, raw, test_provider=object())
                test_reader._load(path.name)
                continue
            if mode != "LIVE_OPERATING":
                raise ValueError("V11_TASK_MODE_INVALID")
            selected = live_2027_reader(contract, raw)
            # read() checks the immutable state and source under the task lock.
            item = selected.read(path.name)
            if symbol is None or item["symbol"] == symbol:
                items.append(item)
                if len(items) > 20:
                    raise ValueError("RESEARCH_TASK_RESULT_LIMIT_EXCEEDED: max_results=20")
        return sorted(items, key=lambda row: (row["updated_at"], row["task_id"]), reverse=True)

    @api.get("/api/v1/operating-research/horizon-cash-policy-tasks/recent")
    def recent_2027_horizon_tasks(request: Request):
        """Discover bounded source-bound task history, never a current candidate pool."""
        error = denied(request)
        if error is not None:
            return error
        try:
            items = (list_live_2027(None, V25_CONTRACT) + list_live_2027(None, V24_CONTRACT) + list_live_2027(None, V23_CONTRACT) + list_live_2027(None, V22_CONTRACT) + list_live_2027(None, V21_CONTRACT) + list_live_2027(None, V20_CONTRACT) + list_live_2027(None, V19_CONTRACT) + list_live_2027(None, V18_CONTRACT) + list_live_2027(None, V17_CONTRACT) + list_live_2027(None, V16_CONTRACT) + list_live_2027(None, V15_CONTRACT) + list_live_2027(None, V14_CONTRACT) + list_live_2027(None, V13_CONTRACT) + list_live_2027(None, V12_CONTRACT) +
                list_live_2027(None, V11_CONTRACT) + list_live_2027(None, V10_CONTRACT))
            return reply(dict(action="no_order", scope="HISTORICAL_D2_TASKS_NOT_CURRENT_CANDIDATES",
                items=sorted(items, key=lambda row: (row["updated_at"], row["task_id"]), reverse=True)))
        except LockTimeout:
            return reply(dict(action="no_order", status="LIVE_STATE_BUSY"), 503)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return reply(dict(action="no_order", status="HORIZON_TASK_DISCOVERY_UNAVAILABLE",
                reason=str(error)), 422)

    @api.get("/api/v1/operating-research/horizon-cash-policy-tasks")
    def list_horizon_cash_policy(request:Request, symbol:str, task_contract:str|None=None):
        error=denied(request)
        if error is not None:return error
        try:
            if not re.fullmatch(r"[0-9]{6}",symbol):raise ValueError("INVALID_CASH_POLICY_SYMBOL")
            if task_contract not in (None, PARENT_WC_CONTRACT, SPLIT_CONTRACT,
                                     ANCHORED_SPLIT_CONTRACT, V10_CONTRACT, V11_CONTRACT,
                                     V12_CONTRACT, V13_CONTRACT, V14_CONTRACT, V15_CONTRACT, V16_CONTRACT, V17_CONTRACT, V18_CONTRACT, V19_CONTRACT, V20_CONTRACT, V21_CONTRACT, V22_CONTRACT, V23_CONTRACT, V24_CONTRACT, V25_CONTRACT):
                raise ValueError("INVALID_CASH_POLICY_TASK_CONTRACT")
            items = (list_live_2027(symbol, task_contract)
                if task_contract in (V10_CONTRACT, V11_CONTRACT, V12_CONTRACT, V13_CONTRACT, V14_CONTRACT, V15_CONTRACT, V16_CONTRACT, V17_CONTRACT, V18_CONTRACT, V19_CONTRACT, V20_CONTRACT, V21_CONTRACT, V22_CONTRACT, V23_CONTRACT, V24_CONTRACT, V25_CONTRACT)
                else list_live_split(symbol, anchored=True) if task_contract == ANCHORED_SPLIT_CONTRACT
                else list_live_split(symbol) if task_contract == SPLIT_CONTRACT
                else list_live_parent_wc(symbol) if task_contract == PARENT_WC_CONTRACT
                else horizon_cash_policy.list_for_symbol(symbol))
            return reply(dict(action="no_order",symbol=symbol,
                items=items))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CASH_POLICY_TASKS_UNAVAILABLE",reason=str(error)),422)

    @api.get("/api/v1/operating-research/cash-policy-tasks")
    def list_compact_cash_policy(request:Request, symbol:str):
        error=denied(request)
        if error is not None:return error
        try:
            if not re.fullmatch(r"[0-9]{6}",symbol):raise ValueError("INVALID_CASH_POLICY_SYMBOL")
            items=compact_cash_policy.list_for_symbol(symbol)
            return reply(dict(action="no_order",symbol=symbol,items=items))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="CASH_POLICY_TASKS_UNAVAILABLE",reason=str(error)),422)

    @api.post("/api/v1/operating-research/cash-policy-tasks")
    async def create_compact_cash_policy(request:Request, background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            task=compact_cash_policy.create(**_cash_policy_body(await request.body()))
            if task["status"]=="QUEUED":
                background.add_task(compact_cash_policy.run,task["task_id"])
            return reply(task,202)
        except (PermissionError,ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="CASH_POLICY_TASK_REJECTED",reason=str(error)),422)

    @api.get("/api/v1/operating-research/cash-policy-tasks/{task_id}")
    def read_compact_cash_policy(task_id:str, request:Request):
        error=denied(request)
        if error is not None:return error
        try:return reply(compact_cash_policy.read(task_id))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="CASH_POLICY_TASK_UNAVAILABLE",reason=str(error)),422)

    @api.get("/api/v1/operating-research/cash-policy-tasks/{task_id}/e2-input")
    def read_compact_cash_policy_e2_input(task_id:str, request:Request,
                                          annual_task_id:str|None=None):
        error=denied(request)
        if error is not None:return error
        try:
            from ...application.research.operating_horizon_cash_policy_e2_v1 import (
                read_d2_cash_policy_e2_input, read_split_d2_e2_input)
            if annual_task_id is not None:
                return reply(read_split_d2_e2_input(root=project,
                    annual_task_id=annual_task_id, cash_task_id=task_id,
                    now=datetime.now(timezone.utc),
                    annual_service=anchored_annual,
                    cash_service=compact_cash_policy))
            return reply(read_d2_cash_policy_e2_input(root=project,task_id=task_id,
                now=datetime.now(timezone.utc),service=compact_cash_policy))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="UNASSESSABLE",reason=str(error),
                formal_eligibility=False,condition_price=None))

    @api.post("/api/v1/operating-research/cash-policy-tasks/{task_id}/{operation}")
    def control_compact_cash_policy(task_id:str, operation:str, request:Request, background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            if operation=="cancel":task=compact_cash_policy.cancel(task_id)
            elif operation=="resume":
                task=compact_cash_policy.resume(task_id)
                if task["status"]=="QUEUED":background.add_task(compact_cash_policy.run,task_id)
            else:raise ValueError("UNSUPPORTED_CASH_POLICY_OPERATION")
            return reply(task)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="CASH_POLICY_CONTROL_REJECTED",reason=str(error)),409)

    @api.get("/api/v1/operating-research/horizon-tasks")
    def list_horizon(request:Request, symbol:str):
        error=denied(request)
        if error is not None:return error
        try:
            if not re.fullmatch(r"[0-9]{6}",symbol):
                raise ValueError("INVALID_HORIZON_SYMBOL")
            return reply(dict(action="no_order",symbol=symbol,
                items=horizon.list_for_symbol(symbol) + anchored_annual.list_for_symbol(symbol)))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_TASKS_UNAVAILABLE",reason=str(error)),422)

    @api.post("/api/v1/operating-research/horizon-tasks")
    async def create_horizon(request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            raw=await request.body()
            if len(raw)>1024:raise ValueError("HORIZON_REQUEST_TOO_LARGE")
            body=json.loads(raw)
            if not isinstance(body,dict) or set(body)!={"symbol","request_key","years"}:
                raise ValueError("HORIZON_REQUEST_INVALID")
            task=horizon.create(**body)
            if task["status"]=="QUEUED":background.add_task(horizon.run,task["task_id"])
            return reply(task,202)
        except (PermissionError,ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_TASK_REJECTED",reason=str(error)),422)

    @api.get("/api/v1/operating-research/horizon-tasks/{task_id}")
    def read_horizon(task_id:str,request:Request):
        error=denied(request)
        if error is not None:return error
        try:return reply(horizon.read(task_id))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_TASK_UNAVAILABLE",reason=str(error)),422)

    @api.post("/api/v1/operating-research/horizon-tasks/{task_id}/{operation}")
    def control_horizon(task_id:str,operation:str,request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            if operation=="cancel":task=horizon.cancel(task_id)
            elif operation=="resume":
                task=horizon.resume(task_id)
                if task["status"]=="QUEUED":background.add_task(horizon.run,task_id)
            else:raise ValueError("UNSUPPORTED_HORIZON_OPERATION")
            return reply(task)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CONTROL_REJECTED",reason=str(error)),409)

    @api.post("/api/v1/operating-research/horizon-v3-tasks")
    async def create_anchored_annual(request:Request, background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            raw=await request.body()
            if len(raw)>1024:raise ValueError("HORIZON_REQUEST_TOO_LARGE")
            body=json.loads(raw)
            if not isinstance(body,dict) or set(body)!={"symbol","request_key","years"}:
                raise ValueError("HORIZON_REQUEST_INVALID")
            task=anchored_annual.create(**body)
            if task["status"]=="QUEUED":background.add_task(anchored_annual.run,task["task_id"])
            return reply(task,202)
        except (PermissionError,ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_TASK_REJECTED",reason=str(error)),422)

    @api.get("/api/v1/operating-research/horizon-v3-tasks/{task_id}")
    def read_anchored_annual(task_id:str,request:Request):
        error=denied(request)
        if error is not None:return error
        try:return reply(anchored_annual.read(task_id))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_TASK_UNAVAILABLE",reason=str(error)),422)

    @api.post("/api/v1/operating-research/horizon-v3-tasks/{task_id}/{operation}")
    def control_anchored_annual(task_id:str,operation:str,request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            if operation=="cancel":task=anchored_annual.cancel(task_id)
            elif operation=="resume":
                task=anchored_annual.resume(task_id)
                if task["status"]=="QUEUED":background.add_task(anchored_annual.run,task_id)
            else:raise ValueError("UNSUPPORTED_HORIZON_OPERATION")
            return reply(task)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CONTROL_REJECTED",reason=str(error)),409)

    def _cash_policy_body(raw, *, allow_v5=False):
        if len(raw) > 1024:
            raise ValueError("HORIZON_CASH_POLICY_REQUEST_TOO_LARGE")
        body = json.loads(raw)
        fields = set(body) if isinstance(body, dict) else set()
        if fields == {"symbol", "request_key", "years"}:
            return body
        if allow_v5 and fields == {"symbol", "request_key", "years", "task_contract"} \
                and body["task_contract"] in (PARENT_WC_CONTRACT, SPLIT_CONTRACT,
                                              ANCHORED_SPLIT_CONTRACT, V19_CONTRACT, V20_CONTRACT, V21_CONTRACT, V22_CONTRACT, V23_CONTRACT, V24_CONTRACT, V25_CONTRACT):
            return {key: body[key] for key in ("symbol", "request_key", "years")}
        if allow_v5 and fields == {"symbol", "request_key", "years", "task_contract", "source_loader_version"} \
                and body["task_contract"] in (V11_CONTRACT, V12_CONTRACT, V13_CONTRACT, V14_CONTRACT, V15_CONTRACT, V16_CONTRACT) \
                and body["source_loader_version"] in (wc_v9.VERSION, dividend_v9.VERSION):
            return {key: body[key] for key in ("symbol", "request_key", "years")}
        else:
            raise ValueError("HORIZON_CASH_POLICY_REQUEST_INVALID")

    @api.post("/api/v1/operating-research/horizon-cash-policy-tasks/repair-v16-cash")
    async def repair_v16_cash(request: Request, background: BackgroundTasks):
        """Continue only a source-verified failed V16 annual response; no annual model call."""
        error = denied(request)
        if error is not None:
            return error
        try:
            raw = await request.body()
            body = json.loads(raw) if len(raw) <= 1024 else None
            if not isinstance(body, dict) or set(body) != {"source_task_id", "request_key"}:
                raise ValueError("V17_REPAIR_REQUEST_INVALID")
            source = live_2027_for(body["source_task_id"])
            if source is None or source.__class__ is not V16HorizonTaskService:
                raise ValueError("V17_EXACT_V16_SOURCE_REQUIRED")
            selected = V17HorizonTaskService(project, source_service=source)
            task = selected.create_imported(**body)
            if task["status"] == "QUEUED":
                background.add_task(selected.run, task["task_id"])
            return reply(task, 202)
        except LockTimeout:
            return reply(dict(action="no_order", status="LIVE_STATE_BUSY"), 503)
        except (PermissionError, ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return reply(dict(action="no_order", status="V17_REPAIR_REJECTED", reason=str(error)), 422)

    @api.post("/api/v1/operating-research/horizon-cash-policy-tasks/research-v18-cash")
    async def research_v18_cash(request: Request, background: BackgroundTasks):
        """Create a distinct source-bound conditional cash study from a failed V16 annual packet."""
        error = denied(request)
        if error is not None:
            return error
        try:
            raw = await request.body()
            body = json.loads(raw) if len(raw) <= 1024 else None
            if not isinstance(body, dict) or set(body) != {"source_task_id", "request_key"}:
                raise ValueError("V18_RESEARCH_REQUEST_INVALID")
            source = live_2027_for(body["source_task_id"])
            if source is None or source.__class__ is not V16HorizonTaskService:
                raise ValueError("V18_EXACT_V16_SOURCE_REQUIRED")
            selected = V18HorizonTaskService(project, source_service=source)
            task = selected.create_imported(**body)
            if task["status"] == "QUEUED":
                background.add_task(selected.run, task["task_id"])
            return reply(task, 202)
        except LockTimeout:
            return reply(dict(action="no_order", status="LIVE_STATE_BUSY"), 503)
        except (PermissionError, ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return reply(dict(action="no_order", status="V18_RESEARCH_REJECTED", reason=str(error)), 422)

    @api.post("/api/v1/operating-research/horizon-cash-policy-tasks/import-v12")
    async def import_v12_horizon_cash_policy(request:Request, background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            raw = await request.body()
            body = json.loads(raw) if len(raw) <= 1024 else None
            if not isinstance(body, dict) or set(body) not in (
                    {"source_task_id", "request_key"}, {"source_task_id", "request_key", "task_contract"}):
                raise ValueError("V13_IMPORT_REQUEST_INVALID")
            source_task_id, request_key = body["source_task_id"], body["request_key"]
            pins = sealed_v12_import_pins(source_task_id)
            contract = body.get("task_contract", V13_CONTRACT)
            if contract not in (V13_CONTRACT, V14_CONTRACT, V15_CONTRACT, V16_CONTRACT):
                raise ValueError("HORIZON_IMPORT_CONTRACT_UNSUPPORTED")
            selected = live_2027_horizon(contract)
            task = selected.create_imported(source_task_id=source_task_id,
                request_key=request_key, **pins)
            if task["status"] == "QUEUED":
                background.add_task(selected.run, task["task_id"])
            return reply(task, 202)
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (PermissionError,ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CASH_POLICY_IMPORT_REJECTED",
                reason=str(error)),422)

    @api.post("/api/v1/operating-research/horizon-cash-policy-tasks")
    async def create_horizon_cash_policy(request:Request, background:BackgroundTasks):
        """Start the v4 D2 cash-policy appendix; task lifecycle is real, never approval."""
        error=denied(request)
        if error is not None:return error
        try:
            raw = await request.body()
            body = json.loads(raw) if len(raw) <= 1024 else None
            selected = (anchored_split_horizon() if isinstance(body, dict)
                and body.get("task_contract") == ANCHORED_SPLIT_CONTRACT else
                split_horizon() if isinstance(body, dict)
                and body.get("task_contract") == SPLIT_CONTRACT else
                parent_wc_horizon() if isinstance(body, dict)
                and body.get("task_contract") == PARENT_WC_CONTRACT else
                live_2027_horizon(V25_CONTRACT, loader_version=selected_v25_loader(body.get("symbol")), compact_cash=True) if isinstance(body, dict)
                and body.get("task_contract") == V25_CONTRACT else
                live_2027_horizon(V24_CONTRACT) if isinstance(body, dict)
                and body.get("task_contract") == V24_CONTRACT else
                live_2027_horizon(V23_CONTRACT) if isinstance(body, dict)
                and body.get("task_contract") == V23_CONTRACT else
                live_2027_horizon(V22_CONTRACT) if isinstance(body, dict)
                and body.get("task_contract") == V22_CONTRACT else
                live_2027_horizon(V21_CONTRACT) if isinstance(body, dict)
                and body.get("task_contract") == V21_CONTRACT else
                live_2027_horizon(V20_CONTRACT) if isinstance(body, dict)
                and body.get("task_contract") == V20_CONTRACT else
                live_2027_horizon(V19_CONTRACT) if isinstance(body, dict)
                and body.get("task_contract") == V19_CONTRACT else
                live_2027_horizon(body["task_contract"], loader_version=body["source_loader_version"])
                if isinstance(body, dict) and body.get("task_contract") in (V11_CONTRACT, V12_CONTRACT, V13_CONTRACT, V14_CONTRACT, V15_CONTRACT, V16_CONTRACT)
                and body.get("source_loader_version") in (wc_v9.VERSION, dividend_v9.VERSION) else horizon_cash_policy)
            inputs = _cash_policy_body(raw, allow_v5=True)
            if (body.get("task_contract") == V25_CONTRACT
                    and selected.source_loader_version in (compact_sources.VERSION, parent_cost_sources.VERSION, parent_income_sources.VERSION, parent_layout_sources.VERSION)):
                from ...application.research.operating_horizon_cash_policy_e2_v17 import (
                    cash_constraint_anchor_ids,
                )

                now = datetime.now(timezone.utc)
                context = selected.source_loader(root=selected.root, symbol=inputs["symbol"], now=now)
                missing = sorted(term for term, ids in cash_constraint_anchor_ids(context).items()
                                 if not ids)
                if missing:
                    return reply(dict(action="no_order", status="HORIZON_CASH_POLICY_TASK_REJECTED",
                        reason="V25_E2_CASH_ANCHORS_MISSING:" + ",".join(missing),
                        missing_e2_anchors=missing, formal_eligibility=False), 422)
                inputs["now"] = now
            task = selected.create(**inputs)
            if task["status"] == "QUEUED":
                background.add_task(selected.run, task["task_id"])
            return reply(task, 202)
        except (PermissionError,ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CASH_POLICY_TASK_REJECTED",reason=str(error)),422)

    @api.get("/api/v1/operating-research/horizon-cash-policy-tasks/{task_id}")
    def read_horizon_cash_policy(task_id:str, request:Request):
        error=denied(request)
        if error is not None:return error
        try:
            selected = live_2027_for(task_id) or cash_horizon_for(task_id)
            task = selected.read(task_id)
            if task.get("workflow") == V25_CONTRACT:
                from ...application.research.agent_review.operating_cash_evidence_coverage import (
                    describe_cash_evidence,
                )
                context = selected.source_loader(root=selected.root, symbol=task["symbol"],
                    binding=task["source_binding"], now=datetime.fromisoformat(task["research_as_of"]))
                task = {**task, "cash_evidence_coverage": describe_cash_evidence(context)}
                research = task.get("research_result") or {}
                cash = research.get("cash_result") or research.get("cash_policy_result") or {}
                years = cash.get("years") or {}
                if task.get("cash_status") == "SETTLED_VALIDATED" and years:
                    missing = [
                        dict(year=year, scenario=scenario, term=term)
                        for year, row in years.items()
                        for scenario, path in row["shareholder_cash_paths"].items()
                        for term, value in path["terms"].items()
                        if value["classification"] == "UNKNOWN"
                    ]
                    accepted = task["status"] == "SUCCEEDED" and not missing
                    task["cash_policy_completeness"] = dict(
                        status=("INCOMPLETE_UNKNOWN_TERMS" if missing else
                                "COMPLETE_UNAPPROVED_RESEARCH" if accepted else "NO_VALIDATED_RESULT"),
                        missing_terms=missing, source_scope="SEALED_RESPONSE_READ_ONLY",
                        task_accepted=accepted, formal_eligibility=False, action="no_order")
                elif (task["status"] == "FAILED" and
                      (selected._directory(task_id) / "cash-term-guided-v1" / "result.json").is_file()):
                    from ...application.research.agent_review.cash_json_transcription import replay_guided_cash_diagnostic
                    try:
                        diagnostic = replay_guided_cash_diagnostic(selected, task_id)
                    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
                        task["guided_cash_diagnostic_status"] = "SEALED_CONTINUATION_REVALIDATION_FAILED"
                    else:
                        task["guided_cash_diagnostic_status"] = diagnostic["economic_status"]
                        if diagnostic["economic_status"] == "INCOMPLETE_UNKNOWN_TERMS":
                            task["cash_policy_completeness"] = dict(
                                status="INCOMPLETE_UNKNOWN_TERMS",
                                missing_terms=[dict(year="2027", scenario=scenario, term=term)
                                    for scenario, terms in diagnostic["unknown_terms"].items()
                                    for term in terms],
                                missing_e2_anchors=diagnostic["missing_e2_anchors"],
                                source_scope="SEALED_CONTINUATION_DIAGNOSTIC_ONLY",
                                task_accepted=False, formal_eligibility=False, action="no_order")
                elif task.get("error_code") == "V25_CASH_RESPONSE_REJECTED":
                    from ...application.research.agent_review.cash_json_transcription import replay_compact_cash_diagnostic

                    try:
                        diagnostic = replay_compact_cash_diagnostic(selected, task_id)
                    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
                        pass  # The original failed response remains authoritative.
                    else:
                        task["cash_policy_completeness"] = dict(
                            status=diagnostic["economic_status"],
                            missing_terms=[dict(year="2027", scenario=scenario, term=term)
                                           for scenario, terms in diagnostic["unknown_terms"].items()
                                           for term in terms],
                            missing_e2_anchors=diagnostic["missing_e2_anchors"],
                            source_scope="SEALED_PRIMARY_DIAGNOSTIC_ONLY",
                            task_accepted=False, formal_eligibility=False, action="no_order")
            return reply(task)
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CASH_POLICY_TASK_UNAVAILABLE",reason=str(error)),422)

    @api.get("/api/v1/operating-research/horizon-cash-policy-tasks/{task_id}/e2-input")
    def read_horizon_cash_policy_e2_input(task_id:str, request:Request):
        """Project an immutable D2 policy task into E2 readiness; it never runs a model."""
        error=denied(request)
        if error is not None:return error
        try:
            selected = live_2027_for(task_id)
            if selected is not None:
                if isinstance(selected, V25HorizonTaskService):
                    from ...application.research.operating_horizon_cash_policy_e2_v17 import (
                        read_v25_cash_policy_e2_input, replay_v25_annual_e2_candidates,
                    )
                    now = datetime.now(timezone.utc)
                    try:
                        return reply(read_v25_cash_policy_e2_input(
                            root=project, task_id=task_id, now=now, service=selected))
                    except ValueError as error:
                        if str(error) != "V10_E2_SUCCEEDED_TWO_STAGE_TASK_REQUIRED":
                            raise
                        try:
                            annual = replay_v25_annual_e2_candidates(
                                service=selected, task_id=task_id, now=now)
                        except (ValueError, OSError, KeyError, TypeError, RuntimeError):
                            raise error
                        return reply(dict(action="no_order", status="UNASSESSABLE", reason=str(error),
                            annual_operating_status=annual["status"], sealed_annual_candidates=annual,
                            formal_eligibility=False, condition_price=None))
                if selected.__class__ is V24HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v16 import read_v24_cash_policy_e2_input
                    return reply(read_v24_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V23HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v15 import read_v23_cash_policy_e2_input
                    return reply(read_v23_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V22HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v14 import read_v22_cash_policy_e2_input
                    return reply(read_v22_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V21HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v13 import read_v21_cash_policy_e2_input
                    return reply(read_v21_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V20HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v12 import read_v20_cash_policy_e2_input
                    return reply(read_v20_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V19HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v11 import read_v19_cash_policy_e2_input
                    return reply(read_v19_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V18HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v10 import read_v18_cash_policy_e2_input
                    return reply(read_v18_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V17HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v9 import read_v17_cash_policy_e2_input
                    return reply(read_v17_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V16HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v8 import read_v16_cash_policy_e2_input
                    return reply(read_v16_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V15HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v7 import read_v15_cash_policy_e2_input
                    return reply(read_v15_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V14HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v6 import read_v14_cash_policy_e2_input
                    return reply(read_v14_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V13HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v5 import read_v13_cash_policy_e2_input
                    return reply(read_v13_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V12HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v4 import read_v12_cash_policy_e2_input
                    return reply(read_v12_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                if selected.__class__ is V11HorizonTaskService:
                    from ...application.research.operating_horizon_cash_policy_e2_v3 import read_v11_cash_policy_e2_input
                    return reply(read_v11_cash_policy_e2_input(root=project, task_id=task_id,
                        now=datetime.now(timezone.utc), service=selected))
                from ...application.research.operating_horizon_cash_policy_e2_v2 import read_v10_cash_policy_e2_input
                return reply(read_v10_cash_policy_e2_input(root=project, task_id=task_id,
                    now=datetime.now(timezone.utc), service=selected))
            from ...application.research.operating_horizon_cash_policy_e2_v1 import read_d2_cash_policy_e2_input
            return reply(read_d2_cash_policy_e2_input(
                root=project, task_id=task_id, now=datetime.now(timezone.utc),
                service=cash_horizon_for(task_id)))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            # E2 readiness is an assessed research state, not an HTTP failure.
            # The UI must be able to show the exact missing-policy reason without
            # treating it as a reason to launch another model task.
            return reply(dict(action="no_order",status="UNASSESSABLE",
                reason=str(error),formal_eligibility=False,condition_price=None))

    @api.post("/api/v1/operating-research/horizon-cash-policy-tasks/{task_id}/{operation}")
    def control_horizon_cash_policy(task_id:str, operation:str, request:Request, background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            selected = live_2027_for(task_id) or cash_horizon_for(task_id)
            if operation == "cancel":
                task = selected.cancel(task_id)
            elif operation == "resume":
                task = selected.resume(task_id)
                if task["status"] == "QUEUED":
                    background.add_task(selected.run, task_id)
            else:
                raise ValueError("UNSUPPORTED_HORIZON_CASH_POLICY_OPERATION")
            return reply(task)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CASH_POLICY_CONTROL_REJECTED",reason=str(error)),409)

    @api.get("/api/v1/operating-research/model-status")
    def availability():
        return reply({**model_status(project), "code_root": str(code_root),
            "research_task_root": str(project),
            "research_task_root_binding": "CONFIGURED_SIBLING_WORKTREE" if project != code_root else "CODE_ROOT"})

    @api.get("/api/v1/operating-research/tasks")
    def history(request:Request,symbol:str):
        error=denied(request)
        if error is not None:return error
        try:return reply(dict(action="no_order",symbol=symbol,items=[review_projection(row) for row in service.list_for_symbol(symbol)]))
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_HISTORY_UNAVAILABLE"),422)

    @api.post("/api/v1/operating-research/tasks")
    async def create(request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            raw=await request.body()
            if len(raw)>1024:raise ValueError("LIVE_REQUEST_TOO_LARGE")
            body=json.loads(raw)
            if (not isinstance(body,dict) or set(body)!={"symbol","request_key"}
                    or not isinstance(body["symbol"],str) or re.fullmatch("[0-9]{6}",body["symbol"]) is None):
                raise ValueError("LIVE_REQUEST_INVALID")
            task=service.create(symbol=body["symbol"],request_key=body["request_key"])
            if task["status"]=="QUEUED":enqueue(background,task["task_id"])
            return reply(review_projection(task),202)
        except PermissionError as error:
            return reply(dict(action="no_order",status=str(error)),409)
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_TASK_REJECTED_SOURCE_CONFIG_OR_BUDGET"),422)

    @api.get("/api/v1/operating-research/tasks/{task_id}")
    def read(task_id:str,request:Request):
        error=denied(request)
        if error is not None:return error
        try:
            waiting=pending(task_id)
            if waiting is not None:
                spec,state,pin=service._load(task_id,recover=False)
                value=service._view(spec,state,pin,datetime.now(timezone.utc))
                value["controller_finalization"]=waiting
                return reply(review_projection(value))
            return reply(review_projection(service.read(task_id)))
        except LockTimeout:
            return JSONResponse(dict(action="no_order",status="LIVE_STATE_BUSY",
                detail="任务正在封存状态，请稍后继续读取；这不表示任务不存在或失败。"),
                status_code=503,headers={"Cache-Control":"no-store","Retry-After":"3"})
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_TASK_UNAVAILABLE"),404)

    @api.post("/api/v1/operating-research/tasks/{task_id}/{operation}")
    def control(task_id:str,operation:str,request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            if operation=="cancel":task=service.cancel(task_id)
            elif operation=="finalize":
                if type(service) is not _NativeLiveService or service.test_provider is not None:
                    raise ValueError("NATIVE_FINALIZATION_REQUIRED")
                finalize_pending_live_task(project,task_id)
                waiting=pending(task_id)
                if waiting is not None:return pending_response(waiting)
                task=service.read(task_id)
            elif operation=="resume":
                if pending(task_id) is not None:
                    finalize_pending_live_task(project,task_id)
                    waiting=pending(task_id)
                    if waiting is not None:return pending_response(waiting)
                # The controller owns the worker until termination/finalization.
                # Recover a stranded RUNNING task only after that owner is gone;
                # the native execution lock then protects against a surviving worker.
                if type(service) is _NativeLiveService and service.test_provider is None:
                    with service._lock(service._directory(task_id), "controller"):
                        task=service.resume(task_id)
                else:
                    task=service.resume(task_id)
                if task["status"]=="QUEUED":enqueue(background,task_id)
            else:raise ValueError("UNSUPPORTED_OPERATION")
            return reply(review_projection(task))
        except LockTimeout:
            return reply(dict(action="no_order",status="LIVE_EXECUTION_STILL_ACTIVE",
                detail="任务仍由执行进程持有，请读取状态；不会启动重复模型调用。"),409)
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_CONTROL_REJECTED"),409)

    @api.get("/api/v1/operating-research/companies/{symbol}")
    def public_result(symbol:str):
        if re.fullmatch("[0-9]{6}",symbol) is None:
            return reply(dict(action="no_order",status="INVALID_SYMBOL"),422)
        # Registered public filing observations remain readable even when no
        # paid Agent task exists or its latest result is no longer verifiable.
        try:
            from ...application.research.current_capital_observation_v1 import read_current_capital_observation
            capital_observation=read_current_capital_observation(
                project,symbol,datetime.now(timezone.utc))
        except (ValueError,OSError,KeyError,TypeError):
            capital_observation=dict(status="UNASSESSABLE",
                reason="CURRENT_CAPITAL_SOURCE_NOT_VERIFIED",action="no_order",formal_eligibility=False)
        # Preserve the established capital result for workspaces without an H1
        # registration. Registered historical shares are an additive observation.
        if (project / 'config/current-capital-h1-ocr-v2.json').is_file():
            try:
                from ...application.research.current_capital_h1_ocr_overlay_v2 import read_capital_with_h1_shares
                overlay = read_capital_with_h1_shares(
                    project, symbol, datetime.now(timezone.utc),
                    base_observation=capital_observation)
                if overlay['h1_share_observation']['status'] != 'NOT_REGISTERED':
                    capital_observation = overlay
            except (ValueError, OSError, KeyError, TypeError):
                capital_observation['h1_share_observation'] = dict(
                    status='UNASSESSABLE', error_code='H1_SOURCE_BINDING_NOT_VERIFIED',
                    report_period_end=None, ordinary_shares=None,
                    current_continuity='UNPROVEN', formal_eligibility=False,
                    action='no_order')
        # A fixed-source Q3 observation is independent of the paid research task.
        # It does not change model validity, valuation or current price gates.
        try:
            from ...application.research.quarter_financial_read_model_v1 import read_quarter_financial_ocr
            quarter = read_quarter_financial_ocr(project, symbol, datetime.now(timezone.utc))
            if quarter['status'] not in {'NOT_STARTED', 'NOT_SUPPORTED'}:
                capital_observation['quarter_financial_observation'] = quarter
        except (ValueError, OSError, KeyError, TypeError):
            capital_observation['quarter_financial_observation'] = dict(
                status='UNASSESSABLE', reason='QUARTER_SOURCE_BINDING_NOT_VERIFIED',
                action='no_order', formal_eligibility=False, valuation_admitted=False)
        from ...application.research import current_capital_q3_h1_bridge_v1 as q3_h1_bridge
        if (symbol == q3_h1_bridge.SUPPORTED_SYMBOL and
                (project / q3_h1_bridge.REGISTRY).is_file()):
            try:
                capital_observation['q3_h1_capital_bridge'] = q3_h1_bridge.read_q3_h1_capital_bridge(
                    project, datetime.now(timezone.utc))
            except (ValueError, OSError, KeyError, TypeError):
                capital_observation['q3_h1_capital_bridge'] = dict(
                    status='UNASSESSABLE', reason='Q3_H1_CAPITAL_BRIDGE_UNAVAILABLE',
                    current_continuity='UNPROVEN', formal_eligibility=False, action='no_order')
        try:
            tasks=service.list_for_symbol(symbol)
            if not tasks:return reply(dict(action="no_order",symbol=symbol,status="NOT_STARTED",
                reason="NO_VERIFIED_LIVE_RESEARCH_RESULT",formal_eligibility=False,
                current_capital_observation=capital_observation))
            value=tasks[0]
            draft=value.get("research_draft")
            verified_partial=(isinstance(draft,dict) and bool(draft) and set(draft)<=set(ROLES)
                and value.get("error_code") not in {"SOURCE_OR_IMPLEMENTATION_CHANGED","LIVE_CHECKPOINT_INVALID"})
            if (value["scope"]!="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED"
                    or (value["status"]!="SUCCEEDED" and not verified_partial)):
                return reply(dict(action="no_order",symbol=symbol,status="UNASSESSABLE",
                    reason=value.get("error_code") or "LATEST_TASK_NOT_VERIFIED_LIVE_RESEARCH",
                    task_id=value["task_id"],latest_task_status=value["status"],formal_eligibility=False,
                    current_capital_observation=capital_observation))

            keys=("symbol","status","task_id","scope","model_id","new_llm_calls","research_draft",
                  "context_fingerprint","source_binding","research_as_of","formal_fact_count",
                  "approval_changed","main_range_adopted","condition_price","personal_quantity","research_completeness")
            public={k:value[k] for k in keys}
            if "operating_driver_bridge" in value:
                public["operating_driver_bridge"]=value["operating_driver_bridge"]
            if value["status"]!="SUCCEEDED":
                public.update(status="PARTIAL",execution_status=value["status"],
                    reason=value.get("error_code") or "LATEST_TASK_INCOMPLETE_VERIFIED_PARTIAL_RESEARCH",
                    error_code=value.get("error_code"),
                    completed_roles=[role for role in ROLES if role in draft],
                    pending_roles=[role for role in ROLES if role not in draft])
            # A new read-model consumer, outside the immutable paid research task.
            # Failure here does not erase valid public operating research.
            try:
                from ...application.research.operating_cash_consumption_v7 import read_operating_cash_consumption
                public["cash_consumption"]=read_operating_cash_consumption(
                    root=project,task=value,now=datetime.now(timezone.utc))
            except (ValueError,OSError,KeyError,TypeError):
                public["cash_consumption"]=dict(status="UNASSESSABLE",
                    reason="CASH_SOURCE_OR_MAPPING_NOT_VERIFIED",action="no_order",formal_eligibility=False)
            public["current_capital_observation"] = capital_observation
            try:
                from ...application.research.operating_distribution_review_v1 import read_operating_distribution_review
                public["fiscal_distribution_review"] = read_operating_distribution_review(
                    root=project,task=value,now=datetime.now(timezone.utc))
            except (ValueError,OSError,KeyError,TypeError):
                public["fiscal_distribution_review"] = dict(status="UNASSESSABLE",
                    reason="FISCAL_POLICY_SOURCE_OR_PERIOD_NOT_VERIFIED",action="no_order",formal_eligibility=False)
            try:
                from ...application.research.parent_funding_review_v1 import read_registered_parent_funding_review
                public["parent_funding_review"] = read_registered_parent_funding_review(
                    root=project,symbol=symbol,now=datetime.now(timezone.utc))
                from ...application.research.parent_funding_review_v1 import compare_parent_cash_opening
                public["parent_funding_review"]["cash_input_comparison"] = compare_parent_cash_opening(
                    public["parent_funding_review"],public.get("cash_consumption",{}))
            except (ValueError,OSError,KeyError,TypeError):
                public["parent_funding_review"] = dict(status="UNASSESSABLE",
                    reason="PARENT_FUNDING_SOURCE_NOT_VERIFIED",action="no_order",formal_eligibility=False)
            # This is an E2 input-preparation projection only.  It intentionally
            # exposes retained parent-cash observations before any policy,
            # valuation or price consumer is allowed to use them.
            try:
                from ...application.research.operating_cash_followup_v1 import read_registered_operating_cash_followup
                public["parent_cash_followup"] = read_registered_operating_cash_followup(
                    root=project, task=value, now=datetime.now(timezone.utc))
            except (ValueError, OSError, KeyError, TypeError):
                public["parent_cash_followup"] = dict(status="UNASSESSABLE",
                    reason="PARENT_CASH_FOLLOWUP_SOURCE_NOT_VERIFIED", action="no_order",
                    formal_eligibility=False)
            # Versioned public revalidation never changes the paid task or approval.
            try:
                from ...application.research.main_valuation_revalidation_v1 import read_main_valuation_revalidation
                public["main_valuation_revalidation"] = read_main_valuation_revalidation(
                    root=project,symbol=symbol,now=datetime.now(timezone.utc))
            except (ValueError,OSError,KeyError,TypeError) as error:
                public["main_valuation_revalidation"] = dict(status="UNASSESSABLE",
                    reason=str(error),action="no_order",formal_eligibility=False,
                    current_comparable=False,personal_quantity=None)
            reviewed=review_projection(value)
            for key in ("independent_review","independent_review_status"):
                if key in reviewed:public[key]=reviewed[key]
            return reply(dict(action="no_order",formal_eligibility=False,**public))
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",symbol=symbol,status="UNASSESSABLE",
                reason="LIVE_SOURCE_OR_CHECKPOINT_NOT_VERIFIED",formal_eligibility=False,
                current_capital_observation=capital_observation))
