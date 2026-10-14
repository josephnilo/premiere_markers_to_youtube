import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'premiere_markers_to_youtube.py'


class MarkerTests(unittest.TestCase):
    def convert(self, rows):
        with tempfile.TemporaryDirectory(prefix='markers-ci-') as directory:
            root = Path(directory); source = root / 'synthetic.tsv'
            with source.open('w', encoding='utf-16', newline='') as stream:
                writer = csv.writer(stream, delimiter='\t')
                writer.writerow(['A', 'B', 'C', 'In', 'Out', 'Duration', 'Name'])
                writer.writerows(rows)
            result = subprocess.run([sys.executable, str(SCRIPT), str(source)], cwd=root,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = source.with_name(source.name + '_markers.txt').read_text()
            # The existing CLI consumes the input; only a disposable fixture is used.
            self.assertFalse(source.exists())
            self.assertFalse((root / 'temp_file.txt').exists())
            self.assertFalse((root / 'new_file.txt').exists())
            return output

    def test_timecodes_and_unicode_titles(self):
        rows = [['a', 'b', 'c', '00:00:00:00', '', '', 'Introduction'],
                ['a', 'b', 'c', '00:01:23:12', '', '', 'Café tour']]
        self.assertEqual(self.convert(rows), '00:00 Introduction\n01:23 Café tour\n')

    def test_header_only(self):
        self.assertEqual(self.convert([]), '')

    def test_missing_input_fails_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(SCRIPT), 'missing.tsv'], cwd=directory,
                                    capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(directory).iterdir()), [])
