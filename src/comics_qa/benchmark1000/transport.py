"""Bounded OpenAI-compatible endpoint client; no endpoint is assumed configured."""
import base64
import json
from pathlib import Path
import urllib.request
from .io import digest, publish, stable


def request(pack, model, max_tokens=2048):
    if not model or type(max_tokens) is not int or max_tokens < 1:
        raise ValueError('Explicit model and positive token budget required')
    if pack.get('validation_status') != 'hydrated_not_wording_verified':
        raise ValueError('Do not send unresolved evidence packs')
    content = [{'type': 'text', 'text': json.dumps(pack, ensure_ascii=False)}]
    if pack['mode'] == 'synthesis':
        for crop in pack['evidence_crops']:
            path = Path(crop['path'])
            if digest(path) != crop['sha256']:
                raise ValueError('Evidence crop changed')
            data = base64.b64encode(path.read_bytes()).decode()
            content.append({'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + data}})
    return {'model': model, 'messages': [
        {'role': 'system', 'content': 'Write a grounded QA response from this private evidence pack. Do not add facts. Return JSON. Your response cannot approve itself or claim human review.'},
        {'role': 'user', 'content': content}], 'max_tokens': max_tokens, 'temperature': 0}


def infer(payload, endpoint, out, timeout=60, api_key=None):
    """One request per call; a published matching result resumes without another call."""
    if not endpoint.startswith(('http://', 'https://')) or not 0 < timeout <= 60:
        raise ValueError('Explicit HTTP endpoint and timeout <=60 seconds required')
    out = Path(out)
    request_sha = stable(payload)
    if out.exists():
        from .io import read
        saved = read(out)
        if saved.get('request_sha256') != request_sha or saved.get('endpoint') != endpoint:
            raise ValueError('Existing inference request differs')
        return saved
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode()
    result = {'request_sha256': request_sha, 'endpoint': endpoint, 'raw_response': raw,
              'validation_status': 'pending', 'api_key_stored': False}
    publish(out, result)
    return result
