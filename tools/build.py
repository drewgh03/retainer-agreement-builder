#!/usr/bin/env python3
"""Rebuild retainer-agreement.html from src/template.html and the two fillable PDFs in templates/.

For each PDF this reads where every blank sits, then the position of every word on the lines that hold a
blank, so the page can re-space those lines after a name or amount is typed in. The PDFs are embedded in the
page as base64.

Needs: pypdf, reportlab, and poppler-utils (pdftotext).   Run:  python3 tools/build.py
"""
import base64, html, json, re, statistics, subprocess
from pathlib import Path
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

ROOT = Path(__file__).resolve().parent.parent
SRC = {"trial": "retainer-balance-and-trial-fee.pdf", "today": "retainer-paid-today-only.pdf"}
# Position of the attorney's large signature on the last page (PDF points, origin bottom-left).
SIG_NAME = {"trial": {"page": 3, "x": 72.1, "yb": 432.7, "yt": 459.3},
            "today": {"page": 3, "x": 72.1, "yb": 477.7, "yt": 504.3}}
H = 792
SW = lambda s: stringWidth(s, "Times-Roman", 12)
WORD = re.compile(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')


def read_fields(reader):
    fields = []
    for pi, p in enumerate(reader.pages):
        for a in (p.get("/Annots") or []):
            a = a.get_object()
            par = a.get("/Parent")
            par = par.get_object() if par else a
            name = str(a.get("/T") or par.get("/T"))
            x0, y0, x1, y1 = [round(float(v), 2) for v in a["/Rect"]]
            fields.append({"name": name, "page": pi, "rect": [x0, y0, x1, y1]})
    return fields


def bbox_text(path):
    return subprocess.run(["pdftotext", "-bbox", str(path), "-"], capture_output=True, text=True, check=True).stdout


def underline_marks(bb):
    """The blank lines for 'Other Contacts' (page 3) and the client signature (page 4)."""
    page, lines = 0, []
    for line in bb.splitlines():
        if "<page " in line:
            page += 1
        m = WORD.search(line)
        if m and m.group(5).startswith("____"):
            xm, ym, xM, yM = map(float, m.groups()[:4])
            lines.append((page, xm, ym, xM, yM))
    base = lambda l: round(H - (l[4] - 2.4), 2)
    other = [l for l in lines if l[0] == 3][0]
    sig = [l for l in lines if l[0] == 4][0]
    return (
        {"page": 2, "x": round(other[1] + 2, 2), "y": base(other) + 1.6, "w": round(other[3] - other[1] - 4, 2)},
        {"page": 3, "x": round(sig[1], 2), "y": base(sig) + 2.5, "w": round(sig[3] - sig[1], 2)},
    )


def line_layout(bb, fields):
    page, words = -1, []
    for line in bb.splitlines():
        if "<page " in line:
            page += 1
        m = WORD.search(line)
        if m:
            x0, yt, x1, yb = map(float, m.groups()[:4])
            words.append({"page": page, "t": html.unescape(m.group(5)), "x0": x0, "x1": x1, "yb": H - yb, "yt": H - yt})

    def inside(w, f):
        cx, cy, r = (w["x0"] + w["x1"]) / 2, (w["yb"] + w["yt"]) / 2, f["rect"]
        return f["page"] == w["page"] and r[0] - 1 <= cx <= r[2] + 1 and r[1] - 2 <= cy <= r[3] + 2

    plain = []
    for w in words:
        if any(inside(w, f) for f in fields):
            # Punctuation or a "$" glued to a blank's placeholder is real page text; keep it as its own word.
            if "[" in w["t"] or "]" in w["t"]:
                pre = w["t"].split("[", 1)[0]
                if pre and "[" in w["t"]:
                    plain.append(dict(w, t=pre, x1=w["x0"] + SW(pre)))
                suf = w["t"].rsplit("]", 1)[1] if "]" in w["t"] else ""
                if suf:
                    plain.append(dict(w, t=suf, x0=w["x1"] - SW(suf)))
            continue
        plain.append(w)

    groups = []
    for f in sorted(fields, key=lambda f: (f["page"], -(f["rect"][1] + f["rect"][3]) / 2, f["rect"][0])):
        mid = (f["rect"][1] + f["rect"][3]) / 2
        for g in groups:
            if g["page"] == f["page"] and abs(g["mid"] - mid) < 5:
                g["fields"].append(f)
                break
        else:
            groups.append({"page": f["page"], "mid": mid, "fields": [f]})

    out = []
    for g in groups:
        fs = sorted(g["fields"], key=lambda f: f["rect"][0])
        ws = [w for w in plain if w["page"] == g["page"] and abs((w["yb"] + w["yt"]) / 2 - g["mid"]) < 5]
        ws.sort(key=lambda w: w["x0"])
        # Bold, underlined headings ("Fees:") stay as printed; re-spacing starts after the heading.
        start_i = 0
        for i, w in enumerate(ws):
            if w["x1"] <= fs[0]["rect"][0] + 1 and w["t"].endswith(":") and i < 8:
                start_i = i + 1
                break
        items = [{"k": "f", "name": f["name"], "x0": f["rect"][0], "x1": f["rect"][2]} for f in fs]
        items += [{"k": "w", "t": w["t"], "x0": round(w["x0"], 2), "x1": round(w["x1"], 2)} for w in ws[start_i:]]
        items.sort(key=lambda i: i["x0"])
        right = max(i["x1"] for i in items)
        base = round(statistics.median([w["yb"] for w in ws]) + 2.6, 2) if ws else round(g["mid"] - 3.5, 2)
        out.append({"page": g["page"], "base": base, "R": round(right, 2), "justified": right >= 537.5, "items": items})
    return out


def main():
    data = {}
    for key, fn in SRC.items():
        path = ROOT / "templates" / fn
        fields = read_fields(PdfReader(str(path)))
        bb = bbox_text(path)
        other, sig = underline_marks(bb)
        data[key] = {
            "b64": base64.b64encode(path.read_bytes()).decode(),
            "lines": line_layout(bb, fields),
            "other": other,
            "sig": sig,
            "sigName": SIG_NAME[key],
        }
    template = (ROOT / "src" / "template.html").read_text()
    out = template.replace("__TEMPLATES_JSON__", json.dumps(data, separators=(",", ":")))
    (ROOT / "retainer-agreement.html").write_text(out)
    print(f"wrote retainer-agreement.html ({len(out) // 1024} KB)")


if __name__ == "__main__":
    main()
