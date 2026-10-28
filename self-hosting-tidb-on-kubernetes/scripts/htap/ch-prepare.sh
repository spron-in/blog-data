#!/bin/bash
# CH-benCHmark's extra tables (supplier, nation, region) on top of the TPC-C data.
go-tpc ch prepare --warehouses 100 -T 8 -H $H -P $PO -p $PW $SSL -D tpcc
