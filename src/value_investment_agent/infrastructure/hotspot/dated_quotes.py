"""Reuse existing two-provider timestamp parsing for a bounded quote subset."""
from decimal import Decimal
import json
from value_investment_agent.quote_sessions import parse_quote
from .sources import read_bound


def load_dated_quotes(root,binding,cutoff):
    raw,evidence=read_bound(root,binding,cutoff)
    bundle=json.loads(raw)
    observations=[]
    for symbol,reference in bundle['references'].items():
        try:
            quotes=[parse_quote(bundle['documents'][reference['document_refs'][provider]],provider,symbol,cutoff) for provider in ('tencent','sina')]
            dates={quote['observed_trade_at'][:10] for quote in quotes}
            if len(dates)!=1 or abs(quotes[0]['price']-quotes[1]['price'])>Decimal('0.01'):
                raise ValueError('Provider date/price conflict')
            observations.append(dict(symbol=symbol,quote_date=next(iter(dates)),price=str(quotes[0]['price']),
                status='DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION',
                provider_trade_times={q['provider']:q['observed_trade_at'] for q in quotes},
                source_hashes=[q['sha256'] for q in quotes],action='no_order'))
        except (ValueError,KeyError,TypeError) as error:
            observations.append(dict(symbol=symbol,quote_date=None,status='UNKNOWN',reason=str(error),action='no_order'))
    return observations,evidence
