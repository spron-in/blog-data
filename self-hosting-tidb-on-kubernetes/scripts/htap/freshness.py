# Runs inside loadgen: python3 freshness.py <label> <n>
import json, os, ssl, sys, time, pymysql
label, n = sys.argv[1], int(sys.argv[2])
kw = dict(host=os.environ["H"], port=int(os.environ["PO"]), user="root", password=os.environ["PW"], database="tpcc", autocommit=True)
if os.environ.get("CA"):
    kw["ssl"] = {"ca": os.environ["CA"]}
w, r = pymysql.connect(**kw), pymysql.connect(**kw)
wc, rc = w.cursor(), r.cursor()
rc.execute("set session tidb_isolation_read_engines='tiflash,tidb'")
rc.execute("explain select count(*) from fresh where id=1")
plan = "\n".join(str(x) for x in rc.fetchall())
assert "tiflash" in plan, plan
base = int(time.time() * 1000) * 1000
out = []
for i in range(n):
    k = base + i
    t0 = time.perf_counter(); wc.execute("insert into fresh values (%s, now(6))", (k,)); t1 = time.perf_counter()
    err = None
    try:
        rc.execute("select count(*) from fresh where id=%s", (k,)); seen = rc.fetchone()[0] == 1
    except pymysql.MySQLError as e:
        seen, err = None, str(e)[:160]
    t2 = time.perf_counter()
    out.append({"i": i, "w_ms": round((t1 - t0) * 1000, 2), "r_ms": round((t2 - t1) * 1000, 2), "seen": seen, "err": err})
    time.sleep(0.05)
json.dump({"label": label, "plan": plan, "samples": out}, open(f"/work/fresh-{label}.json", "w"))
ok = [x for x in out if x["err"] is None]
s = sorted(x["r_ms"] for x in ok)
print(label, "reads", len(ok), "errors", n - len(ok), "seen", sum(1 for x in ok if x["seen"]), "/", len(ok), "read p50", s[len(s)//2] if s else None, "p99", s[int(len(s)*.99)] if s else None)
