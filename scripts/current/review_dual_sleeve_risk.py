"""Review local dual-sleeve risk or append a user-provided manual declaration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))

from value_investment_agent.application.product.dual_sleeve_risk import (
    run_dual_sleeve_review, append_dual_sleeve_manual_record, _storage_path, _strict_json,
    run_dual_sleeve_input_sheet_review,
)
from value_investment_agent.application.product.common import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--input', '--portfolio', dest='input', type=Path)
    parser.add_argument('--input-sha256', '--portfolio-sha256', dest='input_sha256')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--private-root', type=Path)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--input-sheet', type=Path)
    parser.add_argument('--input-sheet-sha256')
    parser.add_argument('--manual-record', type=Path)
    parser.add_argument('--manual-record-sha256')
    parser.add_argument('--record-directory', type=Path)
    parser.add_argument('--expected-head-sha256')
    parser.add_argument('--private-risk-config', type=Path)
    parser.add_argument('--private-risk-config-sha256')
    parser.add_argument('--summary-preview', action='store_true')
    args = parser.parse_args()
    if args.private_risk_config is not None or args.summary_preview or args.private_risk_config_sha256:
        if not args.summary_preview or args.private_risk_config is None or not args.private_risk_config_sha256:
            parser.error('summary preview requires private config path and hash')
        if args.synthetic or any(value is not None for value in (args.input, args.input_sha256,
                args.output, args.private_root, args.input_sheet, args.input_sheet_sha256,
                args.manual_record, args.manual_record_sha256, args.record_directory, args.expected_head_sha256)):
            parser.error('summary preview excludes other operations')
        from value_investment_agent.application.product.dual_sleeve_public_summary import (
            prepare_private_risk_summary, public_summary_sha256,
        )
        summary, _ = prepare_private_risk_summary(root=ROOT, config_path=args.private_risk_config,
            config_sha256=args.private_risk_config_sha256)
        print(json.dumps(dict(summary=summary, approved_summary_sha256=public_summary_sha256(summary)),
            ensure_ascii=False, indent=2))
        return 0
    if args.manual_record is not None:
        if any(value is not None for value in (args.input, args.output, args.input_sha256,
                args.input_sheet, args.input_sheet_sha256)):
            parser.error('manual append excludes risk report inputs/output')
        if args.record_directory is None or args.manual_record_sha256 is None:
            parser.error('manual record needs exact input hash and record directory')
        source = _storage_path(ROOT, args.manual_record, namespace='SIMULATED' if args.synthetic else 'ACTUAL',
            private_root=args.private_root, must_exist=True)
        if sha256_file(source) != args.manual_record_sha256:
            raise ValueError('manual record input hash mismatch')
        body = _strict_json(source)
        if sha256_file(source) != args.manual_record_sha256:
            raise ValueError('manual record input changed while reading')
        result = append_dual_sleeve_manual_record(root=ROOT, directory=args.record_directory,
            body=body, expected_head_sha256=args.expected_head_sha256, private_root=args.private_root,
            synthetic=args.synthetic)
    else:
        if any(value is not None for value in (args.manual_record_sha256, args.record_directory, args.expected_head_sha256)):
            parser.error('manual journal flags require --manual-record')
        if args.input_sheet is not None:
            if args.input is not None or args.input_sha256 is not None:
                parser.error('input-sheet excludes portfolio JSON input')
            result = run_dual_sleeve_input_sheet_review(root=ROOT, input_path=args.input_sheet,
                input_sha256=args.input_sheet_sha256, output_path=args.output,
                private_root=args.private_root, synthetic=args.synthetic)
        else:
            if args.input_sheet_sha256 is not None:
                parser.error('input-sheet hash requires input-sheet')
            result = run_dual_sleeve_review(root=ROOT, input_path=args.input, input_sha256=args.input_sha256,
                output_path=args.output, private_root=args.private_root, synthetic=args.synthetic)
        if result.get('sensitivity') == 'PRIVATE_USER_CONFIRMED':
            result = dict(schema_version=result['schema_version'], action='no_order', status=result['status'],
                detail='PRIVATE_REPORT_IN_MEMORY_OR_EXPLICIT_PRIVATE_OUTPUT', trade_eligible=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
