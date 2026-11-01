"""CRL-1 parsers, canonical serialization and static types. Never evaluates Python."""
import ast
import hashlib
import json
import re
import unicodedata

VERSION = 'crl1.1'
MAX_DEPTH = 64
MAX_NODES = 2048


class LanguageError(ValueError):
    pass


def call(op, *args, **kw):
    return {'op':op,'args':list(args),'kw':kw}


SPECS = {}
def register(names, params, defaults=None, deferred=False):
    for name in names.split():
        SPECS[name]={'params':params.split() if params else [],'defaults':defaults or {},'deferred':deferred}


register('ctx unknown','')
register('page','i'); register('pages','i j'); register('char','name')
register('chars apps texts lines turns','span',{'span':call('ctx')})
register('apps_of lines_of pages_with pages_speaking first_app last_app first_line line_count longest_streak','c span',{'span':call('ctx')})
register('char_of','a'); register('page_of','x'); register('speaker speaker_char next_line prev_line next_other_speaker','t')
register('chars_on','p'); register('co_present','c unit span',{'unit':'page','span':call('ctx')})
register('present speaks_on silent_on','c p'); register('together','c1 c2 unit');register('is_named','c')
register('eq neq precedes compare minus','x y');register('in','x S')
register('first last distinct the count max min sum mode','S');register('nth','S k')
register('next prev rank','x S');register('span_before span_after','x within',{'within':call('ctx')})
register('between gap','x y');register('next_app','c after');register('nth_line','c k span',{'span':call('ctx')})
register('exchanges','c1 c2 span',{'span':call('ctx')})
register('filter map sort_by argmax argmin group_count','S fn');register('top_k','S fn k')
register('union intersect diff','A B');register('exists none','S fn',{'fn':None});register('forall','S fn')
register('and or','*');register('not','p');register('at_least','S n')
register('name_texts','s on',{'on':call('ctx')},True)
register('quote','s on',{'on':call('ctx')},True);register('panels','p',deferred=True)
register('panel_of','x',deferred=True);register('mentions_of first_mention','c span',{'span':call('ctx')},True)
register('mentioned_in offpanel_line','t',deferred=True)


def bind(node):
    op=node['op']
    if op not in SPECS:raise LanguageError(f'Unknown operation: {op}')
    spec=SPECS[op];args=node.get('args',[]);kw=node.get('kw',{})
    if spec['params']==['*']:
        if kw or len(args)<2:raise LanguageError(f'{op} needs at least two positional operands')
        return {'values':args}
    if len(args)>len(spec['params']):raise LanguageError(f'Too many arguments for {op}')
    result=dict(zip(spec['params'],args))
    for key,value in kw.items():
        if key not in spec['params'] or key in result:raise LanguageError(f'Unknown/duplicate argument {key} for {op}')
        result[key]=value
    for key in spec['params']:
        if key not in result:
            if key not in spec['defaults']:raise LanguageError(f'Missing {key} for {op}')
            result[key]=spec['defaults'][key]
    return result


TOKEN=re.compile(r'''\s*(?:(-?\d+)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|([A-Za-z_][A-Za-z_0-9]*)|([(),.=\\λ:]))''')


class Parser:
    def __init__(self,text,sexpr=False):
        self.tokens=[];self.i=0;self.sexpr=sexpr
        pos=0
        while pos<len(text):
            if not text[pos:].strip():break
            match=TOKEN.match(text,pos)
            if not match:raise LanguageError(f'Unexpected character at offset {pos}')
            self.tokens.append(next(x for x in match.groups() if x is not None));pos=match.end()
        self.depth=0

    def peek(self):return self.tokens[self.i] if self.i<len(self.tokens) else None
    def take(self,expected=None):
        value=self.peek()
        if value is None or expected is not None and value!=expected:raise LanguageError(f'Expected {expected or "expression"}, got {value}')
        self.i+=1;return value

    def expr(self):
        self.depth+=1
        if self.depth>MAX_DEPTH:raise LanguageError('Program nesting limit exceeded')
        try:return self.sexp() if self.sexpr else self.surface()
        finally:self.depth-=1

    def atom(self,value):
        if value[0:1] in ('"',"'"):
            parsed=ast.literal_eval(value)
            if not isinstance(parsed,str):raise LanguageError('Invalid string literal')
            return unicodedata.normalize('NFKC',parsed)
        if re.fullmatch(r'-?\d+',value):return int(value)
        if value in ('true','false'):return value=='true'
        if value=='unknown':return call('unknown')
        if value in ('more','fewer','equal'):return {'enum':value}
        if value in ('page','panel'):return value
        if not re.fullmatch(r'[A-Za-z_]\w*',value):raise LanguageError('Invalid atom')
        return {'var':value}

    def surface(self):
        token=self.take()
        if token=='let':
            bindings=[]
            while True:
                name=self.take();self.take('=');value=self.expr();bindings.append({'name':name,'value':value})
                if self.peek()!=',':break
                self.take(',')
            self.take('in');return {'let':bindings,'in':self.expr()}
        if token in ('\\','λ'):
            name=self.take();self.take('.');return {'lambda':{'param':name,'body':self.expr()}}
        if token=='(':
            value=self.expr();self.take(')');return value
        if self.peek()=='(' and re.fullmatch(r'[A-Za-z_]\w*',token):
            self.take('(');args=[];kw={}
            while self.peek()!=')':
                if self.i+1<len(self.tokens) and self.tokens[self.i+1]=='=':
                    key=self.take();self.take('=')
                    if key in kw:raise LanguageError('Duplicate keyword')
                    kw[key]=self.expr()
                else:
                    if kw:raise LanguageError('Positional argument after keyword')
                    args.append(self.expr())
                if self.peek()!=',':break
                self.take(',')
            self.take(')');return call(token,*args,**kw)
        return self.atom(token)

    def sexp(self):
        token=self.take()
        if token!='(':return self.atom(token)
        op=self.take()
        if op=='var':
            name=self.take();self.take(')');return {'var':name}
        if op=='lambda':
            name=self.take();body=self.expr();self.take(')');return {'lambda':{'param':name,'body':body}}
        if op=='let':
            bindings=[];self.take('(')
            while self.peek()!=')':
                self.take('(');name=self.take();value=self.expr();self.take(')');bindings.append({'name':name,'value':value})
            self.take(')');body=self.expr();self.take(')');return {'let':bindings,'in':body}
        args=[];kw={}
        while self.peek()!=')':
            if self.peek()==':':
                self.take(':');key=self.take()
                if key in kw:raise LanguageError('Duplicate keyword')
                kw[key]=self.expr()
            else:args.append(self.expr())
        self.take(')');return call(op,*args,**kw)


def validate_ast(node,depth=0,budget=None):
    if budget is None:budget=[MAX_NODES]
    budget[0]-=1
    if budget[0]<0 or depth>MAX_DEPTH:raise LanguageError('Program size/nesting limit exceeded')
    if type(node) in (int,bool,str):return node
    if not isinstance(node,dict):raise LanguageError('Expected literal or AST object')
    if set(node)=={'var'}:
        if not isinstance(node['var'],str) or not re.fullmatch(r'[A-Za-z_]\w*',node['var']):raise LanguageError('Invalid variable')
    elif set(node)=={'enum'}:
        if node['enum'] not in ('more','fewer','equal'):raise LanguageError('Invalid comparison enum')
    elif set(node)=={'lambda'}:
        value=node['lambda']
        if not isinstance(value,dict) or set(value)!={'param','body'}:raise LanguageError('Malformed lambda')
        validate_ast({'var':value['param']},depth+1,budget);validate_ast(value['body'],depth+1,budget)
    elif set(node)=={'let','in'}:
        if not isinstance(node['let'],list) or not node['let']:raise LanguageError('Empty/malformed let')
        seen=set()
        for b in node['let']:
            if not isinstance(b,dict) or set(b)!={'name','value'}:raise LanguageError('Malformed binding')
            validate_ast({'var':b['name']},depth+1,budget)
            if b['name'] in seen:raise LanguageError('Duplicate let binding')
            seen.add(b['name']);validate_ast(b['value'],depth+1,budget)
        validate_ast(node['in'],depth+1,budget)
    elif 'op' in node and set(node)<={'op','args','kw'}:
        if not isinstance(node['op'],str) or not isinstance(node.get('args',[]),list) or not isinstance(node.get('kw',{}),dict):raise LanguageError('Malformed call')
        bind(node)
        for arg in [*node.get('args',[]),*node.get('kw',{}).values()]:validate_ast(arg,depth+1,budget)
    else:raise LanguageError('Unknown AST shape')
    return node


def parse(program,format='auto'):
    try:
        if format not in ('auto','surface','sexpr','json'):raise LanguageError('Unknown input format')
        if isinstance(program,dict) or type(program) in (int,bool):return validate_ast(program)
        if not isinstance(program,str) or len(program)>100000:raise LanguageError('Invalid/oversized program')
        if format=='json' or format=='auto' and program.lstrip().startswith('{'):
            return validate_ast(json.loads(program))
        p=Parser(program,format=='sexpr' or format=='auto' and program.lstrip().startswith('('))
        node=p.expr()
        if p.peek() is not None:raise LanguageError('Trailing program tokens')
        return validate_ast(node)
    except (SyntaxError,RecursionError,ValueError) as exc:
        if isinstance(exc,LanguageError):raise
        raise LanguageError(str(exc)) from exc


COMMUTATIVE={'and','or','union','intersect','eq','neq'}
def canonical(node):
    if type(node) in (int,bool,str):return json.dumps(unicodedata.normalize('NFKC',node) if type(node) is str else node,ensure_ascii=False)
    if 'var' in node:return '(var '+node['var']+')'
    if 'enum' in node:return node['enum']
    if 'lambda' in node:return '(lambda '+node['lambda']['param']+' '+canonical(node['lambda']['body'])+')'
    if 'let' in node:return '(let ('+' '.join('('+b['name']+' '+canonical(b['value'])+')' for b in node['let'])+') '+canonical(node['in'])+')'
    args=[canonical(x) for x in node.get('args',[])]
    if node['op'] in COMMUTATIVE:args.sort()
    kw=[':'+k+' '+canonical(v) for k,v in sorted(node.get('kw',{}).items())]
    return '('+' '.join([node['op'],*kw,*args])+')'


def program_hash(node):return hashlib.sha256((VERSION+'\n'+canonical(node)).encode()).hexdigest()
def element(t):
    if t=='Span':return 'Page'
    if t.startswith(('Set[','Seq[')):return t[4:-1]
    raise LanguageError(f'Expected collection, got {t}')
def scope_type(t):return t in ('Page','Span','Seq[Page]','Set[Page]')


def infer(node,env=None,types=None):
    env={} if env is None else env;types={} if types is None else types
    def put(t):types[canonical(node)]=t;return t
    if type(node) is bool:return put('Bool3')
    if type(node) is int:return put('Int')
    if type(node) is str:return put('Str')
    if 'var' in node:
        if node['var'] not in env:raise LanguageError('Unbound variable: '+node['var'])
        return put(env[node['var']])
    if 'enum' in node:return put('Cmp')
    if 'lambda' in node:raise LanguageError('Lambdas are allowed only as operator arguments')
    if 'let' in node:
        local=dict(env)
        for b in node['let']:local[b['name']]=infer(b['value'],local,types)
        return put(infer(node['in'],local,types))
    op=node['op'];bound=bind(node);ts={}
    for k,v in bound.items():
        if k=='fn' or v is None:continue
        ts[k]=[infer(x,env,types) for x in v] if k=='values' else infer(v,env,types)
    def need(key,*allowed):
        if ts[key] not in allowed:raise LanguageError(f'{op}.{key}: expected {allowed}, got {ts[key]}')
    def scope(key):
        if not scope_type(ts[key]):raise LanguageError(f'{op}.{key}: expected page scope')
    def fn(expected=None):
        value=bound.get('fn')
        if value is None:return None
        if not isinstance(value,dict) or 'lambda' not in value:raise LanguageError(op+' requires a lambda')
        lam=value['lambda'];t=infer(lam['body'],{**env,lam['param']:element(ts['S'])},types)
        if expected and t not in expected:raise LanguageError(f'{op} lambda must return {expected}, got {t}')
        return t
    if op=='ctx':return put('Span')
    if op=='unknown':return put('Bool3')
    if op=='page':need('i','Int');return put('Page')
    if op=='pages':need('i','Int');need('j','Int');return put('Span')
    if op=='char':need('name','Str');return put('Char')
    if op in ('chars','apps','texts','lines','turns'):
        scope('span');return put({'chars':'Set[Char]','apps':'Seq[App]','texts':'Seq[Text]','lines':'Seq[Text]','turns':'Seq[Turn]'}[op])
    if op in ('apps_of','lines_of','pages_with','pages_speaking','first_app','last_app','first_line','line_count','longest_streak','mentions_of','first_mention'):
        need('c','Char');scope('span')
        return put({'apps_of':'Seq[App]','lines_of':'Seq[Text]','pages_with':'Seq[Page]','pages_speaking':'Seq[Page]',
            'first_app':'App','last_app':'App','first_line':'Text','line_count':'Int','longest_streak':'Int',
            'mentions_of':'Seq[Text]','first_mention':'Text'}[op])
    if op in ('char_of','speaker','speaker_char','next_line','prev_line','next_other_speaker','mentioned_in','offpanel_line'):
        need('a' if op=='char_of' else 't','App' if op=='char_of' else 'Text')
        return put({'char_of':'Char','speaker':'App','speaker_char':'Char','next_line':'Text','prev_line':'Text',
                    'next_other_speaker':'Char','mentioned_in':'Set[Char]','offpanel_line':'Bool3'}[op])
    if op in ('page_of','panel_of'):
        need('x','Page','App','Text','Tail','Panel');return put('Page' if op=='page_of' else 'Panel')
    if op in ('chars_on','panels'):
        need('p','Page');return put('Set[Char]' if op=='chars_on' else 'Seq[Panel]')
    if op=='co_present':need('c','Char');need('unit','Str');scope('span');return put('Set[Char]')
    if op in ('present','speaks_on','silent_on'):need('c','Char');need('p','Page');return put('Bool3')
    if op in ('together','exchanges'):
        need('c1','Char');need('c2','Char')
        if op=='together':need('unit','Page');return put('Bool3')
        scope('span');return put('Int')
    if op=='is_named':need('c','Char');return put('Bool3')
    if op in ('eq','neq'):
        if ts['x']!=ts['y']:raise LanguageError('Equality operands must have identical types')
        return put('Bool3')
    if op=='in':
        if ts['x']!=element(ts['S']):raise LanguageError('Membership element type mismatch')
        return put('Bool3')
    if op in ('first','last','the','mode'):return put(element(ts['S']))
    if op=='nth':need('k','Int');return put(element(ts['S']))
    if op in ('next','prev','rank'):
        if ts['x']!=element(ts['S']):raise LanguageError('Sequence item type mismatch')
        return put('Int' if op=='rank' else ts['x'])
    if op in ('precedes','between','gap'):
        for k in ('x','y'):need(k,'Page','App','Text','Tail')
        return put({'precedes':'Bool3','between':'Span','gap':'Int'}[op])
    if op in ('span_before','span_after'):need('x','Page','App','Text','Tail');scope('within');return put('Span')
    if op=='next_app':need('c','Char');need('after','Page','App','Text','Tail');return put('App')
    if op=='nth_line':need('c','Char');need('k','Int');scope('span');return put('Text')
    if op in ('filter','map','sort_by','argmax','argmin','group_count','top_k'):
        item=element(ts['S']);ret=fn(('Bool3',) if op=='filter' else ('Int',) if op in ('argmax','argmin','top_k') else None)
        if ret is None:raise LanguageError('Missing lambda')
        if op=='top_k':need('k','Int')
        if op in ('group_count','sort_by') and ret not in ('Int','Str','Page','Char','App','Text','Tail','Cmp','Bool3'):
            raise LanguageError('Key must be a scalar/entity')
        return put({'filter':ts['S'] if ts['S']!='Span' else 'Seq[Page]','map':f'Seq[{ret}]','sort_by':f'Seq[{item}]',
                    'argmax':item,'argmin':item,'group_count':f'Map[{ret},Int]','top_k':f'Seq[{item}]'}[op])
    if op in ('union','intersect','diff'):
        item=element(ts['A'])
        if item!=element(ts['B']):raise LanguageError('Set element type mismatch')
        return put(f'Set[{item}]')
    if op=='distinct':element(ts['S']);return put(ts['S'])
    if op in ('exists','forall','none'):element(ts['S']);fn(('Bool3',));return put('Bool3')
    if op in ('and','or'):
        if any(t!='Bool3' for t in ts['values']):raise LanguageError('Logic requires Bool3')
        return put('Bool3')
    if op=='not':need('p','Bool3');return put('Bool3')
    if op=='count':element(ts['S']);return put('Int')
    if op=='at_least':element(ts['S']);need('n','Int');return put('Bool3')
    if op in ('max','min','sum'):
        if element(ts['S'])!='Int':raise LanguageError('Numeric aggregation requires Int elements')
        return put('Int')
    if op in ('compare','minus'):need('x','Int');need('y','Int');return put('Cmp' if op=='compare' else 'Int')
    if op in ('quote','name_texts'):need('s','Str');scope('on');return put('Text' if op=='quote' else 'Seq[Text]')
    raise LanguageError('Type rule missing: '+op)
