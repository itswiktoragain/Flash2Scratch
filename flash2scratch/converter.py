from __future__ import annotations
import re,tempfile
from pathlib import Path
from .as3 import parse_sources
from .compiler import AS3Compiler
from .ffdec import assert_as3,export_swf,find_ffdec
from .report import ConversionReport
from .sb3 import Asset,ScratchProject
from .swfxml import parse_swf_xml

def _natural(p):return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)',str(p))]
def _pngs(root):return sorted(root.rglob('*.png'),key=_natural) if root.exists() else []
def _sprite(root,cid):
    if not root.exists():return None
    hits=[p for p in root.rglob('*.png') if re.search(rf'(^|\D){cid}(\D|$)',p.stem)]
    return sorted(hits,key=lambda p:(len(str(p)),str(p)))[0] if hits else None

def convert(swf,output,*,ffdec=None,keep_temp=None):
    swf=Path(swf).expanduser().resolve(); output=Path(output).expanduser().resolve()
    if not swf.is_file():raise FileNotFoundError(swf)
    exe=find_ffdec(ffdec); report=ConversionReport(swf,output); assert_as3(exe,swf)
    if keep_temp:
        root=Path(keep_temp).expanduser().resolve(); result=export_swf(exe,swf,root); _compile(result,output,report)
    else:
        with tempfile.TemporaryDirectory(prefix='flash2scratch-') as td:_compile(export_swf(exe,swf,Path(td)),output,report)
    return report

def _compile(result,output,report):
    info=parse_swf_xml(result.xml); program=parse_sources(result.scripts); report.source_files=len(program.sources); project=ScratchProject(); frames=_pngs(result.frames); report.frame_assets=len(frames)
    for i,f in enumerate(frames,1): project.add_stage_costume(f,f'frame {i}')
    if not frames: report.warnings.append('FFDec exported no main-timeline frame PNGs; using a blank stage.')
    for name in sorted(program.display_objects):
        spr=project.sprite(name); cid=info.instances.get(name); asset=_sprite(result.sprites,cid) if cid is not None else None
        if asset: spr.costumes=[Asset(asset.read_bytes(),'png',name)]; report.sprite_assets+=1
    AS3Compiler(project,program,report,info.frame_rate).compile(); project.save(output); output.with_suffix(output.suffix+'.report.txt').write_text(report.text(),encoding='utf-8')
