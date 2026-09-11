from __future__ import annotations
import json, hashlib
from pathlib import Path
import requests
OUT=Path('probe_fast_artifact'); OUT.mkdir(exist_ok=True)
page='https://www.81.cn/tp_207717/9938169.html'
rel='/tp_207717/_attachment/2020/11/17/9938169_175d8b2541799381691307.jpg'
urls=[
 'https://www.81.cn'+rel,
 'http://www.81.cn'+rel,
 'https://www.81.cn/js_208592/jdt_208593/_attachment/2020/11/17/9943470_175d8b2541799381691307.jpg',
 'http://www.81.cn/js_208592/jdt_208593/_attachment/2020/11/17/9943470_175d8b2541799381691307.jpg',
 'https://photo.81.cn'+rel,
]
hdrs=[
 {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36','Referer':page,'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8','Accept-Language':'zh-CN,zh;q=0.9','Sec-Fetch-Dest':'image','Sec-Fetch-Mode':'no-cors','Sec-Fetch-Site':'same-origin'},
 {'User-Agent':'curl/8.5.0','Referer':page},
]
s=requests.Session(); rows=[]
try:
 r=s.get(page,headers=hdrs[0],timeout=(8,20)); rows.append({'page':r.status_code,'len':len(r.content),'headers':dict(r.headers),'cookies':dict(s.cookies)})
except Exception as e: rows.append({'page_error':repr(e)})
for i,u in enumerate(urls):
 for j,h in enumerate(hdrs):
  rec={'i':i,'h':j,'url':u}
  try:
   r=s.get(u,headers=h,timeout=(8,20),allow_redirects=True)
   b=r.content; (OUT/f'{i}_{j}.bin').write_bytes(b)
   rec.update(status=r.status_code,len=len(b),ctype=r.headers.get('content-type'),final=r.url,headers=dict(r.headers),magic=b[:20].hex(),text=b[:1000].decode('utf-8','replace'))
  except Exception as e: rec['error']=repr(e)
  rows.append(rec)
(OUT/'result.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:
 print(json.dumps({k:r.get(k) for k in ['i','h','url','status','len','ctype','final','error','magic','text']},ensure_ascii=False)[:1400])
