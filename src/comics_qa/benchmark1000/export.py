"""Release gate and allowlisted model-input export; never publishes private proofs."""
from .evaluation import diagnostic_inputs
from .review import release_eligible
from .selection import violations, policy
from .io import stable, digest
from pathlib import Path


def prepare(items, raw_policy, decisions_by_id):
    policy(raw_policy)
    failures = violations(items, raw_policy, final=True)
    if failures:
        raise ValueError('Final policy not satisfied: ' + ', '.join(failures))
    if len({i['item_id'] for i in items}) != len(items):
        raise ValueError('Duplicate final item')
    for item in items:
        if not release_eligible(item, decisions_by_id.get(item['item_id'], [])):
            raise ValueError('Pending release verification/review: ' + item['item_id'])
    main = []
    assets = {}
    for item in items:
        if item['answer_format'] == 'visual_choice' or item.get('image_variant'):
            raise ValueError('Derived option/mask release binding is not enabled yet')
        public = diagnostic_inputs(item)['main']
        for page, original in zip(public['images'], item['legacy']['context']['pages']):
            source = Path(original['image_path'])
            if digest(source) != original['image_sha256']:
                raise ValueError('Release image changed: ' + str(source))
            relative = 'images/' + original['image_sha256'] + source.suffix.lower()
            assets[relative] = {'source_path': str(source), 'sha256': original['image_sha256']}
            page['image_path'] = relative
        main.append(public)
    private = [{'item_id': i['item_id'], 'answer': i['answer'], 'candidate_sha256': stable(i)} for i in items]
    return {'schema': 'comics_qa.benchmark1000.export.1', 'public_inputs': main,
            'private_scoring': private, 'private_asset_mapping': assets, 'counts': {'main': len(main)},
            'warning': 'Public and private sections must be written to separate release files.'}
