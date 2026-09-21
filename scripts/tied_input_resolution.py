"""Exact, evidence-reviewed replacements; never infer replacements by tolerance."""
from decimal import Decimal


CASES = (
    dict(symbol='000612', field='operating_cost',
         old_id='5fe0231d-5c91-4d76-bbaf-22151e078545', old_value='5040616835.68', old_page=83,
         new_id='a10229cf-c6be-45c3-9445-404dbdc50b2e', new_value='5038014974.44', new_page=81,
         sha256='ae530051d9ac6d568bb42884d01fb30dcfd04c0cc887725fd594eefcc081ca98',
         reason='parent_only_cost_must_not_replace_consolidated_cost'),
    dict(symbol='002125', field='bonds_payable',
         old_id='a9ad813b-31ed-4971-86bc-1e05f4ca83c3', old_value='450138600.00', old_page=161,
         new_id='15fd8775-32ba-480b-8ea8-0056f2e5db7d', new_value='450138560.42', new_page=80,
         sha256='01c39e74315dbc38e3d7d7bf0d12dd439433e7ec2561f45eaadc835e57ec7859',
         reason='rounded_note_does_not_replace_precise_statement_amount'),
    dict(symbol='300014', field='short_term_borrowings',
         old_id='467600fc-6bd9-4252-8ab0-50876c2bbc7f', old_value='706335000.00', old_page=198,
         new_id='d6ec9251-b9f7-41f1-905a-336f077692f3', new_value='706335000.01', new_page=86,
         sha256='3bee0ca9a6232c60c53f195d078446a45fd4941bd997258b474cebe835eea3b8',
         reason='rounded_note_does_not_replace_precise_statement_amount'),
)


def plan_resolution(rows):
    by_id = {str(r['data_point_id']): r for r in rows}
    changes = []
    for case in CASES:
        pair = []
        for prefix in ('old', 'new'):
            row = by_id.get(case[prefix + '_id'])
            if row is None:
                raise ValueError('Missing reviewed input: ' + case[prefix + '_id'])
            metadata = row.get('metadata') or {}
            if not (row['symbol'] == case['symbol'] and row['field_name'] == case['field']
                    and str(row['period_label']) == '2025-12-31' and row['unit'] == 'CNY'
                    and Decimal(str(row['value'])) == Decimal(case[prefix + '_value'])
                    and row['sha256'] == case['sha256']
                    and metadata.get('page_number') == case[prefix + '_page']
                    and row['validation_status'] == 'verified'
                    and metadata.get('automatic_cross_source_verification') is True
                    and not metadata.get('evidence_quarantine')
                    and not metadata.get('superseded_by_parser')
                    and not row.get('human_reviewed')):
                raise ValueError('Reviewed input preconditions changed: ' + case[prefix + '_id'])
            pair.append(row)
        if pair[0]['source_id'] != pair[1]['source_id']:
            raise ValueError('Reviewed pair no longer references the same original document')
        changes.append({**case, 'previous_metadata': dict(pair[0].get('metadata') or {}),
                        'original_value_preserved': True,
                        'replacement_data_point_id': case['new_id']})
    return changes
