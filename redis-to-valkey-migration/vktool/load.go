package main

import (
	"context"
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"math/rand/v2"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

// phase runs fn for indexes [0,total) in chunks of batch, one pipeline per
// chunk. stop, if set, is checked between chunks and ends the phase early.
func phase(ctx context.Context, c *redis.ClusterClient, name string, total int64, workers, batch int,
	stop func() bool, fn func(p redis.Pipeliner, r *rand.Rand, i int64)) int64 {
	var next, done atomic.Int64
	start := time.Now()
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	finished := make(chan struct{})
	go func() {
		for {
			select {
			case <-finished:
				return
			case <-ticker.C:
				d := done.Load()
				log.Printf("%s: %d/%d (%.0f/s)", name, d, total, float64(d)/time.Since(start).Seconds())
			}
		}
	}()
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for ctx.Err() == nil {
				if stop != nil && stop() {
					return
				}
				from := next.Add(int64(batch)) - int64(batch)
				if from >= total {
					return
				}
				to := min(from+int64(batch), total)
				r := rand.New(rand.NewPCG(uint64(from), 0x5eed))
				for attempt := 0; ; attempt++ {
					p := c.Pipeline()
					for i := from; i < to; i++ {
						fn(p, r, i)
					}
					if _, err := p.Exec(ctx); err != nil {
						if attempt < 5 && ctx.Err() == nil {
							log.Printf("%s: retry chunk %d: %v", name, from, err)
							time.Sleep(time.Second)
							continue
						}
						log.Fatalf("%s: chunk %d: %v", name, from, err)
					}
					break
				}
				done.Add(to - from)
			}
		}()
	}
	wg.Wait()
	close(finished)
	d := done.Load()
	log.Printf("%s: done %d in %s", name, d, time.Since(start).Round(time.Second))
	return d
}

func randHex(r *rand.Rand, n int) string {
	b := make([]byte, (n+1)/2)
	for i := range b {
		b[i] = byte(r.Uint32())
	}
	return hex.EncodeToString(b)[:n]
}

var countries = []string{"US", "DE", "FR", "GB", "IN", "BR", "JP", "NL", "PL", "ES", "IT", "CA"}
var plans = []string{"free", "starter", "pro", "business", "enterprise"}

func sessionValue(r *rand.Rand) string {
	size := 400 + r.IntN(1200)
	items := 1 + r.IntN(6)
	cart := ""
	for i := 0; i < items; i++ {
		if i > 0 {
			cart += ","
		}
		cart += fmt.Sprintf(`{"sku":"SKU-%06d","qty":%d,"price":%d.%02d}`, r.IntN(1000000), 1+r.IntN(4), r.IntN(500), r.IntN(100))
	}
	v := fmt.Sprintf(`{"uid":%d,"token":"%s","csrf":"%s","ip":"10.%d.%d.%d","ua":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36","locale":"en-%s","cart":[%s],"flash":"`,
		r.IntN(50000000), randHex(r, 32), randHex(r, 32), r.IntN(256), r.IntN(256), r.IntN(256), countries[r.IntN(len(countries))], cart)
	if pad := size - len(v) - 2; pad > 0 {
		v += randHex(r, pad)
	}
	return v + `"}`
}

func loadA(args []string) {
	fs := flag.NewFlagSet("load-a", flag.ExitOnError)
	var src endpointFlags
	src.register(fs, "")
	targetGB := fs.Float64("target-gb", 50, "stop adding sessions when used_memory reaches this many GiB")
	scale := fs.Float64("scale", 1, "scale every fixed phase (for small trial runs)")
	workers := fs.Int("workers", 64, "concurrent pipelines")
	only := fs.String("only", "", "run only this phase")
	_ = fs.Parse(args)
	ctx := signalContext()
	c := src.client(*workers * 2)
	n := func(x float64) int64 { return int64(x * *scale) }
	run := func(name string) bool { return *only == "" || *only == name }

	if run("leaderboards") {
		// 20 sorted sets of 1M members, one ZADD of 1000 members per item.
		boards, members := int64(20), n(1_000_000)
		perBoard := (members + 999) / 1000
		phase(ctx, c, "leaderboards", boards*perBoard, *workers, 4, nil, func(p redis.Pipeliner, r *rand.Rand, i int64) {
			board, chunk := i/perBoard, i%perBoard
			zs := make([]redis.Z, 0, 1000)
			for m := chunk * 1000; m < min(chunk*1000+1000, members); m++ {
				zs = append(zs, redis.Z{Score: float64(r.IntN(10_000_000)), Member: fmt.Sprintf("player:%08d", m)})
			}
			p.ZAdd(ctx, fmt.Sprintf("lb:{game%02d}", board), zs...)
		})
	}
	streams, perStream := int64(200), n(50_000)
	if run("streams") {
		phase(ctx, c, "streams", streams*perStream, *workers, 500, nil, func(p redis.Pipeliner, r *rand.Rand, i int64) {
			p.XAdd(ctx, &redis.XAddArgs{Stream: fmt.Sprintf("events:{%03d}", i%streams), Values: []any{
				"type", []string{"click", "view", "purchase", "signup"}[r.IntN(4)],
				"user", strconv.Itoa(r.IntN(10_000_000)),
				"payload", randHex(r, 120+r.IntN(80)),
			}})
		})
		for s := int64(0); s < streams; s++ {
			key := fmt.Sprintf("events:{%03d}", s)
			if err := c.XGroupCreate(ctx, key, "workers", "0").Err(); err != nil {
				log.Printf("group %s: %v", key, err)
			}
			_ = c.XGroupCreate(ctx, key, "analytics", "$").Err()
			// Leave 2000 entries pending in the workers group.
			if err := c.XReadGroup(ctx, &redis.XReadGroupArgs{Group: "workers", Consumer: "w1", Streams: []string{key, ">"}, Count: 2000}).Err(); err != nil {
				log.Printf("readgroup %s: %v", key, err)
			}
		}
	}
	if run("users") {
		phase(ctx, c, "users", n(10_000_000), *workers, 500, nil, func(p redis.Pipeliner, r *rand.Rand, i int64) {
			p.HSet(ctx, fmt.Sprintf("user:%d", i),
				"name", "user-"+randHex(r, 10),
				"email", fmt.Sprintf("u%d@example.com", i),
				"country", countries[r.IntN(len(countries))],
				"plan", plans[r.IntN(len(plans))],
				"created", strconv.FormatInt(1_600_000_000+r.Int64N(150_000_000), 10),
				"last_login", strconv.FormatInt(1_780_000_000+r.Int64N(10_000_000), 10),
				"score", strconv.Itoa(r.IntN(100000)),
				"flags", strconv.Itoa(r.IntN(256)),
				"locale", "en-"+countries[r.IntN(len(countries))],
				"bio", randHex(r, 100+r.IntN(100)))
		})
	}
	if run("feeds") {
		phase(ctx, c, "feeds", n(1_000_000), *workers, 100, nil, func(p redis.Pipeliner, r *rand.Rand, i int64) {
			items := make([]any, 40)
			for j := range items {
				items[j] = fmt.Sprintf(`{"post":%d,"author":%d,"ts":%d,"t":"%s"}`, r.IntN(1e9), r.IntN(1e7), 1_780_000_000+r.IntN(1e7), randHex(r, 40))
			}
			p.RPush(ctx, fmt.Sprintf("feed:%d", i), items...)
		})
	}
	if run("tags") {
		phase(ctx, c, "tags", n(2_000_000), *workers, 500, nil, func(p redis.Pipeliner, r *rand.Rand, i int64) {
			members := make([]any, 15)
			for j := range members {
				members[j] = "tag-" + strconv.Itoa(r.IntN(5000))
			}
			p.SAdd(ctx, fmt.Sprintf("tags:%d", i), members...)
		})
	}
	if run("counters") {
		phase(ctx, c, "counters", n(5_000_000), *workers, 1000, nil, func(p redis.Pipeliner, r *rand.Rand, i int64) {
			p.Set(ctx, fmt.Sprintf("cnt:%d", i), r.IntN(1_000_000), 0)
		})
	}
	if run("sessions") {
		target := int64(*targetGB * (1 << 30))
		var full atomic.Bool
		go func() {
			for !full.Load() && ctx.Err() == nil {
				used := usedMemory(ctx, c)
				if used >= target {
					full.Store(true)
				}
				time.Sleep(2 * time.Second)
			}
		}()
		phase(ctx, c, "sessions", 1<<40, *workers, 200, full.Load, func(p redis.Pipeliner, r *rand.Rand, i int64) {
			ttl := time.Duration(7*24+r.IntN(23*24)) * time.Hour
			p.Set(ctx, fmt.Sprintf("sess:%d", i), sessionValue(r), ttl)
		})
	}
	log.Printf("used_memory: %.2f GiB", float64(usedMemory(ctx, c))/(1<<30))
}

func loadB(args []string) {
	fs := flag.NewFlagSet("load-b", flag.ExitOnError)
	var src endpointFlags
	src.register(fs, "")
	count := fs.Int64("count", 150_000_000, "keys")
	workers := fs.Int("workers", 64, "concurrent pipelines")
	_ = fs.Parse(args)
	ctx := signalContext()
	c := src.client(*workers * 2)
	const alnum = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	phase(ctx, c, "keys", *count, *workers, 1000, nil, func(p redis.Pipeliner, r *rand.Rand, i int64) {
		v := make([]byte, 32+r.IntN(33))
		for j := range v {
			v[j] = alnum[r.IntN(len(alnum))]
		}
		var ttl time.Duration
		if r.IntN(5) == 0 {
			ttl = time.Duration(7*24+r.IntN(23*24)) * time.Hour
		}
		p.Set(ctx, fmt.Sprintf("obj:%010d", i), v, ttl)
	})
	log.Printf("used_memory: %.2f GiB", float64(usedMemory(ctx, c))/(1<<30))
}
