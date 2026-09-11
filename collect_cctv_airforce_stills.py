from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps

PAGE = "https://www.12371.cn/2020/11/04/VIDE1604444880212697.shtml"
OUT = Path("cctv_airforce_stills")
IMG = OUT / "images"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Referer": PAGE,
})

r = session.get(PAGE, timeout=(20, 120))
r.raise_for_status()
r.encoding = r.apparent_encoding or r.encoding
soup = BeautifulSoup(r.text, "html.parser")

urls = []
for tag in soup.find_all("img"):
    for attr in ("src", "data-src", "data-original"):
        value = tag.get(attr)
        if not value:
            continue
        url = urljoin(r.url, value)
        if "img.cctvpic.com/photoworkspace/contentimg/2020/10/27/" in url:
            urls.append(url)
urls = list(dict.fromkeys(urls))

rows = []
for index, url in enumerate(urls, 1):
    try:
        rr = session.get(url, timeout=(15, 90))
        rr.raise_for_status()
        ext = Path(url.split("?")[0]).suffix or ".png"
        digest = hashlib.sha1(url.encode()).hexdigest()[:8]
        path = IMG / f"cctv_{index:02d}_{digest}{ext}"
        path.write_bytes(rr.content)
        with Image.open(path) as im:
            im.load()
            width, height = im.size
        if width < 400 or height < 220 or len(rr.content) < 15000:
            path.unlink(missing_ok=True)
            continue
        rows.append({
            "index": index,
            "file": str(path),
            "source_page": PAGE,
            "source_image": url,
            "width": width,
            "height": height,
            "bytes": len(rr.content),
        })
        print("OK", index, width, height, len(rr.content), url, flush=True)
    except Exception as exc:
        print("ERROR", index, repr(exc), url, flush=True)

(OUT / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

font = ImageFont.load_default()
cols = 4
thumb_w, thumb_h, label_h = 360, 220, 30
cell_w, cell_h = thumb_w + 16, thumb_h + label_h + 16
for sheet_no, start in enumerate(range(0, len(rows), 24), 1):
    batch = rows[start:start + 24]
    nrows = (len(batch) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * cell_w, nrows * cell_h), "white")
    draw = ImageDraw.Draw(canvas)
    for j, row in enumerate(batch):
        x = (j % cols) * cell_w + 8
        y = (j // cols) * cell_h + 8
        with Image.open(row["file"]) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((thumb_w, thumb_h))
            canvas.paste(im, (x + (thumb_w - im.width) // 2, y + (thumb_h - im.height) // 2))
        draw.text((x, y + thumb_h + 3), f"{start + j + 1:02d} {row['width']}x{row['height']}", fill="black", font=font)
    canvas.save(OUT / f"contact_{sheet_no:02d}.jpg", quality=92)

if not rows:
    raise SystemExit("No stills downloaded")
