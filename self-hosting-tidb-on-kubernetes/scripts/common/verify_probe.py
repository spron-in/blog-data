# Runs inside loadgen: python3 verify_probe.py <label> — match each acknowledged write (t rounded to 1 ms)
# to a row in the probe table (id = exact microseconds); writes are 100 ms apart, so matching is unambiguous.
import bisect, json, os, sys, pymysql
label = sys.argv[1]
kw = dict(host=os.environ["H"], port=int(os.environ["PO"]), user="root", password=os.environ["PW"], database="tpcc")
if os.environ.get("CA"): kw["ssl"] = {"ca": os.environ["CA"]}
rows = [json.loads(l) for l in open(f"/work/probe-{label}.jsonl")]
acked = [r for r in rows if r["ok"]]
lo, hi = int(min(r["t"] for r in acked) * 1e6) - 2000, int(max(r["t"] for r in acked) * 1e6) + 2000
c = pymysql.connect(**kw).cursor(); c.execute("select id from probe where id between %s and %s", (lo, hi))
ids = sorted(r[0] for r in c.fetchall())
missing = []
for r in acked:
    want = r.get("id") or int(r["t"] * 1e6)
    i = bisect.bisect_left(ids, want - 1000)
    if not (i < len(ids) and ids[i] <= want + 1000): missing.append(r["t"])
json.dump({"acked": len(acked), "rows_in_window": len(ids), "missing": missing}, open(f"/work/probe-{label}-verify.json", "w"))
print(label, "acked", len(acked), "rows", len(ids), "missing", len(missing), missing[:5])
