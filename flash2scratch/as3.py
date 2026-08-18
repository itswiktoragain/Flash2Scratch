from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Handler: name: str; body: str
@dataclass
class Listener: owner: str; event: str; handler: str
@dataclass
class AS3Program:
    sources:list[Path]=field(default_factory=list); text:str=''; handlers:dict[str,Handler]=field(default_factory=dict); listeners:list[Listener]=field(default_factory=list); variables:dict[str,str]=field(default_factory=dict); display_objects:set[str]=field(default_factory=set)

COMMENT_RE=re.compile(r'//[^\n]*|/\*.*?\*/',re.S)
FUNC_RE=re.compile(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::\s*[\w.$<>]+)?\s*\{',re.M)
LISTENER_RE=re.compile(r'(?P<owner>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*|this|stage)\s*\.\s*addEventListener\s*\(\s*(?P<event>[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*)\s*,\s*(?P<handler>[A-Za-z_$][\w$]*)',re.M)
VAR_RE=re.compile(r'\bvar\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?::\s*(?P<type>[\w.$<>]+))?\s*(?:=\s*(?P<value>[^;]+))?;')

def _brace_body(text:str,open_brace:int)->tuple[str,int]:
    depth=0; quote=None; esc=False
    for i in range(open_brace,len(text)):
        ch=text[i]
        if quote:
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch==quote: quote=None
            continue
        if ch in "'\"": quote=ch
        elif ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:return text[open_brace+1:i],i+1
    return text[open_brace+1:],len(text)

def parse_sources(root:Path)->AS3Program:
    files=sorted(root.rglob('*.as')) if root.exists() else []
    p=AS3Program(sources=files)
    text=COMMENT_RE.sub('', '\n'.join(f.read_text(encoding='utf-8',errors='replace') for f in files))
    p.text=text
    for m in FUNC_RE.finditer(text):
        body,_=_brace_body(text,text.find('{',m.start())); p.handlers[m.group(1)]=Handler(m.group(1),body)
    for m in LISTENER_RE.finditer(text):
        owner='stage' if m.group('owner')=='this' else m.group('owner'); p.listeners.append(Listener(owner,m.group('event'),m.group('handler')))
        if owner!='stage': p.display_objects.add(owner.split('.')[0])
    for m in VAR_RE.finditer(text):
        name,typ,val=m.group('name'),m.group('type') or '',m.group('value')
        if re.search(r'(MovieClip|Sprite|SimpleButton|DisplayObject|Bitmap|TextField)$',typ): p.display_objects.add(name)
        elif val is not None: p.variables[name]=val.strip()
    for name in re.findall(r'\b([A-Za-z_$][\w$]*)\s*\.\s*(?:x|y|rotation|visible|alpha|scaleX|scaleY)\b',text):
        if name not in {'this','stage'}: p.display_objects.add(name)
    return p

def split_statements(body:str)->list[str]:
    out=[]; start=0; depth=0; quote=None; esc=False
    for i,ch in enumerate(body):
        if quote:
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch==quote: quote=None
            continue
        if ch in "'\"": quote=ch
        elif ch=='{': depth+=1
        elif ch=='}': depth=max(0,depth-1)
        elif ch==';' and depth==0:
            s=body[start:i].strip();
            if s: out.append(s)
            start=i+1
    tail=body[start:].strip()
    if tail: out.append(tail)
    return out
