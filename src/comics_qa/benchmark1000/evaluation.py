"""Exact typed scoring and diagnostic metrics. No graph annotations in main inputs."""
import re
import unicodedata
from .io import stable


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def exact(answer_format, predicted, expected, accepted_forms=()):
    if answer_format in ('sentence', 'multi_part'):
        raise ValueError('Use claim or component scorers for structured answers')
    if answer_format in ('count', 'page'):
        if type(predicted) is int:
            return type(expected) is int and predicted == expected
        if not isinstance(predicted, str) or not re.fullmatch(r'-?\d+', predicted.strip()):
            return False
        return type(expected) is int and int(predicted.strip()) == expected
    if answer_format == 'boolean':
        if type(predicted) is bool:
            return type(expected) is bool and predicted == expected
        values = {'true': True, 'false': False, 'yes': True, 'no': False}
        return isinstance(predicted, str) and normalized(predicted) in values and type(expected) is bool and values[normalized(predicted)] == expected
    if answer_format in ('set', 'sequence'):
        if not isinstance(predicted, list) or not isinstance(expected, list):
            return False
        p, e = [normalized(x) for x in predicted], [normalized(x) for x in expected]
        return set(p) == set(e) if answer_format == 'set' else p == e
    return normalized(predicted) in {normalized(x) for x in (expected, *accepted_forms)}


def pair_accuracy(results, pairs):
    if any(len(ids) != 2 or ids[0] == ids[1] for ids in pairs.values()):
        raise ValueError('Pairs need two distinct members')
    if any(i not in results for ids in pairs.values() for i in ids):
        raise ValueError('Missing pair prediction')
    if any(type(v) is not bool for v in results.values()):
        raise ValueError('Pair inputs must be Boolean scores')
    return sum(all(results[i] for i in ids) for ids in pairs.values()) / len(pairs) if pairs else None


def evidence_score(predicted, valid_sets):
    if not valid_sets:
        raise ValueError('No accepted evidence set')
    p = set(predicted)
    scores = []
    for evidence in valid_sets:
        e = set(evidence); n = len(p & e)
        precision = n / len(p) if p else float(not e)
        recall = n / len(e) if e else float(not p)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        scores.append({'precision': precision, 'recall': recall, 'f1': f1})
    return max(scores, key=lambda s: s['f1'])


def diagnostic_inputs(item, facts=None, ocr=None):
    """Explicit allowlist. Privileged facts must be ID-free and scope-prepared upstream."""
    base = {'item_id': item['item_id'], 'question': item['question'], 'answer_format': item['answer_format']}
    pages = [{'index': p['index'], 'image_path': p['image_path']} for p in item['legacy']['context']['pages']]
    result = {'main': {**base, 'images': pages}, 'blind': dict(base)}
    if facts is not None:
        if not isinstance(facts, list) or any(not isinstance(f, str) for f in facts):
            raise ValueError('Diagnostic facts must be ID-free text')
        result['facts_only'] = {**base, 'facts': facts, 'privileged': True}
        result['images_facts'] = {**base, 'images': pages, 'facts': facts, 'privileged': True}
    if ocr is not None:
        result['text_only'] = {**base, 'ocr': ocr, 'privileged': True}
    return result
