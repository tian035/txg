from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import fitz
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT = Path("usaf_airfield_pages")
OUT.mkdir(exist_ok=True)
RENDER = OUT / "rendered_pages"
IMAGES = OUT / "embedded_images"
RENDER.mkdir(exist_ok=True)
IMAGES.mkdir(exist_ok=True)

SOURCES = {
    "futrell_usaf_in_korea": "https://media.defense.gov/2010/Dec/02/2001329903/-1/-1/0/usaf_in_korea-2.pdf",
    "mig_alley": "https://media.defense.gov/2010/Sep/28/2001330151/-1/-1/0/MigAlley.pdf",
}

KEYWORDS = [
    "Antung", "An-tung", "Antung airfield", "Antung complex", "Mukden",
    "Liaoyang", "Anshan", "Takushan", "Ta-ku-shan", "Tatungkow",
    "airfield complex", "Manchurian airfield", "Chinese airfield",
    "Miaogou", "Miao-kou", "Miao Gou", "Tunghua", "Tungfeng",
    "Yalu airfield", "runway", "revetment", "taxiway",
]

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36"})


def download_pdf(key: str, url: str) -> Path:
    path = OUT / f"{key}.pdf"
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    with session.get(url, stream=True, timeout=(30, 300)) as r:
        r.raise_for_status()
        with path.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    return path


def safe(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("_")


def contact_sheet(files: list[Path], out: Path, cols: int = 3) -> None:
    if not files:
        return
    font = ImageFont.load_default()
    tw, th, lh = 430, 560, 42
    cw, ch = tw + 18, th + lh + 18
    for sheet_no, start in enumerate(range(0, len(files), 18), 1):
        batch = files[start:start+18]
        rows = (len(batch)+cols-1)//cols
        canvas = Image.new("RGB", (cols*cw, rows*ch), "white")
        draw = ImageDraw.Draw(canvas)
        for i, path in enumerate(batch):
            x=(i%cols)*cw+9; y=(i//cols)*ch+9
            with Image.open(path) as im:
                im=ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((tw, th))
                canvas.paste(im,(x+(tw-im.width)//2,y+(th-im.height)//2))
            draw.text((x,y+th+3),path.name,fill="black",font=font)
        target = out.with_name(out.stem + f"_{sheet_no:02d}" + out.suffix)
        canvas.save(target, quality=90)


def main() -> None:
    report=[]
    rendered=[]
    embedded=[]
    for key,url in SOURCES.items():
        pdf_path=download_pdf(key,url)
        doc=fitz.open(pdf_path)
        page_hits=[]
        all_text=[]
        for pno,page in enumerate(doc):
            text=page.get_text("text") or ""
            all_text.append(text)
            low=text.lower()
            matches=[kw for kw in KEYWORDS if kw.lower() in low]
            if matches:
                snippet=" ".join(text.split())
                first=min((low.find(kw.lower()) for kw in matches if low.find(kw.lower())>=0),default=0)
                snippet=snippet[max(0,first-400):first+1200]
                page_hits.append({"page_index":pno,"page_number":pno+1,"matches":matches,"snippet":snippet})
        (OUT/f"{key}_text.txt").write_text("\n\n--- PAGE ---\n\n".join(all_text),encoding="utf-8")

        # Render hit pages plus one page on either side, with a cap that still covers the relevant section.
        selected=set()
        for hit in page_hits:
            p=hit["page_index"]
            selected.update(x for x in (p-1,p,p+1) if 0<=x<len(doc))
        selected=sorted(selected)
        if len(selected)>80:
            selected=selected[:80]
        for pno in selected:
            page=doc[pno]
            pix=page.get_pixmap(matrix=fitz.Matrix(2.0,2.0),alpha=False)
            out=RENDER/f"{key}_p{pno+1:04d}.jpg"
            pix.save(out)
            rendered.append(out)
            # Extract embedded raster images on this page.
            for j,img in enumerate(page.get_images(full=True)):
                xref=img[0]
                try:
                    data=doc.extract_image(xref)
                    raw=data["image"]
                    ext=data.get("ext","png")
                    h=hashlib.sha1(raw).hexdigest()[:10]
                    target=IMAGES/f"{key}_p{pno+1:04d}_{j:02d}_{h}.{ext}"
                    if not target.exists():
                        target.write_bytes(raw)
                        try:
                            with Image.open(target) as im:
                                w,hgt=im.size
                            if w<300 or hgt<180 or target.stat().st_size<12000:
                                target.unlink(missing_ok=True)
                                continue
                            embedded.append(target)
                        except Exception:
                            target.unlink(missing_ok=True)
                except Exception:
                    pass
        report.append({"key":key,"url":url,"pdf":str(pdf_path),"pages":len(doc),"hits":page_hits,"selected_pages":[x+1 for x in selected]})
        doc.close()
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    contact_sheet(rendered, OUT/"rendered_contact.jpg")
    contact_sheet(embedded, OUT/"embedded_contact.jpg", cols=4)
    print(json.dumps({"rendered":len(rendered),"embedded":len(embedded),"report":str(OUT/'report.json')},ensure_ascii=False))


if __name__ == "__main__":
    main()
