"""Bounded-memory content checks for a single PostgreSQL transaction snapshot."""
import hashlib
import uuid

from psycopg import sql


def table_checks(connection):
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    connection.execute("SET LOCAL extra_float_digits = 3")
    connection.execute("SET LOCAL work_mem = '8MB'")
    tables = connection.execute("""SELECT c.relname AS name,
        ARRAY(SELECT a.attname FROM pg_index i
          CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, position)
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
          WHERE i.indrelid = c.oid AND i.indisprimary ORDER BY k.position) AS keys
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
        ORDER BY c.relname""").fetchall()
    if not tables:
        raise RuntimeError('No public tables available for backup verification')
    result = {}
    for table in tables:
        if not table['keys']:
            raise RuntimeError('Backup verification requires a primary key: ' + table['name'])
        query = sql.SQL('SELECT row_to_json(t)::text AS row_data FROM {} AS t ORDER BY {}').format(
            sql.Identifier('public', table['name']),
            sql.SQL(', ').join(sql.Identifier(key) for key in table['keys']))
        digest = hashlib.sha256()
        count = 0
        with connection.cursor(name='backup_' + uuid.uuid4().hex) as cursor:
            cursor.itersize = 256
            cursor.execute(query)
            for row in cursor:
                encoded = row['row_data'].encode('utf-8')
                digest.update(len(encoded).to_bytes(8, 'big'))
                digest.update(encoded)
                count += 1
        result[table['name']] = {'rows': count, 'sha256': digest.hexdigest()}
    return result


def compare_checks(expected, actual):
    if not expected or set(expected) != set(actual):
        raise RuntimeError('Restored public table set differs from backup snapshot')
    for name in sorted(expected):
        if expected[name] != actual[name]:
            raise RuntimeError('Restored table count or content hash differs: ' + name)
