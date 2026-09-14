"""Report export must not replace an existing run on conflicting seed."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

class ReportIntegrityTests(unittest.TestCase):
    def test_conflicting_export_preserves_report_and_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'report.json'
            command = [sys.executable, '-m', 'flyhigh.server', '--no-server', '--report', str(path)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            previous = path.read_bytes()
            ledger = path.with_suffix('.events.jsonl').read_bytes()
            second = subprocess.run(command + ['--seed', '19'], capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(path.with_suffix('.events.jsonl').read_bytes(), ledger)
