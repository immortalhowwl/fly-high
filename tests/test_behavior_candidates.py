import copy
import json
import unittest
from flyhigh.behavior_candidates import build_behavior_candidates, seed_candidates
from flyhigh.engine import BOUNDS, Genome, evolve


def snapshot():
    return {'fills': [dict(id=i, ts=100+i*10, wallet='wallet', token='token',
                           chain_id=4663, source='indexer', tx='same-tx',
                           side='buy', usd=10*i) for i in range(1, 5)],
            'coverage': {'endpoints': {'tape': {'url': 'https://example.test/tape',
                         'fetched_at': '1970-01-01T00:03:20Z', 'stale': False}}}}


class BehaviorCandidatesTest(unittest.TestCase):
    def test_features_and_mapping(self):
        report = build_behavior_candidates(snapshot())
        w = report['wallets'][0]
        self.assertEqual(w['buy_count'], 4)
        self.assertEqual(w['sell_count'], 0)
        self.assertEqual(w['buy_token_concentration']['hhi'], 1)
        self.assertEqual(w['cadence']['median'], 10)
        self.assertEqual(w['buy_order_size_usd']['median'], 25)
        self.assertEqual(len(report['candidates']), 3)
        c = report['candidates'][1]
        self.assertEqual(c['genome']['min_liquidity'], 2500)
        self.assertEqual(c['provenance']['default_genes']['allocation'], Genome().allocation)
        self.assertEqual(c['provenance']['mapped_genes']['min_liquidity']['classification'], 'HYPOTHESIZED_PARAMETER')
        self.assertEqual(w['event_ids'], [1, 2, 3, 4])

    def test_missing_sizes_features_still_exist(self):
        s = snapshot()
        for r in s['fills'][:3]:
            r['usd'] = float('nan')
        report = build_behavior_candidates(s)
        self.assertEqual(report['status'], 'features_only')
        self.assertEqual(report['wallets'][0]['order_size_usd']['missing_or_invalid_count'], 3)
        json.dumps(report, allow_nan=False)

    def test_deterministic_permutation_and_no_mutation(self):
        s = snapshot()
        before = copy.deepcopy(s)
        a = build_behavior_candidates(s)
        self.assertEqual(s, before)
        s['fills'].reverse()
        self.assertEqual(a, build_behavior_candidates(s))

    def test_event_not_transaction_deduplication(self):
        s = snapshot()
        s['fills'].append(dict(s['fills'][0]))
        r = build_behavior_candidates(s)
        self.assertEqual(r['stats']['admitted_fills'], 4)
        self.assertEqual(r['stats']['duplicates'], 1)
        s['fills'][-1]['usd'] = 999
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            build_behavior_candidates(s)

    def test_cutoff_and_capture_are_distinct(self):
        report = build_behavior_candidates(snapshot(), evidence_cutoff=130)
        self.assertEqual(report['stats']['after_cutoff'], 1)
        self.assertTrue(report['candidates'])
        self.assertEqual(report['candidates'][0]['provenance']['observed_until'], 130)
        for start in (130, 199, 200):
            self.assertFalse(seed_candidates(report, token='token', chain_id=4663, evaluation_start=start))
        self.assertTrue(seed_candidates(report, token='token', chain_id=4663, evaluation_start=201))
        self.assertFalse(seed_candidates(report, token='COPY', chain_id=4663, evaluation_start=201))
        self.assertFalse(seed_candidates(report, token='token', chain_id=1, evaluation_start=201))

    def test_missing_capture_cannot_export(self):
        s = snapshot()
        s['coverage'] = {}
        r = build_behavior_candidates(s)
        self.assertTrue(r['candidates'])
        self.assertFalse(seed_candidates(r, token='token', chain_id=4663, evaluation_start=1000))

    def test_saturation_dedup_and_bounds(self):
        s = snapshot()
        for row in s['fills']:
            row['usd'] = 10000
        r = build_behavior_candidates(s)
        self.assertEqual(len(r['candidates']), 1)
        self.assertTrue(r['candidates'][0]['provenance']['mapped_genes']['min_liquidity']['clipped'])
        for gene, value in r['candidates'][0]['genome'].items():
            self.assertTrue(BOUNDS[gene][0] <= value <= BOUNDS[gene][1])

    def test_empty_sell_only_and_concentration(self):
        s = snapshot()
        s['fills'][0]['token'] = 'other'
        s['fills'][1]['side'] = 'sell'
        r = build_behavior_candidates(s)
        w = r['wallets'][0]
        self.assertEqual(w['sell_count'], 1)
        self.assertAlmostEqual(w['buy_token_concentration']['shares']['other'], 1/3)
        self.assertFalse(r['candidates'])
        s['fills'] = []
        self.assertEqual(build_behavior_candidates(s)['wallets'], [])

    def test_actual_engine_seed_contract_synthetic_test_only(self):
        r = build_behavior_candidates(snapshot())
        seeds = seed_candidates(r, token='token', chain_id=4663, evaluation_start=201)
        bars = [dict(timestamp=201+i*60, price=1+i*.001, liquidity=10000) for i in range(100)]
        result = evolve(bars, population=6, generations=2, seed_genomes=seeds)
        origins = [e['seed_origin'] for e in result['events'] if e['kind'] == 'birth' and 'seed_origin' in e]
        self.assertEqual(len(origins), len(seeds))
        self.assertEqual(origins[0]['provenance']['wallet'], 'wallet')
        self.assertEqual(result['holdout_evaluations'], 1)


if __name__ == '__main__':
    unittest.main()
