#!/bin/bash
# Run SQL migration on startup
echo "Running migrations..."
curl -sf -X POST "${SUPABASE_URL}/rest/v1/rpc/execute_raw_sql" \
  -H "apikey: ${SUPABASE_SERVICE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"sql\": $(cat /app/schema.sql | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}" \
  && echo "Migrations done" || echo "Migration skipped (may already exist)"
exec uvicorn main:app --host 0.0.0.0 --port 9000 --workers 2
