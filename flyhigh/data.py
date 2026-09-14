"""Explicit, strictly chronological observed bars. Never interpolate missing observations."""
import csv
import json
import math
import random
from pathlib import Path


def validate(rows):
    result = []
    for row in rows:
        bar = {key: float(row[key]) for key in ('timestamp', 'price', 'liquidity')}
        if any(not math.isfinite(v) or v <= 0 for v in bar.values()):
            raise ValueError('timestamp, price and liquidity must be finite and positive')
        if result and bar['timestamp'] <= result[-1]['timestamp']:
            raise ValueError('timestamps must be unique and strictly increasing; sort/deduplicate explicitly')
        result.append(bar)
    if not result:
        raise ValueError('empty series')
    return result


def load(path):
    with Path(path).open() as file:
        rows = list(csv.DictReader(file)) if str(path).endswith('.csv') else json.load(file)
    return validate(rows)


def synthetic(seed=17, count=480):
    """Offline test fixture, not reconstructed market history."""
    rng = random.Random(seed)
    price = 0.005
    rows = []
    for i in range(count):
        price *= math.exp(0.002 * math.sin(i / 27) + rng.gauss(0, 0.018))
        rows.append({'timestamp': 1700000000 + i * 60, 'price': price,
                     'liquidity': 30000 + 12000 * math.sin(i / 37) + rng.uniform(0, 4000)})
    return validate(rows)
