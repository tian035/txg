from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageDraw, ImageFont, ImageOps

PAGE = 'https://www.universalinternetlibrary.ru/book/94545/chitat_knigu.shtml'
OUT = Path('mig15_antung_1951')
IMG = OUT / 'images'
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36'})


def get_img_urls(tag: Tag) -> list[str]:
    vals = []
    for attr in ('src', 'data-src', 'data-original', 'data-lazy-src'):
        if tag.get(attr): vals.append(tag.get(attr))
    for attr in ('srcset','data-srcset'):
        if tag.get(attr):
            vals.extend(x.strip().split()[0] for x in tag.get(attr).split(','))
    return [urljoin(PAGE, v) for v in vals if v and not v.startswith('data:')]


def context(tag: Tag) -> str:
    chunks = []
    # parent and nearby preceding/following elements
    for p in [tag.parent, getattr(tag.parent, 'parent', None)]:
        if isinstance(p, Tag):
            chunks.append(' '.join(p.get_text(' ', strip=True).split()))
    for el in list(tag.find_all_previous(limit=5))[::-1] + list(tag.find_all_next(limit=8)):
        if isinstance(el, Tag):
            t = ' '.join(el.get_text(' ', strip=True).split())
            if t: chunks.append(t)
    return ' | '.join(dict.fromkeys(chunks))[:2500]


def main() -> None:
    r = S.get(PAGE, timeout=(20,180))
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    (OUT/'page.html').write_text(r.text, encoding='utf-8', errors='replace')
    soup = BeautifulSoup(r.text, 'html.parser')
    rows=[]; errors=[]; n=0
    for img in soup.find_all('img'):
        ctx=context(img)
        low=ctx.lower()
        # Select captions explicitly mentioning Antung and 1951, or aircraft 111025.
        if not (('аньдун' in low and '1951' in low) or '111025' in low):
            continue
        for url in get_img_urls(img):
            try:
                rr=S.get(url, headers={'Referer':PAGE}, timeout=(20,180))
                rr.raise_for_status()
                suffix=Path(urlparse(rr.url).path).suffix.lower()
                if suffix not in {'.jpg','.jpeg','.png','.webp'}: suffix='.jpg'
                if suffix=='.jpeg': suffix='.jpg'
                digest=hashlib.sha1(url.encode()).hexdigest()[:10]
                path=IMG/f'antung_{n:02d}_{digest}{suffix}'
                path.write_bytes(rr.content)
                with Image.open(path) as im:
                    im.load(); w,h=im.size; fmt=im.format
                if w<300 or h<180 or len(rr.content)<12000:
                    path.unlink(missing_ok=True); continue
                rows.append({'key':f'antung_{n:02d}','file':str(path),'source_page':PAGE,'source_image':rr.url,'caption_context':ctx,'width':w,'height':h,'format':fmt,'bytes':len(rr.content),'sha256':hashlib.sha256(rr.content).hexdigest()})
                print('OK',path,w,h,len(rr.content),ctx[:300],flush=True)
                n+=1
            except Exception as exc:
                errors.append({'url':url,'error':repr(exc),'context':ctx})
    # Deduplicate file content.
    ded=[]; seen=set()
    for row in rows:
        if row['sha256'] in seen: continue
        seen.add(row['sha256']); ded.append(row)
    (OUT/'manifest.json').write_text(json.dumps(ded,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    if ded:
        font=ImageFont.load_default(); tw,th,lh=500,320,70
        canvas=Image.new('RGB',(tw+20,len(ded)*(th+lh+20)),'white'); d=ImageDraw.Draw(canvas)
        for i,row in enumerate(ded):
            y=i*(th+lh+20)+10
            with Image.open(row['file']) as im:
                im=ImageOps.exif_transpose(im).convert('RGB'); im.thumbnail((tw,th)); canvas.paste(im,(10+(tw-im.width)//2,y+(th-im.height)//2))
            d.multiline_text((10,y+th+4),f"{row['key']} {row['width']}x{row['height']} {row['bytes']//1024}KB\n{row['caption_context'][:100]}",fill='black',font=font)
        canvas.save(OUT/'contact.jpg',quality=92)
    else:
        raise SystemExit('No matching Antung 1951 image found')

if __name__=='__main__': main()
