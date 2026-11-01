"""Repository-local strict decoder limits and conservative grounding validation."""
import math
import re

VERSION = 'grounding-guards-1'


class GroundingLimitError(ValueError):
    pass


def check_budget(prefix_length, new_tokens, capacity, trailing_special):
    if prefix_length + new_tokens > capacity:
        raise GroundingLimitError(f'Decoder budget exceeded: {prefix_length}+{new_tokens}>{capacity}')
    if trailing_special >= 64:
        raise GroundingLimitError('Decoder made no caption progress for 64 location/special tokens')


def install_decoder_guard(model, processor):
    """Guard the actual decoder prefix before CUDA positional embedding lookup.

    This wraps the loaded instance only; installed model files stay unchanged.
    """
    original = model.language_model.generate
    capacity = model.language_model.config.max_position_embeddings

    def generate(*args, **kwargs):
        prefix = kwargs.get('decoder_input_ids')
        if prefix is not None:
            for row in prefix.detach().cpu().tolist():
                trailing = 0
                for token in reversed(processor.tokenizer.convert_ids_to_tokens(row)):
                    if token.startswith('<loc_') or token in ('<s>', '</s>', '<pad>'):
                        trailing += 1
                    else:
                        break
                check_budget(len(row), kwargs.get('max_new_tokens', 0), capacity, trailing)
        return original(*args, **kwargs)
    model.language_model.generate = generate


def words(text):
    # Punctuation-only loss is a known postprocessor behavior, not lexical equality.
    return re.findall(r'\w+', text, flags=re.UNICODE)


def validate_caption(caption, grounded, strict):
    if not isinstance(grounded, str) or not grounded.strip():
        raise ValueError('Empty/malformed grounded caption')
    if strict and words(caption) != words(grounded):
        raise ValueError('Strict grounding changed caption words')
    return 'exact' if caption == grounded else 'punctuation_or_whitespace_only' if words(caption) == words(grounded) else 'rewritten'


def validate_prediction(output, caption, strict):
    if not isinstance(output, dict):
        raise ValueError('Malformed grounding output')
    mode = validate_caption(caption, output.get('grounded_caption'), strict)
    boxes, spans = output.get('bboxes'), output.get('indices_of_bboxes_in_caption')
    if not isinstance(boxes, list) or not isinstance(spans, list) or len(boxes) != len(spans):
        raise ValueError('Grounding boxes/spans differ')
    if sum(len(group) for group in boxes) > 128:
        raise ValueError('Grounding exceeded 128 boxes; quarantine for review')
    for group, span in zip(boxes, spans):
        if len(span) != 2 or any(type(x) is not int for x in span) or not 0 <= span[0] <= span[1] <= len(output['grounded_caption']):
            raise ValueError('Invalid grounding text span')
        for b in group:
            if len(b) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in b) or b[0] >= b[2] or b[1] >= b[3]:
                raise ValueError('Invalid grounding box')
    return mode


def reusable(document, signature, strict):
    """Legacy complete flags alone are insufficient; keep rejected originals intact."""
    try:
        g = document['grounding']
        if g['_meta']['status'] != 'complete' or g['_meta']['signature'] != signature:
            return False
        for p in g['panels']:
            if p['status'] == 'no_caption' and not (p.get('caption') or '').strip():
                continue
            if p['status'] != 'complete' or len(p['entities']) > 128:
                return False
            validate_caption(p['caption'], p['grounded_caption'], strict)
            raw = {'grounded_caption': p['grounded_caption'],
                   'bboxes': [x['boxes_crop'] for x in p['phrases']],
                   'indices_of_bboxes_in_caption': [x['span'] for x in p['phrases']]}
            validate_prediction(raw, p['caption'], strict)
        return True
    except (ValueError, KeyError, TypeError):
        return False
