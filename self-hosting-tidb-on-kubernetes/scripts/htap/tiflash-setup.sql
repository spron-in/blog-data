-- Two TiFlash replicas of every CH-benCHmark table, then fresh statistics. Run with:
--   $MYSQL -D tpcc < tiflash-setup.sql
-- and wait until `select table_name, progress, available from information_schema.tiflash_replica
-- where table_schema='tpcc'` shows every table available.
alter table warehouse set tiflash replica 2;
alter table district set tiflash replica 2;
alter table customer set tiflash replica 2;
alter table history set tiflash replica 2;
alter table new_order set tiflash replica 2;
alter table orders set tiflash replica 2;
alter table order_line set tiflash replica 2;
alter table item set tiflash replica 2;
alter table stock set tiflash replica 2;
alter table supplier set tiflash replica 2;
alter table nation set tiflash replica 2;
alter table region set tiflash replica 2;
analyze table warehouse; analyze table district; analyze table customer; analyze table history;
analyze table new_order; analyze table orders; analyze table order_line; analyze table item;
analyze table stock; analyze table supplier; analyze table nation; analyze table region;
-- Table for freshness.py: written through TiKV, read back through TiFlash.
create table if not exists fresh (id bigint primary key, ts datetime(6));
alter table fresh set tiflash replica 2;
