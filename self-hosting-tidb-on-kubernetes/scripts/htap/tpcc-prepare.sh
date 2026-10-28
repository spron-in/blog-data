#!/bin/bash
# TPC-C data, 100 warehouses.
go-tpc tpcc prepare --warehouses 100 -T 32 --dropdata -H $H -P $PO -p $PW $SSL -D tpcc
