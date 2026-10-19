import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[4]
base=root/'web/civic/offline'
manifest=json.loads((base/'assets-manifest.json').read_text(encoding='utf-8'))
for record in manifest['files']:
    content=(base/record['path']).read_bytes()
    assert len(content)==record['bytes'],record['path']
    assert hashlib.sha256(content).hexdigest()==record['sha256'],record['path']

def varint(blob,pos):
    value=shift=0
    while True:
        current=blob[pos];pos+=1;value|=(current&127)<<shift
        if current<128:return value,pos
        shift+=7
def fields(blob):
    pos=0
    while pos<len(blob):
        tag,pos=varint(blob,pos);number,wire=tag>>3,tag&7
        if wire==0:value,pos=varint(blob,pos)
        elif wire==2:
            size,pos=varint(blob,pos);value=blob[pos:pos+size];pos+=size
        else:raise ValueError(wire)
        yield number,value

glyphs={}
for _,stack in fields((base/'fonts/Noto Sans Regular/1024-1279.pbf').read_bytes()):
    for n,g in fields(stack):
        if n==3:
            values=dict(fields(g));glyphs[values[1]]=len(values.get(2,b''))
required='ҚқҒғҮүҰұӘәӨөҺһІіҢң'
for c in required:assert glyphs.get(ord(c),0)>0,c
archive=root/'data/civic/astana/tiles/astana.pmtiles'
meta=json.loads((root/'research/round-14-results/OFFLINE/ASSETS.json').read_text(encoding='utf-8'))
assert archive.stat().st_size==meta['archive_bytes']
assert hashlib.sha256(archive.read_bytes()).hexdigest()==meta['archive_sha256']
style=json.loads((base/'style.json').read_text(encoding='utf-8'))
assert style['glyphs'].startswith('/civic/offline/') and style['sprite'].startswith('/civic/offline/')
assert all(s['url'].startswith('pmtiles:///civic/offline/') for s in style['sources'].values())
print(json.dumps({'status':'PASS','verified_asset_files':len(manifest['files']),'kazakh_glyphs_with_bitmap':len(required),'archive_bytes':archive.stat().st_size,'archive_sha256':meta['archive_sha256'],'local_style_urls':True},ensure_ascii=False))
