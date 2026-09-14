import hashlib
import json
import unittest
from dataclasses import asdict
from flyhigh import engine
from flyhigh.data import synthetic


class ReplayTests(unittest.TestCase):
    def test_indexer_snapshot_blocks_without_inventing_seeds(self):
        from flyhigh import wallet_replay
        snapshot = {'payload': {'fills': [{'usd': 100, 'amount': 2}],
                                'wallets': [], 'warnings': ['unverified']}}
        report = {'bars': synthetic(count=80),
                  'mode': 'historical_prices_assumed_liquidity',
                  'execution': 'simulated', 'source': {'symbol': 'COPY'},
                  'methodology': {'max_gap_seconds': 300}}
        result = wallet_replay.build_replay(snapshot, report)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['seed_count'], 0)
        self.assertIsNone(result['replay'])
        self.assertIn('quote', ' '.join(result['blocked_reasons']))


    def test_replay_admits_supported_seed_but_blocks_future_evidence(self):
        from flyhigh import wallet_replay
        from tests.test_wallet_rules import fill
        bars = synthetic(count=80)
        snapshot = {'payload': {'fills': [], 'wallets': []}}
        report = {'bars': bars, 'mode': 'historical_prices_assumed_liquidity',
                  'execution': 'simulated', 'source': {'symbol': 'COPY'},
                  'methodology': {'max_gap_seconds': 180, 'historical_liquidity': False,
                                  'assumed_execution_liquidity_usd': 10000}}
        # Preserve provenance, not the original evolution's run parameters.
        rows = [fill(str(i), int(bars[i]['timestamp']), cash_before=1000) for i in range(3)]
        result = wallet_replay.build_replay(snapshot, report, [rows])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['seed_count'], 1)
        self.assertEqual(result['replay']['mode'], report['mode'])
        self.assertIs(result['replay']['methodology']['historical_liquidity'], False)
        self.assertEqual(result['replay']['methodology']['assumed_execution_liquidity_usd'], 10000)
        self.assertEqual(result['replay']['holdout_evaluations'], 1)
        origin = result['replay']['events'][0]['seed_origin']['provenance']
        self.assertEqual(origin['mapped_genes']['allocation']['sample_count'], 3)
        rows[-1]['timestamp'] = int(bars[-1]['timestamp'])
        future = wallet_replay.build_replay(snapshot, report, [rows])
        self.assertEqual(future['status'], 'blocked')
        self.assertIsNone(future['replay'])


class SeedTests(unittest.TestCase):
    def test_opt_in_seeds_preserve_default_report_exactly(self):
        bars = synthetic(count=80)
        default = engine.evolve(bars, population=6, generations=2)
        self.assertEqual(hashlib.sha256(json.dumps(default, sort_keys=True).encode()).hexdigest(),
                         '00b254a8d61a38ab840ca98a8a8cdf2cda73cfc24d4121c1884e7add83fe6a99')
        self.assertEqual(default, engine.evolve(bars, population=6, generations=2, seed_genomes=[]))
        self.assertEqual(default, engine.evolve(bars, population=6, generations=2, seed_genomes=None))

    def test_seed_birth_metadata_determinism_and_holdout_isolation(self):
        bars = synthetic(count=80)
        provenance = {'kind': 'wallet_observations', 'wallet': 'test-fixture',
                      'observed_until': int(bars[55]['timestamp']),
                      'mapped_genes': {'allocation': {'evidence_urls': ['https://example.org/test-receipt']}}}
        source = engine.SeedGenome(engine.Genome(allocation=.3), provenance)
        kwargs = dict(population=6, generations=3, seed_genomes=[source, engine.Genome()])
        run = engine.evolve(bars, **kwargs)
        first, second = run['generations'][0]['flies'][:2]
        self.assertEqual(first['genome'], asdict(source.genome))
        self.assertEqual(first['seed_origin'], {'index': 0, 'provenance': provenance})
        self.assertEqual(first['parents'], [])
        self.assertEqual(first['mutations'], [])
        self.assertEqual(second['seed_origin'], {'index': 1, 'provenance': {'kind': 'supplied_genome'}})
        self.assertEqual(run['events'][0]['seed_origin'], first['seed_origin'])
        self.assertNotIn('seed_origin', run['generations'][0]['flies'][2])
        self.assertEqual(run, engine.evolve(bars, **kwargs))
        changed = [dict(b) for b in bars]
        for b in changed[56:]: b['price'] *= 10
        other = engine.evolve(changed, **kwargs)
        self.assertEqual(run['generations'], other['generations'])
        self.assertEqual(run['champion'], other['champion'])
        self.assertEqual(run['holdout_evaluations'], 1)
        for event in run['events']:
            payload = {k: v for k, v in event.items() if k != 'hash'}
            self.assertEqual(event['hash'], hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
        provenance['mapped_genes'].clear()
        self.assertTrue(first['seed_origin']['provenance']['mapped_genes'])
        # Descendants carry parent IDs/mutations, not an invented observed origin.
        for generation in run['generations'][1:]:
            for fly in generation['flies']:
                if fly['parents']:
                    self.assertNotIn('seed_origin', fly)

    def test_invalid_seeds_and_future_wallet_evidence_rejected(self):
        bars = synthetic(count=80)
        for seeds in ([{}], 'bad', [engine.Genome()] * 7):
            with self.assertRaises(ValueError):
                engine.evolve(bars, population=6, generations=1, seed_genomes=seeds)
        for provenance in ({'kind': 'wallet_observations'},
                           {'kind': 'wallet_observations', 'observed_until': int(bars[56]['timestamp'])},
                           {'kind': 'wallet_observations', 'observed_until': True},
                           {'kind': 'custom', 'x': float('nan')}, {'kind': 'custom', 'x': object()}):
            with self.assertRaises(ValueError):
                engine.evolve(bars, population=6, generations=1,
                              seed_genomes=[engine.SeedGenome(engine.Genome(), provenance)])
