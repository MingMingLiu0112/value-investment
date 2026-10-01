#!/usr/bin/env python3
"""Build an explicitly requested historical preview; never a user frontend."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from dataclasses import asdict, replace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.build_m7_daily_workbench import build_packet  # noqa: E402
from value_investment_agent.application.product.common import (  # noqa: E402
    encode_json_bytes,
    sha256_bytes,
    require_inside,
    load_json_object,
    sha256_file,
    write_new_json,
)
from value_investment_agent.application.product.workbench import load_existing_workbench_for_presentation  # noqa: E402
from value_investment_agent.application.historical_validation.reverse_equity_expectations import load_reverse_expectations_for_presentation
from value_investment_agent.presentation.read_models.conditional_expectations import project_conditional_expectations, render_company_review_cards
from value_investment_agent.presentation.read_models.product_workbench import EvidenceRecord
from value_investment_agent.application.historical_validation.disclosed_metric_review import review_disclosed_metrics
from value_investment_agent.application.historical_validation.reported_cash_proxy import reported_cash_proxies
from value_investment_agent.presentation.read_models.reported_financials import project_reported_financials
from value_investment_agent.application.historical_validation.event_source_review import prepare_event_source_review
from value_investment_agent.presentation.read_models.company_events import project_company_event_questions
from value_investment_agent.application.historical_validation.reported_cash_change import reported_cash_change
from value_investment_agent.application.product.dividend_history import read_dividend_history
from value_investment_agent.presentation.read_models.dividend_history import project_dividend_history
from value_investment_agent.application.product.research_recipe import load_research_recipe
from value_investment_agent.presentation.read_models.existing_research_report import project_existing_research_workbench, public_workbench_payload_from_snapshot  # noqa: E402
from value_investment_agent.application.product.product_workbench_candidate import (  # noqa: E402
    build_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (  # noqa: E402
    write_product_workbench_candidate,
)
from value_investment_agent.presentation.read_models.product_workbench import (  # noqa: E402
    product_workbench_from_payload,
)


def _generated_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("generated-at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--research-recipe', nargs=2, metavar=('PATH', 'SHA256'))
    parser.add_argument("--base-payload", type=Path)
    parser.add_argument("--base-payload-sha256")
    parser.add_argument("--base-read-model-snapshot", action="store_true")
    parser.add_argument("--existing-workbench", type=Path)
    parser.add_argument("--existing-workbench-sha256")
    parser.add_argument('--expectations-replay', type=Path)
    parser.add_argument('--expectations-replay-sha256')
    parser.add_argument('--metric-transcription', nargs=2, action='append', default=[],
                        metavar=('PATH', 'SHA256'), help='Repeat for source-verified disclosed financial rows.')
    parser.add_argument('--event-scan', nargs=2, metavar=('PATH', 'SHA256'))
    parser.add_argument('--cash-change-periods', nargs=2, metavar=('CURRENT', 'PRIOR'))
    parser.add_argument('--dividend-package', nargs=2, metavar=('PATH', 'SHA256'))
    parser.add_argument('--recovered-event-original', nargs=2, action='append', default=[],
                        metavar=('REFERENCE_ID', 'PATH'))
    parser.add_argument('--read-model-only', action='store_true')
    parser.add_argument('--read-model-report', type=Path)
    parser.add_argument('--presentation-as-of', type=date.fromisoformat,
                        help='Explicit read-model observation date; never changes quote or fact dates.')
    parser.add_argument("--integrate-canonical", action="store_true",
                        help="Retain all canonical sheets in a runtime-only reviewed preview.")
    parser.add_argument(
        "--historical-preview",
        action="store_true",
        help="Required acknowledgement that this is a runtime-only historical preview.",
    )
    parser.add_argument(
        "--generated-at",
        type=_generated_at,
        default=datetime.now(timezone.utc),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    recipe_binding = None
    if getattr(args, 'research_recipe', None):
        if (not args.read_model_only or args.integrate_canonical or args.base_payload is not None
                or args.existing_workbench is not None or args.expectations_replay is not None
                or args.metric_transcription or args.event_scan or args.dividend_package
                or args.recovered_event_original or args.cash_change_periods
                or args.presentation_as_of is not None or args.base_payload_sha256
                or args.existing_workbench_sha256 or args.expectations_replay_sha256
                or args.base_read_model_snapshot):
            raise ValueError('recipe requires read-model-only and excludes individual input overrides')
        path, digest = args.research_recipe
        recipe = load_research_recipe(root=ROOT, path=ROOT / path, expected_sha256=digest)
        args.base_payload = Path(recipe['base']['path'])
        args.base_payload_sha256 = recipe['base']['sha256']
        args.base_read_model_snapshot = True
        args.existing_workbench = Path(recipe['workbench']['path'])
        args.existing_workbench_sha256 = recipe['workbench']['sha256']
        args.presentation_as_of = date.fromisoformat(recipe['presentation_as_of'])
        if recipe.get('expectations'):
            args.expectations_replay = Path(recipe['expectations']['path'])
            args.expectations_replay_sha256 = recipe['expectations']['sha256']
        args.metric_transcription = [(item['path'], item['sha256']) for item in recipe.get('metrics', [])]
        args.cash_change_periods = recipe.get('cash_change_periods')
        args.event_scan = None if not recipe.get('event_scan') else (
            recipe['event_scan']['path'], recipe['event_scan']['sha256'])
        args.recovered_event_original = [(item['id'], item['path']) for item in recipe.get('recovered_event_originals', [])]
        args.dividend_package = None if not recipe.get('dividend_package') else (
            recipe['dividend_package']['path'], recipe['dividend_package']['sha256'])
        recipe_binding = dict(path=str(path), sha256=digest, symbol=recipe['symbol'])
    if getattr(args, 'read_model_report', None) is not None and not getattr(args, 'read_model_only', False):
        raise ValueError('read-model report requires read-model-only mode')
    if not args.historical_preview:
        raise ValueError("refusing candidate creation without --historical-preview")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if not output.resolve().is_relative_to(ROOT / "runtime"):
        raise ValueError("historical preview must remain under runtime/")
    source_receipt = output.with_name(output.stem + ".source-bindings.json")
    if source_receipt.exists():
        raise FileExistsError("historical preview source receipt already exists")
    packet = None
    if args.base_payload is not None or args.base_payload_sha256 is not None:
        if args.base_payload is None or args.base_payload_sha256 is None:
            raise ValueError("base payload requires path and hash")
        base = require_inside(ROOT, ROOT / args.base_payload, "base payload")
        if sha256_file(base) != args.base_payload_sha256:
            raise ValueError("base payload hash mismatch")
        payload = load_json_object(base, "base payload")
        if args.base_read_model_snapshot:
            payload = public_workbench_payload_from_snapshot(payload)
    else:
        if args.base_read_model_snapshot:
            raise ValueError("snapshot mode requires pinned base payload")
        packet = build_packet(args.generated_at)
        payload = build_product_workbench_candidate_payload(packet, root=ROOT)
    model = product_workbench_from_payload(payload)
    presentation_date = getattr(args, 'presentation_as_of', None)
    if presentation_date is not None:
        if not model.as_of <= presentation_date <= args.generated_at.date():
            raise ValueError('presentation date must not backdate or exceed generation date')
        model = replace(model, as_of=presentation_date)
    if args.existing_workbench is not None or args.existing_workbench_sha256 is not None:
        if args.existing_workbench is None or args.existing_workbench_sha256 is None:
            raise ValueError("existing workbench requires path and hash")
        research = load_existing_workbench_for_presentation(
            root=ROOT, path=ROOT / args.existing_workbench,
            expected_sha256=args.existing_workbench_sha256,
        )
        model = project_existing_research_workbench(model, research)
    expectations_path = getattr(args, 'expectations_replay', None)
    expectations_hash = getattr(args, 'expectations_replay_sha256', None)
    if expectations_path is not None or expectations_hash is not None:
        if not all((expectations_path, expectations_hash, args.existing_workbench_sha256)):
            raise ValueError('expectations require pinned replay and existing workbench')
        expectations_path = require_inside(ROOT, ROOT / expectations_path, 'expectations replay')
        expectations = load_reverse_expectations_for_presentation(root=ROOT,
            path=expectations_path, expected_sha256=expectations_hash,
            workbench_sha256=args.existing_workbench_sha256)
        evidence = EvidenceRecord(f"{expectations['symbol']}-conditional-expectations-{expectations_hash[:12]}",
            '条件性历史价格预期（非当前建议）', 'retrospective_expectations',
            expectations_path.relative_to(ROOT).as_posix(), expectations_hash,
            datetime.fromisoformat(expectations['created_at']).date())
        model = project_conditional_expectations(model, expectations, evidence)
    metric_bindings = []
    cash_change_built = False
    for metric_path, metric_hash in getattr(args, 'metric_transcription', []):
        if not args.existing_workbench or not args.existing_workbench_sha256:
            raise ValueError('disclosed financial presentation requires pinned workbench')
        metric_path = require_inside(ROOT, ROOT / metric_path, 'metric transcription')
        review = review_disclosed_metrics(root=ROOT, path=metric_path, expected_sha256=metric_hash,
            workbench_path=ROOT / args.existing_workbench, workbench_sha256=args.existing_workbench_sha256)
        has_capex = any(fact['metric_name'] == 'reported_cash_capex' for fact in review['facts'])
        proxy = reported_cash_proxies(review) if has_capex else None
        change = None
        if getattr(args, 'cash_change_periods', None) and any(
                fact['metric_name'].startswith('cash_bridge_') for fact in review['facts']):
            if cash_change_built:
                raise ValueError('multiple cash change transcriptions are ambiguous')
            change = reported_cash_change(review, current_period=args.cash_change_periods[0],
                                          prior_period=args.cash_change_periods[1])
            cash_change_built = True
        evidence = EvidenceRecord(f"{review['symbol']}-disclosed-rows-{metric_hash[:12]}",
            '原报告披露数字复核（不是研究准入）', 'disclosed_financial_rows',
            metric_path.relative_to(ROOT).as_posix(), metric_hash,
            datetime.fromisoformat(review['observed_at']).date())
        model = project_reported_financials(model, review, proxy, evidence, cash_change=change)
        metric_bindings.append(dict(path=metric_path.relative_to(ROOT).as_posix(), sha256=metric_hash,
                                    review=review, cash_proxy=proxy, cash_change=change))
    if getattr(args, 'cash_change_periods', None) and not cash_change_built:
        raise ValueError('cash change requires an explicit matched component transcription')
    event_binding = None
    event_scan = getattr(args, 'event_scan', None)
    recovered = getattr(args, 'recovered_event_original', [])
    if recovered and not event_scan:
        raise ValueError('recovered original requires event scan')
    if event_scan:
        if not args.existing_workbench or not args.existing_workbench_sha256:
            raise ValueError('event presentation requires pinned workbench')
        if len({key for key, _ in recovered}) != len(recovered):
            raise ValueError('duplicate recovered event reference')
        event_path = require_inside(ROOT, ROOT / event_scan[0], 'event scan')
        event_packet = prepare_event_source_review(root=ROOT, path=event_path,
            expected_sha256=event_scan[1], symbol=research['symbol'],
            recovered_originals={key: ROOT / value for key, value in recovered})
        evidence = EvidenceRecord(f"{research['symbol']}-event-originals-{event_scan[1][:12]}",
            '封存区间公告原件复核（影响未批准）', 'event_source_review',
            event_path.relative_to(ROOT).as_posix(), event_scan[1], args.generated_at.date())
        model = project_company_event_questions(model, event_packet, evidence)
        event_binding = dict(path=event_path.relative_to(ROOT).as_posix(), sha256=event_scan[1],
                             recovered_originals=recovered, source_review=event_packet)
    dividend_binding = None
    if getattr(args, 'dividend_package', None):
        if not args.existing_workbench:
            raise ValueError('dividend history requires pinned existing company workbench')
        path, digest = args.dividend_package
        path = require_inside(ROOT, ROOT / path, 'dividend package')
        history = read_dividend_history(root=ROOT, path=path, expected_sha256=digest, symbol=research['symbol'])
        evidence = EvidenceRecord(f"{research['symbol']}-dividend-history-{digest[:12]}",
            '历史分红生命周期（非当前股息率或持续性准入）', 'dividend_history',
            path.relative_to(ROOT).as_posix(), digest, datetime.fromisoformat(history['observed_at']).date())
        model = project_dividend_history(model, history, evidence)
        dividend_binding = dict(path=path.relative_to(ROOT).as_posix(), sha256=digest, history=history)
    if getattr(args, 'read_model_only', False):
        if output.suffix != '.json' or getattr(args, 'integrate_canonical', False):
            raise ValueError('read-model-only requires JSON output without workbook publication')
        snapshot = json.loads(json.dumps(asdict(model), default=lambda value: value.isoformat(), ensure_ascii=False))
        report_path = getattr(args, 'read_model_report', None)
        if report_path is not None:
            report_path = require_inside(ROOT / 'runtime', ROOT / report_path, 'read-model report')
            if report_path.exists():
                raise FileExistsError('read-model report already exists')
        write_new_json(output, dict(schema_version='historical-company-read-model-preview-v1',
            snapshot=snapshot, existing_workbench_sha256=args.existing_workbench_sha256,
            expectations_replay_sha256=expectations_hash, base_payload_sha256=args.base_payload_sha256,
            disclosed_financial_bindings=metric_bindings,
            event_source_binding=event_binding,
            dividend_history_binding=dividend_binding,
            research_recipe_binding=recipe_binding,
            canonical_written=False, historical_preview=True, action='no_order'))
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open('x', encoding='utf-8') as handle:
                handle.write(render_company_review_cards(model))
        print(json.dumps(dict(output=str(output), sha256=sha256_file(output),
                              canonical_written=False, action='no_order'), indent=2))
        return 0
    if getattr(args, "integrate_canonical", False):
        if args.base_payload is None or args.existing_workbench is None:
            raise ValueError("canonical integration requires pinned base and existing research")
        from scripts.current.publish_product_workbench_to_canonical import (
            _workbook_path, build_protected_research_preview,
        )
        receipt = build_protected_research_preview(ROOT, _workbook_path(), output, model)
    else:
        receipt = write_product_workbench_candidate(model, output=output, root=ROOT)
    receipt.update(
        {
            "legacy_packet_schema_version": None if packet is None else packet["schema_version"],
            "legacy_packet_sha256": None if packet is None else sha256_bytes(encode_json_bytes(packet)),
            "legacy_evidence_count": None if packet is None else len(packet["audit"]["artifacts"]),
            "existing_workbench_sha256": args.existing_workbench_sha256,
            "base_payload_sha256": args.base_payload_sha256,
            "expectations_replay_sha256": expectations_hash,
        }
    )
    write_new_json(source_receipt, {
        "schema_version": "existing-workbench-preview-bindings-v1",
        "base_payload_path": None if args.base_payload is None else str(args.base_payload),
        "base_payload_sha256": args.base_payload_sha256,
        "base_is_read_model_snapshot": args.base_read_model_snapshot,
        "integrated_canonical": getattr(args, "integrate_canonical", False),
        "existing_workbench_path": None if args.existing_workbench is None else str(args.existing_workbench),
        "existing_workbench_sha256": args.existing_workbench_sha256,
        "expectations_replay_path": None if expectations_path is None else str(expectations_path.relative_to(ROOT)),
        "expectations_replay_sha256": expectations_hash,
        "disclosed_financial_bindings": metric_bindings,
        "event_source_binding": event_binding,
        "dividend_history_binding": dividend_binding,
        "output_manifest_sha256": receipt["manifest_sha256"],
        "workbook_sha256": receipt["workbook_sha256"],
        "historical_preview": True, "canonical_written": False, "action": "no_order",
    })
    receipt["source_receipt"] = str(source_receipt.relative_to(ROOT))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
