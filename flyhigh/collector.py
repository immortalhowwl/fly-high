"""Public snapshots only. Matching token names on another chain are rejected."""
import argparse
import json
import math
from pathlib import Path
import time
from urllib.request import Request, urlopen

URL = 'https://api.dexscreener.com/latest/dex/search?q=Robinhood'

def decode(doc, timestamp):
    rows, seen = [], set()
    for pair in doc.get('pairs') or []:
        try:
            if pair.get('chainId') != 'robinhood': continue
            address = pair['pairAddress']
            token = pair['baseToken']
            price, liquidity = float(pair['priceUsd']), float(pair['liquidity']['usd'])
            if not token['address'] or not address or address in seen: continue
            if not all(math.isfinite(v) and v > 0 for v in (price,liquidity,timestamp)): continue
            seen.add(address)
            rows.append({'timestamp':timestamp,'price':price,'liquidity':liquidity,'chain':'robinhood',
                         'pair_address':address,'token_address':token['address'],
                         'symbol':str(token.get('symbol','?'))[:40],
                         'quote':str(pair.get('quoteToken',{}).get('symbol','?'))[:40],
                         'source':URL,'identity':'provider-reported chain and base contract; not an authenticity endorsement'})
        except (KeyError,TypeError,ValueError):
            continue
    return rows


def collect(directory='data', fetch=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    observed = time.time()
    try:
        if fetch is None:
            with urlopen(Request(URL,headers={'User-Agent':'FlyHighResearch/1.0'}),timeout=20) as response:
                doc = json.load(response)
        else: doc = fetch(URL)
        rows = decode(doc,observed)
        status = {'status':'collecting' if rows else 'no_verified_pairs','observed_at':observed,
                  'source':URL,'verified_pairs':len(rows),'rows':rows,
                  'note':'Snapshots are not historical candles. Empty Robinhood results are not replaced by another network.'}
        with (directory/'snapshots.jsonl').open('a') as file:
            for row in rows: file.write(json.dumps(row,sort_keys=True)+'\n')
    except Exception as exc:
        status = {'status':'provider_error','observed_at':observed,'source':URL,'verified_pairs':0,
                  'rows':[],'error':f'{type(exc).__name__}: {exc}'}
    with (directory/'collector.jsonl').open('a') as file: file.write(json.dumps(status)+'\n')
    (directory/'latest.json').write_text(json.dumps(status,indent=2))
    return status


def export_pair(directory, address, destination):
    rows=[]
    for line in (Path(directory)/'snapshots.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['pair_address']==address: rows.append({k:row[k] for k in ('timestamp','price','liquidity')})
    from .data import validate
    rows=validate(rows)
    Path(destination).write_text(json.dumps(rows,indent=2))
    return len(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='data')
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--interval',type=float,default=60)
    parser.add_argument('--pair')
    parser.add_argument('--output',default='data/observations.json')
    args=parser.parse_args()
    if args.pair:
        print(json.dumps({'exported':export_pair(args.directory,args.pair,args.output),'path':args.output})); return
    if args.interval < 30: parser.error('minimum interval is 30 seconds')
    while True:
        print(json.dumps(collect(args.directory)),flush=True)
        if not args.watch: break
        time.sleep(args.interval)

if __name__=='__main__': main()
