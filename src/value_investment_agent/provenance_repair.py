"""Repair legacy reference hashes without changing financial facts or statuses."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def verify_archive(row):
    expected = row['official_hash']
    reference = hashlib.sha256(f'official_evidence_sha256={expected}'.encode()).hexdigest()
    if row['stored_hash'] != reference:
        raise ValueError('Not a recognized legacy reference hash')
    with Path(row['local_path']).open('rb') as handle:
        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
    if actual != expected:
        raise ValueError('Official archive hash mismatch')
    return actual


def repair_batch(connection, limit=500, apply=False):
    if not 1 <= limit <= 1000:
        raise ValueError('Batch limit must be between 1 and 1000')
    rows = connection.execute("""
        SELECT p.data_point_id, p.source_id, p.metadata, d.sha256 AS stored_hash,
               o.disclosure_id, o.sha256 AS official_hash, o.local_path,
               o.source_name, o.source_url, o.published_at, o.fetched_at
        FROM data_points p
        JOIN raw_documents d ON d.document_id = p.source_id
        JOIN filing_candidates c ON c.candidate_id = CASE
            WHEN p.metadata->>'candidate_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            THEN (p.metadata->>'candidate_id')::uuid END
        JOIN official_disclosures o ON o.disclosure_id = c.disclosure_id
        WHERE o.archive_status = 'server_resident'
          AND d.sha256 <> o.sha256
        ORDER BY p.data_point_id
        LIMIT %s
        FOR UPDATE OF p
    """, (limit,)).fetchall()
    repaired = 0
    for row in rows:
        digest = verify_archive(row)
        if not apply:
            continue
        now = datetime.now(timezone.utc).isoformat()
        connection.execute("""
            INSERT INTO raw_documents(document_id, source_name, source_url,
                published_at, fetched_at, parser_version, sha256, local_path, metadata)
            VALUES (%s,%s,%s,%s,%s,'provenance-repair-v1',%s,%s,%s)
            ON CONFLICT (sha256) DO NOTHING
        """, (uuid.uuid4(), row['source_name'], row['source_url'], row['published_at'],
              row['fetched_at'], digest, row['local_path'],
              json.dumps({'disclosure_id': str(row['disclosure_id']), 'repair_created_at': now})))
        document = connection.execute(
            'SELECT document_id, source_url, local_path FROM raw_documents WHERE sha256 = %s',
            (digest,),
        ).fetchone()
        # Do not silently inherit conflicting provenance from global hash deduplication.
        if document['source_url'] != row['source_url']:
            raise ValueError('Existing document URL differs; needs explicit lineage review')
        if not document['local_path']:
            raise ValueError('Existing document has no retained archive')
        with Path(document['local_path']).open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != digest:
                raise ValueError('Existing document archive hash mismatch')
        metadata = dict(row['metadata'])
        if 'provenance_repair' in metadata:
            raise ValueError('Existing repair history must not be overwritten')
        metadata['provenance_repair'] = {
            'version': 1, 'at': now, 'previous_source_id': str(row['source_id']),
            'previous_sha256': row['stored_hash'], 'disclosure_id': str(row['disclosure_id']),
            'previous_metadata': row['metadata'],
        }
        metadata['official_file_sha256'] = digest
        metadata['official_file_hash_verified_at_repair'] = True
        cursor = connection.execute("""
            UPDATE data_points SET source_id = %s, metadata = %s
            WHERE data_point_id = %s AND source_id = %s
        """, (document['document_id'], json.dumps(metadata), row['data_point_id'], row['source_id']))
        if cursor.rowcount != 1:
            raise ValueError('Concurrent point change; rolling back batch')
        repaired += 1
    return {'checked': len(rows), 'repaired': repaired, 'apply': apply}
