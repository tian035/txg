from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps

PAGE='https://www.universalinternetlibrary.ru/book/94545/chitat_knigu.shtml'
OUT=Path('mig15_monograph_probe'); IMG=OUT/'images'; OUT.mkdir(exist_ok=True); IMG.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36'})

def main():
    r=S.get(PAGE,timeout=(20,180)); r.raise_for_status(); r.encoding=r.apparent_encoding or r.encoding
    (OUT/'page.html').write_text(r.text,encoding='utf-8',errors='replace')
    soup=BeautifulSoup(r.text,'html.parser')
    urls=[]
    for tag in soup.find_all(['img','source']):
        for attr in ('src','data-src','data-original','data-lazy-src'):
            v=tag.get(attr)
            if v: urls.append(urljoin(r.url,v))
        for attr in ('srcset','data-srcset'):
            v=tag.get(attr)
            if v: urls.extend(urljoin(r.url,x.strip().split()[0]) for x in v.split(',') if x.strip())
    # Images sometimes occur only in scripts/CSS.
    for m in re.findall(r'''["']([^"']+?\.(?:jpe?g|png|webp)(?:\?[^"']*)?)["']''',r.text,re.I):
        urls.append(urljoin(r.url,m))
    urls=list(dict.fromkeys(u for u in urls if not u.startswith('data:')))
    rows=[]; errors=[]
    for i,u in enumerate(urls):
        try:
            rr=S.get(u,headers={'Referer':r.url},timeout=(15,90)); rr.raise_for_status()
            suf=Path(urlparse(rr.url).path).suffix.lower(); suf='.jpg' if suf not in {'.jpg','.jpeg','.png','.webp'} else ('.jpg' if suf=='.jpeg' else suf)
            path=IMG/f'{i:03d}_{hashlib.sha1(u.encode()).hexdigest()[:8]}{suf}'; path.write_bytes(rr.content)
            with Image.open(path) as im: im.load(); w,h=im.size; fmt=im.format
            if w<280 or h<160 or len(rr.content)<10000: path.unlink(missing_ok=True); continue
            rows.append({'index':i,'file':str(path),'source_image':rr.url,'width':w,'height':h,'format':fmt,'bytes':len(rr.content),'sha256':hashlib.sha256(rr.content).hexdigest()})
            print('OK',i,w,h,len(rr.content),rr.url,flush=True)
        except Exception as e: errors.append({'index':i,'url':u,'error':repr(e)})
    # dedupe
    out=[]; seen=set()
    for x in rows:
        if x['sha256'] in seen: continue
        seen.add(x['sha256']); out.append(x)
    (OUT/'manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    font=ImageFont.load_default(); cols=4; tw,th,lh=320,220,45; cw,ch=tw+14,th+lh+14
    for sn,start in enumerate(range(0,len(out),24),1):
        batch=out[start:start+24]; nr=(len(batch)+cols-1)//cols; canv=Image.new('RGB',(cols*cw,nr*ch),'white'); d=ImageDraw.Draw(canv)
        for j,x in enumerate(batch):
            xx=(j%cols)*cw+7; yy=(j//cols)*ch+7
            with Image.open(x['file']) as im: im=ImageOps.exif_transpose(im).convert('RGB'); im.thumbnail((tw,th)); canv.paste(im,(xx+(tw-im.width)//2,yy+(th-im.height)//2))
            d.multiline_text((xx,yy+th+3),f"{start+j:03d} src#{x['index']} {x['width']}x{x['height']}\n{x['source_image'][-55:]}",fill='black',font=font,spacing=1)
        canv.save(OUT/f'contact_{sn:02d}.jpg',quality=92)
    if not out: raise SystemExit('No images')
if __name__=='__main__': main()
