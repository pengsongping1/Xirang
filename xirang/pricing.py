"""Pricing table for major Claude/OpenAI/DeepSeek models.

Prices are per 1M tokens (input, output). Returns 0.0 for unknown models
rather than guessing — honest > wrong.
"""
from __future__ import annotations

# (input $/1M, output $/1M)
_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-opus-4-0": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-0": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    # OpenAI (GPT family)
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "o1": (15.0, 60.0),
    "o1-mini": (3.0, 12.0),
    "o3-mini": (1.10, 4.40),
    # DeepSeek
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}


def lookup(model: str) -> tuple[float, float]:
    """Return (in_price, out_price) per 1M tokens. Strips date/suffix decorators."""
    key = model.lower()
    # Exact match
    if key in _PRICES:
        return _PRICES[key]
    # Strip common suffixes like -20260401 or [1m]
    for suffix_marker in ("-2026", "-2025", "-2024", "["):
        if suffix_marker in key:
            key = key.split(suffix_marker)[0].rstrip("-")
            if key in _PRICES:
                return _PRICES[key]
    # Prefix match for new variants (e.g. "claude-opus-4-7-custom")
    for k, v in _PRICES.items():
        if key.startswith(k):
            return v
    return (0.0, 0.0)


def compute_cost(usage: dict, model: str) -> float:
    """USD cost from a usage dict with input/output/cache_read keys.

    Cache reads are billed at ~0.1x input rate (Anthropic convention).
    """
    in_price, out_price = lookup(model)
    if in_price == 0 and out_price == 0:
        return 0.0
    inp = usage.get("input", 0)
    out = usage.get("output", 0)
    cache_read = usage.get("cache_read", 0)
    cache_create = usage.get("cache_create", 0)
    cost = (
        inp * in_price / 1_000_000
        + out * out_price / 1_000_000
        + cache_read * in_price * 0.1 / 1_000_000
        + cache_create * in_price * 1.25 / 1_000_000
    )
    return cost


def format_cost(cost: float) -> str:
    if cost == 0:
        return "$0 (unknown model)"
    if cost < 0.001:
        return f"${cost * 1000:.3f}m"  # milli-dollars
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.3f}"
