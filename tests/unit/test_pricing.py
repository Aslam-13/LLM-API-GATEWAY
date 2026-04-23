from app.providers.pricing import PROVIDER_PRICING, estimate_cost


def test_known_model_uses_table_rates():
    p, c = PROVIDER_PRICING["openai:gpt-4o-mini"]
    assert estimate_cost("openai", "gpt-4o-mini", 1000, 1000) == p + c


def test_unknown_model_costs_zero():
    assert estimate_cost("who", "what", 1_000_000, 1_000_000) == 0.0


def test_zero_tokens_costs_zero():
    assert estimate_cost("openai", "gpt-4o", 0, 0) == 0.0
