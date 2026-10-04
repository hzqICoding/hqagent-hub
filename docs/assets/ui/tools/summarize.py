import json,html,math
from pathlib import Path
from PIL import Image,ImageDraw
from audit_paths import OUT as out
data=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
folder=out/'contact-sheets';folder.mkdir(exist_ok=True)
profiles=sorted(set(row['profile'] for row in data['captures']))
summary=[]
for profile in profiles:
 rows=sorted([row for row in data['captures'] if row['profile']==profile],key=lambda row:row['code'])
 for n in range(0,len(rows),8):
  part=rows[n:n+8];mobile=profile.startswith('mobile');cellw,cellh=(250,565) if mobile else (480,325);cols=4 if mobile else 2
  sheet=Image.new('RGB',(cellw*cols,cellh*math.ceil(len(part)/cols)),'#ddd');draw=ImageDraw.Draw(sheet)
  for i,row in enumerate(part):
   im=Image.open(out/row['path']);im.thumbnail((cellw-6,cellh-28));x=i%cols*cellw;y=i//cols*cellh;sheet.paste(im,(x,y+25));draw.text((x+3,y+5),row['code']+' '+row['name'],fill='black')
  sheet.save(folder/f'{profile}-{n//8+1:02}.jpg',quality=92)
 for row in rows:
  metrics=json.loads((out/row['metrics']).read_text(encoding='utf-8'))
  small=[item for item in metrics['controls'] if item['width']<44 or item['height']<44]
  low=[item for item in metrics['text'] if item['ratio']<4.5 and not item['disabled']]
  summary.append({'profile':profile,'code':row['code'],'smallTargetCount':len(small),'smallTargets':small,'lowContrast':low,'overflow':metrics['horizontalOverflow'],'rootFont':metrics['rootFont'],'nativeSelects':metrics['visibleNativeSelects']})
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
parts=['<!doctype html><meta charset="utf-8"><title>UI 审计截图索引</title><style>body{font:15px system-ui;margin:24px;background:#eee}nav{position:sticky;top:0;background:white;padding:12px}section{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}article{background:white;padding:12px}img{max-width:100%;max-height:540px;object-fit:contain}h2{margin-top:48px}</style><h1>UI 审计 · 全部为合成 mock 数据</h1><p>点击图片查看原尺寸。未验证实体手机软键盘、权限弹窗或真实网络性能。</p><nav>']
for profile in profiles:parts.append(f'<a href="#{profile}">{profile}</a>　')
parts.append('</nav>')
for profile in profiles:
 parts.append(f'<h2 id="{profile}">{profile}</h2><section>')
 for row in sorted([row for row in data['captures'] if row['profile']==profile],key=lambda row:row['code']):parts.append(f'<article><h3>{row["code"]} {html.escape(row["name"])}</h3><a href="{row["path"]}"><img loading="lazy" src="{row["path"]}" alt="{row["code"]}"></a><p>{html.escape(row["route"])}</p></article>')
 parts.append('</section>')
(out/'gallery.html').write_text(''.join(parts),encoding='utf-8')
print(json.dumps({'screenshots':len(summary),'profiles':profiles,'horizontalOverflow':[(s['profile'],s['code']) for s in summary if s['overflow']]},ensure_ascii=False))
