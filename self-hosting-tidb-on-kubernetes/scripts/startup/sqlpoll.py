# sqlpoll.py <host> <outfile>: poll until SELECT 1 works with the root password (TLS if /work/poll-ca.crt), write the epoch it first worked
import os, ssl, sys, time, pymysql
host, out = sys.argv[1], sys.argv[2]
pw = open("/work/poll-pw").read().strip()
kw = dict(host=host, port=4000, user="root", password=pw, connect_timeout=2, read_timeout=3)
if os.path.getsize("/work/poll-ca.crt") > 0:
    kw["ssl"] = {"ca": "/work/poll-ca.crt", "check_hostname": False}
while True:
    try:
        c = pymysql.connect(**kw); c.cursor().execute("select 1"); c.close()
        open(out, "w").write(f"{time.time():.1f}\n"); break
    except Exception:
        time.sleep(0.5)
