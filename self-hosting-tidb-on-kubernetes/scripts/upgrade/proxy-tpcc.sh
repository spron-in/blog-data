#!/bin/bash
# Upgrade through TiProxy: 32 TPC-C clients for 40 min; change spec.version 7.5.5 -> 8.5.2 at 5 min.
go-tpc tpcc run -T 32 --warehouses 50 -H $H -P $PO -p $PW $SSL -D tpcc --interval 5s --time 40m --ignore-error
