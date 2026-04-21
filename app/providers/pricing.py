from __future__ import annotations

# USD per 1K tokens: (prompt, completion). Figures are rough/public-list and
# should be kept updated. Unknown model → 0 cost (still tracked, just unpriced).
PROVIDER_PRICING: dict[str, tuple[float, float]] = {
    "openai:gpt-4o-mini": (0.00015, 0.0006),
    "openai:gpt-4o": (0.005, 0.015),
    "openai:gpt-3.5-turbo": (0.0005, 0.0015),
    "openai:text-embedding-3-small": (0.00002, 0.0),
    "gemini:gemini-1.5-flash": (0.000075, 0.0003),
    "gemini:gemini-1.5-pro": (0.00125, 0.005),
    "gemini:gemini-2.0-flash": (0.0001, 0.0004),
}


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = PROVIDER_PRICING.get(f"{provider}:{model}")
    if rates is None:
        return 0.0
    p_rate, c_rate = rates
    return (prompt_tokens / 1000.0) * p_rate + (completion_tokens / 1000.0) * c_rate
