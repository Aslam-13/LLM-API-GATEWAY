from __future__ import annotations

from prometheus_client import Counter, Histogram

requests_total = Counter(
    "gateway_requests_total",
    "Total gateway requests",
    ["endpoint", "status", "provider", "cache_hit"],
)
request_duration_seconds = Histogram(
    "gateway_request_duration_seconds",
    "Gateway request duration seconds",
    ["endpoint"],
)
tokens_total = Counter(
    "gateway_tokens_total",
    "Tokens consumed",
    ["provider", "kind"],
)
cost_usd_total = Counter(
    "gateway_cost_usd_total",
    "Estimated USD cost",
    ["provider", "api_key_prefix"],
)
provider_errors_total = Counter(
    "gateway_provider_errors_total",
    "Provider errors",
    ["provider", "error_type"],
)
rate_limit_rejections_total = Counter(
    "gateway_rate_limit_rejections_total",
    "Rate limit rejections",
    ["api_key_prefix"],
)
cache_exact_hits_total = Counter("gateway_cache_exact_hits_total", "Exact cache hits")
cache_exact_misses_total = Counter("gateway_cache_exact_misses_total", "Exact cache misses")
cache_semantic_hits_total = Counter("gateway_cache_semantic_hits_total", "Semantic cache hits")
cache_semantic_misses_total = Counter("gateway_cache_semantic_misses_total", "Semantic cache misses")
