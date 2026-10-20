"""Build the post's widget data and chart: python blogbuild.py <results-dir> <page-bundle-dir>."""
import json
import os
import sys

RES, OUT = sys.argv[1], sys.argv[2]

bank = {g["group"]: g for g in json.load(open(f"{RES}/questions.json"))}

study = {}
for model in ("minilm", "bge-base"):
    rows = []
    for r in json.load(open(f"{RES}/eval-{model}.json")):
        rows.append({
            "k": "p" if r["kind"] == "paraphrase" else "n",
            "q": r["q"],
            "c": bank[r["nearest"]]["variants"][0],
            "d": round(r["dist"], 3),
            "ok": r["kind"] == "paraphrase" and r["nearest"] == r["group"],
        })
    study[model] = sorted(rows, key=lambda x: x["d"])
json.dump(study, open(f"{OUT}/threshold-study.json", "w"), separators=(",", ":"))

runs = [("0.05", "run-t0.05.json"), ("0.10", "run-t0.10.json"), ("0.15", "run-t0.15.json"),
        ("0.20", "run-t0.20.json"), ("0.25", "run-t0.25.json"), ("0.30", "run-t0.30.json")]
bars = []
for t, f in runs:
    res = json.load(open(f"{RES}/{f}"))["results"]
    n = len(res)
    hits = [r for r in res if r["result"] == "hit"]
    exact = sum(r["dist"] < 1e-3 for r in hits)
    false = sum(r.get("false_hit", False) for r in hits)
    tokens = sum(r["usage"]["total_tokens"] for r in res if r.get("usage"))
    bars.append((t, exact / n, (len(hits) - exact - false) / n, false / n, false, tokens))
    print(t, n, len(hits), exact, false, tokens)

W, H = 960, 430
L, R, T, B = 70, 24, 92, 86
pw, ph = W - L - R, H - T - B
y = lambda v: T + ph - v * ph
NAVY, ACC, RED, GREY = "#161641", "#7790de", "#e0565b", "#6b7280"
o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif" role="img" aria-label="Cache hit rate by similarity threshold, split into exact repeats, semantic hits and wrong answers">',
     f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
     f'<text x="24" y="32" font-size="20" font-weight="700" fill="{NAVY}">Where the cache hits came from (600 questions per run)</text>',
     f'<text x="24" y="54" font-size="14" fill="{GREY}">Same traffic at each threshold (cosine distance). With no cache, it would cost about 625k LLM tokens.</text>']
for v in (0, 0.2, 0.4, 0.6, 0.8, 1.0):
    o.append(f'<line x1="{L}" y1="{y(v):.1f}" x2="{W - R}" y2="{y(v):.1f}" stroke="#e5e7eb"/>')
    o.append(f'<text x="{L - 10}" y="{y(v) + 4:.1f}" font-size="12" fill="{GREY}" text-anchor="end">{int(v * 100)}%</text>')
slot = pw / len(bars)
bw = slot * 0.5
for i, (t, ex, sem, fh, fcount, tokens) in enumerate(bars):
    x0 = L + slot * i + (slot - bw) / 2
    base = 0
    for v, color in ((ex, NAVY), (sem, ACC), (fh, RED)):
        o.append(f'<rect x="{x0:.1f}" y="{y(base + v):.1f}" width="{bw:.1f}" height="{v * ph:.1f}" fill="{color}"/>')
        base += v
    o.append(f'<text x="{x0 + bw / 2:.1f}" y="{y(base) - 8:.1f}" font-size="13" font-weight="700" fill="{NAVY}" text-anchor="middle">{base:.0%}</text>')
    o.append(f'<text x="{x0 + bw / 2:.1f}" y="{T + ph + 20:.1f}" font-size="13" font-weight="600" fill="{NAVY}" text-anchor="middle">≤ {t}</text>')
    o.append(f'<text x="{x0 + bw / 2:.1f}" y="{T + ph + 38:.1f}" font-size="12" fill="{RED}" text-anchor="middle">{fcount} wrong</text>')
    o.append(f'<text x="{x0 + bw / 2:.1f}" y="{T + ph + 55:.1f}" font-size="12" fill="{GREY}" text-anchor="middle">{tokens / 1000:.0f}k tokens</text>')
lx = L
for label, color in (("Exact repeat of a cached question", NAVY), ("Reworded question, right answer", ACC), ("Answer that belonged to a different question", RED)):
    o.append(f'<rect x="{lx}" y="68" width="12" height="12" fill="{color}"/>')
    o.append(f'<text x="{lx + 18}" y="78" font-size="13" fill="#374151">{label}</text>')
    lx += 18 + len(label) * 7.1 + 26
o.append('</svg>')
open(f"{OUT}/cache-hits-by-threshold.svg", "w").write("\n".join(o) + "\n")
print(os.path.getsize(f"{OUT}/threshold-study.json"))
