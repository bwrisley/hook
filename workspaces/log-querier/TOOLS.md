# HOOK Log Querier -- TOOLS.md

## Log Query Script

Use the query-logs.py script for all log queries. It handles field discovery, query translation, and execution:

### Natural Language Query
```bash
exec: python3 $HOOK_DIR/scripts/query-logs.py "Show me all denied connections to port 3389 in the last 24 hours"
```

### Specify Index
```bash
exec: python3 $HOOK_DIR/scripts/query-logs.py "DNS queries to suspicious domains" --index "dns-*"
```

### Field Discovery
```bash
exec: python3 $HOOK_DIR/scripts/query-logs.py --fields "logs-*"
```

### Custom Time Range
```bash
exec: python3 $HOOK_DIR/scripts/query-logs.py "All traffic from 10.0.1.50" --hours 48
```

## Output Format

The script returns JSON:
```json
{
  "status": "ok",
  "query_dsl": { ... },
  "results": [ ... ],
  "count": 42,
  "executed_at": "2026-04-02T12:00:00Z"
}
```

## Error Handling

If HOOK_OPENSEARCH_HOST is not set, the script returns:
```json
{
  "status": "error",
  "message": "HOOK_OPENSEARCH_HOST not configured"
}
```

Report this to the coordinator so they know log queries are unavailable.

## Container Tools

**Custom image (hook-openclaw):** `curl`, `python3`, `jq`
**Base image (openclaw):** `curl`, `python3` only

All queries must use `exec` tool with the query-logs.py script.
