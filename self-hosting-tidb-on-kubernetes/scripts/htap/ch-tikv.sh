#!/bin/bash
# CH-benCHmark: 32 TPC-C clients plus 2 analytical clients, analytics pinned to TiKV.
go-tpc ch run -T 32 -t 2 --time 15m --warehouses 100 -H $H -P $PO -p $PW $SSL -D tpcc --interval 10s --ignore-error --ap-conn-params "tidb_isolation_read_engines='tikv,tidb'"
