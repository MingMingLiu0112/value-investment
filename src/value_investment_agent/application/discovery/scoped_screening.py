"""Screen observed official venues without claiming a complete all-A universe."""
from dataclasses import replace

from ...infrastructure.screening import evidence_screen_v3
from ...m2_market_data import parse_sina_industry, parse_tencent_board
from .official_universe_collection import verify_retained_official_input


VERSION = 'm2-scoped-evidence-screen-v1'
OFFICIAL_VERSION = 'official-security-lists-partial-v1'


def scoped_inputs(*, root, official_payload, tencent_payload, sina_payload):
    """Preserve every unmatched quote as an exclusion, not a missing listing fact."""
    verify_retained_official_input(official_payload, root=root)
    if (official_payload.get('parser_version') != OFFICIAL_VERSION
            or official_payload.get('complete') is not False
            or official_payload.get('scope') != 'OBSERVED_VENUES_ONLY_NOT_ALL_A'):
        raise ValueError('Scoped screening requires replay-verified partial official input')
    covered = official_payload['covered_venues']
    official = {row['symbol']: row for row in official_payload['records']}
    if not official or not covered:
        raise ValueError('No observed official universe to screen')
    providers, filtered = {}, {}
    for name, payload, parser in (
            ('tencent', tencent_payload, parse_tencent_board),
            ('sina', sina_payload, parse_sina_industry)):
        parsed = parser(payload)
        raw_rows = payload['rows']
        if len(raw_rows) != len(parsed):
            raise ValueError('Quote parser changed row correspondence')
        kept, excluded = [], []
        for raw, row in zip(raw_rows, parsed):
            if row['symbol'] in official:
                kept.append(raw)
            else:
                excluded.append(dict(symbol=row['symbol'],
                    reason='NOT_IN_OBSERVED_OFFICIAL_LIST_NOT_PROOF_OF_DELISTING'))
        if not kept:
            raise ValueError('Provider has no quotes in observed official scope: ' + name)
        filtered[name] = dict(payload, rows=kept)
        providers[name] = dict(received_row_count=len(parsed), scoped_row_count=len(kept),
            excluded_row_count=len(excluded), excluded_quotes=excluded)
    summary = dict(status='PARTIAL', scope=official_payload['scope'], all_a_complete=False,
        required_venues=official_payload['required_venues'], covered_venues=covered,
        failed_venues=official_payload['failed_venues'],
        effective_session=official_payload['effective_session'],
        observed_universe_count=len(official), venue_coverage=official_payload['venue_coverage'],
        quote_coverage=providers, formal_eligibility=False, action='no_order')
    return filtered['tencent'], filtered['sina'], summary


def build_discovery_receipt(*, root, **kwargs):
    tencent, sina, _ = scoped_inputs(root=root, official_payload=kwargs['official_payload'],
        tencent_payload=kwargs['tencent_payload'], sina_payload=kwargs['sina_payload'])
    # Reuse exactly the existing financial, candidate, threshold and timing rules.
    receipt = evidence_screen_v3.build_discovery_receipt(**dict(kwargs,
        tencent_payload=tencent, sina_payload=sina))
    return replace(receipt, rule_version=VERSION)
