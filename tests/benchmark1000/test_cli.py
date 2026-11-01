import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from comics_qa.benchmark1000.cli import main
from comics_qa.benchmark1000.io import publish
from test_foundation import fixture


class CliTests(unittest.TestCase):
    def test_import_verify_preflight_and_idempotent_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fixture(root / 'old')
            def run(args):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(args), 0)
                    return json.loads(output.getvalue())
            args = ['import', '--source', str(root / 'old'), '--out', str(root / 'new')]
            self.assertEqual(run(args)['candidates'], 1)
            self.assertEqual(run(args)['candidates'], 1)
            self.assertEqual(run(['verify-store', '--store', str(root / 'new')])['candidates'], 1)
            result = run(['preflight', '--store', str(root / 'new'), '--out', str(root / 'report.json')])
            self.assertEqual(result['pool']['proofs_archived'], 1)
            self.assertFalse(result['pool']['meaningful_depth_available'])

    def test_bad_command_input_has_actionable_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as exit:
                    main(['preflight', '--out', str(Path(temp) / 'report.json')])
            self.assertEqual(exit.exception.code, 2)
            self.assertIn('Supply --store', error.getvalue())

    def test_data_root_argument_does_not_block_separate_new_outputs(self):
        # The actual benchmark root is a scope, not an immutable input directory
        # as a whole; new outputs under its benchmark1000 namespace are allowed.
        with tempfile.TemporaryDirectory() as temp:
            bench = Path(temp); fixture(bench / 'items/gen2/v3')
            out = bench / 'items/benchmark1000/store'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['import', '--source', str(bench / 'items/gen2/v3'), '--out', str(out)]), 0)
            self.assertTrue((out / 'manifest.json').exists())

    def test_store_import_into_legacy_output_namespace_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bench = Path(temp); fixture(bench / 'items/gen2/v3')
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    main(['import', '--source', str(bench / 'items/gen2/v3'), '--out', str(bench / 'items/gen1/new')])
            self.assertEqual(result.exception.code, 2)
            self.assertFalse((bench / 'items/gen1/new').exists())
