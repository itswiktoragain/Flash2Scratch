from __future__ import annotations
import argparse,sys
from pathlib import Path
from . import __version__
from .converter import convert
from .ffdec import FFDecError

def main(argv=None):
    p=argparse.ArgumentParser(description='Convert ActionScript 3 / AVM2 SWF to Scratch 3 SB3')
    p.add_argument('swf'); p.add_argument('output',nargs='?'); p.add_argument('--ffdec'); p.add_argument('--keep-temp'); p.add_argument('--version',action='version',version=f'Flash2Scratch {__version__}')
    a=p.parse_args(argv); swf=Path(a.swf); out=Path(a.output) if a.output else swf.with_suffix('.sb3')
    try:r=convert(swf,out,ffdec=a.ffdec,keep_temp=a.keep_temp)
    except (FFDecError,FileNotFoundError,OSError) as e: print(f'flash2scratch: error: {e}',file=sys.stderr); return 2
    print(r.text(),end=''); print(f'Created: {out}'); return 0

if __name__=='__main__':raise SystemExit(main())
