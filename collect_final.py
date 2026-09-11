from pathlib import Path

source = Path("collect_selected.py").read_text(encoding="utf-8")
source = source.replace(
    "if len(imgs) < max(SELECTED):",
    "if len(imgs) < max(SELECTED) + 1:",
)
source = source.replace(
    'rel = imgs[n - 1].get("src")',
    'rel = imgs[n].get("src")',
)
exec(compile(source, "collect_selected_final.py", "exec"), {"__name__": "__main__"})
