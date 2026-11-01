import copy
import unittest
from test_selection import candidate, CONFIG
from comics_qa.benchmark1000.io import read
from comics_qa.benchmark1000.selection import select, violations


class SolverTests(unittest.TestCase):
    def setUp(self):
        try:
            from comics_qa.benchmark1000.solver import select_cp
            import ortools
        except ImportError:
            self.skipTest('Optional OR-Tools missing')
        self.select_cp = select_cp; self.p = read(CONFIG)

    def test_solver_matches_independent_reference_on_sparse_case(self):
        items = [candidate(i, fmt='character', identity='a') for i in range(5)] + [candidate(9, 3)]
        expected, _ = select(items, self.p, pilot=True)
        actual, report = self.select_cp(items, self.p, pilot=True)
        self.assertEqual(report['status'], 'optimal')
        self.assertEqual(len(expected), len(actual))
        self.assertFalse(violations(actual, self.p))

    def test_solver_counts_ratio_repairs(self):
        self.p['minimum_denominator'] = 2; self.p['modal_count_share'] = .5
        items = [candidate(i, 2 if i < 2 else 3) for i in range(4)]
        actual, report = self.select_cp(items, self.p, pilot=True)
        self.assertEqual(len(actual), 4)

    def test_solver_final_proves_small_pool_infeasible(self):
        actual, report = self.select_cp([candidate(1)], self.p)
        self.assertEqual(report['status'], 'infeasible')
        self.assertEqual(actual, [])
