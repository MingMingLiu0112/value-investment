"""Hash-bound archived replay facts for a Root-owned read-only Web route."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json

from .event_replay import _bound_bytes


FOLDER = "artifacts/current/tl11-p5-20261014"
REVIEW_POINTER = "config/hotspot-replay-review-v1.json"


def load_current_hotspot_validation(*, root: Path, now: datetime) -> dict:
    """Recompute the configured retained sample once per consumer request.

    This is evidence about a historical sample, not the signed strategy release.
    An unavailable archive must not hide independently verified current prices.
    """
    from .validation_evidence import build_hotspot_quantitative_validation

    if now.utcoffset() is None:
        raise ValueError("Validation read model requires a timezone-aware clock")
    result = dict(schema_version="hotspot-current-validation-context-v1",
        status="NOT_RUN", source_integrity="NOT_VERIFIED",
        reference_scope="RETAINED_SAMPLE_NOT_CURRENT_STRATEGY_ADMISSION",
        strategy_validation="NOT_PROVEN", signal_event_count=None,
        mature_five_session_count=None, right_censored_count=None, trade_count=None,
        execution_metrics=dict(status="UNASSESSABLE", trade_count=None,
            cost_sensitivity=None, t_plus_one_feasibility="UNKNOWN"),
        case_bindings=[], rule_versions=[], source_bindings=[],
        blockers=["RETAINED_VALIDATION_NOT_CONFIGURED"], strict_pit_admitted=False,
        strict_oos_admitted=False, prospective_oos_admitted=False,
        elapsed_real_shadow_sessions=0, formal_eligibility=False,
        performance_claim_allowed=False, action="no_order")
    root = Path(root).resolve()
    pointer = root / REVIEW_POINTER
    try:
        if not pointer.is_file():
            return result
        raw = pointer.read_bytes()
        pins = json.loads(raw)
        if not isinstance(pins, dict) or pins.get("action") != "no_order":
            raise ValueError("Invalid hotspot validation pointer")
        binding = pins.get("retained_manifest_binding")
        if binding is None:
            return result
        report = build_hotspot_quantitative_validation(root=root,
            protocol_binding=binding, now=now)
        if (report.get("schema_version") != "hotspot-retained-descriptive-validation-v1"
                or report.get("namespace") != "ACTUAL" or report.get("scope") != "DESCRIPTIVE"
                or report.get("action") != "no_order" or report.get("formal_eligibility") is not False
                or report.get("trade_count") is not None):
            raise ValueError("Current validation requires ACTUAL retained descriptive evidence")
        if pointer.read_bytes() != raw:
            raise ValueError("Hotspot validation pointer changed during replay")
        keys = ("namespace", "metrics_scope", "protocol_binding", "historical_protocol_binding",
            "evidence_sha256", "evaluated_at", "data_available_at", "partitions",
            "signal_event_count", "mature_five_session_count", "right_censored_count",
            "execution_metrics", "source_bindings", "historical_selection_status", "limitations")
        summary = {key: deepcopy(report[key]) for key in keys}
        result.update(**summary, status=report["status"], source_integrity="VERIFIED",
            pointer_binding=dict(path=REVIEW_POINTER, sha256=sha256(raw).hexdigest()),
            case_bindings=[deepcopy(row["case_binding"]) for row in report["results"]],
            rule_versions=sorted({row["rule_version"] for row in report["results"]}),
            sample_status="NO_EXECUTION_SAMPLE",
            blockers=["CONTEMPORANEOUS_SELECTION_AND_SOURCE_PIT_NOT_PROVEN",
                "DATED_COST_AND_EXECUTION_EVIDENCE_MISSING",
                "UNTOUCHED_STRATEGY_OOS_NOT_PROVEN", "REAL_SHADOW_SESSIONS_NOT_PROVEN"])
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
        result.update(status="UNAVAILABLE", source_integrity="NOT_VERIFIED",
            blockers=["RETAINED_VALIDATION_EVIDENCE_INVALID"], diagnostic=str(error))
    return result


def load_replay_summary(*, root: Path, manifest_sha256: str,
                        structure_manifest_sha256: str | None = None) -> dict:
    """Require externally pinned manifests; never reinterpret replay as current."""
    root = root.resolve()
    manifest = json.loads(_bound_bytes(root, {"path": FOLDER + "/replay-manifest-v1.json", "sha256": manifest_sha256}))
    if manifest.get("schema_version") != "hotspot-event-replay-manifest-v1" or manifest.get("action") != "no_order":
        raise ValueError("Replay manifest contract mismatch")
    expected = FOLDER + "/replay-results-v1.json"
    binding = next((row for row in manifest["outputs"] if row["path"] == expected), None)
    if binding is None:
        raise ValueError("Bound replay report missing")
    report = json.loads(_bound_bytes(root, binding))
    if report.get("schema_version") != "hotspot-five-case-replay-report-v1" or report.get("action") != "no_order":
        raise ValueError("Replay report contract mismatch")
    structure = None
    if structure_manifest_sha256 is not None:
        structure_manifest = json.loads(_bound_bytes(root, {
            "path": FOLDER + "/replay-structure-manifest-v1.json", "sha256": structure_manifest_sha256}))
        if (structure_manifest.get("schema_version") != "hotspot-structure-prefix-manifest-v1"
                or structure_manifest.get("action") != "no_order"
                or structure_manifest["output_binding"]["path"] != FOLDER + "/replay-structure-results-v1.json"):
            raise ValueError("Structure manifest contract mismatch")
        structure = json.loads(_bound_bytes(root, structure_manifest["output_binding"]))
        if (structure.get("schema_version") != "hotspot-descriptive-structure-prefix-report-v1"
                or structure.get("action") != "no_order"
                or structure.get("parent_spec_binding") != report["spec_binding"]
                or {row["symbol"] for row in structure["results"]} != {row["symbol"] for row in report["results"]}):
            raise ValueError("Structure report belongs to different frozen replay")
    structural = {row["symbol"]: row for row in structure["results"]} if structure else {}
    return {
        "schema_version": "hotspot-replay-web-summary-v1",
        "status": "HISTORICAL_DESCRIPTIVE_REPLAY_NOT_ADMITTED",
        "reference_scope": "FROZEN_REPLAY_NOT_CURRENT_JUDGMENT",
        "computed_at": report["computed_at"], "data_available_at": report["data_available_at"],
        "partitions": report["partitions"],
        "manifest_sha256": manifest_sha256, "structure_manifest_sha256": structure_manifest_sha256,
        "items": [{
            "symbol": row["symbol"], "case_sha256": row["case_binding"]["case_sha256"],
            "v1_rule_version": row["rule_version"], "v1_segments": row["segments"],
            "archived_v1_observation": row["last_observation"],
            "structure_rule_version": structural[row["symbol"]]["rule_version"] if row["symbol"] in structural else None,
            "structure_segments": structural[row["symbol"]]["segments"] if row["symbol"] in structural else None,
            "archived_structure_observation": structural[row["symbol"]]["last_observation"] if row["symbol"] in structural else None,
        } for row in report["results"]],
        "limitations": report["limitations"],
        "strict_pit_admitted": False, "strict_oos_admitted": False,
        "prospective_oos_admitted": False, "performance_claim_allowed": False,
        "formal_eligibility": False, "portfolio_eligibility": None,
        "elapsed_real_shadow_sessions": 0, "action": "no_order",
    }


def _symbol_replay_failure(error: Exception) -> tuple[str, str]:
    """Classify known verifier failures; never publish exception text or paths."""
    message = str(error)
    if isinstance(error, FileNotFoundError):
        return "MISSING_SOURCE", "绑定的留存来源缺失"
    if isinstance(error, OSError):
        return "SOURCE_READ_FAILED", "绑定的留存来源无法读取"
    if message.startswith("Replay source hash mismatch:"):
        return "HASH_MISMATCH", "留存来源哈希与绑定不一致"
    if message == "Running rule differs from historical protocol":
        return "RULE_MISMATCH", "当前规则与冻结协议不一致"
    if message == "Replay pointer changed":
        return "BINDING_CHANGED", "读取期间样本绑定发生变化"
    if message in {
        "Retained replay requires a timezone-aware clock",
        "Historical protocol is not yet available", "Retained evidence is not yet available",
        "Retained source not yet available", "Invalid export clock",
        "Acquisition follows retention", "Dependency availability requires timezone",
    }:
        return "CLOCK_INVALID", "证据时间缺少时区、尚不可得或先后顺序不成立"
    if message == "TEST_ONLY evidence cannot enter ACTUAL retained replay":
        return "NON_ACTUAL_EVIDENCE", "测试或模拟证据不能作为真实样本"
    return "PROTOCOL_INVALID", "留存协议、输入结构或证据契约未通过核验"


def load_symbol_retained_replay(*, root: Path, symbol: str, now: datetime) -> dict:
    """Read only this symbol's bound originals; never replay the five-case batch.

    No cache: each request rechecks bytes and running frozen rules. A corrupt
    other symbol is irrelevant; manifest/protocol integrity is always required.
    """
    from . import retained_source_replay as retained
    from ...domain.hotspot.event_replay import replay_v1

    result = dict(schema_version="hotspot-symbol-retained-replay-v1", symbol=symbol,
        status="UNAVAILABLE", action="no_order", formal_eligibility=False,
        strategy_validation="NOT_PROVEN", trade_count=None, events=[],
        strict_pit_admitted=False, strict_oos_admitted=False,
        performance_claim_allowed=False, portfolio_eligibility=None,
        elapsed_real_shadow_sessions=0,
        reference_scope="HISTORICAL_SAMPLE_NOT_CURRENT_JUDGMENT",
        limitations=[
            "历史选股与同时点可得性未证明；下载日期不等于历史可得日期。",
            "触发随访可能重叠，不是独立交易或策略收益。",
            "未建立成交、历史费用、可交易性及公司行动可比性；无法评估真实退出。",
        ])
    try:
        root = Path(root).resolve()
        retained._clock(now)
        pointer = root / REVIEW_POINTER
        pointer_raw = pointer.read_bytes()
        pins = retained._document(pointer_raw, "ACTUAL")
        if pins.get("action") != "no_order":
            raise ValueError("Invalid replay pointer")
        binding = pins["retained_manifest_binding"]
        directory = retained._manifest_directory(root, binding)
        manifest = retained._document(retained._read(root, binding), "ACTUAL")
        if (manifest.get("schema_version") != retained.MANIFEST_SCHEMA
                or manifest.get("namespace") != "ACTUAL"
                or manifest.get("scope") != "DESCRIPTIVE"
                or manifest.get("action") != "no_order"
                or manifest.get("formal_eligibility") is not False
                or manifest.get("historical_selection_status") != "NOT_REVALIDATED_RETAINED_CASES_ONLY"):
            raise ValueError("ACTUAL descriptive manifest required")
        try:
            retained_at = datetime.fromisoformat(manifest["retained_at"])
        except (ValueError, TypeError):
            raise ValueError("Retained source not yet available") from None
        if retained_at.utcoffset() is None or retained_at > now:
            raise ValueError("Retained source not yet available")
        if directory.parent == (root / retained.PUBLIC_FOLDER).resolve():
            original = manifest["original_manifest_binding"]
            retained._manifest_directory(root, original, folders=(retained.FOLDER,))
            digest = original["sha256"]
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Invalid original manifest digest")
            try:
                exported = datetime.fromisoformat(manifest["exported_at"])
            except (ValueError, TypeError):
                raise ValueError("Invalid export clock") from None
            if exported.utcoffset() is None or not retained_at <= exported <= now:
                raise ValueError("Invalid export clock")
        source_root = directory / "sources"
        mappings = {}
        used = []
        for row in manifest["files"]:
            original, copy = row["original_binding"], row["retained_binding"]
            expected = (source_root / original["path"]).relative_to(root).as_posix()
            if (copy != dict(path=expected, sha256=original["sha256"])
                    or original["path"] in mappings):
                raise ValueError("Invalid retained mapping")
            mappings[original["path"]] = row

        def required(ref):
            row = mappings[ref["path"]]
            if row["original_binding"] != dict(path=ref["path"], sha256=ref["sha256"]):
                raise ValueError("Dependency binding mismatch")
            raw = retained._read(root, row["retained_binding"])
            used.append(row["retained_binding"])
            return raw

        historical = manifest["historical_protocol_binding"]
        spec = retained._spec(required(historical), "ACTUAL", now, source_root=source_root)
        for rule in spec["rule_bindings"]:
            required(rule)
        item = next((row for row in spec["cases"] if row["symbol"] == symbol), None)
        if item is None:
            if pointer.read_bytes() != pointer_raw:
                raise ValueError("Replay pointer changed")
            for ref in [binding, *used]:
                retained._read(root, ref)
            return dict(result, status="NOT_COVERED",
                reason="此证券不在已绑定的真实留存样本中；不借用其他证券结果。")
        case_ref = dict(path=item["case_path"], sha256=item["case_sha256"])
        original_case = retained._document(required(case_ref), "ACTUAL")
        for ref in original_case["source_bindings"].values():
            required(ref)
        quote = original_case["current_reference_close"]
        quote_ref = dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])
        retained._document(required(quote_ref), "ACTUAL")
        case, available = retained._verified_case(source_root, item, "ACTUAL", spec["end_date"], now)
        if datetime.fromisoformat(available) > retained_at:
            raise ValueError("Acquisition follows retention")
        replay = replay_v1(case["bars"], spec)
        if spec["rule_version"] != "hotspot-prior-five-completed-bars-v1":
            raise ValueError("Unsupported rule definition")
        rule_definition = dict(
            source_functions=[
                "domain/hotspot/price_action_plan.py:calculate_price_levels",
                "domain/hotspot/current_price.py:current_signal",
                "domain/hotspot/event_replay.py:replay_v1/_outcome"],
            entry="以每根已完成的60分钟bar为观察点：收盘价严格高于此前5根已完成bar的最高价，且该bar成交量不低于此前5根平均成交量的1.2倍，才记为触发。价格突破但量不足仅为待确认，不是入场成交。",
            invalidation="触发时冻结此前5根bar的最低价为失效参考；之后已完成60分钟bar收盘价严格低于该价，记录首次跌破时间。等于参考价不算跌破；该线不是保证可执行的止损单。",
            context="日线与15分钟数据仅展示截至触发时已经完成的周期背景，不替代60分钟触发条件，也不据此声称多周期趋势确认。",
            followup="从触发之后的bar随访，最多观察后续5个交易日；开发段不得使用验证段数据，随访止于所属分段末日。只有第五个后续交易日15:00收盘可用才算五日完整。下一交易日收盘前任一后续完整60分钟收盘价小于或等于冻结触发价，记为假突破代理。",
            censoring="随访未完整为右删失：已观察窗口内没有记录跌破，不代表后续不会失效，也不能计作成功；五日失效及第五日价格变化仍不可评。",
            exit="本规则没有真实成交、退出执行或止盈目标模型。观察到跌破只要求研究复核；历史可交易性、涨跌停、T+1、数量现金、费用滑点和公司行动未核验，实际EXIT及净收益不可评。")
        if pointer.read_bytes() != pointer_raw:
            raise ValueError("Replay pointer changed")
        for ref in [binding, *used]:
            retained._read(root, ref)
        # Recheck rule identity after computation as well as before it.
        retained._spec(required(historical), "ACTUAL", now, source_root=source_root)
        return dict(result, status="COVERED", namespace="ACTUAL",
            source_integrity="VERIFIED", evaluated_at=now.isoformat(),
            data_available_at=available, retained_at=manifest["retained_at"],
            market_trade_date=case["market_trade_date"],
            manifest_binding=binding, protocol_binding=historical,
            case_binding=case_ref, quote_binding=quote_ref,
            rule_version=spec["rule_version"], rule_bindings=spec["rule_bindings"],
            rule_definition=rule_definition,
            source_bindings=original_case["source_bindings"],
            retained_bindings=used,
            partitions={k: spec[k] for k in
                ("start_date", "development_end", "validation_start", "end_date")},
            rule_inputs=dict(primary_period=spec["primary_period"],
                forward_sessions=spec["forward_sessions"],
                false_breakout_proxy=spec["false_breakout_proxy"],
                failure_proxy=spec["failure_proxy"], outcome_boundary=spec["outcome_boundary"]),
            execution_unassessable_reasons=spec["execution"]["required"],
            segments=replay["segments"],
            events=[dict(event, segment=segment)
                for segment, events in replay["events"].items() for event in events])
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError, AttributeError) as error:
        code, explanation = _symbol_replay_failure(error)
        return dict(result, reason_code=code,
            reason=explanation + "；原候选观察仍可查看。")
