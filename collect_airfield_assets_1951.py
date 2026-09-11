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

OUT = Path("airfield_assets_1951")
IMG = OUT / "images"
HTML = OUT / "html"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)
HTML.mkdir(exist_ok=True)

PAGES = [
    {
        "key": "interaffairs_korea_exhibition",
        "url": "https://interaffairs.ru/news/show/15651",
        "source": "Russian journal International Affairs / Korean War photo exhibition",
    },
    {
        "key": "koryo_saram_korea_exhibition",
        "url": "https://koryo-saram.site/neizvestnaya-vojna-v-nebe-korei-1950-1953-gg/",
        "source": "Koryo Saram report on Korean War photo exhibition",
    },
    {
        "key": "mig15_book_universal",
        "url": "https://www.universalinternetlibrary.ru/book/94545/chitat_knigu.shtml",
        "source": "Digitized Russian-language MiG-15 monograph",
    },
    {
        "key": "mig15_book_litresp",
        "url": "https://litresp.ru/chitat/ru/%D0%90/arsenjev-e/istrebitelj-mig-15",
        "source": "Digitized Russian-language MiG-15 monograph mirror",
    },
    {
        "key": "cctv_bixue_changkong",
        "url": "https://www.12371.cn/2020/11/04/VIDE1604444880212697.shtml",
        "source": "CCTV / 12371 documentary: Bixue Changkong",
    },
    {
        "key": "cctv_2024_air_force",
        "url": "https://news.cctv.com/2024/10/25/ARTIfwIp4GvKdQoWeVjCr6Nt241025.shtml",
        "source": "CCTV report on Korean War air-force tradition",
    },
    {
        "key": "liaoning_dagushan",
        "url": "https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml",
        "source": "Liaoning Daily / Beiguo: Dagushan wartime airfield",
    },
    {
        "key": "plaaf_71_moments",
        "url": "https://www.81.cn/tp_207717/9938169.html",
        "source": "China Military Network: 71 moments of Volunteer Air Force",
    },
    {
        "key": "plaaf_bombing_islands",
        "url": "https://www.81.cn/yw_208727/10103616.html",
        "source": "China Military Network: bombing of Dahe/Xiaohe islands",
    },
]

DIRECT = [
    {
        "key": "interaffairs_kramarenko_antung_1951",
        "url": "https://interaffairs.ru/i/2016/07/c600f07a9ac4d058b6d716f83d189189.jpg",
        "caption": "S. M. Kramarenko in a MiG-15 cockpit, Antung airfield, PRC, 1951 (caption on source page)",
        "source_page": "https://interaffairs.ru/news/show/15651",
    },
    {
        "key": "interaffairs_b29_guncamera",
        "url": "https://interaffairs.ru/i/2016/07/28eb28b5a8f73754a6cd871e74815ed1.jpg",
        "caption": "B-29 in a gun-camera sight; exhibition image",
        "source_page": "https://interaffairs.ru/news/show/15651",
    },
    {
        "key": "dagushan_historical",
        "url": "https://epaper.lnd.com.cn/lnrbepaper/pc/pic/202307/27/b5705eff-ef0e-46fc-bfe3-4091b9bf4cca.jpg.2",
        "caption": "The Dagushan airfield in wartime (caption on Liaoning Daily page)",
        "source_page": "https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml",
    },
    {
        "key": "dagushan_han_decai",
        "url": "https://epaper.lnd.com.cn/lnrbepaper/pc/pic/202307/27/0dd97379-2814-465b-a993-fe67478609ce.jpg.2",
        "caption": "Air hero Han Decai inspecting an aircraft at Dagushan airfield (caption on Liaoning Daily page; exact date not stated)",
        "source_page": "https://liaoning.lnd.com.cn/system/2023/07/27/030425527.shtml",
    },
]

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7,ru;q=0.6",
})


def request(url: str, referer: str | None = None, timeout: int = 90) -> requests.Response:
    last: Exception | None = None
    for attempt in range(5):
        try:
            headers = {"Referer": referer} if referer else {}
            response = S.get(url, headers=headers, timeout=(15, timeout), allow_redirects=True)
            response.raise_for_status()
            return response
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def safe_name(text: str, limit: int = 80) -> str:
    text = re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("_")
    return text[:limit] or "image"


def extension(url: str, mime: str = "") -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if "png" in mime:
        return ".png"
    if "webp" in mime:
        return ".webp"
    if "gif" in mime:
        return ".gif"
    return ".jpg"


def image_info(path: Path) -> dict:
    with Image.open(path) as im:
        im.load()
        return {"width": im.width, "height": im.height, "format": im.format, "bytes": path.stat().st_size}


def surrounding_text(tag, limit: int = 600) -> str:
    chunks: list[str] = []
    for attr in ("alt", "title"):
        value = tag.get(attr)
        if value:
            chunks.append(str(value))
    parent = tag.parent
    for _ in range(3):
        if parent is None:
            break
        text = " ".join(parent.get_text(" ", strip=True).split())
        if text:
            chunks.append(text)
        parent = parent.parent
    return " | ".join(dict.fromkeys(chunks))[:limit]


def candidates_from_tag(tag, page_url: str) -> list[str]:
    raw: list[str] = []
    for attr in ("src", "data-src", "data-original", "data-lazy-src", "data-echo", "data-url"):
        value = tag.get(attr)
        if value:
            raw.append(str(value))
    for attr in ("srcset", "data-srcset"):
        value = tag.get(attr)
        if value:
            for part in str(value).split(","):
                raw.append(part.strip().split(" ")[0])
    result = []
    for value in raw:
        if value.startswith("data:") or value.startswith("javascript:"):
            continue
        result.append(urljoin(page_url, value))
    return list(dict.fromkeys(result))


def download_image(url: str, path: Path, referer: str | None = None) -> tuple[dict | None, str | None]:
    try:
        response = request(url, referer=referer, timeout=180)
        mime = response.headers.get("content-type", "")
        if "image" not in mime.lower() and len(response.content) < 1024:
            return None, f"not an image: {mime} {len(response.content)} bytes"
        path.write_bytes(response.content)
        info = image_info(path)
        if info["width"] < 250 or info["height"] < 160 or info["bytes"] < 12000:
            path.unlink(missing_ok=True)
            return None, f"too small: {info}"
        return info, None
    except Exception as exc:
        path.unlink(missing_ok=True)
        return None, repr(exc)


def scrape_pages() -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()
    for page in PAGES:
        print("PAGE", page["key"], page["url"], flush=True)
        try:
            response = request(page["url"], timeout=180)
            response.encoding = response.apparent_encoding or response.encoding
            html_path = HTML / f"{page['key']}.html"
            html_path.write_text(response.text, encoding="utf-8", errors="replace")
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            idx = 0
            for tag in soup.find_all("img"):
                context = surrounding_text(tag)
                for url in candidates_from_tag(tag, response.url):
                    normalized = url.split("#")[0]
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    idx += 1
                    digest = hashlib.sha1(normalized.encode()).hexdigest()[:10]
                    ext = extension(normalized)
                    key = f"{page['key']}_{idx:03d}_{digest}"
                    path = IMG / f"{safe_name(key)}{ext}"
                    info, err = download_image(normalized, path, referer=response.url)
                    if info:
                        row = {
                            "key": key,
                            "file": str(path),
                            "caption_context": context,
                            "source": page["source"],
                            "source_page": response.url,
                            "source_title": title,
                            "source_image": normalized,
                            **info,
                        }
                        rows.append(row)
                        print("  OK", key, info["width"], info["height"], info["bytes"], normalized, flush=True)
                    elif err and ("too small" not in err):
                        errors.append({"page": page["key"], "url": normalized, "error": err})
        except Exception as exc:
            errors.append({"page": page["key"], "url": page["url"], "error": repr(exc)})
            print("PAGE ERROR", page["key"], repr(exc), flush=True)
    return rows, errors


def direct_images() -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []
    for item in DIRECT:
        ext = extension(item["url"])
        path = IMG / f"{item['key']}{ext}"
        info, err = download_image(item["url"], path, referer=item["source_page"])
        if info:
            rows.append({
                **item,
                "file": str(path),
                "source": "direct known image URL",
                "source_image": item["url"],
                **info,
            })
            print("DIRECT OK", item["key"], info, flush=True)
        else:
            errors.append({"page": "direct", "url": item["url"], "error": err})
            print("DIRECT ERROR", item["key"], err, flush=True)
    return rows, errors


def contact_sheets(rows: list[dict], batch_size: int = 24) -> None:
    font = ImageFont.load_default()
    cols = 4
    thumb_w, thumb_h = 300, 210
    label_h = 62
    cell_w, cell_h = thumb_w + 18, thumb_h + label_h + 18
    for sheet_no, start in enumerate(range(0, len(rows), batch_size), 1):
        batch = rows[start:start + batch_size]
        nrows = (len(batch) + cols - 1) // cols
        canvas = Image.new("RGB", (cell_w * cols, cell_h * nrows), "white")
        draw = ImageDraw.Draw(canvas)
        for i, row in enumerate(batch):
            x = (i % cols) * cell_w + 9
            y = (i // cols) * cell_h + 9
            try:
                with Image.open(row["file"]) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((thumb_w, thumb_h))
                    canvas.paste(im, (x + (thumb_w - im.width) // 2, y + (thumb_h - im.height) // 2))
            except Exception:
                pass
            label = f"{start + i:03d} {row['key'][:42]}\n{row.get('width')}x{row.get('height')} {row.get('bytes', 0)//1024}KB"
            draw.multiline_text((x, y + thumb_h + 4), label, fill="black", font=font, spacing=2)
        canvas.save(OUT / f"contact_{sheet_no:02d}.jpg", quality=92)


def main() -> None:
    direct, direct_errors = direct_images()
    scraped, scrape_errors = scrape_pages()
    # Keep direct rows first; deduplicate identical file hashes after download.
    all_rows = direct + scraped
    deduped: list[dict] = []
    hashes: set[str] = set()
    for row in all_rows:
        data = Path(row["file"]).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest in hashes:
            continue
        hashes.add(digest)
        row["sha256"] = digest
        deduped.append(row)
    (OUT / "manifest.json").write_text(json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "errors.json").write_text(json.dumps(direct_errors + scrape_errors, ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheets(deduped)
    print("TOTAL", len(deduped), "ERRORS", len(direct_errors) + len(scrape_errors), flush=True)


if __name__ == "__main__":
    main()
