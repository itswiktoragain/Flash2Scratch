from __future__ import annotations
import re
from .as3 import split_statements

KEYS={'Keyboard.LEFT':'left arrow','37':'left arrow','Keyboard.UP':'up arrow','38':'up arrow','Keyboard.RIGHT':'right arrow','39':'right arrow','Keyboard.DOWN':'down arrow','40':'down arrow','Keyboard.SPACE':'space','32':'space','Keyboard.ENTER':'enter','13':'enter'}

class AS3Compiler:
    def __init__(self,project,program,report,fps=30):
        self.p=project; self.program=program; self.report=report; self.y=20
        for n,v in program.variables.items(): self.p.global_var(n,self._literal(v))
        for n in sorted(program.display_objects): self.p.sprite(n)
    def _literal(self,t):
        t=str(t).strip()
        if t in ('true','false'): return 1 if t=='true' else 0
        if len(t)>=2 and t[0] in "'\"" and t[-1]==t[0]: return t[1:-1]
        try:return float(t) if '.' in t else int(t)
        except:return t
    def _top(self,b,opcode,**kw):
        x=b.add(opcode,top=True,x=20,y=self.y,**kw); self.y+=120; return x
    def compile(self):
        for l in self.program.listeners:
            h=self.program.handlers.get(l.handler)
            if h:self._listener(l,h)
            else:self.report.unsupported.append(f'missing handler {l.handler}')
    def _listener(self,l,h):
        target=self.p.stage if l.owner=='stage' else self.p.sprite(l.owner.split('.')[0]); b=target.blocks
        if l.event=='Event.ENTER_FRAME':
            hat=self._top(b,'event_whenflagclicked'); forever=b.add('control_forever',parent=hat); b.blocks[hat]['next']=forever; first=self._body(b,h.body,forever)
            if first:b.blocks[forever]['inputs']['SUBSTACK']=[2,first]
            self.report.translated.append(f'{l.handler}: ENTER_FRAME'); return
        if l.event=='MouseEvent.CLICK':
            hat=self._top(b,'event_whenthisspriteclicked'); b.blocks[hat]['next']=self._body(b,h.body,hat); self.report.translated.append(f'{l.handler}: CLICK'); return
        if l.event=='KeyboardEvent.KEY_DOWN':
            found=False
            for m in re.finditer(r'if\s*\(\s*\w+\.keyCode\s*={2,3}\s*([^\)]+)\)\s*\{([^{}]*)\}',h.body,re.S):
                key=KEYS.get(m.group(1).strip())
                if not key: continue
                found=True; hat=self._top(b,'event_whenkeypressed',fields={'KEY_OPTION':[key,None]}); b.blocks[hat]['next']=self._body(b,m.group(2),hat)
            if found:self.report.translated.append(f'{l.handler}: KEY_DOWN')
            else:self.report.unsupported.append(f'{l.handler}: dynamic KEY_DOWN handler')
            return
        self.report.unsupported.append(f'event {l.event}')
    def _body(self,b,body,parent):
        ids=[]
        for s in split_statements(body):
            x=self._stmt(b,' '.join(s.split()),parent)
            if x:ids.append(x)
        if ids:b.chain(ids); b.blocks[ids[0]]['parent']=parent
        return ids[0] if ids else None
    def _stmt(self,b,s,parent):
        m=re.fullmatch(r'([A-Za-z_$][\w$]*)\.(x|y|rotation)\s*([+\-])=\s*([-+]?\d+(?:\.\d+)?)',s)
        if m:
            obj,prop,op,n=m.groups(); vid=self.p.global_var(f'{obj}.{prop}'); val=float(n)*(1 if op=='+' else -1); self.report.translated.append(s); return b.add('data_changevariableby',parent=parent,inputs={'VALUE':b.num(val)},fields={'VARIABLE':[f'{obj}.{prop}',vid]})
        m=re.fullmatch(r'([A-Za-z_$][\w$]*)\s*([+\-])=\s*([-+]?\d+(?:\.\d+)?)',s)
        if m:
            n,op,v=m.groups(); vid=self.p.global_var(n); val=float(v)*(1 if op=='+' else -1); self.report.translated.append(s); return b.add('data_changevariableby',parent=parent,inputs={'VALUE':b.num(val)},fields={'VARIABLE':[n,vid]})
        m=re.fullmatch(r'([A-Za-z_$][\w$]*)\s*=\s*(.+)',s)
        if m:
            n,v=m.groups(); vid=self.p.global_var(n); self.report.translated.append(s); return b.add('data_setvariableto',parent=parent,inputs={'VALUE':b.text(self._literal(v))},fields={'VARIABLE':[n,vid]})
        m=re.fullmatch(r'(?:this\.)?gotoAndStop\s*\(([^)]+)\)',s)
        if m:self.report.translated.append(s); return b.add('looks_switchbackdropto',parent=parent,inputs={'BACKDROP':b.text(self._literal(m.group(1)))})
        if re.fullmatch(r'(?:this\.)?nextFrame\s*\(\s*\)',s): self.report.translated.append(s); return b.add('looks_nextbackdrop',parent=parent)
        m=re.fullmatch(r'(?:trace|console\.log)\s*\((.*)\)',s)
        if m:self.report.translated.append(s); return b.add('looks_say',parent=parent,inputs={'MESSAGE':b.text(self._literal(m.group(1)))})
        if s and not re.match(r'^(var |const |import |package |super\s*\()',s): self.report.unsupported.append(s[:180])
        return None
