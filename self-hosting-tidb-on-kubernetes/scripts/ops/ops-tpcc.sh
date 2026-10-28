#!/bin/bash
# 32 TPC-C clients for 60 min while force-deleting a TiKV pod and taking a backup.
go-tpc tpcc run -T 32 --warehouses 100 -H $H -P $PO -p $PW $SSL -D tpcc --interval 5s --time 60m --ignore-error --conn-params "tidb_isolation_read_engines='tikv,tidb'"
