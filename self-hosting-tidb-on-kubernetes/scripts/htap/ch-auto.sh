#!/bin/bash
# CH-benCHmark with the optimizer choosing the engine for every session.
go-tpc ch run -T 32 -t 2 --time 15m --warehouses 100 -H $H -P $PO -p $PW $SSL -D tpcc --interval 10s --ignore-error
