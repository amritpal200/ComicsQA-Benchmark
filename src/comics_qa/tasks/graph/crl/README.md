# CRL-1: language and interpreter

CPU-only, Python standard library. Executes typed programs over one complete CKG-1 chapter and
its CKG-2 name-visibility companion. Does not run models, rebuild evidence, write annotations,
generate questions, or independently verify proofs. Use the implemented
[CRL-2 independent checker](CHECKER.md) to verify saved results. The implemented
[GEN-1 generator](../generation/README.md) uses both to prepare the first question candidates.

## Run

From `ComicsQA_Benchmark/Code`:

```bash
bash scripts/run_crl.sh --chapter dragon-ball__c002 \
  --program 'count(texts(ctx()))' \
  --out /tmp/dragon-ball-text-count.json

code /tmp/dragon-ball-text-count.json
```

The checked full-data snapshot returns `183`, `OK`, `exact=true` for this program.
Choose a new output filename on each run, or omit `--out` to print JSON. Existing files are
never replaced; file publication is atomic. Outputs cannot go inside either evidence directory.

The launcher defaults to `/data/151-3/comics/ComicsQA_Benchmark`. On another machine:

```bash
BENCH_ROOT=/your/data/ComicsQA_Benchmark bash scripts/run_crl.sh \
  --chapter dragon-ball__c002 \
  --program 'at_least(pages_with(char("Bulma")),1)'
```

Override `--graphs` and `--visibility` to use other completed builds. The loader checks both
manifests, selected chapter hashes, the companion's graph hash, chapter scope, graph structures,
and the visibility build's pinned graph-manifest hash. Original absolute paths may differ after
relocation; content hashes must still match. This checks the selected immutable artifacts, **not**
the current raw image/OCR files or every chapter in the collection. Raw-source freshness belongs
to the CKG build/verification stages.

`--program-file path` reads one program (surface, S-expression, or JSON AST).
`--format auto|surface|sexpr|json` selects its syntax. The CLI exits 2 for `ERROR` or invalid
inputs/output; `UNKNOWN`, `EMPTY`, and `AMBIGUOUS` are valid evaluation results and exit 0.
There is no full-collection CRL job to run: this stage provides an interpreter
that the generator will call for each candidate program.

## Syntax and types

These programs are equivalent:

```text
count(texts(page(1)))
(count (texts (page 1)))
```

```json
{"op":"count","args":[{"op":"texts","args":[{"op":"page","args":[1]}]}]}
```

Calls accept positional arguments followed by named arguments. Collection predicates and keys
use `\x.expression` or `λx.expression`. Sequential bindings use `let x=e, y=e in expression`:

```text
let c=char("Bulma") in count(filter(ctx(), \p.present(c,p)))
```

S-expression lambdas are `(lambda p (present (char "Bulma") (var p)))`; bindings are
`(let ((c (char "Bulma"))) (count (pages_with (var c))))`.
JSON uses `{"var":"c"}`, `{"lambda":{"param":"p","body":EXPR}}`, and
`{"let":[{"name":"c","value":EXPR}],"in":EXPR}`.

Types include `Page`, `App`, `Char`, `Text`, `Panel`, `Tail`, `Int`, `Str`, `Bool3`, `Cmp`,
`Span`, `Seq[T]`, `Set[T]`, `Map[K,Int]`, and `Turn`. Functions occur only as operator arguments.
All programs are statically checked before evaluation; there is no Python evaluation, recursion,
file access, or arbitrary function call in the language. Limits: 100,000 input characters,
2,048 explicit AST nodes, depth 64, and 50,000 evaluated steps (configurable with `--max-steps`).

Canonical S-expressions sort keyword arguments and positional operands of commutative calls;
string literals use Unicode NFKC while preserving case. Hashes include the CRL version.
This is syntactic canonicalization: omitted defaults, named versus positional arguments, and
renamed bound variables need not have identical hashes. Name matching separately uses CKG-2
normalization. Use `--format surface` for a parenthesized surface expression; auto mode treats
leading `(` as S-expression syntax.

## Implemented operations

`span` defaults to `ctx()` where optional. A page scope accepts a `Page`, `Span`, `Seq[Page]`,
or `Set[Page]`. `ctx()` always contains every supplied chapter image, including pages without GT.
`page(i)` and `pages(i,j)` use **1-based context indices**, with inclusive endpoints. A spread
is one context image; an index is not the original printed page number or filename number.

| Group | Operations |
|---|---|
| Anchors/enumeration | `ctx()`, `page(i)`, `pages(i,j)`, `char(name)`, `chars(span)`, `apps(span)`, `texts(span)`, `lines(span)` |
| Navigation | `char_of(a)`, `page_of(x)`, `speaker(t)`, `speaker_char(t)`, `apps_of(c,span)`, `lines_of(c,span)`, `chars_on(p)`, `pages_with(c,span)`, `pages_speaking(c,span)`, `co_present(c,unit="page",span=ctx())` |
| Predicates | `present(c,p)`, `speaks_on(c,p)`, `silent_on(c,p)`, `together(c1,c2,unit=page(i))`, `is_named(c)`, `eq(x,y)`, `neq(x,y)`, `in(x,S)` |
| Order/spans | `first(S)`, `last(S)`, `nth(S,k)`, `next(x,S)`, `prev(x,S)`, `rank(x,S)`, `precedes(x,y)`, `span_before(x,within=ctx())`, `span_after(x,within=ctx())`, `between(x,y)`, `gap(x,y)`, `first_app(c,span)`, `last_app(c,span)`, `next_app(c,after=x)`, `longest_streak(c,span)`, `sort_by(S,fn)` |
| Discourse | `first_line(c,span)`, `nth_line(c,k,span)`, `line_count(c,span)`, `next_line(t)`, `prev_line(t)`, `next_other_speaker(t)`, `turns(span)`, `exchanges(c1,c2,span)` |
| Sets/logic | `filter(S,fn)`, `map(S,fn)`, `union(A,B)`, `intersect(A,B)`, `diff(A,B)`, `distinct(S)`, `the(S)`, `exists(S,fn)` / `exists(S)`, `forall(S,fn)`, `none(S,fn)` / `none(S)`, `and(...)`, `or(...)`, `not(p)`, `unknown` |
| Aggregates | `count(S)`, `at_least(S,n)`, `argmax(S,fn)`, `argmin(S,fn)`, `max(S)`, `min(S)`, `sum(S)`, `mode(S)`, `group_count(S,fn)`, `top_k(S,fn,k)`, `compare(x,y)`, `minus(x,y)` |

`map` preserves multiplicity. Set operations remove duplicates. `compare` produces `more`,
`fewer`, or `equal`; `group_count` serializes as `[key,count]` pairs. Numeric aggregates require
integers. `argmax`/`argmin` require a winner margin of at least `max(2,0.25*winning_score)`;
`top_k` applies that margin at the k/k+1 boundary. Ties in selected top-k ranks or sort keys
return `AMBIGUOUS`, rather than letting arbitrary IDs become a semantic ordering.

## Coverage, ordering, and names

| Result status | Meaning |
|---|---|
| `OK` | Known value; inspect `exact` for collection completeness |
| `EMPTY` | Selection has no match in an exact collection |
| `AMBIGUOUS` | Multiple matches, tied keys/winners, or insufficient winner margin |
| `UNKNOWN` | Required coverage, identity, readable name, or ordering evidence is unavailable |
| `ERROR` | Invalid program, index, type, or exceeded execution budget |

Only H/V answer-eligible facts are used. Default closed coverage accepts `closed_assumed`,
`closed_audited`, and `closed_verified`, preserving the CKG policy; the exact certificate IDs
are recorded. `--require-verified-coverage` excludes `closed_assumed`, including supplied page
order. It does not silently upgrade any annotation or certificate.

Open collections contain known members with `exact=false`. Counting, negation, set difference,
uniqueness, ordinals, and non-monotone aggregates require appropriate closed coverage.
An empty list from an unannotated page does not imply absence. Positive existence/threshold
witnesses may still be known. `and`/`or` implement Kleene absorption; `EMPTY`, `AMBIGUOUS`, and
`ERROR` cannot be absorbed. `none` requires a closed domain and exact predicates.
The empty scope between adjacent pages is a known empty range and can be counted as zero.

Chapter order is available; within-page order is not yet verified. IDs provide deterministic
storage order only. An ordinal cannot select among same-page appearances/texts. Selection can
succeed when its requested position and anchor have unique page positions, even if other pages
contain ties. Span operations and `next_app` exclude the anchor's entire page. `next_app` checks
coverage through its first candidate page; it does not require unrelated later pages to be closed.
Discourse currently requires at most one known line per page plus closed text/speaker coverage.
Speaker selection requires closed speaker/text coverage to establish uniqueness.

`char("name")` requires both an exact graph name/alias mapping and verified readability of
that **same form** somewhere in the chapter. It records CKG-2 evidence IDs. Visibility of an
alias does not authorize an unseen canonical name. Character answers display a verified canonical
name or a verified alias; generic/unverified names fail the named-answer gate. Even an absorbed
failed name anchor blocks generation eligibility. CKG-2 visibility verifies lexical readability,
not complete OCR transcripts or the speaker/referent of a name occurrence.

`quote` and `name_texts` require the optional verified OCR/lexical profile described below.
`panels`, `panel_of`, `mentions_of`, `mentioned_in`, `first_mention`, and `offpanel_line`
remain typed but return `UNKNOWN`; their consuming semantics are not implemented. Panel
co-presence is also gated. Spatial operators, world edits, and determinability are outside this
CRL-1 profile and are rejected as unknown operations. These remain later-stage work in the
[design](../../../../../docs/notes/graph_reasoning.md).

## Result and evidence contract

Each result contains its canonical program/hash, value/type/display/status/exactness/reason,
an evaluation DAG, graph fact IDs with transitive premises, coverage certificate IDs, node
references, name-visibility evidence IDs, supporting/range pages, and minimum evidence trust.
Each trace step records its expression, children, result, order flag, and evidence references.
Fact/node/source details are resolved against the pinned input shards. `range_pages` includes
input scopes and anchors; consult each step's certificates for the actual closure obligation.
Supporting pages can include a name-readability page outside a searched subspan, since the
visible question context is the full chapter. Traces are conservative and need not be minimal.

The CLI also records input and implementation hashes. In-memory `Interpreter(graph, companion)`
validates structure but cannot verify original file bytes; use `load_world` for artifact checks.

`eligible_for_generation` is an **interpreter precheck**, not an accepted benchmark question.
It requires a renderable answer, readable names, `OK`, and exactness, except a top-level
`at_least(...)=true` may use an open-world lower bound. Internal App/Text/Turn/Map values remain
available for composition/traces but are not final rendered answers. Independent proof validation
is recorded separately by [CRL-2](CHECKER.md); the immutable producer result keeps
`proof_check="pending_CRL-2"`. GEN-1 must subsequently enforce necessity, uniqueness,
robustness, no answer leakage, name use in wording, answer balancing, and other acceptance rules.

## Validation

```bash
python3 -m unittest discover -s tests -p 'test_crl.py' -v
python3 -m unittest discover -s tests -p 'test_ckg*.py' -q
```

30 CRL tests cover three syntaxes, types/bounds, open versus closed coverage, missing GT,
UNKNOWN/EMPTY/AMBIGUOUS, page spreads, name/alias visibility, generic answers, order uncertainty,
speaker/discourse navigation, sets/lambdas/aggregates, proof references, immutability, checksums,
and CLI output safety. The 57 existing CKG tests also pass.

## Optional verified OCR/lexical profile (2026-10-29)

Supply `--rich /data/151-3/comics/ComicsQA_Benchmark/evidence/ckg3/v1` to both the interpreter
and checker. The validated companion is pinned alongside CKG-1/2 (six artifact hashes), and
`rich_evidence_sha256` binds the reconstructed payload. Its eligible `V` transcript/name-occurrence
facts retain CKG-3 IDs and source/review premises; OCR coverage is transported as `rich_ocr`.
The companion loader re-derives the input evidence, while producer/checker implement their query
semantics separately. Base CKG-1 files are not modified. Existing programs without `--rich`
keep the original behavior and version/hash convention.

- `quote(s,on=ctx()) -> Text`: unique **full** transcript after NFKC/case/whitespace/curly-apostrophe
  normalization. Punctuation remains significant. No substring/fuzzy match. Exact uniqueness or
  absence needs closed human text inventory plus rich OCR coverage throughout the search scope;
  two verified matches give `AMBIGUOUS`, and incomplete coverage prevents claiming uniqueness.
- `name_texts(s,on=ctx()) -> Seq[Text]`: literal contiguous normalized name tokens in full verified
  transcripts, plus verified lexical occurrences. The exact form must resolve unambiguously to
  a readable CKG-2 identity. This makes no semantic coreference claim. Missing complete OCR leaves
  an open collection: positive lower bounds can be proved, exact counts/only/absence cannot.
  Within-page reading order is not inferred. Conflicting lexical/full-text evidence cannot close
  the result. Without a rich companion both operations remain `UNKNOWN`.

For example, the bounded real-data smoke confirmed this count as 5:

```bash
bash scripts/run_crl.sh --chapter chainsaw-man__c001 \
  --rich /data/151-3/comics/ComicsQA_Benchmark/evidence/ckg3/v1 \
  --program 'count(apps_of(speaker_char(quote("make my dreams come true for me!",on=page(32))),page(32)))' \
  --out /tmp/crl-rich-example.json
bash scripts/check_crl.sh \
  --rich /data/151-3/comics/ComicsQA_Benchmark/evidence/ckg3/v1 \
  --result /tmp/crl-rich-example.json --out /tmp/crl-rich-example.check.json
```

Other deferred panel/order/spatial/semantic-mention operations remain unsupported.
[GEN-2](../gen2/README.md) composes these anchors with supported visual relations and applies
additional generation gates; an eligible CRL answer alone is not an accepted benchmark question.
