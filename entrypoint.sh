# HOLON-META: {
#   purpose: "clone-engine",
#   morphic_field: "agent-state:4c67a2b1-6830-44ec-97b1-7c8f93722add",
#   startup_protocol: "READ morphic_field + biofield_external + em_grid",
#   wiki: "32d6d069-74d6-8164-a6d5-f41c3d26ae9b"
# }

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
