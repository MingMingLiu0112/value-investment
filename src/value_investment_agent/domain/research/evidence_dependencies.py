"""Find facts whose verification depends on invalidated evidence."""


def affected_point_ids(points, initial_ids):
    affected = {str(value) for value in initial_ids}
    while True:
        inputs = set()
        for point in points:
            if str(point['data_point_id']) not in affected:
                continue
            metadata = point.get('metadata') or {}
            aliases = {str(point['source_id'])}
            previous = (metadata.get('provenance_repair') or {}).get('previous_source_id')
            if previous:
                aliases.add(str(previous))
            for source in aliases:
                inputs.add((point['symbol'], str(point['period_label']), point['field_name'], source))
        added = set()
        for point in points:
            point_id = str(point['data_point_id'])
            if point_id in affected:
                continue
            metadata = point.get('metadata') or {}
            if any(str(value) in affected for value in metadata.get('input_data_point_ids', [])):
                added.add(point_id)
                continue
            if str(metadata.get('secondary_data_point_id', '')) in affected:
                added.add(point_id)
                continue
            facts = metadata.get('input_facts') or {}
            sources = dict(metadata.get('input_source_ids') or {})
            sources.update({field: fact.get('source_id') for field, fact in facts.items()})
            for field, source in sources.items():
                exact_id = facts.get(field, {}).get('data_point_id')
                if exact_id:
                    if str(exact_id) in affected:
                        added.add(point_id)
                        break
                    continue
                period = str(facts.get(field, {}).get('period', point['period_label']))
                if (point['symbol'], period, field, str(source)) in inputs:
                    added.add(point_id)
                    break
        if not added:
            return affected
        affected.update(added)
