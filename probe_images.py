from __future__ import annotations
import json, hashlib, subprocess, time
from pathlib import Path
from urllib.parse import quote
import requests

OUT=Path('probe_artifact'); OUT.mkdir(exist_ok=True)
base='https://www.81.cn/tp_207717/_attachment/2020/11/17/9938169_175d8b2541799381691307.jpg'
alt='https://www.81.cn/js_208592/jdt_208593/_attachment/2020/11/17/9943470_175d8b2541799381691307.jpg'
variants=[
 ('direct',base),('direct_q',base+'?v=1'),('http',base.replace('https://','http://')),
 ('alt',alt),('alt_http',alt.replace('https://','http://')),
 ('photo_host',base.replace('www.81.cn','photo.81.cn')),
 ('image_host',base.replace('www.81.cn','image.81.cn')),
 ('wayback_cdx','https://web.archive.org/cdx/search/cdx?url='+quote(base,safe='')+'&output=json&filter=statuscode:200&filter=mimetype:image/jpeg&fl=timestamp,original,statuscode,mimetype,length&limit=10'),
]
headersets=[
 ('browser',{'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36','Referer':'https://www.81.cn/tp_207717/9938169.html','Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8','Accept-Language':'zh-CN,zh;q=0.9'}),
 ('simple',{'User-Agent':'Mozilla/5.0','Referer':'https://www.81.cn/'}),
]
rows=[]
s=requests.Session()
try:
 r=s.get('https://www.81.cn/tp_207717/9938169.html',headers=headersets[0][1],timeout=60)
 rows.append({'name':'page_prime','status':r.status_code,'len':len(r.content),'ctype':r.headers.get('content-type'),'cookies':dict(s.cookies),'headers':dict(r.headers)})
except Exception as e: rows.append({'name':'page_prime','error':repr(e)})

for name,url in variants:
 for hname,h in headersets:
  rec={'name':name+'_'+hname,'url':url}
  try:
   r=s.get(url,headers=h,timeout=90,allow_redirects=True)
   data=r.content
   fn=OUT/(rec['name']+'.bin'); fn.write_bytes(data)
   rec.update(status=r.status_code,final_url=r.url,length=len(data),ctype=r.headers.get('content-type'),headers=dict(r.headers),magic=data[:32].hex(),sha256=hashlib.sha256(data).hexdigest(),text=data[:1000].decode('utf-8','replace'))
  except Exception as e: rec['error']=repr(e)
  rows.append(rec)

# Try Wayback CDX and available snapshots
try:
 cdx=requests.get('https://web.archive.org/cdx/search/cdx',params={'url':base,'output':'json','filter':['statuscode:200','mimetype:image/jpeg'],'fl':'timestamp,original,statuscode,mimetype,length','limit':'20'},timeout=90)
 (OUT/'cdx_response.txt').write_bytes(cdx.content)
 rows.append({'name':'cdx_api','status':cdx.status_code,'length':len(cdx.content),'ctype':cdx.headers.get('content-type'),'text':cdx.text[:3000]})
 if cdx.ok:
  j=cdx.json()
  for idx,row in enumerate(j[1:6],1):
   ts,orig=row[0],row[1]
   u=f'https://web.archive.org/web/{ts}id_/{orig}'
   rr=requests.get(u,headers=headersets[0][1],timeout=120)
   data=rr.content; (OUT/f'wayback_{idx}.bin').write_bytes(data)
   rows.append({'name':f'wayback_{idx}','url':u,'status':rr.status_code,'length':len(data),'ctype':rr.headers.get('content-type'),'magic':data[:32].hex(),'text':data[:1000].decode('utf-8','replace')})
except Exception as e: rows.append({'name':'cdx_api','error':repr(e)})

(OUT/'probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:
 print('\n###',r.get('name'))
 print({k:r.get(k) for k in ['status','length','ctype','final_url','error','magic']})
 print((r.get('text') or '')[:350].replace('\n',' '))
