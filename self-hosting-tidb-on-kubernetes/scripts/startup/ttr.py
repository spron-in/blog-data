#!/usr/bin/env python3
"""ttr.py <instance> <apply-epoch> <ready-s> <sql-s> <id> <label> <preset>: one ttr.json run from pod conditions and events."""
import json, os, subprocess, sys
from datetime import datetime
name, t0, ready, sql, rid, label, preset = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6], sys.argv[7]
ns = os.environ.get("NS", "tidb")
k = lambda *a: json.loads(subprocess.check_output(["kubectl", "-n", ns, *a, "-o", "json"]))
ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() - t0 if s else None
pods = k("get", "pods", "-l", f"core.openeverest.io/instance={name}")["items"]
events = k("get", "events")["items"]
out = []
for p in pods:
    pn, comp = p["metadata"]["name"], p["metadata"]["labels"]["core.openeverest.io/component"]
    cond = {c["type"]: c.get("lastTransitionTime") for c in p["status"].get("conditions", [])}
    ev = [e for e in events if e["involvedObject"].get("name") == pn]
    att = [ts(e.get("lastTimestamp") or e.get("eventTime")) for e in ev if e["reason"] == "SuccessfulAttachVolume"]
    # the pod's first image is ready (PD's init container uses the PD image)
    pulled = [ts(e.get("lastTimestamp") or e.get("eventTime")) for e in ev if e["reason"] == "Pulled"]
    restarts = sum(cs.get("restartCount", 0) for cs in p["status"].get("containerStatuses", []))
    r1 = lambda v: round(v, 1) if v is not None else None
    out.append({"c": comp, "_n": pn, "s": r1(ts(cond.get("PodScheduled"))), "a": r1(min(att)) if att else None,
                "p": r1(min(pulled)) if pulled else None, "r": r1(ts(cond.get("Ready"))), "x": restarts})
order = ["pd", "tidb", "tikv", "tiflash", "tiproxy"]
out.sort(key=lambda o: (order.index(o["c"]), o["s"] or 0, o["_n"]))
cnt = {}
for o in out:
    cnt[o["c"]] = cnt.get(o["c"], 0) + 1; o["n"] = f'{o["c"]}-{cnt[o["c"]]}'; del o["_n"]
    o.update({kk: o.pop(kk) for kk in ["n", "s", "a", "p", "r", "x"]})
print(json.dumps({"id": rid, "label": label, "preset": preset, "ready": ready, "sql": sql, "pods": out}))
