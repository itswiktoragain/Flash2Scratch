import json,zipfile
from pathlib import Path
from flash2scratch.as2 import parse_sources as parse_as2_sources
from flash2scratch.as3 import parse_sources
from flash2scratch.ffdec import swf_version
from flash2scratch.sb3 import ScratchProject

def test_parse_as3(tmp_path:Path):
    d=tmp_path/'scripts';d.mkdir();(d/'Main.as').write_text('function k(e:KeyboardEvent):void { player.x -= 5; } stage.addEventListener(KeyboardEvent.KEY_DOWN,k); var score:int=2; var player:MovieClip;')
    p=parse_sources(d);assert 'k' in p.handlers;assert p.variables['score']=='2';assert 'player' in p.display_objects

def test_parse_flash8_as2(tmp_path:Path):
    d=tmp_path/'scripts';d.mkdir();(d/'Main.as').write_text('var score = 2; player.onEnterFrame = function() { if (Key.isDown(Key.LEFT)) { player._x -= 5; } }; button.onRelease = function() { score += 1; };')
    p=parse_as2_sources(d)
    assert p.variables['score']=='2'
    assert 'player' in p.display_objects
    assert any(x.event=='Event.ENTER_FRAME' for x in p.listeners)
    assert any(x.event=='MouseEvent.CLICK' for x in p.listeners)

def test_swf8_header_is_valid(tmp_path:Path):
    f=tmp_path/'old.swf';f.write_bytes(b'FWS'+bytes([8])+b'placeholder')
    assert swf_version(f)==8

def test_sb3(tmp_path:Path):
    p=ScratchProject();p.global_var('score',0);p.sprite('player');o=tmp_path/'x.sb3';p.save(o)
    with zipfile.ZipFile(o) as z:
        j=json.loads(z.read('project.json'));assert j['meta']['semver']=='3.0.0';assert all(c['md5ext'] in z.namelist() for t in j['targets'] for c in t['costumes'])
