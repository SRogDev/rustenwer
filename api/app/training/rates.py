"""Provider rate table: USD per wall-clock hour (plan §45).

DO GPU prices are the on-demand list prices from
https://docs.digitalocean.com/products/droplets/details/pricing/
(checked 2026-09-26). They drift — treat as indicative config, not a quote.
`local-cpu` is a nominal rate so local experiments still produce cost
accounting; override via `LOCAL_RATE_USD_PER_HOUR`.
"""

from __future__ import annotations

import os

# provider key -> USD/hour. Keys double as ComputeProvider names where the
# provider is a single machine class; DO GPU flavors are separate keys.
PROVIDER_RATES_USD_PER_HOUR: dict[str, float] = {
    # Nominal local rate: real electricity-class cost of a dev CPU.
    "local-cpu": float(os.environ.get("LOCAL_RATE_USD_PER_HOUR", "0.02")),
    # DigitalOcean on-demand GPU droplets (indicative, 2026-09-26).
    "digitalocean/gpu-rtx4000x1": 0.76,
    "digitalocean/gpu-l40sx1-48gb": 1.57,
    "digitalocean/gpu-rtx6000x1": 1.57,
    "digitalocean/gpu-mi300xx1": 2.59,
    "digitalocean/gpu-mi325xx1": 3.80,
    "digitalocean/gpu-h100x1-80gb": 4.41,
    "digitalocean/gpu-h200x1": 4.47,
    "digitalocean/gpu-h100x8-640gb": 35.28,
}

#: DO API size slugs for the GPU flavors above (verify against the live
#: catalog — slugs are stable but DO does add flavors).
DO_GPU_SIZE_SLUGS: dict[str, str] = {
    "digitalocean/gpu-rtx4000x1": "gpu-rtx4000x1-20gb",
    "digitalocean/gpu-l40sx1-48gb": "gpu-l40sx1-48gb",
    "digitalocean/gpu-rtx6000x1": "gpu-rtx6000x1-48gb",
    "digitalocean/gpu-mi300xx1": "gpu-mi300xx1-192gb",
    "digitalocean/gpu-mi325xx1": "gpu-mi325xx1-256gb",
    "digitalocean/gpu-h100x1-80gb": "gpu-h100x1-80gb",
    "digitalocean/gpu-h200x1": "gpu-h200x1-141gb",
    "digitalocean/gpu-h100x8-640gb": "gpu-h100x8-640gb",
}

DEFAULT_LOCAL_PROVIDER = "local-cpu"


def rate_for(provider_key: str) -> float:
    """USD/hour for a provider key; 0.0 for unknown keys (never crash billing)."""
    return PROVIDER_RATES_USD_PER_HOUR.get(provider_key, 0.0)
