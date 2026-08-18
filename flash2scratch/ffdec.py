from __future__ import annotations
import os, shutil, subprocess
from dataclasses import dataclass
from pathlib import Path

class FFDecError(RuntimeError): pass

@dataclass
class FFDecResult:
    root: Path; scripts: Path; frames: Path; sprites: Path; sounds: Path; xml: Path

def find_ffdec(explicit: str | None = None) -> str:
    candidates=[]
    if explicit: candidates.append(explicit)
    if os.getenv('FFDEC'): candidates.append(os.environ['FFDEC'])
    candidates += ['ffdec','ffdec.sh','ffdec-cli.exe','ffdec.bat']
    for c in candidates:
        p = c if Path(c).exists() else shutil.which(c)
        if p: return str(p)
    raise FFDecError('JPEXS FFDec not found. Put ffdec/ffdec.sh in PATH, set FFDEC, or pass --ffdec.')

def _run(ffdec: str, args: list[str]) -> str:
    p=subprocess.run([ffdec,'-cli',*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    if p.returncode != 0: raise FFDecError(f'FFDec failed ({p.returncode}):\n{p.stdout}')
    return p.stdout

def assert_as3(ffdec: str, swf: Path) -> None:
    tags=_run(ffdec,['-dumpSWF',str(swf)])
    if 'DoABC' not in tags and 'DoABCDefine' not in tags:
        raise FFDecError('This SWF does not contain AVM2 / ActionScript 3 DoABC tags.')

def export_swf(ffdec: str, swf: Path, root: Path) -> FFDecResult:
    root.mkdir(parents=True,exist_ok=True)
    _run(ffdec,['-format','script:as,frame:png,sprite:png,sound:mp3_wav','-export','script,frame,sprite,sound,symbolClass',str(root),str(swf)])
    xml=root/'movie.xml'; _run(ffdec,['-swf2xml',str(swf),str(xml)])
    return FFDecResult(root,root/'scripts',root/'frames',root/'sprites',root/'sounds',xml)
