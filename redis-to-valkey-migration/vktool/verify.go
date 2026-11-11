package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

const internalPrefix = "__openeverest_migration"

type verifyStats struct {
	mu            sync.Mutex
	Checked       int64            `json:"checked"`
	ByType        map[string]int64 `json:"byType"`
	Missing       int64            `json:"missingOnTarget"`
	TypeMismatch  int64            `json:"typeMismatch"`
	ValueMismatch int64            `json:"valueMismatch"`
	TTLLost       int64            `json:"ttlLost"`
	TTLAdded      int64            `json:"ttlAdded"`
	Expiring      int64            `json:"expiringSkipped"`
	WithTTL       int64            `json:"withTTL"`
	DriftBuckets  map[string]int64 `json:"ttlDriftBuckets"`
	DriftMinMs    int64            `json:"ttlDriftMinMs"`
	DriftMaxMs    int64            `json:"ttlDriftMaxMs"`
	DriftSumMs    float64          `json:"-"`
	DriftMeanMs   float64          `json:"ttlDriftMeanMs"`
	Examples      []string         `json:"examples"`
	SourceKeys    int64            `json:"sourceKeys"`
	TargetKeys    int64            `json:"targetKeys"`
	TargetIntern  int64            `json:"targetInternalKeys"`
	SourceIntern  int64            `json:"sourceInternalKeys"`
	Duration      string           `json:"duration"`
	MaxDriftKeys  []string         `json:"-"`
}

func (s *verifyStats) bad(kind *int64, key string) {
	s.mu.Lock()
	*kind++
	if len(s.Examples) < 30 {
		s.Examples = append(s.Examples, key)
	}
	s.mu.Unlock()
}

func driftBucket(ms int64) string {
	if ms < 0 {
		ms = -ms
	}
	switch {
	case ms == 0:
		return "0ms"
	case ms <= 1000:
		return "<=1s"
	case ms <= 10_000:
		return "<=10s"
	case ms <= 60_000:
		return "<=60s"
	case ms <= 600_000:
		return "<=10m"
	default:
		return ">10m"
	}
}

func digest(parts []string) [32]byte {
	h := sha256.New()
	for _, p := range parts {
		fmt.Fprintf(h, "%d:%s|", len(p), p)
	}
	var out [32]byte
	copy(out[:], h.Sum(nil))
	return out
}

// valueDigest reads one key's logical value and hashes it in a canonical form.
func valueDigest(ctx context.Context, c *redis.ClusterClient, key, typ string) ([32]byte, error) {
	var parts []string
	switch typ {
	case "string":
		v, err := c.Get(ctx, key).Result()
		if err != nil {
			return [32]byte{}, err
		}
		parts = []string{v}
	case "hash":
		m, err := c.HGetAll(ctx, key).Result()
		if err != nil {
			return [32]byte{}, err
		}
		for k, v := range m {
			parts = append(parts, k+"="+v)
		}
		sort.Strings(parts)
	case "list":
		v, err := c.LRange(ctx, key, 0, -1).Result()
		if err != nil {
			return [32]byte{}, err
		}
		parts = v
	case "set":
		v, err := c.SMembers(ctx, key).Result()
		if err != nil {
			return [32]byte{}, err
		}
		sort.Strings(v)
		parts = v
	case "zset":
		for start := int64(0); ; start += 10000 {
			v, err := c.ZRangeWithScores(ctx, key, start, start+9999).Result()
			if err != nil {
				return [32]byte{}, err
			}
			for _, z := range v {
				parts = append(parts, fmt.Sprint(z.Member)+"="+strconv.FormatFloat(z.Score, 'g', -1, 64))
			}
			if len(v) < 10000 {
				break
			}
		}
	case "stream":
		from := "-"
		for {
			v, err := c.XRangeN(ctx, key, from, "+", 5000).Result()
			if err != nil {
				return [32]byte{}, err
			}
			for _, m := range v {
				fields := make([]string, 0, len(m.Values))
				for k, val := range m.Values {
					fields = append(fields, k+"="+fmt.Sprint(val))
				}
				sort.Strings(fields)
				parts = append(parts, m.ID+"{"+strings.Join(fields, ",")+"}")
			}
			if len(v) < 5000 {
				break
			}
			from = "(" + v[len(v)-1].ID
		}
		groups, err := c.XInfoGroups(ctx, key).Result()
		if err != nil {
			return [32]byte{}, err
		}
		for _, g := range groups {
			parts = append(parts, fmt.Sprintf("group %s consumers=%d pending=%d last=%s", g.Name, g.Consumers, g.Pending, g.LastDeliveredID))
		}
	default:
		parts = []string{"unsupported type " + typ}
	}
	return digest(parts), nil
}

func verify(args []string) {
	fs := flag.NewFlagSet("verify", flag.ExitOnError)
	var src, dst endpointFlags
	src.register(fs, "src-")
	dst.register(fs, "dst-")
	workers := fs.Int("workers", 48, "concurrent batches")
	out := fs.String("out", "", "write the JSON summary here too")
	_ = fs.Parse(args)
	ctx := signalContext()
	s := src.client(*workers * 2)
	d := dst.client(*workers * 2)
	stats := &verifyStats{ByType: map[string]int64{}, DriftBuckets: map[string]int64{}, DriftMinMs: 1 << 62, DriftMaxMs: -(1 << 62)}
	start := time.Now()

	batches := make(chan []string, *workers*2)
	var scanned atomic.Int64
	go func() {
		_ = s.ForEachMaster(ctx, func(ctx context.Context, n *redis.Client) error {
			iter := n.Scan(ctx, 0, "", 1000).Iterator()
			batch := make([]string, 0, 1000)
			for iter.Next(ctx) {
				key := iter.Val()
				if strings.HasPrefix(key, internalPrefix) {
					atomic.AddInt64(&stats.SourceIntern, 1)
					continue
				}
				batch = append(batch, key)
				if len(batch) == 1000 {
					batches <- batch
					batch = make([]string, 0, 1000)
				}
			}
			if err := iter.Err(); err != nil {
				log.Fatalf("scan: %v", err)
			}
			if len(batch) > 0 {
				batches <- batch
			}
			return nil
		})
		close(batches)
	}()

	go func() {
		t := time.NewTicker(30 * time.Second)
		defer t.Stop()
		for range t.C {
			stats.mu.Lock()
			log.Printf("verify: checked=%d missing=%d typeMismatch=%d valueMismatch=%d (%.0f keys/s)",
				stats.Checked, stats.Missing, stats.TypeMismatch, stats.ValueMismatch, float64(stats.Checked)/time.Since(start).Seconds())
			stats.mu.Unlock()
		}
	}()

	var wg sync.WaitGroup
	for w := 0; w < *workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for batch := range batches {
				checkBatch(ctx, s, d, batch, stats)
				scanned.Add(int64(len(batch)))
			}
		}()
	}
	wg.Wait()

	count := func(c *redis.ClusterClient, internal *int64) int64 {
		var total atomic.Int64
		_ = c.ForEachMaster(ctx, func(ctx context.Context, n *redis.Client) error {
			size, err := n.DBSize(ctx).Result()
			if err != nil {
				log.Fatalf("dbsize: %v", err)
			}
			total.Add(size)
			if internal != nil {
				iter := n.Scan(ctx, 0, internalPrefix+"*", 1000).Iterator()
				for iter.Next(ctx) {
					atomic.AddInt64(internal, 1)
				}
			}
			return nil
		})
		return total.Load()
	}
	stats.SourceKeys = count(s, nil)
	stats.TargetKeys = count(d, &stats.TargetIntern)
	if stats.WithTTL > 0 {
		stats.DriftMeanMs = stats.DriftSumMs / float64(stats.WithTTL)
	}
	stats.Duration = time.Since(start).Round(time.Second).String()
	summary, _ := json.MarshalIndent(stats, "", "  ")
	fmt.Println(string(summary))
	if *out != "" {
		_ = os.WriteFile(*out, summary, 0o644)
	}
}

func checkBatch(ctx context.Context, s, d *redis.ClusterClient, keys []string, stats *verifyStats) {
	meta := func(c *redis.ClusterClient) ([]*redis.StatusCmd, []*redis.DurationCmd) {
		for attempt := 0; ; attempt++ {
			p := c.Pipeline()
			types := make([]*redis.StatusCmd, len(keys))
			exps := make([]*redis.DurationCmd, len(keys))
			for i, k := range keys {
				types[i] = p.Type(ctx, k)
				exps[i] = p.PExpireTime(ctx, k)
			}
			if _, err := p.Exec(ctx); err != nil && attempt < 5 {
				time.Sleep(time.Second)
				continue
			} else if err != nil {
				log.Fatalf("meta: %v", err)
			}
			return types, exps
		}
	}
	sTypes, sExps := meta(s)
	dTypes, dExps := meta(d)
	now := time.Now().UnixMilli()
	var simple []simpleKey
	for i, key := range keys {
		st, dt := sTypes[i].Val(), dTypes[i].Val()
		se, de := sExps[i].Val().Milliseconds(), dExps[i].Val().Milliseconds()
		// PExpireTime returns -1/-2 as durations of nanoseconds; normalize.
		if sExps[i].Val() < 0 {
			se = int64(sExps[i].Val())
		}
		if dExps[i].Val() < 0 {
			de = int64(dExps[i].Val())
		}
		if st == "none" || (se > 0 && se-now < 60_000) {
			atomic.AddInt64(&stats.Expiring, 1)
			continue
		}
		stats.mu.Lock()
		stats.Checked++
		stats.ByType[st]++
		stats.mu.Unlock()
		if dt == "none" {
			stats.bad(&stats.Missing, key)
			continue
		}
		if st != dt {
			stats.bad(&stats.TypeMismatch, key)
			continue
		}
		switch {
		case se > 0 && de <= 0:
			stats.bad(&stats.TTLLost, key)
		case se <= 0 && de > 0:
			stats.bad(&stats.TTLAdded, key)
		case se > 0:
			drift := de - se
			stats.mu.Lock()
			stats.WithTTL++
			stats.DriftBuckets[driftBucket(drift)]++
			stats.DriftSumMs += float64(drift)
			stats.DriftMinMs = min(stats.DriftMinMs, drift)
			stats.DriftMaxMs = max(stats.DriftMaxMs, drift)
			stats.mu.Unlock()
		}
		if simpleType(st) {
			simple = append(simple, simpleKey{key, st})
			continue
		}
		sd, err1 := valueDigest(ctx, s, key, st)
		dd, err2 := valueDigest(ctx, d, key, dt)
		if err1 != nil || err2 != nil {
			log.Printf("read %s: %v %v", key, err1, err2)
			stats.bad(&stats.ValueMismatch, key)
			continue
		}
		if sd != dd {
			stats.bad(&stats.ValueMismatch, key)
		}
	}
	if len(simple) == 0 {
		return
	}
	sd := simpleDigests(ctx, s, simple)
	dd := simpleDigests(ctx, d, simple)
	for i, k := range simple {
		if sd[i] != dd[i] {
			stats.bad(&stats.ValueMismatch, k.key)
		}
	}
}

type simpleKey struct{ key, typ string }

func simpleType(t string) bool { return t == "string" || t == "hash" || t == "list" || t == "set" }

// simpleDigests reads small values with one pipeline and hashes them.
func simpleDigests(ctx context.Context, c *redis.ClusterClient, keys []simpleKey) [][32]byte {
	for attempt := 0; ; attempt++ {
		p := c.Pipeline()
		cmds := make([]redis.Cmder, len(keys))
		for i, k := range keys {
			switch k.typ {
			case "string":
				cmds[i] = p.Get(ctx, k.key)
			case "hash":
				cmds[i] = p.HGetAll(ctx, k.key)
			case "list":
				cmds[i] = p.LRange(ctx, k.key, 0, -1)
			case "set":
				cmds[i] = p.SMembers(ctx, k.key)
			}
		}
		if _, err := p.Exec(ctx); err != nil && err != redis.Nil {
			if attempt < 5 {
				time.Sleep(time.Second)
				continue
			}
			log.Fatalf("values: %v", err)
		}
		out := make([][32]byte, len(keys))
		for i, cmd := range cmds {
			var parts []string
			switch v := cmd.(type) {
			case *redis.StringCmd:
				parts = []string{v.Val()}
			case *redis.MapStringStringCmd:
				for k, val := range v.Val() {
					parts = append(parts, k+"="+val)
				}
				sort.Strings(parts)
			case *redis.StringSliceCmd:
				parts = append(parts, v.Val()...)
				if keys[i].typ == "set" {
					sort.Strings(parts)
				}
			}
			if err := cmd.Err(); err != nil && err != redis.Nil {
				parts = []string{"error " + err.Error()}
			}
			out[i] = digest(parts)
		}
		return out
	}
}
