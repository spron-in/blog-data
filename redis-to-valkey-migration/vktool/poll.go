package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

type clusterSample struct {
	used, rss, maxRSS, keys, ops, inKbps, outKbps, replicas, forks, cow int64
}

func sampleCluster(ctx context.Context, c *redis.ClusterClient) clusterSample {
	var mu sync.Mutex
	var s clusterSample
	_ = c.ForEachMaster(ctx, func(ctx context.Context, n *redis.Client) error {
		ctx, cancel := context.WithTimeout(ctx, 4*time.Second)
		defer cancel()
		info, err := n.Info(ctx, "memory", "persistence", "stats", "replication", "keyspace").Result()
		if err != nil {
			return nil
		}
		f := infoFields(info)
		mu.Lock()
		defer mu.Unlock()
		s.used += infoInt(f, "used_memory")
		rss := infoInt(f, "used_memory_rss")
		s.rss += rss
		s.maxRSS = max(s.maxRSS, rss)
		s.keys += keyCount(f)
		s.ops += infoInt(f, "instantaneous_ops_per_sec")
		in, _ := strconv.ParseFloat(f["instantaneous_input_kbps"], 64)
		out, _ := strconv.ParseFloat(f["instantaneous_output_kbps"], 64)
		s.inKbps += int64(in)
		s.outKbps += int64(out)
		s.replicas += infoInt(f, "connected_slaves")
		s.forks += infoInt(f, "rdb_bgsave_in_progress") + infoInt(f, "aof_rewrite_in_progress")
		s.cow += infoInt(f, "current_cow_size")
		return nil
	})
	return s
}

type workerStatus struct {
	State                string `json:"state"`
	Message              string `json:"message"`
	Error                string `json:"error"`
	CopyDone             bool   `json:"copyDone"`
	InitialSyncCompleted bool   `json:"initialSyncCompleted"`
	BytesTotal           uint64 `json:"bytesTotal"`
	BytesCopied          uint64 `json:"bytesCopied"`
	LagSeconds           int64  `json:"lagSeconds"`
}

func poll(args []string) {
	fs := flag.NewFlagSet("poll", flag.ExitOnError)
	var src, dst endpointFlags
	src.register(fs, "src-")
	dst.register(fs, "dst-")
	workerURL := fs.String("worker", "", "worker base URL, e.g. http://10.2.3.4:2243 (or a file containing it)")
	out := fs.String("out", "metrics.csv", "CSV file")
	interval := fs.Duration("interval", 5*time.Second, "sample period")
	_ = fs.Parse(args)
	ctx := signalContext()
	s := src.client(8)
	d := dst.client(8)
	f, err := os.OpenFile(*out, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()
	w := csv.NewWriter(f)
	cols := []string{"ts", "src_used", "src_rss", "src_max_rss", "src_keys", "src_ops", "src_in_kbps", "src_out_kbps", "src_replicas", "src_forks", "src_cow",
		"dst_used", "dst_rss", "dst_max_rss", "dst_keys", "dst_ops", "dst_in_kbps", "dst_out_kbps", "dst_replicas", "dst_forks", "dst_cow",
		"w_state", "w_copy_done", "w_initial_sync", "w_bytes_total", "w_bytes_copied", "w_lag", "w_message", "w_error"}
	if st, _ := f.Stat(); st.Size() == 0 {
		_ = w.Write(cols)
	}
	httpc := &http.Client{Timeout: 3 * time.Second}
	t := time.NewTicker(*interval)
	defer t.Stop()
	for {
		now := time.Now()
		var ss, ds clusterSample
		var ws workerStatus
		var wg sync.WaitGroup
		wg.Add(3)
		go func() { defer wg.Done(); ss = sampleCluster(ctx, s) }()
		go func() { defer wg.Done(); ds = sampleCluster(ctx, d) }()
		go func() {
			defer wg.Done()
			url := *workerURL
			if b, err := os.ReadFile(url); err == nil {
				url = string(b)
			}
			if url == "" {
				return
			}
			resp, err := httpc.Get(url + "/status")
			if err != nil {
				ws.State = "unreachable"
				return
			}
			defer resp.Body.Close()
			_ = json.NewDecoder(resp.Body).Decode(&ws)
		}()
		wg.Wait()
		row := []string{now.UTC().Format(time.RFC3339)}
		for _, c := range []clusterSample{ss, ds} {
			for _, v := range []int64{c.used, c.rss, c.maxRSS, c.keys, c.ops, c.inKbps, c.outKbps, c.replicas, c.forks, c.cow} {
				row = append(row, strconv.FormatInt(v, 10))
			}
		}
		row = append(row, ws.State, fmt.Sprint(ws.CopyDone), fmt.Sprint(ws.InitialSyncCompleted),
			strconv.FormatUint(ws.BytesTotal, 10), strconv.FormatUint(ws.BytesCopied, 10), strconv.FormatInt(ws.LagSeconds, 10), ws.Message, ws.Error)
		_ = w.Write(row)
		w.Flush()
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}
