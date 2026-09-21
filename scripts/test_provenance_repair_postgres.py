"""Exercise actual repair SQL only against connection-local temporary tables."""
import hashlib
import json
import tempfile
import uuid
from pathlib import Path

from psycopg import sql

from provenance_repair import repair_batch
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


def main():
    with tempfile.TemporaryDirectory() as directory, connect(get_settings().database_url) as db:
        db.execute("SET lock_timeout = '5s'")
        db.execute("SET statement_timeout = '30s'")
        # Clone column constraints, never production rows or production foreign keys.
        tables = ('raw_documents', 'data_points', 'official_disclosures', 'filing_candidates')
        for table in tables:
            db.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE public.{} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)').format(
                sql.Identifier(table), sql.Identifier(table)))
        db.execute('SET LOCAL search_path = pg_temp')
        for table in tables:
            assert db.execute('SELECT relpersistence FROM pg_class WHERE oid = %s::regclass',
                              (table,)).fetchone()['relpersistence'] == 't'

        def seed(number, corrupt=False):
            path = Path(directory) / f'{number}.pdf'
            payload = f'%PDF synthetic repair fixture {number}'.encode()
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            reference = hashlib.sha256(f'official_evidence_sha256={digest}'.encode()).hexdigest()
            document, disclosure, candidate = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            point = uuid.UUID(int=number)
            db.execute("""INSERT INTO raw_documents
                (document_id, source_name, source_url, fetched_at, parser_version, sha256, local_path)
                VALUES (%s,'fixture','https://example.invalid/test.pdf',now(),'test',%s,%s)""",
                (document, reference, str(path)))
            db.execute("""INSERT INTO official_disclosures
                (disclosure_id,symbol,report_period,report_kind,title,source_name,source_url,published_at,sha256,local_path)
                VALUES (%s,'000001','2025-12-31','annual','fixture','fixture',
                        'https://example.invalid/test.pdf',now(),%s,%s)""", (disclosure,digest,str(path)))
            db.execute("""INSERT INTO filing_candidates
                (candidate_id,disclosure_id,field_name,value,unit,page_number,source_label,excerpt,parser_version,status)
                VALUES (%s,%s,'roe',8.32,'percent',1,'fixture','fixture','test','automatically_verified')""",
                (candidate,disclosure))
            metadata = {'candidate_id':str(candidate), 'note':'preserve me'}
            db.execute("""INSERT INTO data_points
                (data_point_id,symbol,field_name,period_label,value,unit,source_id,validation_status,metadata)
                VALUES (%s,'000001','roe','2025-12-31',8.32,'percent',%s,'verified',%s)""",
                (point,document,json.dumps(metadata)))
            if corrupt:
                path.write_bytes(b'corrupted fixture')
            return point, document, metadata

        point, old_source, old_metadata = seed(1)
        original = db.execute('SELECT * FROM data_points WHERE data_point_id=%s',(point,)).fetchone()
        assert repair_batch(db, apply=True)['repaired'] == 1
        updated = db.execute('SELECT * FROM data_points WHERE data_point_id=%s',(point,)).fetchone()
        for key in original:
            if key not in ('source_id','metadata'):
                assert updated[key] == original[key], key
        assert updated['source_id'] != old_source
        history = updated['metadata']['provenance_repair']
        assert history['previous_source_id'] == str(old_source)
        assert history['previous_metadata'] == old_metadata
        assert db.execute('SELECT 1 FROM raw_documents WHERE document_id=%s',(old_source,)).fetchone()
        assert repair_batch(db, apply=True)['repaired'] == 0
        first, source, _ = seed(2)
        seed(3, corrupt=True)
        before_count = db.execute('SELECT count(*) AS n FROM raw_documents').fetchone()['n']
        try:
            with db.transaction():
                repair_batch(db, apply=True)
        except ValueError as error:
            assert 'hash mismatch' in str(error)
        else:
            raise AssertionError('Corruption should abort repair')
        assert db.execute('SELECT source_id FROM data_points WHERE data_point_id=%s',
                          (first,)).fetchone()['source_id'] == source
        assert db.execute('SELECT count(*) AS n FROM raw_documents').fetchone()['n'] == before_count
        db.rollback()
    print(json.dumps({'temporary_tables_only':True,'financial_fields_preserved':True,
                      'old_metadata_preserved':True,'idempotent':True,'batch_rollback_verified':True}))


if __name__ == '__main__':
    main()
