# Runs inside loadgen: python3 probe.py <label> <seconds>  -- one write every 100ms, new conn on error
import json, os, sys, time, pymysql
label, dur = sys.argv[1], float(sys.argv[2])
kw = dict(host=os.environ["H"], port=int(os.environ["PO"]), user="root", password=os.environ["PW"], database="tpcc",
          autocommit=True, connect_timeout=2, read_timeout=5, write_timeout=5)
if os.environ.get("CA"): kw["ssl"] = {"ca": os.environ["CA"]}
def conn():
    try: return pymysql.connect(**kw)
    except Exception: return None
c = conn()
if c: c.cursor().execute("create table if not exists probe (id bigint primary key, ts datetime(6))")
stop = f"/work/probe-{label}.stop"
if os.path.exists(stop): os.remove(stop)
f = open(f"/work/probe-{label}.jsonl", "w"); end = time.time() + dur; i = 0
while time.time() < end and not os.path.exists(stop):
    i += 1; t0 = time.time(); ok, err = False, None; rid = int(t0 * 1e6)
    try:
        if c is None: c = conn()
        if c is None: raise Exception("connect failed")
        c.cursor().execute("insert into probe values (%s, now(6))", (rid,)); ok = True
    except Exception as e:
        err = str(e)[:120]
        try: c and c.close()
        except Exception: pass
        c = None
    f.write(json.dumps({"t": round(t0, 3), "id": rid, "ms": round((time.time() - t0) * 1000, 1), "ok": ok, "err": err}) + "\n"); f.flush()
    time.sleep(max(0, 0.1 - (time.time() - t0)))
# verify acknowledged writes survived, by exact id
if c is None: c = conn()
cur = c.cursor(); acked = [json.loads(l) for l in open(f"/work/probe-{label}.jsonl")]
ids = {a["id"] for a in acked if a["ok"]}
cur.execute("select id from probe where id between %s and %s", (min(ids), max(ids)))
present = {r[0] for r in cur.fetchall()}
missing = sorted(ids - present)
json.dump({"acked": len(ids), "missing": missing}, open(f"/work/probe-{label}-verify.json", "w"))
print(label, "acked", len(ids), "found", len(ids & present), "missing", len(missing), "errors", sum(1 for a in acked if not a["ok"]))
