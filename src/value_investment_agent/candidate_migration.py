"""Plan parser supersession without deleting facts or modifying source evidence."""
from decimal import Decimal
import uuid


def supersede_unpromoted(db, identifiers):
    ids = {uuid.UUID(str(value)) for value in identifiers}
    if not ids:
        return 0
    updated = db.execute("""UPDATE filing_candidates c SET status='superseded_by_parser'
        WHERE c.candidate_id=ANY(%s)
          AND c.status='candidate_pending_automated_verification'
          AND NOT EXISTS (SELECT 1 FROM data_points p
              WHERE p.metadata->>'candidate_id'=c.candidate_id::text)
        RETURNING c.candidate_id""", (list(ids),)).fetchall()
    if len(updated) != len(ids):
        raise ValueError('Supersession preconditions changed; roll back transaction')
    return len(updated)


def plan_candidate_supersession(existing, revised, fact_candidate_ids):
    def key(row):
        return (row['field_name'], row.get('page', row.get('page_number')), row['source_label'],
                Decimal(str(row['value'])), row['unit'])

    retained = {key(row) for row in revised}
    fact_ids = {str(value) for value in fact_candidate_ids}
    revised_by_slot = {}
    for row in revised:
        full_key = key(row)
        revised_by_slot.setdefault(full_key[:3], set()).add(full_key[3:])
    plan = {'unpromoted_obsolete': [], 'fact_backed_requires_audit': [], 'reproduced': [],
            'unique_key_collisions': [], 'already_superseded': []}
    for row in existing:
        identifier = str(row['candidate_id'])
        full_key = key(row)
        alternatives = revised_by_slot.get(full_key[:3], set())
        if alternatives and alternatives != {full_key[3:]}:
            plan['unique_key_collisions'].append(identifier)
        if row['status'] == 'superseded_by_parser':
            plan['already_superseded'].append(identifier)
        elif key(row) in retained:
            plan['reproduced'].append(identifier)
        elif identifier in fact_ids or row['status'] != 'candidate_pending_automated_verification':
            plan['fact_backed_requires_audit'].append(identifier)
        else:
            plan['unpromoted_obsolete'].append(identifier)
    return plan
