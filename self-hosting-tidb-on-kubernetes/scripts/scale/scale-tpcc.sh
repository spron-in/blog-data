#!/bin/bash
# 64 TPC-C clients for 90 min while scaling TiKV 3->5->3 and TiDB 2->4->2 (patch the Instance by hand).
go-tpc tpcc run -T 64 --warehouses 100 -H $H -P $PO -p $PW $SSL -D tpcc --interval 5s --time 90m --ignore-error --conn-params "tidb_isolation_read_engines='tikv,tidb'"
