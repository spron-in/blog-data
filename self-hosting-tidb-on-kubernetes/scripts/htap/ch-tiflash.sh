#!/bin/bash
# CH-benCHmark with OLTP pinned to TiKV and analytics pinned to TiFlash.
go-tpc ch run -T 32 -t 2 --time 15m --warehouses 100 -H $H -P $PO -p $PW $SSL -D tpcc --interval 10s --ignore-error --conn-params "tidb_isolation_read_engines='tikv,tidb'" --ap-conn-params "tidb_isolation_read_engines='tiflash,tidb'"
