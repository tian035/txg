from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps

PAGES = {
    "china_military_71": "https://www.81.cn/tp_207717/9938169.html",
    "china_military_71_alt": "https://www.81.cn/js_208592/jdt_208593/9943470.html?big=fan",
    "xinhua_dabao": "https://www.xinhuanet.com/politics/2020-10/23/c_1126645709.htm",
    "zhao_baotong": "https://photo.81.cn/tsjs/2020-02/03/content_9730970.htm",
    "han_decai": "https://news.bjd.com.cn/2023/07/04/10484268.shtml",
}

OUT = Path("scrape_artifact")
IMGDIR = OUT / "images"
OUT.mkdir(exist_ok=True)
IMGDIR.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
})

ATTRS = ["src", "data-src", "data-original", "data-url", "data-lazy-src", "original"]


def clean_url(raw: str, base: str) -> str | None:
    raw = (raw or "").strip().replace("&amp;", "&")
    if not raw or raw.startswith(("data:", "javascript:", "#")):
        return None
    if raw.startswith("//"):
        raw = "https:" + raw
    return urljoin(base, raw)


def context_for(img) -> str:
    pieces: list[str] = []
    for node in [img.parent, img.parent.parent if img.parent else None]:
        if node:
            txt = " ".join(node.get_text(" ", strip=True).split())
            if txt:
                pieces.append(txt[:500])
    prev = img.find_previous(string=True)
    if prev:
        txt = " ".join(str(prev).split())
        if txt:
            pieces.append(txt[-300:])
    return " | ".join(dict.fromkeys(pieces))[:900]


def fetch_page(key: str, url: str) -> list[dict]:
    print(f"Fetching page: {key} {url}")
    r = session.get(url, timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    html = r.text
    (OUT / f"{key}.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    for dom_index, img in enumerate(soup.find_all("img")):
        candidates: list[str] = []
        for attr in ATTRS:
            v = img.get(attr)
            if isinstance(v, str):
                candidates.append(v)
        srcset = img.get("srcset") or img.get("data-srcset")
        if isinstance(srcset, str):
            for item in srcset.split(","):
                candidates.append(item.strip().split()[0])
        for raw in candidates:
            u = clean_url(raw, url)
            if not u or u in seen:
                continue
            seen.add(u)
            rows.append({
                "page_key": key,
                "page_url": url,
                "dom_index": dom_index,
                "url": u,
                "alt": img.get("alt", ""),
                "title": img.get("title", ""),
                "class": img.get("class", []),
                "context": context_for(img),
            })
    return rows


def suffix_for(url: str, ctype: str) -> str:
    p = urlparse(url).path.lower()
    ext = Path(p).suffix
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}:
        return ".jpg" if ext == ".jpeg" else ext
    if "png" in ctype:
        return ".png"
    if "webp" in ctype:
        return ".webp"
    if "gif" in ctype:
        return ".gif"
    return ".jpg"


def download(row: dict, serial: int) -> dict:
    url = row["url"]
    try:
        r = session.get(url, timeout=60, headers={"Referer": row["page_url"]})
        r.raise_for_status()
        data = r.content
        if len(data) < 4_000:
            raise ValueError(f"too small: {len(data)}")
        ext = suffix_for(url, r.headers.get("content-type", ""))
        digest = hashlib.sha1(url.encode()).hexdigest()[:9]
        fn = f"{serial:03d}_{row['page_key']}_{row['dom_index']:03d}_{digest}{ext}"
        path = IMGDIR / fn
        path.write_bytes(data)
        with Image.open(path) as im:
            im.load()
            w, h = im.size
            fmt = im.format
        row.update({"file": str(path), "bytes": len(data), "width": w, "height": h, "format": fmt, "status": "ok"})
    except Exception as e:
        row.update({"status": "error", "error": repr(e)})
    return row


def make_contact_sheet(rows: list[dict]) -> None:
    good = [r for r in rows if r.get("status") == "ok" and r.get("width", 0) >= 250 and r.get("height", 0) >= 160]
    thumb_w, thumb_h = 300, 220
    label_h = 52
    cols = 4
    cell_w, cell_h = thumb_w + 18, thumb_h + label_h + 18
    pages = [good[i:i+40] for i in range(0, len(good), 40)]
    font = ImageFont.load_default()
    for page_no, batch in enumerate(pages, 1):
        rows_n = (len(batch) + cols - 1) // cols
        canvas = Image.new("RGB", (cols * cell_w, rows_n * cell_h), "white")
        draw = ImageDraw.Draw(canvas)
        for i, item in enumerate(batch):
            x = (i % cols) * cell_w + 9
            y = (i // cols) * cell_h + 9
            try:
                with Image.open(item["file"]) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((thumb_w, thumb_h))
                    px = x + (thumb_w - im.width) // 2
                    py = y + (thumb_h - im.height) // 2
                    canvas.paste(im, (px, py))
                label = f"{Path(item['file']).name}\n{item['width']}x{item['height']}  {item['bytes']//1024}KB"
                draw.multiline_text((x, y + thumb_h + 2), label, fill="black", font=font, spacing=2)
            except Exception as e:
                draw.text((x, y), f"ERROR {e}", fill="black", font=font)
        canvas.save(OUT / f"contact_sheet_{page_no:02d}.jpg", quality=90)


def main() -> None:
    rows: list[dict] = []
    for key, url in PAGES.items():
        try:
            rows.extend(fetch_page(key, url))
        except Exception as e:
            rows.append({"page_key": key, "page_url": url, "status": "page_error", "error": repr(e)})
    downloaded: list[dict] = []
    for i, row in enumerate([r for r in rows if "url" in r], 1):
        print(f"[{i}/{len(rows)}] {row['url']}")
        downloaded.append(download(row, i))
        time.sleep(0.05)
    errors = [r for r in rows if "url" not in r]
    all_rows = downloaded + errors
    (OUT / "metadata.json").write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "metadata.tsv").open("w", encoding="utf-8") as f:
        f.write("file\tpage_key\tdom_index\twidth\theight\tbytes\turl\talt\tcontext\tstatus\terror\n")
        for r in all_rows:
            vals = [r.get(k, "") for k in ["file", "page_key", "dom_index", "width", "height", "bytes", "url", "alt", "context", "status", "error"]]
            f.write("\t".join(str(v).replace("\t", " ").replace("\n", " ") for v in vals) + "\n")
    make_contact_sheet(all_rows)
    print(f"Saved {sum(1 for r in all_rows if r.get('status') == 'ok')} images")


if __name__ == "__main__":
    main()
