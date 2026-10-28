#!/bin/bash
# Baseline: TPC-C alone, 32 clients, 10 min.
go-tpc tpcc run -T 32 --time 10m --warehouses 100 -H $H -P $PO -p $PW $SSL -D tpcc --interval 10s --ignore-error
