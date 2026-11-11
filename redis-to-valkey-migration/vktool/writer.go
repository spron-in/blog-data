package main

import (
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

// writer is a light application workload: a steady rate of writes of every
// kind the dataset has (new keys, updates, deletes, TTL changes, short-lived
// keys), until it is stopped.
func writer(args []string) {
	fs := flag.NewFlagSet("writer", flag.ExitOnError)
	var src endpointFlags
	src.register(fs, "")
	dataset := fs.String("dataset", "a", "a or b")
	rate := fs.Int("rate", 2000, "operations per second")
	workers := fs.Int("workers", 20, "concurrent clients")
	bKeys := fs.Int64("b-keys", 150_000_000, "keys of dataset b")
	_ = fs.Parse(args)
	ctx := signalContext()
	c := src.client(*workers + 4)

	var seq, ok, failed atomic.Int64
	var mu sync.Mutex
	counts := map[string]int64{}
	opA := func(r *rand.Rand) (string, redis.Cmder) {
		x := r.IntN(100)
		switch {
		case x < 25:
			return "new-session", c.Set(ctx, fmt.Sprintf("sess:live:%d", seq.Add(1)), sessionValue(r), 24*time.Hour)
		case x < 35:
			return "update-session", c.Set(ctx, fmt.Sprintf("sess:%d", r.IntN(1_000_000)), sessionValue(r), 7*24*time.Hour)
		case x < 50:
			return "hset-user", c.HSet(ctx, fmt.Sprintf("user:%d", r.IntN(10_000_000)), "last_login", time.Now().Unix())
		case x < 65:
			return "incr", c.Incr(ctx, fmt.Sprintf("cnt:%d", r.IntN(5_000_000)))
		case x < 75:
			return "lpush-feed", c.LPush(ctx, fmt.Sprintf("feed:%d", r.IntN(1_000_000)), fmt.Sprintf(`{"post":%d,"ts":%d}`, r.IntN(1e9), time.Now().Unix()))
		case x < 80:
			return "zincrby", c.ZIncrBy(ctx, fmt.Sprintf("lb:{game%02d}", r.IntN(20)), 1, fmt.Sprintf("player:%08d", r.IntN(1_000_000)))
		case x < 85:
			return "xadd", c.XAdd(ctx, &redis.XAddArgs{Stream: fmt.Sprintf("events:{%03d}", r.IntN(200)), Values: []any{"type", "live", "user", strconv.Itoa(r.IntN(1e7))}})
		case x < 90:
			return "del-session", c.Del(ctx, fmt.Sprintf("sess:%d", 1_000_000+r.IntN(1_000_000)))
		case x < 95:
			return "short-ttl", c.Set(ctx, fmt.Sprintf("tmp:%d", seq.Add(1)), "x", 20*time.Second)
		default:
			return "expire-user", c.Expire(ctx, fmt.Sprintf("user:%d", r.IntN(10_000_000)), 30*24*time.Hour)
		}
	}
	opB := func(r *rand.Rand) (string, redis.Cmder) {
		x := r.IntN(100)
		switch {
		case x < 40:
			return "update", c.Set(ctx, fmt.Sprintf("obj:%010d", r.Int64N(*bKeys)), randHex(r, 48), 0)
		case x < 60:
			return "new", c.Set(ctx, fmt.Sprintf("obj:live:%d", seq.Add(1)), randHex(r, 48), 24*time.Hour)
		case x < 80:
			return "incr", c.Incr(ctx, fmt.Sprintf("ctr:%d", r.IntN(1000)))
		case x < 90:
			return "del", c.Del(ctx, fmt.Sprintf("obj:%010d", r.Int64N(*bKeys)))
		default:
			return "short-ttl", c.Set(ctx, fmt.Sprintf("tmp:%d", seq.Add(1)), "x", 20*time.Second)
		}
	}
	op := opA
	if *dataset == "b" {
		op = opB
	}

	interval := time.Duration(float64(time.Second) * float64(*workers) / float64(*rate))
	var wg sync.WaitGroup
	for w := 0; w < *workers; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			r := rand.New(rand.NewPCG(uint64(time.Now().UnixNano()), uint64(w)))
			t := time.NewTicker(interval)
			defer t.Stop()
			for {
				select {
				case <-ctx.Done():
					return
				case <-t.C:
				}
				name, cmd := op(r)
				if err := cmd.Err(); err != nil && err != redis.Nil {
					failed.Add(1)
					if failed.Load()%100 == 1 {
						log.Printf("%s: %v", name, err)
					}
					continue
				}
				ok.Add(1)
				mu.Lock()
				counts[name]++
				mu.Unlock()
			}
		}(w)
	}
	go func() {
		t := time.NewTicker(30 * time.Second)
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				log.Printf("writer: ok=%d failed=%d", ok.Load(), failed.Load())
			}
		}
	}()
	wg.Wait()
	mu.Lock()
	log.Printf("writer stopped: ok=%d failed=%d by type=%v", ok.Load(), failed.Load(), counts)
	mu.Unlock()

}
