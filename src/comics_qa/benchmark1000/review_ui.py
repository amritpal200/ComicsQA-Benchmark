"""Private static review queue. Decisions must be ingested with snapshot validation."""
import html
import json
from pathlib import Path
from .io import stable


def page(items):
    blocks = []
    for item in items:
        old = item.get('legacy', item)
        images = ''.join('<figure><figcaption>Page ' + str(p['index']) + '</figcaption><img loading="lazy" width="420" src="' + html.escape(Path(p['image_path']).as_uri(), quote=True) + '"></figure>' for p in old['context']['pages'] if p['page_id'] in item['complexity']['necessary_pages'])
        skeleton = {'item_id': item['item_id'], 'item_sha256': stable(item), 'reviewer': '', 'reviewer_type': 'human', 'decision': 'flag', 'reason': '', 'review_version': 'benchmark1000.review.1'}
        blocks.append('<article><h2>' + html.escape(item['item_id']) + '</h2><p>' + html.escape(item['question']) + '</p><pre>' + html.escape(json.dumps(item['answer'], ensure_ascii=False, indent=2)) + '</pre>' + images + '<details><summary>Private evidence and pending statuses</summary><pre>' + html.escape(json.dumps({'proof': (old.get('execution') or {}).get('proof', old.get('execution')), 'verification': item['verification']}, ensure_ascii=False, indent=2)) + '</pre></details><p>Copy and complete this decision record; accept/reject/flag. Empty or stale records are rejected by ingestion.</p><textarea rows="10" cols="100">' + html.escape(json.dumps(skeleton, ensure_ascii=False, indent=2)) + '</textarea></article>')
    return '<!doctype html><meta charset="utf-8"><title>Private benchmark1000 review</title><style>body{max-width:1100px;margin:2rem auto;font:16px sans-serif}article{border-bottom:2px solid #aaa;padding:1rem}pre{white-space:pre-wrap}img{max-width:100%}</style><h1>Private review — contains answers and evidence</h1><p>AI review is not human approval. This queue does not auto-approve records. Local images require access to the original paths.</p>' + ''.join(blocks)
