from __future__ import annotations


def formula_prob(inputs: list[dict]) -> float:
    total_weight = sum(i["weight"] for i in inputs)
    if total_weight == 0:
        return 0.5
    return sum(i["probability"] * i["weight"] for i in inputs) / total_weight


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def final_prob(formula: float, delta: float) -> float:
    delta_clamped = clamp(delta, -0.15, 0.15)
    return clamp(formula + delta_clamped)


def confidence_band(probability: float, layer: int) -> tuple[float, float]:
    sigma = 0.05 * (1.2 ** (layer - 1))
    low = clamp(probability - 1.96 * sigma)
    high = clamp(probability + 1.96 * sigma)
    return (round(low, 3), round(high, 3))
