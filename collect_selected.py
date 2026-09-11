from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT = Path("selected_artifact")
IMG = OUT / "images"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
})

OFFICIAL_PAGE = "https://www.81.cn/tp_207717/9938169.html"
SELECTED = [13, 14, 15, 18, 23, 27, 28, 29, 30, 31, 32, 33, 35, 36, 48, 53, 55, 58, 59, 60, 61, 62]

COMMONS = [
    {
        "key": "commons_mig15",
        "title": "File:Chinese Air Force Mig-15 (26448272976).jpg",
        "caption": "米格-15歼击机外形参考（中国航空博物馆现代馆藏照片；非1951年现场照）",
        "license": "CC BY-SA 2.0；作者 G B_NZ",
    },
    {
        "key": "commons_tu2",
        "title": "File:Tu-2 at the China Aviation Museum.jpg",
        "caption": "图-2轰炸机外形参考（中国航空博物馆现代馆藏照片；非1951年现场照）",
        "license": "公有领域；作者 Max Smith",
    },
    {
        "key": "commons_la11",
        "title": "File:Lavochkin La-11 - 50814819093.jpg",
        "caption": "拉-11战斗机外形参考（现代保存飞机；非中国1951年参战原机）",
        "license": "CC BY 2.0；作者 Eric Friedebach",
    },
]

SITE_PAGES = [
    ("dagushan", "https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml", "大孤山机场历史与遗址"),
    ("dabao", "https://k.sina.cn/article_213815211_0cbe8fab020011xeu.html", "大堡机场跑道与遗址"),
]


def fetch(url: str, *, referer: str | None = None, timeout: int = 60) -> requests.Response:
    headers = {"Referer": referer} if referer else {}
    last = None
    for attempt in range(5):
        try:
            r = SESSION.get(url, headers=headers, timeout=(12, timeout), allow_redirects=True)
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def image_info(path: Path) -> dict:
    with Image.open(path) as im:
        im.load()
        return {"width": im.width, "height": im.height, "format": im.format}


def save_image(data: bytes, path: Path) -> dict:
    path.write_bytes(data)
    info = image_info(path)
    info["bytes"] = len(data)
    return info


def parse_official() -> list[dict]:
    r = fetch(OFFICIAL_PAGE)
    r.encoding = r.apparent_encoding or r.encoding
    soup = BeautifulSoup(r.text, "html.parser")
    imgs = [i for i in soup.find_all("img") if "9938169_" in str(i.get("src", ""))]
    captions: dict[int, str] = {}
    for p in soup.find_all("p"):
        txt = " ".join(p.get_text(" ", strip=True).split())
        m = re.match(r"^(\d{2})[\.、]\s*(.*)", txt)
        if m:
            captions[int(m.group(1))] = m.group(2)
    rows = []
    if len(imgs) < max(SELECTED):
        raise RuntimeError(f"only found {len(imgs)} official images")
    for n in SELECTED:
        rel = imgs[n - 1].get("src")
        # HTTPS returns a JS anti-bot page; HTTP serves the original JPEG.
        url = urljoin("http://www.81.cn", rel)
        rr = fetch(url, referer=OFFICIAL_PAGE, timeout=120)
        ctype = rr.headers.get("content-type", "")
        if "image" not in ctype and not rr.content.startswith(b"\xff\xd8"):
            raise RuntimeError(f"official figure {n} did not return image: {ctype} {len(rr.content)}")
        path = IMG / f"official_{n:02d}.jpg"
        info = save_image(rr.content, path)
        rows.append({
            "key": f"official_{n:02d}",
            "figure_number": n,
            "file": str(path),
            "caption": captions.get(n, ""),
            "source_page": OFFICIAL_PAGE,
            "source_image": url,
            "source_name": "中国军网《震撼！71个瞬间，回眸志愿军空军参加抗美援朝战争历史》",
            "license": "版权未标为开放许可；研究引用请注明来源，公开出版或商业使用需另行核权。",
            "category": "official_historical",
            **info,
        })
        print("official", n, info)
    return rows


def fetch_commons() -> list[dict]:
    api = "https://commons.wikimedia.org/w/api.php"
    rows = []
    for item in COMMONS:
        params = {
            "action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|size|mime", "titles": item["title"],
        }
        data = fetch(api + "?" + requests.compat.urlencode(params), timeout=90).json()
        page = next(iter(data["query"]["pages"].values()))
        ii = page["imageinfo"][0]
        url = ii["url"]
        rr = fetch(url, referer="https://commons.wikimedia.org/", timeout=180)
        ext = ".png" if "png" in ii.get("mime", "") else ".jpg"
        path = IMG / f"{item['key']}{ext}"
        info = save_image(rr.content, path)
        rows.append({
            **item,
            "file": str(path),
            "source_page": "https://commons.wikimedia.org/wiki/" + item["title"].replace("File:", "File:").replace(" ", "_"),
            "source_image": url,
            "source_name": "Wikimedia Commons",
            "category": "modern_reference",
            **info,
        })
        print(item["key"], info)
    return rows


def context_for(img) -> str:
    parts = []
    for node in [img.parent, img.parent.parent if img.parent else None]:
        if node:
            t = " ".join(node.get_text(" ", strip=True).split())
            if t:
                parts.append(t[:600])
    return " | ".join(dict.fromkeys(parts))[:1000]


def scrape_site_candidates() -> list[dict]:
    rows = []
    for key, page_url, label in SITE_PAGES:
        try:
            r = fetch(page_url, timeout=90)
            r.encoding = r.apparent_encoding or r.encoding
            soup = BeautifulSoup(r.text, "html.parser")
            seen = set()
            idx = 0
            for img in soup.find_all("img"):
                candidates = []
                for attr in ["src", "data-src", "data-original", "data-lazy-src", "data-url"]:
                    v = img.get(attr)
                    if isinstance(v, str): candidates.append(v)
                srcset = img.get("srcset")
                if isinstance(srcset, str):
                    candidates += [x.strip().split()[0] for x in srcset.split(",")]
                for raw in candidates:
                    if not raw or raw.startswith(("data:", "javascript:")): continue
                    url = urljoin(page_url, raw.replace("&amp;", "&"))
                    if url in seen: continue
                    seen.add(url)
                    try:
                        rr = fetch(url, referer=page_url, timeout=60)
                        if len(rr.content) < 20000: continue
                        ext = ".png" if "png" in rr.headers.get("content-type", "") else ".jpg"
                        path = IMG / f"site_{key}_{idx:02d}{ext}"
                        info = save_image(rr.content, path)
                        if info["width"] < 500 or info["height"] < 300:
                            path.unlink(missing_ok=True)
                            continue
                        rows.append({
                            "key": f"site_{key}_{idx:02d}", "file": str(path),
                            "caption": label, "source_page": page_url, "source_image": url,
                            "source_name": label, "license": "媒体网页配图，未标为开放许可；公开使用需核权。",
                            "category": "modern_site_candidate", "alt": img.get("alt", ""),
                            "context": context_for(img), **info,
                        })
                        idx += 1
                    except Exception as exc:
                        print("site image error", url, exc)
        except Exception as exc:
            print("site page error", page_url, exc)
    return rows


def make_sheet(rows: list[dict], category: str, output: Path) -> None:
    items = [r for r in rows if r.get("category") == category]
    if not items: return
    tw, th, lh, cols = 320, 220, 55, 4
    cw, ch = tw + 20, th + lh + 20
    pages = [items[i:i+32] for i in range(0, len(items), 32)]
    font = ImageFont.load_default()
    for pno, batch in enumerate(pages, 1):
        nr = (len(batch) + cols - 1) // cols
        canvas = Image.new("RGB", (cols*cw, nr*ch), "white")
        draw = ImageDraw.Draw(canvas)
        for i, item in enumerate(batch):
            x = (i % cols)*cw + 10; y = (i // cols)*ch + 10
            with Image.open(item["file"]) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((tw, th))
                canvas.paste(im, (x+(tw-im.width)//2, y+(th-im.height)//2))
            lab = f"{item['key']}\n{item['width']}×{item['height']} {item['bytes']//1024}KB"
            draw.multiline_text((x, y+th+3), lab, fill="black", font=font, spacing=2)
        canvas.save(output.with_name(output.stem + (f"_{pno:02d}" if len(pages)>1 else "") + output.suffix), quality=92)


def main():
    rows = []
    rows += parse_official()
    rows += fetch_commons()
    rows += scrape_site_candidates()
    (OUT / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    make_sheet(rows, "official_historical", OUT / "contact_official.jpg")
    make_sheet(rows, "modern_reference", OUT / "contact_reference.jpg")
    make_sheet(rows, "modern_site_candidate", OUT / "contact_sites.jpg")
    print("TOTAL", len(rows))

if __name__ == "__main__":
    main()
