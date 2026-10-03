import re, json
from pathlib import Path
root=Path('apps/desktop/dist')
assets=root/'assets'
chunks={p.name:p for p in assets.glob('*.js')}
qr=[p for p in chunks.values() if 'jsqr' in p.name.lower()]
assert qr, 'Missing lazy jsqr chunk'
static=re.compile(r'''\b(?:import|export)\s*(?:[^;()]*?\bfrom\s*)?["'](\./[^"']+\.js)["']''')
def closure(names):
    found=set()
    def visit(name):
        if name in found:return
        assert name in chunks, 'Missing referenced chunk'
        found.add(name)
        for path in static.findall(chunks[name].read_text(encoding='utf-8')):visit(Path(path).name)
    for name in names:visit(name)
    return found
html=(root/'index.html').read_text(encoding='utf-8')
entry=re.findall(r'<script[^>]+src="/?assets/([^"]+\.js)"',html)
assert entry, 'Missing entry module'
first=closure(entry)
pair=[name for name in chunks if name.startswith('RemotePairingPage-')]
assert pair, 'Missing pairing page chunk'
pair_static=closure(pair)
assert not any(p.name in first or p.name in pair_static or p.name in html for p in qr), 'jsqr was included in startup or pairing static graph'
scanner=[p for p in chunks.values() if p.name.startswith('PairingScanner-')]
assert scanner, 'Missing lazy scanner chunk'
assert any('import(' in p.read_text(encoding='utf-8') and any(q.name in p.read_text(encoding='utf-8') for q in qr) for p in scanner), 'Missing runtime jsqr import'
print(json.dumps({'jsqrChunks':[{'file':p.name,'bytes':p.stat().st_size} for p in qr], 'entryStaticChunkCount':len(first), 'jsqrInEntryStaticGraph':False, 'jsqrInPairingStaticGraph':False, 'jsqrPreloadedByHtml':False,'scannerChunks':[p.name for p in scanner]},ensure_ascii=False))
