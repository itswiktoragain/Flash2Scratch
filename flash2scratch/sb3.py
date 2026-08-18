from __future__ import annotations
import hashlib,json,struct,uuid,zipfile
from dataclasses import dataclass,field
from pathlib import Path
from typing import Any

def uid(): return uuid.uuid4().hex[:20]
def png_size(data:bytes): return struct.unpack('>II',data[16:24]) if data[:8]==b'\x89PNG\r\n\x1a\n' and len(data)>=24 else (1,1)
TRANSPARENT_SVG=b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
BLANK_STAGE_SVG=b'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><rect width="480" height="360" fill="white"/></svg>'

class BlockBuilder:
    def __init__(self): self.blocks={}
    def add(self,opcode,*,parent=None,next_=None,inputs=None,fields=None,top=False,x=0,y=0,shadow=False):
        bid=uid(); o={'opcode':opcode,'next':next_,'parent':parent,'inputs':inputs or {},'fields':fields or {},'shadow':shadow,'topLevel':top}
        if top:o.update({'x':x,'y':y})
        self.blocks[bid]=o; return bid
    def chain(self,ids):
        for a,b in zip(ids,ids[1:]): self.blocks[a]['next']=b; self.blocks[b]['parent']=a
        return ids[0] if ids else None
    @staticmethod
    def num(v): return [1,[4,str(v)]]
    @staticmethod
    def text(v): return [1,[10,str(v)]]

@dataclass
class Asset:
    data:bytes; ext:str; name:str
    @property
    def md5(self): return hashlib.md5(self.data).hexdigest()
    @property
    def filename(self): return f'{self.md5}.{self.ext}'
@dataclass
class Target:
    name:str; is_stage:bool; blocks:BlockBuilder=field(default_factory=BlockBuilder); costumes:list[Asset]=field(default_factory=list); variables:dict=field(default_factory=dict); broadcasts:dict=field(default_factory=dict); x:float=0;y:float=0;size:float=100;direction:float=90;visible:bool=True

class ScratchProject:
    def __init__(self): self.stage=Target('Stage',True); self.sprites={}; self._assets={}
    def sprite(self,name):
        if name not in self.sprites:
            t=Target(name,False); t.costumes.append(Asset(TRANSPARENT_SVG,'svg','proxy')); self.sprites[name]=t
        return self.sprites[name]
    def global_var(self,name,value=0):
        for vid,pair in self.stage.variables.items():
            if pair[0]==name:return vid
        vid=uid(); self.stage.variables[vid]=[name,value]; return vid
    def add_stage_costume(self,path:Path,name=None): self.stage.costumes.append(Asset(path.read_bytes(),path.suffix.lower().lstrip('.'),name or path.stem))
    def _costume(self,a):
        self._assets[a.filename]=a
        if a.ext=='png':
            w,h=png_size(a.data); return {'assetId':a.md5,'name':a.name,'bitmapResolution':1,'md5ext':a.filename,'dataFormat':'png','rotationCenterX':w/2,'rotationCenterY':h/2}
        return {'assetId':a.md5,'name':a.name,'md5ext':a.filename,'dataFormat':a.ext,'rotationCenterX':0.5,'rotationCenterY':0.5}
    def _target(self,t,layer):
        if not t.costumes:t.costumes.append(Asset(BLANK_STAGE_SVG if t.is_stage else TRANSPARENT_SVG,'svg','backdrop1' if t.is_stage else 'proxy'))
        o={'isStage':t.is_stage,'name':t.name,'variables':t.variables if t.is_stage else {},'lists':{},'broadcasts':t.broadcasts if t.is_stage else {},'blocks':t.blocks.blocks,'comments':{},'currentCostume':0,'costumes':[self._costume(a) for a in t.costumes],'sounds':[],'volume':100,'layerOrder':layer}
        if t.is_stage:o.update({'tempo':60,'videoTransparency':50,'videoState':'off','textToSpeechLanguage':None})
        else:o.update({'visible':t.visible,'x':t.x,'y':t.y,'size':t.size,'direction':t.direction,'draggable':False,'rotationStyle':'all around'})
        return o
    def to_json(self):
        self._assets={}; targets=[self._target(self.stage,0)]+[self._target(t,i+1) for i,t in enumerate(self.sprites.values())]
        return {'targets':targets,'monitors':[],'extensions':[],'meta':{'semver':'3.0.0','vm':'flash2scratch-0.1.0','agent':'Flash2Scratch'}}
    def save(self,path:Path):
        project=self.to_json(); path.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('project.json',json.dumps(project,separators=(',',':')))
            for fn,a in self._assets.items(): z.writestr(fn,a.data)
