from __future__ import annotations
import re
from dataclasses import dataclass,field
from pathlib import Path
@dataclass
class SWFInfo:
    width:int=480; height:int=360; frame_rate:float=30.0; instances:dict[str,int]=field(default_factory=dict)
def parse_swf_xml(path:Path)->SWFInfo:
    if not path.exists(): return SWFInfo()
    text=path.read_text(encoding='utf-8',errors='replace'); info=SWFInfo()
    m=re.search(r'\bframeRate="([0-9.+-]+)"',text,re.I)
    if m:
        try: info.frame_rate=float(m.group(1))
        except ValueError: pass
    for tag in re.findall(r'<[^>]*PlaceObject[^>]*>',text,re.I):
        n=re.search(r'\bname="([^"]+)"',tag); c=re.search(r'\bcharacterId="(\d+)"',tag,re.I)
        if n and c: info.instances.setdefault(n.group(1),int(c.group(1)))
    return info
