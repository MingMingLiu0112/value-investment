"""Read-only audit of promoted filing hashes, streaming each retained PDF."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


def retained_hash(path):
    if not path or not Path(path).is_file():
        return None
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    with connect(get_settings().database_url) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        connection.execute("SET statement_timeout = '45s'")
        rows = connection.execute("""
            SELECT d.document_id, d.sha256 AS stored_hash, d.local_path AS stored_path,
                   o.disclosure_id, o.sha256 AS official_hash, o.local_path,
                   o.source_url, count(*) AS point_count
            FROM data_points p
            JOIN raw_documents d ON d.document_id = p.source_id
            LEFT JOIN filing_candidates c ON c.candidate_id::text = p.metadata->>'candidate_id'
            LEFT JOIN official_disclosures o ON o.disclosure_id = c.disclosure_id
            WHERE p.metadata ? 'candidate_id'
            GROUP BY d.document_id, o.disclosure_id
        """).fetchall()
        counts = Counter()
        details = []
        for row in rows:
            status = 'ok'
            actual = None
            stored_actual = None
            if not row['official_hash']:
                status = 'missing_candidate_lineage'
            else:
                path = Path(row['local_path']) if row['local_path'] else None
                if path is None or not path.is_file():
                    status = 'missing_archive'
                else:
                    actual = retained_hash(path)
                    if actual != row['official_hash']:
                        status = 'archive_hash_mismatch'
                    elif row['stored_hash'] != actual:
                        reference = hashlib.sha256(
                            f"official_evidence_sha256={row['official_hash']}".encode()
                        ).hexdigest()
                        status = 'legacy_reference_hash' if row['stored_hash'] == reference else 'unexplained_stored_hash'
                    elif row['stored_path'] != row['local_path']:
                        stored_actual = retained_hash(row['stored_path'])
                        if stored_actual == actual:
                            status = 'identical_archive_alternate_path'
                        elif stored_actual is None:
                            status = 'stored_archive_missing'
                        else:
                            status = 'stored_archive_hash_mismatch'
            counts[status] += row['point_count']
            details.append(dict(row, actual_file_hash=actual,
                                stored_path_file_hash=stored_actual, status=status))
        print(json.dumps({'point_counts': dict(counts), 'document_links': len(rows),
                          'details': details}, default=str, ensure_ascii=False))


if __name__ == '__main__':
    main()
