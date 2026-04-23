# Tests

## Unit (no infra)
```
.venv/Scripts/python.exe -m pytest tests/unit -q
```

## Integration (requires Postgres + Redis up via docker-compose.dev.yml)
Uses the dev database; TRUNCATEs `usage_logs`, `jobs`, `cached_responses`, `semantic_cache_entries` between tests. `api_keys` is preserved; each test seeds a scoped key via the `test_key` fixture and deletes it on teardown.

```
.venv/Scripts/python.exe -m pytest tests/integration -q
```

Full run:
```
.venv/Scripts/python.exe -m pytest -q
```

## Load (post-deploy, not part of CI)

Runs against the deployed gateway. Requires `locust` (already in `requirements-dev.txt`).

```
export GATEWAY_API_KEY=sk-gw-live-...
export GATEWAY_ADMIN_KEY=sk-gw-live-...   # optional, for /admin/* mix

# interactive (web UI at http://localhost:8089)
locust -f tests/load/locustfile.py --host https://api.yourdomain.com

# headless 10-minute run
locust -f tests/load/locustfile.py --host https://api.yourdomain.com \
  --users 50 --spawn-rate 5 --run-time 10m --headless --csv results
```

Output CSVs (`results_stats.csv`, etc.) feed the "Results" section of the README in Phase 18.

The traffic mix (~60% chat, 20% sync embed, 10% batch embed, 10% admin) and prompt-pool sizing (~30% unseen prompts) are tuned to exercise exact + semantic cache hits.
