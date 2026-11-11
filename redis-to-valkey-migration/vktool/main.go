// vktool loads, exercises, verifies and observes Redis/Valkey clusters for
// the Redis → Valkey migration tests.
package main

import (
	"context"
	"crypto/tls"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"
)

type endpointFlags struct {
	addr, user, password string
	tls                  bool
	cert, key            string
}

func (e *endpointFlags) register(fs *flag.FlagSet, prefix string) {
	fs.StringVar(&e.addr, prefix+"addr", "", "seed address host:port")
	fs.StringVar(&e.user, prefix+"user", "", "username")
	fs.StringVar(&e.password, prefix+"password", os.Getenv(strings.ToUpper(strings.ReplaceAll(prefix, "-", "_"))+"PASSWORD"), "password (or env)")
	fs.BoolVar(&e.tls, prefix+"tls", false, "use TLS (server not verified)")
	fs.StringVar(&e.cert, prefix+"cert", "", "client certificate file")
	fs.StringVar(&e.key, prefix+"key", "", "client key file")
}

func (e *endpointFlags) client(poolSize int) *redis.ClusterClient {
	opts := &redis.ClusterOptions{
		Addrs:        []string{e.addr},
		Username:     e.user,
		Password:     e.password,
		PoolSize:     poolSize,
		ReadTimeout:  60 * time.Second,
		WriteTimeout: 60 * time.Second,
		MaxRedirects: 8,
	}
	if e.tls {
		cfg := &tls.Config{InsecureSkipVerify: true} //nolint:gosec // test tool
		if e.cert != "" {
			pair, err := tls.LoadX509KeyPair(e.cert, e.key)
			if err != nil {
				log.Fatalf("load client certificate: %v", err)
			}
			cfg.Certificates = []tls.Certificate{pair}
		}
		opts.TLSConfig = cfg
	}
	c := redis.NewClusterClient(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if err := c.Ping(ctx).Err(); err != nil {
		log.Fatalf("ping %s: %v", e.addr, err)
	}
	return c
}

func signalContext() context.Context {
	ctx, _ := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	if d, err := time.ParseDuration(os.Getenv("VKTOOL_FOR")); err == nil {
		ctx, _ = context.WithTimeout(ctx, d)
	}
	return ctx
}

// infoFields parses INFO output into a map.
func infoFields(s string) map[string]string {
	m := map[string]string{}
	for _, line := range strings.Split(s, "\n") {
		line = strings.TrimSpace(line)
		if k, v, ok := strings.Cut(line, ":"); ok && !strings.HasPrefix(line, "#") {
			m[k] = v
		}
	}
	return m
}

func infoInt(m map[string]string, k string) int64 {
	v, _ := strconv.ParseInt(m[k], 10, 64)
	return v
}

// keyCount sums keys=N of every db line.
func keyCount(m map[string]string) int64 {
	var n int64
	for k, v := range m {
		if strings.HasPrefix(k, "db") {
			for _, part := range strings.Split(v, ",") {
				if strings.HasPrefix(part, "keys=") {
					x, _ := strconv.ParseInt(strings.TrimPrefix(part, "keys="), 10, 64)
					n += x
				}
			}
		}
	}
	return n
}

// usedMemory sums used_memory over the cluster's primaries.
func usedMemory(ctx context.Context, c *redis.ClusterClient) int64 {
	var total int64
	ch := make(chan int64, 64)
	_ = c.ForEachMaster(ctx, func(ctx context.Context, n *redis.Client) error {
		info, err := n.Info(ctx, "memory").Result()
		if err == nil {
			ch <- infoInt(infoFields(info), "used_memory")
		}
		return nil
	})
	close(ch)
	for v := range ch {
		total += v
	}
	return total
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: vktool load-a|load-b|writer|verify|poll [flags]")
		os.Exit(2)
	}
	cmd, args := os.Args[1], os.Args[2:]
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
	switch cmd {
	case "load-a":
		loadA(args)
	case "load-b":
		loadB(args)
	case "writer":
		writer(args)
	case "verify":
		verify(args)
	case "poll":
		poll(args)
	default:
		log.Fatalf("unknown command %q", cmd)
	}
}
