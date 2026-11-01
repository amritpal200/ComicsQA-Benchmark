import unittest
from comics_qa.benchmark1000.long_relational import propose
from comics_qa.tasks.graph.crl.language import infer


class LongProposalTests(unittest.TestCase):
    def test_target_first_clues_are_spread_and_necessary_by_known_members(self):
        # Only T satisfies all; A/B/C each satisfy two. Exact graph proof is still needed.
        pages = ['p1', 'p4', 'p8']
        sets = [('p1', 'present', ['T', 'A', 'B']), ('p4', 'speaks_on', ['T', 'B', 'C']), ('p8', 'present', ['T', 'A', 'C'])]
        graph = {'page_ids': ['p' + str(i) for i in range(1, 9)],
                 'nodes': [{'id': c, 'type': 'Character', 'generic': False} for c in 'TABC'], 'facts': []}
        for pid, rel, chars in sets:
            graph['facts'].extend({'rel': rel, 'args': [cid, pid], 'answer_eligible': True, 'origin': 'H'} for cid in chars)
        qs = list(propose(graph, budget=10))
        self.assertEqual(len(qs), 1)
        q = qs[0]
        self.assertEqual(q.target_answer, 'T')
        self.assertEqual(len(q.clauses), 3)
        self.assertEqual(set(q.anchors), {1, 4, 8})
        self.assertEqual(infer(q.ast), 'Char')
        self.assertGreaterEqual(len(q.question.split()), 81)
        self.assertTrue(all(infer(p) == 'Char' for p in q.relaxations))

    def test_search_budget_is_explicit(self):
        graph = {'page_ids': ['p'], 'nodes': [], 'facts': []}
        self.assertEqual(list(propose(graph, 1, 1)), [])
