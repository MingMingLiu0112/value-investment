-- Read-only census. Current and annual views overlap; do not sum as issuers.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
WITH views AS (
    SELECT 'current' AS view_name, p.* FROM data_points p
    WHERE NOT (metadata ? 'superseded_by_parser')
    UNION ALL
    SELECT 'annual', p.* FROM data_points p
    WHERE NOT (metadata ? 'superseded_by_parser')
      AND period_label ~ '^[0-9]{4}-12-31$'
), ranked AS (
    SELECT *, dense_rank() OVER (
        PARTITION BY view_name, symbol, field_name
        ORDER BY period_label DESC, created_at DESC
    ) AS latest_rank FROM views
), normalized AS (
    SELECT *, value * CASE unit
        WHEN 'CNY 100M' THEN 100000000 WHEN 'CNY 10K' THEN 10000 ELSE 1 END AS comparable_value,
        CASE WHEN unit IN ('CNY', 'CNY 10K', 'CNY 100M') THEN 'CNY' ELSE unit END AS comparable_unit
    FROM ranked WHERE latest_rank = 1
), conflicts AS (
    SELECT view_name, symbol, field_name FROM normalized
    GROUP BY view_name, symbol, field_name
    HAVING count(DISTINCT (comparable_value, comparable_unit, validation_status,
        COALESCE(metadata->>'evidence_quarantine', ''),
        COALESCE(metadata->>'automatic_cross_source_verification', ''))) > 1
)
SELECT n.view_name, n.symbol, n.field_name, n.period_label, n.data_point_id,
       n.value, n.unit, n.validation_status, n.created_at,
       n.metadata->>'page_number' AS pdf_page,
       d.document_id, d.source_url, d.sha256
FROM normalized n JOIN conflicts USING (view_name, symbol, field_name)
JOIN raw_documents d ON d.document_id = n.source_id
ORDER BY n.view_name, n.symbol, n.field_name, n.data_point_id;
COMMIT;
