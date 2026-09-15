import unittest
from flyhigh.wallet_activity import activity_summary

class ActivityTests(unittest.TestCase):
    def row(self,side='buy',ts=100,kind='trade',token='0x'+'1'*40):
        return dict(side=side,ts=ts,kind=kind,mint=token,source='rpc',usd=10,sym='TEST')
    def test_excludes_transfers_and_missing_classification(self):
        rows=[self.row(),self.row(ts=110),self.row(kind='direct'),self.row(kind='dust')]
        r=activity_summary({'fills':rows})
        self.assertEqual(r['counts']['eligible'],2)
        self.assertIn('TEST has 2 buys totaling $20.00',r['takeaway'])
        self.assertNotIn('sales elsewhere',r['takeaway'])
    def test_partial_sequence_is_not_holding_or_profit(self):
        r=activity_summary({'fills':[self.row(),self.row(side='sell',ts=86500)]})
        self.assertIn('1.0 days later',r['takeaway'])
        self.assertIn('not a verified holding period or profit',r['takeaway'])
        self.assertTrue(r['takeaway'].endswith('Not Financial Advice.'))
    def test_no_unknown_or_other_chain_address_admission(self):
        self.assertIsNone(activity_summary({'fills':[self.row(kind=None),self.row(token='SolanaAddress')]}))
    def test_equal_rows_not_deduplicated_without_event_identity(self):
        self.assertEqual(activity_summary({'fills':[self.row(),self.row()]})['counts']['eligible'],2)
