#!/usr/bin/env python3
"""Minimal SVG line/bar charts in the style of the existing Solanica blog charts."""
import html

W, H = 960, 400
L, R, T, B = 90, 30, 78, 330  # plot box: x from L to W-R, y from T to B
COLORS = ["#4f46e5", "#16a34a", "#f59e0b", "#dc2626", "#0891b2", "#9333ea"]


def _nice_step(span, target=6):
    raw = span / target
    mag = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _head(title, subtitle):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           "font-family=\"-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif\" "
           f'role="img" aria-label="{html.escape(title)}">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="24" y="32" font-size="20" font-weight="700" fill="#161641">{html.escape(title)}</text>',
           f'<text x="24" y="54" font-size="14" fill="#6b7280">{html.escape(subtitle)}</text>']
    return out


def line_chart(path, title, subtitle, series, xlabel, ylabel, ymax=None, xmax=None, markers=(), yfmt="{:g}", legend="br"):
    """series: list of (label, [(x, y), ...]); markers: list of (x, label)."""
    xs = [x for _, pts in series for x, _ in pts]
    ys = [y for _, pts in series for _, y in pts]
    xmax = xmax or max(xs)
    ymax = ymax or (max(ys) * 1.1 or 1)
    sx = lambda x: L + (W - R - L) * x / xmax
    sy = lambda y: B - (B - T) * y / ymax
    out = _head(title, subtitle)
    ystep = _nice_step(ymax)
    y = 0
    while y <= ymax + 1e-9:
        out.append(f'<line x1="{L}" y1="{sy(y):.1f}" x2="{W-R}" y2="{sy(y):.1f}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{L-8}" y="{sy(y)+4:.1f}" font-size="13" fill="#6b7280" text-anchor="end">{yfmt.format(y)}</text>')
        y += ystep
    xstep = _nice_step(xmax, 8)
    x = 0
    while x <= xmax + 1e-9:
        out.append(f'<text x="{sx(x):.1f}" y="{B+20}" font-size="13" fill="#6b7280" text-anchor="middle">{x:g}</text>')
        x += xstep
    out.append(f'<text x="{(L+W-R)/2}" y="{B+44}" font-size="13" fill="#374151" text-anchor="middle">{html.escape(xlabel)}</text>')
    out.append(f'<text x="18" y="{(T+B)/2}" font-size="13" fill="#374151" text-anchor="middle" transform="rotate(-90 18 {(T+B)/2})">{html.escape(ylabel)}</text>')
    for k, (mx, mlabel) in enumerate(markers):
        out.append(f'<line x1="{sx(mx):.1f}" y1="{T}" x2="{sx(mx):.1f}" y2="{B}" stroke="#9ca3af" stroke-dasharray="4 4"/>')
        anchor, dx = ("end", -4) if sx(mx) > W - R - 120 else ("start", 4)
        out.append(f'<text x="{sx(mx)+dx:.1f}" y="{T+12+14*(k%2)}" font-size="12" fill="#6b7280" text-anchor="{anchor}">{html.escape(mlabel)}</text>')
    for i, (label, pts) in enumerate(series):
        c = COLORS[i % len(COLORS)]
        d = " ".join(f"{'M' if j == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for j, (x, y) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.5"/>')
        lx = {"br": W - R - 300, "bl": L + 16, "tl": L + 16, "tr": W - R - 300}[legend]
        ly = (B - 14 - 20 * (len(series) - 1 - i)) if legend.startswith("b") else (T + 34 + 20 * i)
        out.append(f'<rect x="{lx}" y="{ly-10}" width="14" height="4" fill="{c}"/>')
        out.append(f'<text x="{lx+20}" y="{ly-4}" font-size="13" fill="#374151">{html.escape(label)}</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out) + "\n")


def bar_chart(path, title, subtitle, groups, series_labels, unit, ymax=None):
    """groups: list of (group label, [value per series])."""
    vals = [v for _, vs in groups for v in vs]
    ymax = ymax or max(vals) * 1.2
    sy = lambda y: B - (B - T) * y / ymax
    out = _head(title, subtitle)
    ystep = _nice_step(ymax)
    y = 0
    while y <= ymax + 1e-9:
        out.append(f'<line x1="{L}" y1="{sy(y):.1f}" x2="{W-R}" y2="{sy(y):.1f}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{L-8}" y="{sy(y)+4:.1f}" font-size="13" fill="#6b7280" text-anchor="end">{y:g} {unit}</text>')
        y += ystep
    gw = (W - R - L) / len(groups)
    n = len(series_labels)
    bw = min(90, gw * 0.7 / n)
    for g, (glabel, vs) in enumerate(groups):
        x0 = L + gw * g + (gw - bw * n) / 2
        for i, v in enumerate(vs):
            c = COLORS[i % len(COLORS)]
            x = x0 + bw * i
            out.append(f'<rect x="{x:.1f}" y="{sy(v):.1f}" width="{bw-6:.1f}" height="{B-sy(v):.1f}" fill="{c}" rx="3"/>')
            out.append(f'<text x="{x+(bw-6)/2:.1f}" y="{sy(v)-6:.1f}" font-size="13" fill="#161641" text-anchor="middle" font-weight="600">{v:.1f} {unit}</text>')
        out.append(f'<text x="{L+gw*g+gw/2:.1f}" y="{B+22}" font-size="14" fill="#374151" text-anchor="middle">{html.escape(glabel)}</text>')
    for i, label in enumerate(series_labels):
        c = COLORS[i % len(COLORS)]
        lx, ly = W - R - 220, T + 6 + 20 * i
        out.append(f'<rect x="{lx}" y="{ly-10}" width="14" height="10" fill="{c}" rx="2"/>')
        out.append(f'<text x="{lx+20}" y="{ly}" font-size="13" fill="#374151">{html.escape(label)}</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out) + "\n")


def stacked_hbar(path, title, subtitle, rows, segment_labels, unit="min"):
    """rows: list of (label, [segment values]); one horizontal stacked bar per row."""
    left, right = 230, W - 40
    total_max = max(sum(v) for _, v in rows) * 1.08
    sx = lambda x: left + (right - left) * x / total_max
    out = _head(title, subtitle)
    step = _nice_step(total_max, 8)
    x = 0
    while x <= total_max + 1e-9:
        out.append(f'<line x1="{sx(x):.1f}" y1="{T}" x2="{sx(x):.1f}" y2="{B-50}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{sx(x):.1f}" y="{B-32}" font-size="13" fill="#6b7280" text-anchor="middle">{x:g} {unit}</text>')
        x += step
    bh = 44
    for i, (label, vals) in enumerate(rows):
        y = T + 14 + i * (bh + 26)
        out.append(f'<text x="{left-12}" y="{y+bh/2+5}" font-size="14" fill="#161641" text-anchor="end" font-weight="600">{html.escape(label)}</text>')
        acc = 0
        for j, v in enumerate(vals):
            c = COLORS[j % len(COLORS)]
            out.append(f'<rect x="{sx(acc):.1f}" y="{y}" width="{max(sx(acc+v)-sx(acc), 1):.1f}" height="{bh}" fill="{c}"/>')
            if sx(acc + v) - sx(acc) > 34:
                out.append(f'<text x="{(sx(acc)+sx(acc+v))/2:.1f}" y="{y+bh/2+5}" font-size="12" fill="#ffffff" text-anchor="middle" font-weight="600">{v:.1f}</text>')
            acc += v
        out.append(f'<text x="{sx(acc)+8:.1f}" y="{y+bh/2+5}" font-size="13" fill="#161641">{acc:.1f} {unit}</text>')
    lx, ly = 24, B - 2
    for j, sl in enumerate(segment_labels):
        c = COLORS[j % len(COLORS)]
        out.append(f'<rect x="{lx}" y="{ly-10}" width="12" height="12" fill="{c}" rx="2"/>')
        out.append(f'<text x="{lx+18}" y="{ly}" font-size="13" fill="#374151">{html.escape(sl)}</text>')
        lx += 30 + 7.2 * len(sl)
    out.append("</svg>")
    open(path, "w").write("\n".join(out) + "\n")
