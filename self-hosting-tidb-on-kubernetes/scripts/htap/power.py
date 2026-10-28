# Runs inside loadgen: python3 power.py <engines> <label> [runs]   e.g. "tikv,tidb" tikv 2
import json, os, sys, time, pymysql
engines, label = sys.argv[1], sys.argv[2]; runs = int(sys.argv[3]) if len(sys.argv) > 3 else 2
qs = json.load(open("/work/ch-queries.json"))
kw = dict(host=os.environ["H"], port=int(os.environ["PO"]), user="root", password=os.environ["PW"], database="tpcc", autocommit=True)
if os.environ.get("CA"): kw["ssl"] = {"ca": os.environ["CA"]}
res = []
for name in sorted(qs, key=lambda k: int(k[1:])):
    for r in range(runs):
        c = pymysql.connect(**kw); cur = c.cursor()
        cur.execute(f"set session tidb_isolation_read_engines='{engines}'")
        cur.execute("set session max_execution_time=300000")
        t0 = time.perf_counter(); err = None; rows = None
        try:
            cur.execute(qs[name]); rows = len(cur.fetchall())
        except Exception as e:
            err = str(e)[:200]
        dt = time.perf_counter() - t0
        plan = None
        if r == 0:
            try:
                cur.execute("explain format='brief' " + qs[name].split("*/", 2)[-1]); plan = [list(map(str, x)) for x in cur.fetchall()]
            except Exception as e:
                plan = str(e)[:200]
        c.close()
        res.append({"q": name, "run": r + 1, "s": round(dt, 3), "rows": rows, "err": err, "plan": plan})
        print(label, name, r + 1, round(dt, 2), err or "", flush=True)
        json.dump({"label": label, "engines": engines, "results": res}, open(f"/work/power-{label}.json", "w"))
