"""New-layer typed compositions; existing CRL registries remain untouched."""
from comics_qa.tasks.graph.crl.language import call, infer


def next_speaking_page(character, after):
    return call('first', call('pages_speaking', character, call('span_after', after)))


def next_joint_page(first, second, after):
    span = call('span_after', after)
    return call('first', call('intersect', call('pages_with', first, span), call('pages_with', second, span)))


def last_presence(character, span=None):
    return call('page_of', call('last_app', character, span or call('ctx')))


def page_gap(first, second):
    return call('gap', first, second)


def shared_characters(first, second, excluded=None):
    shared = call('intersect', call('co_present', first, 'page'), call('co_present', second, 'page'))
    return call('diff', shared, call('co_present', excluded, 'page')) if excluded else shared


def typed(program):
    return infer(program)
