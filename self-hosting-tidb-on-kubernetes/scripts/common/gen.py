#!/usr/bin/env python3
"""gen.py <preset> <name> [--version V] [--no-tls] [--drop comp,...] : Instance YAML on stdout,
from the live InstancePreset, pinned to the dedicated DB nodes. Volumes go on $STORAGE_CLASS if set."""
import argparse, json, os, subprocess, sys
ap = argparse.ArgumentParser()
ap.add_argument("preset"); ap.add_argument("name")
ap.add_argument("--version"); ap.add_argument("--no-tls", action="store_true"); ap.add_argument("--drop", default="")
a = ap.parse_args()
p = json.loads(subprocess.check_output(["kubectl", "get", "instancepresets.core.openeverest.io", "-n", "everest-system", a.preset, "-o", "json"]))
spec = p["spec"]
for c in filter(None, a.drop.split(",")):
    spec["components"].pop(c)
if a.version: spec["version"] = a.version
if a.no_tls: spec["topology"]["parameters"]["tls"] = {"cluster": False, "client": False}
for comp in spec["components"].values():
    comp["schedulingPolicy"] = {"nodeSelector": {"tidb-bench": "db"},
                                "tolerations": [{"key": "dedicated", "operator": "Equal", "value": "tidb", "effect": "NoSchedule"}]}
    if "storage" in comp and os.environ.get("STORAGE_CLASS"):
        comp["storage"]["storageClass"] = os.environ["STORAGE_CLASS"]
inst = {"apiVersion": "core.openeverest.io/v1alpha1", "kind": "Instance", "metadata": {"name": a.name, "namespace": os.environ.get("NS", "tidb")}, "spec": spec}
json.dump(inst, sys.stdout, indent=1)
