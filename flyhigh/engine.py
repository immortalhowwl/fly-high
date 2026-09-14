"""Causal single-pair evolutionary paper execution. No wallet connectivity."""
from dataclasses import dataclass, asdict
import hashlib
import json
import random
from .data import validate

BOUNDS = {'lookback': (2, 20), 'momentum': (-0.02, 0.08), 'min_liquidity': (100, 50000),
          'stop': (0.01, 0.12), 'take': (0.015, 0.25), 'hold': (3, 50), 'allocation': (0.05, 0.5)}

@dataclass(frozen=True)
class Genome:
    lookback: int = 5
    momentum: float = 0.01
    min_liquidity: float = 1000
    stop: float = 0.04
    take: float = 0.08
    hold: int = 20
    allocation: float = 0.2

    def __post_init__(self):
        for key, (low, high) in BOUNDS.items():
            value = getattr(self, key)
            if not low <= value <= high or (key in ('lookback','hold') and type(value) is not int):
                raise ValueError('out of bounds genome: ' + key)


def simulate(genome, bars, fee=0.003, slippage=0.002, max_gap=180, policy='genome', seed=1):
    bars = validate(bars)
    if not 0 <= fee < 0.1 or not 0 <= slippage < 0.1 or max_gap <= 0:
        raise ValueError('invalid execution configuration')
    rng = random.Random(seed)
    cash, qty, entry, entered = 1000.0, 0.0, 0.0, 0
    peak, drawdown, fees = 1000.0, 0.0, 0.0
    pending = None
    trades, decisions, curve = [], [], []
    for i, b in enumerate(bars):
        p, liquidity, timestamp = b['price'], b['liquidity'], b['timestamp']
        action, reason = 'watch', 'insufficient history'
        if pending:
            side, signal_ts, why = pending
            if timestamp - signal_ts > max_gap:
                action, reason = 'cancel', 'missing observation gap; no interpolated fill'
            else:
                fill = p * (1 + slippage if side == 'buy' else 1 - slippage)
                if side == 'buy':
                    notional = min(cash * genome.allocation / (1+fee), liquidity * 0.01)
                    if liquidity < genome.min_liquidity:
                        notional = 0
                    if notional > 0:
                        qty = notional / fill
                        cash -= notional * (1+fee)
                        entry, entered = fill, i
                else:
                    # Partial exits obey the same liquidity cap. Remaining inventory stays at risk.
                    sold = min(qty, liquidity * 0.01 / fill)
                    notional = sold * fill
                    qty -= sold
                    if qty < 1e-12: qty = 0.0
                    cash += notional * (1-fee)
                if notional > 0:
                    fees += notional * fee
                    trades.append({'side':side,'timestamp':timestamp,'signal_timestamp':signal_ts,
                                   'price':fill,'notional':notional,'fee':notional*fee,
                                   'liquidity':liquidity,'reason':why})
                    action, reason = side, why
                else:
                    action, reason = 'cancel', 'liquidity below threshold'
            pending = None
        if qty:
            move = p / entry - 1
            exit_reason = ('stop loss' if move <= -genome.stop else 'take profit' if move >= genome.take
                           else 'max holding bars' if i-entered >= genome.hold else None)
            if exit_reason:
                pending = ('sell', timestamp, exit_reason)
        elif i >= genome.lookback:
            momentum = p / bars[i-genome.lookback]['price'] - 1
            # Do not trade across holes in the signal window.
            contiguous = all(bars[k]['timestamp']-bars[k-1]['timestamp'] <= max_gap
                             for k in range(i-genome.lookback+1, i+1))
            trigger = rng.random() < 0.12 if policy == 'random' else momentum >= genome.momentum
            if contiguous and trigger and liquidity >= genome.min_liquidity:
                pending = ('buy', timestamp, f'momentum {momentum:.5f}; liquidity {liquidity:.2f}')
            if action == 'watch': reason = f'momentum {momentum:.5f}; ' + ('entry queued' if pending else 'entry conditions not met')
        # Fitness credits only inventory inside this observation's modeled exit cap.
        # Any excess remains held, but gets zero credit until depth supports it.
        mark_to_market_equity = cash + qty*p*(1-slippage)*(1-fee)
        equity = cash + min(qty*p*(1-slippage),liquidity*0.01)*(1-fee)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak-equity)/peak)
        curve.append({'timestamp':timestamp,'equity':equity,'holding':qty > 0})
        decisions.append({'timestamp':timestamp,'action':action,'reason':reason,
                          'pending': pending[0] if pending else None,'equity':equity})
    ret = equity/1000-1
    return {'equity':equity,'return':ret,'drawdown':drawdown,'fees':fees,'trades':trades,
            'decisions':decisions,'curve':curve,'open_quantity':qty,'cash':cash,
            'fitness':ret-1.5*drawdown-0.0001*len(trades),
            'mark_to_market_equity':mark_to_market_equity,
            'mark_note':'Cash plus inventory within the modeled one-observation exit cap, net of costs; excess inventory valued at zero for fitness. Not an executed closing trade.'}


def evolve(bars, seed=17, population=24, generations=6, max_gap=180):
    bars = validate(bars)
    if len(bars) < 80 or not 6 <= population <= 64 or not 1 <= generations <= 20:
        raise ValueError('need >=80 observations, population 6..64, generations 1..20')
    split = int(len(bars)*0.7)
    train, holdout = bars[:split], bars[split:]
    rng = random.Random(seed)
    events, history = [], []
    serial = 0
    def event(kind, generation, **fields):
        obj = {'sequence':len(events), 'kind':kind, 'generation':generation,
               'previous_hash':events[-1]['hash'] if events else '0'*64, **fields}
        obj['hash'] = hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()
        events.append(obj)
    def random_genome():
        return {k: rng.randint(lo, hi) if k in ('lookback','hold') else rng.uniform(lo,hi)
                for k,(lo,hi) in BOUNDS.items()}
    def born(g, generation, parents=None, mutations=None):
        nonlocal serial
        serial += 1
        fly = {'id':f'F{serial:04d}', 'genome':g, 'parents':parents or [], 'mutations':mutations or [],
               'born':generation}
        event('birth', generation, fly=fly['id'], parents=fly['parents'], mutations=fly['mutations'])
        return fly
    flies = [born(random_genome(), 0) for _ in range(population)]
    for generation in range(generations):
        evaluated = []
        for fly in flies:
            result = simulate(Genome(**fly['genome']), train, max_gap=max_gap)
            evaluated.append({**fly, 'result':result})
        ranked = sorted(evaluated, key=lambda f: (-f['result']['fitness'], f['id']))
        history.append({'index':generation, 'flies':evaluated, 'best':ranked[0]['id'],
                        'diversity':len({json.dumps(f['genome'],sort_keys=True) for f in flies})})
        event('generation', generation, best=ranked[0]['id'], fitness=ranked[0]['result']['fitness'])
        if generation == generations-1:
            break
        # Keep elites AND the farthest normalized genome for exploration.
        survivors = ranked[:max(2,population//4)]
        def distance(f):
            return min(sum(((f['genome'][k]-s['genome'][k])/(hi-lo))**2
                           for k,(lo,hi) in BOUNDS.items()) for s in survivors)
        diverse = max(ranked[len(survivors):], key=distance)
        survivors.append(diverse)
        ids = {f['id'] for f in survivors}
        for fly in evaluated:
            if fly['id'] not in ids: event('extinction', generation, fly=fly['id'], fitness=fly['result']['fitness'])
        flies = [{k:v for k,v in f.items() if k != 'result'} for f in survivors]
        while len(flies) < population-1:
            parent = rng.choice(survivors)
            g = dict(parent['genome'])
            changes = []
            for key in rng.sample(list(BOUNDS), rng.randint(1,3)):
                lo,hi = BOUNDS[key]
                before = g[key]
                after = max(lo,min(hi,before+rng.gauss(0,(hi-lo)*0.18)))
                if key in ('lookback','hold'): after = int(round(after))
                if after == before: after = lo if before != lo else hi
                g[key] = after
                changes.append({'gene':key,'before':before,'after':after})
            flies.append(born(g,generation+1,[parent['id']],changes))
        flies.append(born(random_genome(),generation+1))  # immigrant preserves exploration
    champion = {k:v for k,v in ranked[0].items() if k != 'result'}
    event('freeze', generations-1, fly=champion['id'], train_end=train[-1]['timestamp'])
    evaluation = simulate(Genome(**champion['genome']), holdout, max_gap=max_gap)
    baselines = {name:simulate(Genome(), holdout, policy=name, seed=seed+10000, max_gap=max_gap)
                 for name in ('random','momentum')}
    event('holdout', generations-1, fly=champion['id'], equity=evaluation['equity'])
    return {'schema_version':1,'seed':seed,'mode':'synthetic','execution':'simulated',
            'bars':bars,'split':split,'generations':history,'champion':champion,
            'holdout':evaluation,'holdout_evaluations':1,'baselines':baselines,'events':events,
            'methodology':{'initial_cash':1000,'fee':0.003,'slippage':0.002,'liquidity_cap':0.01,
                           'max_gap_seconds':max_gap,'fitness':'return - 1.5 * max_drawdown - 0.0001 * fills',
                           'holdout':'last 30%; cold-start, frozen champion, evaluated once per run'}}
