#!/bin/bash
# TPC-C data, 50 warehouses (also used for the TLS clusters).
go-tpc tpcc prepare --warehouses 50 -T 16 -H $H -P $PO -p $PW $SSL -D tpcc
