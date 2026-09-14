# FLY HIGH — methodology and limitations

## Three separate data modes

1. **Synthetic:** deterministic seeded offline fixture for UI and regression tests. Not a market reconstruction.
2. **Observed snapshots:** single-pair prospective price/liquidity observations collected from a public provider. Observation time is collection time, not a guaranteed exchange update time.
3. **Historical prices / assumed liquidity:** genuine completed pool OHLCV closes, with an explicitly chosen constant execution-liquidity scenario. Reports declare `historical_liquidity: false`. Current liquidity snapshots are retained only as source context and never consulted by the adapter. No assumption is supplied automatically; without `--assumed-liquidity` the historical CLI refuses to run.

## Causality and missing intervals

Canonical source timestamps denote interval starts. The historical adapter adds `interval_seconds` so a close is visible only at interval completion. A signal on observation t can fill only on a later observed close. This is next-close simulation, not a claim that the close was a tradable quote. Intrabar highs/lows do not trigger stops; no intrabar path is invented.

Every series is positive, finite, strictly chronological and unique. No sorting, deduplication or interpolation occurs silently inside the engine. Historical gaps greater than 300 seconds cancel pending fills and invalidate entry lookback windows. The ordinary snapshot/synthetic engine defaults to a 180-second threshold. A holding-period gene counts observed bars, not elapsed minutes; missing bars can extend wall-clock holding time. Existing positions remain exposed across gaps. Exits triggered after a gap can queue for a subsequent valid observation.

## Paper execution

- Initial cash: USD 1,000 per strategy; long-only, one position at a time.
- Fee: 0.3% of each executed notional; adverse slippage: 0.2% on each side.
- Buy size: minimum of fee-adjusted allocation budget and 1% of execution-liquidity input; entry requires the genome's liquidity threshold.
- Exits also obey the 1% cap and may be partial. Residual inventory stays at risk.
- The historical demonstration fixes execution liquidity to an arbitrary USD 10,000. This is neither verified historical liquidity nor inferred from candle volume. The resulting USD execution capacity can exceed actual market capacity; these numbers are a sensitivity scenario, not a realistic fill estimate.
- Fitness equity is cash plus the inventory value within the current observation's modeled 1% exit cap, net of fee/slippage. Excess inventory remains held but receives zero fitness credit until depth supports it. A separate `mark_to_market_equity` reports the full marked value. Neither valuation is an executed sale or a prediction of multi-bar liquidation; no forced end fill is created.
- No gas, MEV, failed transactions, latency, spread history, price impact curve, routing, token transfer taxes or malicious-token behavior is modelled.

## Evolution and evaluation

The first 70% of observations train the population; the last 30% form a cold-start holdout. Split is by observation count, not wall time. Defaults: seed 17, population 24, six generations. Genome bounds are enforced by `Genome`; integer lookback and holding-period fields remain integers.

Fitness is `return - 1.5 * maximum_drawdown - 0.0001 * number_of_fills`. Ranking is deterministic with stable identity tie-breaking. Elites survive alongside a genome distant from the elites; offspring mutate one to three genes, and a random immigrant enters each non-final generation. Birth, extinction, generation, freeze and holdout events form an in-memory SHA-256 hash chain. This is tamper-evident linkage, not an externally anchored immutable ledger.

The training winner is frozen before one holdout evaluation per run. Random-entry and fixed-momentum baselines use the same execution assumptions and cold-start holdout, but different entry rules. Seeded replay is reproducible. Re-running many seeds or choosing assumptions after inspecting results still introduces researcher selection bias; a single per-run holdout does not remove that.

## Dataset scope and selection bias

The checked-in source contains 200 COPY, 102 HOPOUT and 49 GPTHEIST completed five-minute candles. Missing intervals are not zeros. The selected pool for each token had the highest *current* reported liquidity at collection time; this introduces retrospective selection bias. Token names are not identity proof: source receipts include chain and base-contract checks. Data describes these pools only, not all markets or a survivorship-free Robinhood token universe.

GPTHEIST's 49 observations are below the engine's 80-observation minimum; evolution on that asset intentionally fails rather than padding history. The checked-in COPY champion made no holdout fills. Zero return here means inactivity, not proven risk control or profitable generalization. Short sparse histories, large price jumps and missing depth make alpha claims unjustified.

## Reproduction

Run the COPY command in the root README. Source JSON SHA-256 is embedded in the report; request-level hashes are in `examples/provenance.json`, and original bodies in `examples/raw/`. A replay needs no network. Re-fetching the same public endpoints may return changed, corrected or unavailable history. Provider data terms are separate from the software's MIT license.
