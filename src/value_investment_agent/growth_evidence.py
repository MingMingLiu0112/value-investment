"""Same-scope supplemental growth evidence, never automatically verified facts."""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from .models import SourceRecord

GROWTH_SOURCE = 'Value Investment Agent same-scope secondary growth'
SOURCES = {'revenue':'AkShare / Sina detailed financial statements',
           'net_income':'AkShare / Sina financial abstract'}


def official_growth_period_matches(excerpt: str, period: str) -> bool:
    """Bind the explicit annual comparison header to the disclosure period."""
    if not isinstance(excerpt, str) or not isinstance(period, str):
        return False
    if not re.fullmatch(r'20\d{2}-12-31', period):
        return False
    if any(label in excerpt for label in ('调整前', '调整后', '重述后')):
        return False
    headers = re.findall(r'(20\d{2})\s*年\s*(20\d{2})\s*年\s*本年比上年\s*增减', excerpt)
    return len(headers) == 1 and headers[0] == (period[:4], str(int(period[:4]) - 1))


def validate_retained_growth(metadata: dict, rows: list[dict], symbol: str,
                             period: str, field: str, value: Decimal) -> bool:
    """Recheck both retained source facts before accepting a growth cross-check."""
    try:
        inputs = metadata['growth_inputs']
        ids = metadata['input_data_point_ids']
        if len(inputs) != 2 or len(ids) != 2 or len(set(ids)) != 2 or len(rows) != 2:
            return False
        base = field.removesuffix('_yoy')
        if base not in SOURCES or metadata['comparison_scope'] != base:
            return False
        by_id = {str(row['data_point_id']):row for row in rows}
        values = []
        for index, item in enumerate(inputs):
            row = by_id[ids[index]]
            expected_period = period if index == 0 else f'{int(period[:4])-1}-12-31'
            if not period.endswith('-12-31') or item['data_point_id'] != ids[index]:
                return False
            for key, expected in [('symbol',symbol),('field_name',base),('period_label',expected_period),
                                  ('unit','CNY'),('source_name',SOURCES[base])]:
                if str(row[key]) != expected or str(item[key]) != expected:
                    return False
            if (row['validation_status'] not in ('pending','verified')
                or (row.get('metadata') or {}).get('evidence_quarantine')
                or row['sha256'] != item['sha256'] or row['source_url'] != item['source_url']):
                return False
            number = Decimal(str(row['value']))
            if not number.is_finite() or number != Decimal(item['value']):
                return False
            values.append(number)
        return values[1] > 0 and abs((values[0]/values[1]-1)*100-value) < Decimal('0.00000001')
    except (KeyError,ValueError,TypeError,ArithmeticError):
        return False


def build_growth_evidence(current: SourceRecord, previous: SourceRecord,
                          current_point_id: str, previous_point_id: str) -> SourceRecord:
    field = current.field_name
    if (field not in SOURCES or previous.field_name != field or current.symbol != previous.symbol
        or current.source_name != SOURCES[field] or previous.source_name != SOURCES[field]
        or current.unit != 'CNY' or previous.unit != 'CNY'):
        raise ValueError('Growth inputs require the same symbol, field, CNY unit and approved source scope')
    current_date, previous_date = map(date.fromisoformat,[current.period_label,previous.period_label])
    if (current_date.month,current_date.day) != (12,31) or previous_date != date(current_date.year-1,12,31):
        raise ValueError('Growth inputs require consecutive annual periods')
    if not current_point_id or not previous_point_id or current_point_id == previous_point_id:
        raise ValueError('Distinct retained input point IDs are required')
    for record in (current,previous):
        if not record.value.is_finite() or (record.point_metadata or {}).get('evidence_quarantine'):
            raise ValueError('Invalid or quarantined growth input')
    if previous.value <= 0:
        raise ValueError('Growth comparison requires a positive prior-year base')
    value = (current.value / previous.value - 1) * Decimal(100)
    inputs = [{'data_point_id':str(point_id), **record.audit_metadata(),
               'sha256':hashlib.sha256(record.raw_payload).hexdigest()}
              for record,point_id in ((current,current_point_id),(previous,previous_point_id))]
    metadata = {'input_data_point_ids':[str(current_point_id),str(previous_point_id)],
                'growth_inputs':inputs,'formula':'(current / previous - 1) * 100',
                'comparison_scope':field,'requires_official_growth_match':True}
    return SourceRecord(symbol=current.symbol,field_name=field+'_yoy',period_label=current.period_label,
        value=value,unit='percent',source_name=GROWTH_SOURCE,
        source_url='internal://value-investment-agent/same-scope-secondary-growth',
        published_at=None,fetched_at=datetime.now(timezone.utc),parser_version='secondary-growth-v1',
        raw_payload=json.dumps(metadata,sort_keys=True).encode(),point_metadata=metadata)
