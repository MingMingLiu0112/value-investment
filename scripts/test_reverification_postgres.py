"""Exercise recovery against temporary PostgreSQL tables, never production rows."""
import hashlib
import importlib.util
import json
import tempfile
import uuid
from pathlib import Path

from psycopg import sql
from value_investment_agent.db import connect, store_record
from value_investment_agent.settings import get_settings


def main():
    spec = importlib.util.spec_from_file_location('value_investment_agent.recovery_probe',
                                                Path(__file__).with_name('candidate_review.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory, connect(get_settings().database_url) as db:
        db.execute("SET statement_timeout='30s'")
        for table in ('raw_documents', 'data_points', 'official_disclosures', 'filing_candidates'):
            db.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE public.{} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)').format(
                sql.Identifier(table), sql.Identifier(table)))
        db.execute('SET LOCAL search_path=pg_temp')
        path = Path(directory) / 'official.pdf'
        payload = b'%PDF synthetic recovery fixture'
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        disclosure, candidate, document, old, secondary = [uuid.uuid4() for _ in range(5)]
        db.execute("""INSERT INTO raw_documents
            (document_id,source_name,source_url,fetched_at,parser_version,sha256)
            VALUES (%s,'AkShare / Sina detailed financial statements','https://example.invalid/secondary',now(),'test',%s)""",
            (document, 'a' * 64))
        db.execute("""INSERT INTO official_disclosures
            (disclosure_id,symbol,report_period,report_kind,title,source_name,source_url,published_at,sha256,local_path)
            VALUES (%s,'000001','2025-12-31','annual','fixture','CNINFO',
                    'https://example.invalid/official.pdf',now(),%s,%s)""", (disclosure,digest,str(path)))
        db.execute("""INSERT INTO filing_candidates
            (candidate_id,disclosure_id,field_name,value,unit,page_number,source_label,excerpt,parser_version,status)
            VALUES (%s,%s,'revenue',1000000,'CNY',1,'fixture','fixture','test','automatically_verified')""",
            (candidate,disclosure))
        metadata = {'candidate_id':str(candidate), 'evidence_quarantine': {
            'reason':'total_revenue_used_as_operating_revenue'}}
        for point, meta in ((old,metadata),(secondary,{})):
            db.execute("""INSERT INTO data_points
                (data_point_id,symbol,field_name,period_label,value,unit,source_id,validation_status,metadata)
                VALUES (%s,'000001','revenue','2025-12-31',1000000,'CNY',%s,'failed',%s)""",
                (point,document,json.dumps(meta)))
        assert list(module.automatically_verified_candidates(db,10)) == []
        db.execute("UPDATE data_points SET validation_status='pending',metadata=%s WHERE data_point_id=%s",
                   (json.dumps({'evidence_quarantine':{'reason':'other'}}),secondary))
        assert list(module.automatically_verified_candidates(db,10)) == []
        db.execute("UPDATE data_points SET metadata='{}'::jsonb WHERE data_point_id=%s",(secondary,))
        records = list(module.automatically_verified_candidates(db,10))
        assert len(records) == 1
        record = records[0][1]
        assert record.point_metadata['secondary_data_point_id'] == str(secondary)
        assert record.point_metadata['reverification']['previous_data_point_ids'] == [str(old)]
        store_record(db,record,'verified',False)
        assert list(module.automatically_verified_candidates(db,10)) == []
        preserved = db.execute('SELECT metadata,validation_status FROM data_points WHERE data_point_id=%s',(old,)).fetchone()
        assert preserved == {'metadata':metadata,'validation_status':'failed'}
        db.rollback()
    print(json.dumps({'temporary_tables_only':True,'failed_and_quarantined_evidence_blocked':True,
                      'recovery_verified':True,'idempotent':True,'old_evidence_preserved':True}))


if __name__ == '__main__':
    main()
