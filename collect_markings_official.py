from pathlib import Path

source = Path("collect_selected.py").read_text(encoding="utf-8")
source = source.replace('OUT = Path("selected_artifact")', 'OUT = Path("markings_official")')
source = source.replace('SELECTED = [13, 14, 15, 18, 23, 27, 28, 29, 30, 31, 32, 33, 35, 36, 48, 53, 55, 58, 59, 60, 61, 62]', 'SELECTED = [7, 8, 12, 19, 50, 54, 56, 57, 69]')
source = source.replace('if len(imgs) < max(SELECTED):', 'if len(imgs) < max(SELECTED) + 2:')
source = source.replace('rel = imgs[n - 1].get("src")', 'rel = imgs[n].get("src")')
source = source.replace('rows += fetch_commons()', '')
source = source.replace('rows += scrape_site_candidates()', '')
exec(compile(source, "collect_markings_official_runtime.py", "exec"), {"__name__": "__main__"})
