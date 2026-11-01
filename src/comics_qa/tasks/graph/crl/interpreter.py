"""Page-level CRL execution with explicit open-world results and evidence traces."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import sys

GRAPH = Path(__file__).resolve().parents[3] / 'evidence/graph'
sys.path.insert(0,str(GRAPH))
from ckg_schema import CLOSED, TRUST, validate_graph
from name_visibility import normalized
from build_ckg2 import validate_companion
try:
    from .language import LanguageError, VERSION, bind, call, canonical, element, infer, parse, program_hash, SPECS
except ImportError:
    from language import LanguageError, VERSION, bind, call, canonical, element, infer, parse, program_hash, SPECS


class ExecutionLimit(ValueError):
    pass


@dataclass
class Result:
    value: object = None
    type: str = ''
    status: str = 'OK'
    exact: bool = True
    facts: set = field(default_factory=set)
    certificates: set = field(default_factory=set)
    visibility: set = field(default_factory=set)
    nodes: set = field(default_factory=set)
    scope: set = field(default_factory=set)
    families: set = field(default_factory=set)
    ordered: bool = False
    reason: str = ''
    nid: int = -1


def merged(value=None, children=(), **changes):
    children=list(children)
    kwargs={k:set().union(*(getattr(c,k) for c in children)) for k in ('facts','certificates','visibility','nodes','scope','families')}
    kwargs.update(value=value,exact=all(c.exact for c in children))
    kwargs.update(changes)
    return Result(**kwargs)


def key(value):return json.dumps(value,sort_keys=True,ensure_ascii=False)
def unique(values):return list({key(x):x for x in values}.values())


class Interpreter:
    def __init__(self,graph,visibility,max_steps=50000,allow_closed_assumed=True,rich=None):
        validate_graph(graph);validate_companion(visibility,graph)
        if graph['chapter_id']!=visibility['chapter_id']:raise ValueError('Visibility chapter mismatch')
        if max_steps<1:raise ValueError('Execution step budget must be positive')
        self.graph=graph;self.name_visibility=visibility;self.max_steps=max_steps
        self.closed=set(CLOSED) if allow_closed_assumed else set(CLOSED)-{'closed_assumed'}
        self.nodes={n['id']:n for n in graph['nodes']}
        self.facts={f['fact_id']:f for f in graph['facts']}
        self.by_rel=defaultdict(list)
        for fact in graph['facts']:
            if fact['origin'] in ('H','V') and fact['answer_eligible']:self.by_rel[fact['rel']].append(fact)
        self.pages=graph['page_ids'];self.pos={p:i for i,p in enumerate(self.pages)}
        self.certs={(c['page_id'],c['family']):c for c in graph['coverage']}
        self.vis={v['identity_id']:v for v in visibility['visibility']}
        self.vis_evidence={e['evidence_id']:e for e in visibility['evidence']}
        self.trace=[];self.type_cache={}
        try:
            from .rich_contract import prepare, fingerprint
        except ImportError:
            from rich_contract import prepare, fingerprint
        self.rich_hash=fingerprint(rich)
        rich_facts,rich_certs=prepare(graph,visibility,rich)
        self.facts.update({f['fact_id']:f for f in rich_facts})
        for f in rich_facts:self.by_rel[f['rel']].append(f)
        self.certs.update({(c['page_id'],c['family']):c for c in rich_certs})

    def page_id(self,x):
        node=self.nodes.get(x) if isinstance(x,str) else None
        return x if node and node['type']=='Page' else node.get('page_id') if node else None

    def sort_values(self,values):
        return sorted(unique(values),key=lambda x:(self.pos.get(self.page_id(x),len(self.pages)),key(x)))

    def ordered(self,values):
        if len(values)<=1:return True
        ps=[self.page_id(x) for x in values]
        return all(p is not None for p in ps) and len(set(ps))==len(ps) and ps==sorted(ps,key=self.pos.get)

    def scope(self,r):return [r.value] if r.type=='Page' else list(r.value)

    def coverage(self,pages,families):
        refs=set();ok=True
        for p in pages:
            for family in families:
                cert=self.certs.get((p,family))
                if cert:refs.add(cert['coverage_id'])
                ok &= bool(cert and cert['status'] in self.closed)
        return ok,refs

    def scanned(self,value,pages,families,children=(),facts=(),**kw):
        ok,refs=self.coverage(pages,families)
        r=merged(value,children,**kw)
        r.exact &= ok;r.scope.update(pages);r.families.update(families)
        r.certificates.update(refs);r.facts.update(facts)
        return r

    def unknown(self,reason,children=()):return merged(children=children,status='UNKNOWN',exact=False,reason=reason)

    def _record(self,node,result,children=()):
        if len(self.trace)>=self.max_steps:raise ExecutionLimit('Execution step budget exceeded')
        result=replace(result,nid=len(self.trace))
        origins=[self.facts[f]['origin'] for f in result.facts]+[self.nodes[n]['origin'] for n in result.nodes]+['V' for _ in result.visibility]
        self.trace.append({'nid':result.nid,'op':node.get('op','let' if 'let' in node else 'var' if 'var' in node else 'literal') if isinstance(node,dict) else 'literal',
            'expression':canonical(node),'type':result.type,'value':result.value,'status':result.status,'exact':result.exact,'ordered':result.ordered,
            'facts':sorted(result.facts),'certificates':sorted(result.certificates),'visibility_evidence':sorted(result.visibility),
            'node_refs':sorted(result.nodes),'range_pages':sorted(result.scope,key=self.pos.get),
            'children':[r.nid for r in children if r.nid>=0],'reason':result.reason,
            'trust_min':min(origins,key=TRUST.get) if origins else None})
        return result

    def eval(self,node,env=None):
        env={} if env is None else env
        if len(self.trace)>=self.max_steps:raise ExecutionLimit('Execution step budget exceeded')
        if type(node) in (str,int,bool):return self._record(node,Result(node,infer(node)))
        if 'enum' in node:return self._record(node,Result(node['enum'],'Cmp'))
        if 'var' in node:return self._record(node,replace(env[node['var']]),[env[node['var']]])
        if 'let' in node:
            local=dict(env);children=[]
            for b in node['let']:
                r=self.eval(b['value'],local);local[b['name']]=r;children.append(r)
            r=self.eval(node['in'],local)
            return self._record(node,replace(r),children+[r])
        bound=bind(node);op=node['op'];args={};children=[]
        for name,value in bound.items():
            if name=='fn':continue
            if name=='values':
                args[name]=[self.eval(v,env) for v in value];children.extend(args[name])
            else:
                args[name]=self.eval(value,env);children.append(args[name])
        type_key=(canonical(node),tuple(sorted((k,r.type) for k,r in env.items())))
        if type_key not in self.type_cache:self.type_cache[type_key]=infer(node,{k:r.type for k,r in env.items()})
        if op in ('and','or'):
            r=self.logic(op,args['values'])
        elif any(c.status!='OK' for c in children):
            failed=next(c for c in children if c.status!='OK')
            r=merged(children=children,status=failed.status,exact=False,reason='Child: '+failed.reason)
        elif op in ('quote','name_texts') and self.rich_hash is not None:
            r=self.rich_operation(op,args)
        elif SPECS[op]['deferred']:
            r=self.unknown('Evidence stage unavailable: '+op,children)
        elif 'fn' in bound and bound['fn'] is not None:
            r,extra=self.functional(op,args,bound['fn'],env);children.extend(extra)
        else:r=self.operation(op,args)
        r.type=self.type_cache[type_key]
        return self._record(node,r,children)

    def rich_operation(self,op,args):
        import unicodedata
        from name_visibility import tokens
        children=list(args.values());pages=self.scope(args['on']);form=args['s'].value
        normalize=lambda s:' '.join(unicodedata.normalize('NFKC',s).casefold().replace('’',"'").split())
        rows=[f for f in self.by_rel['transcript'] if self.page_id(f['args'][0]) in pages]
        if op=='quote':
            matches=self.sort_values([f['args'][0] for f in rows if normalize(f['args'][1])==normalize(form) and normalize(form)])
            scanned=self.scanned(matches,pages,['text_boxes','rich_ocr'],children,facts=[f['fact_id'] for f in rows])
            return self.select(scanned,'the')
        anchor=self.operation('char',{'name':args['s']})
        if anchor.status!='OK':return merged(children=[*children,anchor],status=anchor.status,exact=False,reason=anchor.reason)
        needle=tokens(form)
        full={f['args'][0] for f in rows if needle and any(tokens(f['args'][1])[i:i+len(needle)]==needle for i in range(len(tokens(f['args'][1]))-len(needle)+1))}
        lexical=[f for f in self.by_rel['name_occurs'] if f['args'][1]==anchor.value and normalized(f['args'][2])==normalized(form) and self.page_id(f['args'][0]) in pages]
        known=full|{f['args'][0] for f in lexical}
        values=self.sort_values(known)
        result=self.scanned(values,pages,['text_boxes','rich_ocr'],[*children,anchor],facts=[f['fact_id'] for f in rows+lexical],ordered=self.ordered(values))
        if result.exact and known!=full:result.exact=False
        return result

    def logic(self,op,items):
        # EMPTY/AMBIGUOUS/ERROR are not Kleene unknowns and cannot be absorbed.
        failed=next((r for r in items if r.status not in ('OK','UNKNOWN')),None)
        if failed:return merged(children=items,status=failed.status,exact=False,reason=failed.reason)
        decisive=next((r for r in items if r.status=='OK' and r.value==(op=='or')),None)
        if decisive:return merged(decisive.value,[decisive])
        if any(r.status=='UNKNOWN' for r in items):return self.unknown('Kleene unknown',items)
        return merged(op=='and',items)

    def select(self,s,op,k=None,x=None):
        if op=='the' and len(s.value)>1:return merged(children=[s],status='AMBIGUOUS',exact=False,reason='More than one known match')
        if not s.exact:return self.unknown('Selection requires exact collection coverage',[s])
        if op=='the':
            return merged(s.value[0],[s]) if s.value else merged(children=[s],status='EMPTY',reason='Empty exact collection')
        values=list(s.value)
        if not values:return merged(children=[s],status='EMPTY',reason='Empty exact collection')
        if op in ('next','prev','rank'):
            positions=[i for i,v in enumerate(values) if v==x]
            if not positions:return merged(children=[s],status='EMPTY',reason='Anchor not in exact sequence')
            if len(positions)>1:return merged(children=[s],status='AMBIGUOUS',reason='Anchor occurs more than once')
            anchor=positions[0];index=anchor+({'next':1,'prev':-1,'rank':0}[op])
        else:index=0 if op=='first' else len(values)-1 if op=='last' else k-1
        if op=='nth' and k<1:return merged(children=[s],status='ERROR',exact=False,reason='nth index is one-based')
        if not 0<=index<len(values):return merged(children=[s],status='EMPTY',reason='No item at requested position')
        if not s.ordered:
            ps=[self.page_id(v) for v in values]
            affected=[index]+([anchor] if op in ('next','prev','rank') else [])
            if any(ps[i] is None or ps.count(ps[i])>1 for i in affected):
                return self.unknown('Within-page order or explicit sort key is unavailable',[s])
        return merged(index+1 if op=='rank' else values[index],[s])

    def query(self,op,pages,c=None):
        families={'apps':['char_boxes'],'texts':['text_boxes'],'lines':['text_boxes','speaker_links'],
                  'chars':['char_boxes','names'],'apps_of':['char_boxes','names'],
                  'lines_of':['text_boxes','speaker_links','char_boxes','names'],
                  'pages_with':['char_boxes','names'],'pages_speaking':['char_boxes','names','text_boxes','speaker_links'],
                  'co_present':['char_boxes','names']}[op]
        selected=[];facts=[];scope=set(pages)
        if op in ('apps','texts'):
            wanted='Appearance' if op=='apps' else 'Text'
            for f in self.by_rel['on_page']:
                if f['args'][1] in scope and self.nodes[f['args'][0]]['type']==wanted:
                    selected.append(f['args'][0]);facts.append(f['fact_id'])
        elif op=='lines':
            for f in self.by_rel['is_line']:
                if self.page_id(f['args'][0]) in scope:selected.append(f['args'][0]);facts.append(f['fact_id'])
        elif op=='apps_of':
            for f in self.by_rel['is_char']:
                if f['args'][1]==c and self.page_id(f['args'][0]) in scope:selected.append(f['args'][0]);facts.append(f['fact_id'])
        elif op=='lines_of':
            identity={f['args'][0]:f for f in self.by_rel['is_char']}
            for f in self.by_rel['spoken_by']:
                link=identity.get(f['args'][1])
                if link and link['args'][1]==c and self.page_id(f['args'][0]) in scope:
                    selected.append(f['args'][0]);facts.extend([f['fact_id'],link['fact_id']])
        else:
            rel='speaks_on' if op=='pages_speaking' else 'co_present' if op=='co_present' else 'present'
            for f in self.by_rel[rel]:
                args=f['args']
                if args[-1] not in scope:continue
                if op=='chars':selected.append(args[0])
                elif op=='co_present':
                    if c not in args[:2]:continue
                    selected.append(args[1] if args[0]==c else args[0])
                elif args[0]==c:selected.append(args[1])
                else:continue
                facts.append(f['fact_id'])
        selected=self.sort_values(selected)
        return self.scanned(selected,pages,families,facts=facts,ordered=self.ordered(selected))

    def navigate(self,op,value):
        if op=='page_of':
            if self.nodes[value]['type']=='Page':return Result(value,nodes={value},scope={value})
            rel='on_page'
        elif op=='char_of':rel='is_char'
        else:rel='spoken_by'
        rows=[f for f in self.by_rel[rel] if f['args'][0]==value]
        targets=unique(f['args'][1] for f in rows)
        pid=self.page_id(value)
        r=Result(facts={f['fact_id'] for f in rows},nodes={value},scope={pid} if pid else set())
        if len(targets)>1:return merged(children=[r],status='AMBIGUOUS',reason='Multiple relation targets')
        if op=='speaker':
            r=self.scanned(None,[pid],['text_boxes','speaker_links'],[r])
            if not r.exact:return self.unknown('Speaker uniqueness/completeness is open',[r])
        if not targets:return self.unknown('Required relation target missing',[r])
        r.value=targets[0];r.nodes.add(targets[0]);return r

    def predicate(self,op,c,p):
        rel='present' if op=='present' else 'speaks_on'
        families=['char_boxes','names'] if rel=='present' else ['char_boxes','names','text_boxes','speaker_links']
        fs=[f['fact_id'] for f in self.by_rel[rel] if f['args']==[c,p]]
        r=self.scanned(bool(fs),[p],families,facts=fs)
        if not fs and not r.exact:return self.unknown('Missing fact is not evidence of absence',[r])
        return r

    def functional(self,op,args,lam,env):
        s=args['S'];values=s.value;children=list(args.values());evaluated=[]
        for value in values:
            item=merged(value,[s],type=element(s.type),exact=True)
            # Individual positive members are known; enumeration completeness stays on S.
            r=self.eval(lam['lambda']['body'],{**env,lam['lambda']['param']:item});evaluated.append(r)
        children.extend(evaluated)
        invalid=next((r for r in evaluated if r.status not in ('OK','UNKNOWN')),None)
        if invalid:return merged(children=children,status=invalid.status,exact=False,reason=invalid.reason),evaluated
        if op in ('exists','forall','none'):
            if op=='none' and (not s.exact or any(not r.exact or r.status!='OK' for r in evaluated)):
                return self.unknown('none requires exact predicate domain',children),evaluated
            decisive=next((r for r in evaluated if r.status=='OK' and r.value==(op!='forall')),None)
            if decisive:
                return merged(op=='exists',[s,decisive]),evaluated
            if not s.exact or any(r.status=='UNKNOWN' for r in evaluated):return self.unknown('Quantifier domain/predicate incomplete',children),evaluated
            return merged(op!='exists',children),evaluated
        if op=='filter':
            kept=[x for x,r in zip(values,evaluated) if r.status=='OK' and r.value is True]
            return merged(kept,children,exact=s.exact and all(r.status=='OK' and r.exact for r in evaluated),
                          ordered=s.ordered or self.ordered(kept)),evaluated
        if any(r.status!='OK' for r in evaluated):return self.unknown('Unknown mapped value/key',children),evaluated
        if op=='map':return merged([r.value for r in evaluated],children,ordered=s.ordered),evaluated
        if not s.exact or any(not r.exact for r in evaluated):return self.unknown('Aggregate/sort requires exact domain and keys',children),evaluated
        if op=='group_count':
            counts=Counter(key(r.value) for r in evaluated)
            return merged([[json.loads(k),v] for k,v in sorted(counts.items())],children),evaluated
        if op=='sort_by':
            def score(r):return self.pos[r.value] if r.type=='Page' else r.value
            if len({key(score(r)) for r in evaluated})!=len(evaluated):
                return merged(children=children,status='AMBIGUOUS',reason='Sort keys tie; no semantic tie breaker'),evaluated
            ranked=sorted(zip(values,evaluated),key=lambda pair:score(pair[1]))
            return merged([v for v,r in ranked],children,ordered=True),evaluated
        if not values:return merged(children=children,status='EMPTY',reason='Empty exact domain'),evaluated
        ranked=sorted(zip(values,evaluated),key=lambda pair:((-pair[1].value if op!='argmin' else pair[1].value),key(pair[0])))
        k=args['k'].value if op=='top_k' else 1
        if k<1:return merged(children=children,status='ERROR',exact=False,reason='k must be positive'),evaluated
        if k>len(ranked):return merged(children=children,status='EMPTY',reason='k exceeds exact domain'),evaluated
        if k<len(ranked):
            best,runner=ranked[k-1][1].value,ranked[k][1].value
            gap=runner-best if op=='argmin' else best-runner
            if gap<max(2,0.25*best):return merged(children=children,status='AMBIGUOUS',reason='Aggregate winner/boundary margin not met'),evaluated
        if op=='top_k' and len({r.value for _,r in ranked[:k]})<k:
            return merged(children=children,status='AMBIGUOUS',reason='Top-k ranks tie'),evaluated
        out=[x for x,r in ranked[:k]] if op=='top_k' else ranked[0][0]
        return merged(out,children,ordered=op=='top_k'),evaluated

    def operation(self,op,a):
        children=list(a.values());v={k:r.value for k,r in a.items()}
        def finish(r):
            # Preserve operator-specific exactness but propagate uncertain input anchors.
            combined=merged(r.value,[*children,r],status=r.status,ordered=r.ordered,reason=r.reason)
            return combined
        if op=='unknown':return self.unknown('Explicit unknown')
        if op in ('ctx','page','pages'):
            if op=='ctx':ps=self.pages[:]
            else:
                i=v['i'];j=v.get('j',i)
                if not 1<=i<=j<=len(self.pages):return Result(status='ERROR',exact=False,reason='Page indices are one-based within the full chapter')
                ps=self.pages[i-1:j]
            r=self.scanned(ps[0] if op=='page' else ps,ps,['page_sequence'],children,ordered=True)
            r.nodes.update(ps);return r
        if op=='char':
            form=normalized(v['name'])
            candidates=[n for n in self.nodes.values() if n['type']=='Character' and not n['generic']
                        and form in {normalized(x) for x in [n['canonical_name'],*n['aliases']]}]
            if len(candidates)>1:return Result(status='AMBIGUOUS',exact=False,reason='Name resolves to multiple identities')
            if not candidates:return self.unknown('Name is not a graph identity')
            cid=candidates[0]['id'];vis=self.vis[cid]
            ev=[eid for eid in vis['verified_evidence_ids'] if self.vis_evidence[eid]['normalized_form']==form]
            if not ev:return self.unknown('Exact name form lacks verified chapter readability')
            facts={f['fact_id'] for rel in ('named','alias') for f in self.by_rel[rel]
                   if f['args'][0]==cid and normalized(f['args'][1])==form}
            if not facts:return self.unknown('Name mapping lacks a trusted graph fact')
            return Result(cid,facts=facts,visibility={sorted(ev)[0]},nodes={cid})
        if op in ('chars','apps','texts','lines','apps_of','lines_of','pages_with','pages_speaking','co_present','chars_on'):
            if op=='co_present' and v['unit']!='page':return self.unknown('Panel co-presence is not enabled',children)
            pages=self.scope(a['p' if op=='chars_on' else 'span'])
            return finish(self.query('chars' if op=='chars_on' else op,pages,v.get('c')))
        if op in ('page_of','char_of','speaker','speaker_char'):
            r=self.navigate('speaker' if op=='speaker_char' else op,next(iter(v.values())))
            if op=='speaker_char' and r.status=='OK':r=self.compose_character(r)
            return finish(r)
        if op in ('present','speaks_on','silent_on'):
            if op!='silent_on':return finish(self.predicate(op,v['c'],v['p']))
            p=self.predicate('present',v['c'],v['p']);s=self.predicate('speaks_on',v['c'],v['p'])
            neg=self.unknown('Silence requires closed speaker coverage',[s]) if s.status!='OK' or not s.exact else merged(not s.value,[s])
            return finish(self.logic('and',[p,neg]))
        if op=='together':return finish(self.logic('and',[self.predicate('present',v['c1'],v['unit']),self.predicate('present',v['c2'],v['unit'])]))
        if op=='is_named':return merged(not self.nodes[v['c']]['generic'],children,nodes=set().union(*(c.nodes for c in children),{v['c']}))
        if op in ('eq','neq'):
            if not all(c.exact for c in children):return self.unknown('Equality requires exact operands',children)
            equal=({key(x) for x in v['x']}=={key(x) for x in v['y']}) if a['x'].type.startswith('Set[') else v['x']==v['y']
            return merged(equal==(op=='eq'),children)
        if op=='in':
            if v['x'] in v['S']:return merged(True,children)
            return merged(False,children) if a['S'].exact else self.unknown('Membership absent from an open collection',children)
        if op in ('first','last','nth','the','next','prev','rank'):return finish(self.select(a['S'],op,k=v.get('k'),x=v.get('x')))
        if op in ('span_before','span_after','between','gap','precedes'):
            p=self.page_id(v['x']);q=self.page_id(v['y']) if 'y' in v else None
            if p is None or 'y' in v and q is None:return self.unknown('Missing page position',children)
            if op=='precedes':
                if p==q and v['x']!=v['y']:return self.unknown('Within-page order is unverified',children)
                r=self.scanned(self.pos[p]<self.pos[q],[p,q],['page_sequence']);return finish(r)
            if op=='gap':return finish(self.scanned(max(0,abs(self.pos[p]-self.pos[q])-1),[p,q],['page_sequence']))
            if op=='between':
                lo,hi=sorted([self.pos[p],self.pos[q]]);ps=self.pages[lo+1:hi]
            else:ps=[page for page in self.scope(a['within']) if (self.pos[page]<self.pos[p] if op=='span_before' else self.pos[page]>self.pos[p])]
            return finish(self.scanned(ps,ps,['page_sequence'],ordered=True))
        if op in ('first_app','last_app','next_app','first_line','nth_line','line_count'):
            ps=self.pages[self.pos[self.page_id(v['after'])]+1:] if op=='next_app' else self.scope(a['span'])
            q=self.query('apps_of' if 'app' in op else 'lines_of',ps,v['c'])
            if op=='next_app' and q.value:
                end=self.pos[self.page_id(q.value[0])]
                ps=[p for p in ps if self.pos[p]<=end];q=self.query('apps_of',ps,v['c'])
            if op=='line_count':return finish(merged(len(q.value),[q]) if q.exact else self.unknown('Exact line count needs closed coverage',[q]))
            return finish(self.select(q,'last' if op=='last_app' else 'nth' if op=='nth_line' else 'first',k=v.get('k')))
        if op=='longest_streak':
            ps=self.scope(a['span']);q=self.query('pages_with',ps,v['c'])
            if not q.exact:return finish(self.unknown('Streak needs closed scope',[q]))
            longest=current=0;previous=None
            # A computed Seq[Page] may repeat a page once per appearance. Scope
            # membership is set-like; duplicates must not break a consecutive run.
            for p in sorted(set(ps),key=self.pos.get):
                current=current+1 if p in q.value and previous is not None and self.pos[p]==self.pos[previous]+1 else 1 if p in q.value else 0
                longest=max(longest,current);previous=p
            return finish(merged(longest,[q]))
        if op in ('next_line','prev_line','next_other_speaker','turns','exchanges'):
            return finish(self.discourse(op,a))
        if op in ('union','intersect','diff'):
            left,right=v['A'],v['B'];ls={key(x):x for x in left};rs={key(x):x for x in right}
            if op=='diff' and not all(c.exact for c in children):return self.unknown('Set difference requires closed operands',children)
            keys=ls.keys()|rs.keys() if op=='union' else ls.keys()&rs.keys() if op=='intersect' else ls.keys()-rs.keys()
            values=self.sort_values([{**rs,**ls}[k] for k in keys])
            return merged(values,children,ordered=self.ordered(values))
        if op=='distinct':return merged(unique(v['S']),children,ordered=a['S'].ordered)
        if op in ('exists','forall','none'):
            s=a['S']
            if op=='exists' and s.value:return merged(True,children)
            if not s.exact:return self.unknown('Quantifier requires closed domain for this answer',children)
            return merged(bool(s.value) if op=='exists' else not s.value if op=='none' else True,children)
        if op=='not':return merged(not v['p'],children) if a['p'].exact else self.unknown('Negation requires exact coverage',children)
        if op=='at_least':
            if v['n']<0:return Result(status='ERROR',exact=False,reason='Threshold must be nonnegative')
            if len(v['S'])>=v['n']:return merged(True,children)
            return merged(False,children) if a['S'].exact else self.unknown('Insufficient known members in open collection',children)
        if op in ('count','max','min','sum','mode'):
            s=a['S']
            if not s.exact:return self.unknown('Exact aggregation requires closed coverage',children)
            if op=='count':return merged(len(s.value),children)
            if op=='sum':return merged(sum(s.value),children)
            if not s.value:return merged(children=children,status='EMPTY',reason='Empty exact collection')
            if op=='mode':
                counts=Counter(key(x) for x in s.value);best=max(counts.values());winners=[k for k,n in counts.items() if n==best]
                if len(winners)!=1:return merged(children=children,status='AMBIGUOUS',reason='Mode tie')
                value=json.loads(winners[0])
            else:value=(max if op=='max' else min)(s.value)
            return merged(value,children)
        if op in ('compare','minus'):
            if not all(c.exact for c in children):return self.unknown('Comparison needs exact operands',children)
            return merged(v['x']-v['y'] if op=='minus' else 'more' if v['x']>v['y'] else 'fewer' if v['x']<v['y'] else 'equal',children)
        raise LanguageError('Runtime operation missing: '+op)

    def compose_character(self,speaker):
        target=self.navigate('char_of',speaker.value)
        return merged(target.value,[speaker,target],status=target.status,reason=target.reason)

    def discourse(self,op,args):
        ps=self.scope(args['span']) if 'span' in args else self.pages
        lines=self.query('lines',ps)
        if not lines.exact:return self.unknown('Discourse needs closed text/speaker coverage',[lines])
        if not lines.ordered:return self.unknown('Discourse requires verified within-page order',[lines])
        if op in ('next_line','prev_line'):return self.select(lines,'next' if op=='next_line' else 'prev',x=args['t'].value)
        speakers=[];supports=[lines]
        for text in lines.value:
            speaker=self.navigate('speaker',text)
            if speaker.status!='OK':return self.unknown('Unresolved line speaker',[*supports,speaker])
            character=self.compose_character(speaker);supports.append(character)
            if character.status!='OK':return self.unknown('Unresolved line identity',supports)
            speakers.append(character.value)
        if op=='next_other_speaker':
            text=args['t'].value
            if text not in lines.value:return merged(children=supports,status='EMPTY',reason='Anchor is not a line')
            i=lines.value.index(text)
            for c in speakers[i+1:]:
                if c!=speakers[i]:return merged(c,supports)
            return merged(children=supports,status='EMPTY',reason='No later different speaker')
        if op=='exchanges':
            c1,c2=args['c1'].value,args['c2'].value
            if c1==c2:return merged(0,supports)
            return merged(sum({a,b}=={c1,c2} for a,b in zip(speakers,speakers[1:])),supports)
        turns=[]
        for text,speaker in zip(lines.value,speakers):
            if not turns or turns[-1]['speaker']!=speaker:turns.append({'speaker':speaker,'lines':[],'pages':[]})
            turns[-1]['lines'].append(text)
            page=self.page_id(text)
            if page not in turns[-1]['pages']:turns[-1]['pages'].append(page)
        return merged(turns,supports,ordered=True)

    def execute(self,program,format='auto'):
        self.trace=[];self.type_cache={};node=None
        try:
            node=parse(program,format);infer(node)
            # Evaluate canonical commutative order for reproducible traces across input syntaxes.
            node=parse(canonical(node),'sexpr');result=self.eval(node)
        except (LanguageError,ExecutionLimit,RecursionError) as exc:
            result=Result(status='ERROR',exact=False,reason=str(exc))
        facts=set(result.facts);pending=list(facts)
        while pending:
            for fid in self.facts[pending.pop()]['premises']:
                if fid not in facts:facts.add(fid);pending.append(fid)
        origins=[self.facts[f]['origin'] for f in facts]+[self.nodes[n]['origin'] for n in result.nodes]+['V' for _ in result.visibility]
        support_pages={p for f in facts for p in self.facts[f]['page_ids']}
        support_pages.update(self.vis_evidence[e]['page_id'] for e in result.visibility)
        display=result.value;answer_vis=set()
        # Even a logically absorbed branch may put a name in the eventual question.
        named_answer_ok=all(step['status']=='OK' for step in self.trace if step['op'] in ('char','name_texts'))
        if result.status=='OK' and result.type in ('Char','Set[Char]','Seq[Char]'):
            values=[result.value] if result.type=='Char' else result.value;rendered=[]
            for cid in values:
                visible=self.vis[cid];forms=visible['verified_forms']
                if not forms:named_answer_ok=False;rendered.append(None);continue
                form=visible['canonical_name'] if visible['canonical_visible'] else sorted(forms,key=lambda s:(len(s),s))[0]
                rendered.append(form)
                eid=next(e for e in visible['verified_evidence_ids'] if self.vis_evidence[e]['normalized_form']==normalized(form))
                answer_vis.add(eid)
            display=rendered[0] if result.type=='Char' else rendered
        elif result.status=='OK' and result.type=='Page':display=self.pos[result.value]+1
        elif result.status=='OK' and result.type in ('Span','Seq[Page]','Set[Page]'):display=[self.pos[p]+1 for p in result.value]
        renderable=result.type in ('Bool3','Int','Cmp','Page','Char','Span','Seq[Page]','Set[Page]','Seq[Char]','Set[Char]')
        eligible=renderable and result.status=='OK' and named_answer_ok and (result.exact or isinstance(node,dict) and node.get('op')=='at_least' and result.value is True)
        all_vis=result.visibility|answer_vis
        origins+=['V' for _ in answer_vis];support_pages.update(self.vis_evidence[e]['page_id'] for e in answer_vis)
        return {**({'rich_evidence_sha256':self.rich_hash} if self.rich_hash else {}),'schema':'comics_qa.crl_result.v1','crl_version':VERSION,'chapter_id':self.graph['chapter_id'],
            'program':node,'canonical':canonical(node) if node is not None else None,'program_sha256':program_hash(node) if node is not None else None,
            'result':{'type':result.type,'value':result.value,'display':display,'status':result.status,'exact':result.exact,'reason':result.reason},
            'eligible_for_generation':bool(eligible),'proof_check':'pending_CRL-2',
            'proof':{'root':result.nid,'steps':self.trace,'facts':sorted(facts),'certificates':sorted(result.certificates),
                     'visibility_evidence':sorted(all_vis),'answer_visibility_evidence':sorted(answer_vis),'node_refs':sorted(result.nodes),
                     'key_support_pages':sorted(support_pages,key=self.pos.get),'range_pages':sorted(result.scope,key=self.pos.get),
                     'trust_min':min(origins,key=TRUST.get) if origins else None},
            'policy':{'closed_statuses':sorted(self.closed),'page_indexing':'1-based full supplied chapter',
                      'nonexact_final':'rejected except top-level at_least true','max_steps':self.max_steps}}
