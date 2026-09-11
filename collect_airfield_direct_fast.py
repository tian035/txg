from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT = Path('airfield_direct_fast')
IMG = OUT / 'images'
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

ITEMS = [
    {
        'key': 'antung_kramarenko_1951',
        'url': 'https://interaffairs.ru/i/2016/07/c600f07a9ac4d058b6d716f83d189189.jpg',
        'source_page': 'https://interaffairs.ru/news/show/15651',
        'caption': 'S. M. Kramarenko in a MiG-15 cockpit, Antung airfield, PRC, 1951.',
        'note_zh': '苏联第64航空军飞行员克拉马连科在安东机场的米格-15座舱内，来源页明确标注为1951年。人物不是中国志愿军空军飞行员，图片仅用于中方境内联合使用机场的环境参照。',
    },
    {
        'key': 'dagushan_historical',
        'url': 'https://epaper.lnd.com.cn/lnrbepaper/pc/pic/202307/27/b5705eff-ef0e-46fc-bfe3-4091b9bf4cca.jpg.2',
        'source_page': 'https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml',
        'caption': 'The Dagushan airfield in wartime.',
        'note_zh': '辽宁日报页面图注明确为“当年的大孤山机场”；公开页面未给出底片编号和精确拍摄日。',
    },
    {
        'key': 'dagushan_command_post_modern',
        'url': 'https://epaper.lnd.com.cn/lnrbepaper/pc/pic/202307/27/2d8616a2-b764-482b-b5ca-40e4f32a0719.jpg.2',
        'source_page': 'https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml',
        'caption': 'Modern photograph of the underground command-post remains at Dagushan airfield.',
        'note_zh': '大孤山机场地下指挥所遗址的现代照片；不得标成1951年现场照。',
    },
    {
        'key': 'dagushan_site_modern',
        'url': 'https://epaper.lnd.com.cn/lnrbepaper/pc/pic/202307/27/9bbcea19-34d0-4ad3-9fcf-e2e61627224c.jpg.2',
        'source_page': 'https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml',
        'caption': 'Modern photograph of the Dagushan airfield site.',
        'note_zh': '大孤山机场遗址的现代照片；不得标成1951年现场照。',
    },
    {
        'key': 'dagushan_han_decai',
        'url': 'https://epaper.lnd.com.cn/lnrbepaper/pc/pic/202307/27/0dd97379-2814-465b-a993-fe67478609ce.jpg.2',
        'source_page': 'https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml',
        'caption': 'Air hero Han Decai inspecting an aircraft at Dagushan airfield.',
        'note_zh': '来源页图注为“飞行英雄韩德彩在大孤山机场检查飞机”；公开图注没有说明拍摄年月，不能直接写成1951年。',
    },
]

S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36'})


def fetch(item: dict) -> tuple[dict | None, str | None]:
    last = None
    for i in range(4):
        try:
            r = S.get(item['url'], headers={'Referer': item['source_page']}, timeout=(15, 90), allow_redirects=True)
            r.raise_for_status()
            suffix = Path(urlparse(item['url']).path).suffix.lower()
            if suffix not in {'.jpg', '.jpeg', '.png', '.webp'}:
                suffix = '.jpg'
            if suffix == '.jpeg':
                suffix = '.jpg'
            path = IMG / f"{item['key']}{suffix}"
            path.write_bytes(r.content)
            with Image.open(path) as im:
                im.load()
                info = {'width': im.width, 'height': im.height, 'format': im.format, 'bytes': len(r.content)}
            if info['width'] < 250 or info['height'] < 160 or info['bytes'] < 10000:
                raise ValueError(f'image too small: {info}')
            result = dict(item)
            result.update(info)
            result['file'] = str(path)
            result['resolved_url'] = r.url
            result['sha256'] = hashlib.sha256(r.content).hexdigest()
            return result, None
        except Exception as exc:
            last = repr(exc)
            time.sleep(1 + i)
    return None, last


def contact(rows: list[dict]) -> None:
    if not rows:
        return
    font = ImageFont.load_default()
    tw, th, lh = 420, 280, 60
    canvas = Image.new('RGB', (tw + 20, len(rows) * (th + lh + 20)), 'white')
    d = ImageDraw.Draw(canvas)
    for i, row in enumerate(rows):
        y = i * (th + lh + 20) + 10
        with Image.open(row['file']) as im:
            im = ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((tw, th))
            canvas.paste(im, (10 + (tw-im.width)//2, y + (th-im.height)//2))
        d.multiline_text((10, y + th + 4), f"{row['key']}\n{row['width']}x{row['height']} {row['bytes']//1024}KB", fill='black', font=font)
    canvas.save(OUT / 'contact.jpg', quality=92)


def main() -> None:
    rows, errors = [], []
    for item in ITEMS:
        row, err = fetch(item)
        if row:
            rows.append(row)
            print('OK', row['key'], row['width'], row['height'], row['bytes'], flush=True)
        else:
            errors.append({'key': item['key'], 'url': item['url'], 'error': err})
            print('ERROR', item['key'], err, flush=True)
    (OUT / 'manifest.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding='utf-8')
    contact(rows)
    if not rows:
        raise SystemExit('no image downloaded')


if __name__ == '__main__':
    main()
