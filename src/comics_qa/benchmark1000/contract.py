"""New-layer metadata; legacy records are never migrated in place."""
from .io import stable

SCHEMA = 'comics_qa.benchmark1000.candidate.1'
EVIDENCE = {'executed', 'claim_verified', 'interpretive'}
MODES = {'template', 'paraphrase', 'synthesis'}
STRUCTURES = {'direct', 'chain', 'branch_combine', 'aggregate', 'compare', 'counterfactual', 'determinability'}
FORMATS = {'character', 'page', 'count', 'boolean', 'set', 'sequence', 'quote', 'visual_choice', 'multiple_choice', 'sentence', 'multi_part'}


def validate(item):
    if item.get('schema') == 'comics_qa.benchmark1000.contrast_member.1':
        from .contrast import validate_member
        return validate_member(item)
    if item.get('schema') == 'comics_qa.benchmark1000.admitted_native.1':
        from .admission_store import validate as validate_admitted
        return validate_admitted(item)
    if item.get('schema') == 'comics_qa.benchmark1000.native.1':
        from .native import validate as validate_native
        return validate_native(item)
    if item.get('schema') != SCHEMA:
        raise ValueError('Wrong candidate schema')
    for key, domain in [('evidence_class', EVIDENCE), ('generation_mode', MODES),
                        ('reasoning_structure', STRUCTURES), ('answer_format', FORMATS)]:
        if item.get(key) not in domain:
            raise ValueError('Invalid ' + key)
    for key in ('item_id', 'chapter_id', 'split', 'source_item_id', 'question'):
        if not isinstance(item.get(key), str) or not item[key]:
            raise ValueError('Missing ' + key)
    if item['split'] not in ('seen', 'unseen'):
        raise ValueError('Unknown source split')
    for key in ('legacy', 'source', 'answer', 'verification', 'complexity', 'features'):
        if not isinstance(item.get(key), dict):
            raise ValueError('Missing object: ' + key)
    if item['source']['item_sha256'] != stable(item['legacy']):
        raise ValueError('Legacy item binding mismatch')
    original = item['legacy']
    if (item['chapter_id'], item['split'], item['question'], item['answer']) != (
            original['chapter_id'], original['split'], original['question'], original['answer']):
        raise ValueError('Imported answer/question/source mismatch')
    if item['item_id'] != 'b1000:' + stable([item['source_item_id'], item['source']['item_sha256']]):
        raise ValueError('Candidate ID mismatch')
    saved_check = original.get('proof_check', {})
    if saved_check.get('execution_sha256') is not None and saved_check['execution_sha256'] != stable(original['execution']):
        raise ValueError('Saved execution hash mismatch')
    if original['program'] != original['execution']['program']:
        raise ValueError('Program/execution mismatch')
    return item
