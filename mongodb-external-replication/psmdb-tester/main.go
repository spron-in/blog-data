package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/spf13/viper"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readpref"
	"gopkg.in/mgo.v2/bson"
)

func main() {
	viper.SetConfigType("yaml")
	viper.AddConfigPath(".")
	if err := viper.ReadInConfig(); err != nil {
		panic(err)
	}

	uri := fmt.Sprintf("mongodb://%s/%s", viper.Get("host"), viper.Get("database"))
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	credential := options.Credential{Username: viper.GetString("username"), Password: viper.GetString("password")}

	clientOpts := options.Client().ApplyURI(uri).SetAuth(credential)
	client, err := mongo.Connect(ctx, clientOpts)
	if err != nil {
		panic(err)
	}

	defer func() {
		if err = client.Disconnect(ctx); err != nil {
			panic(err)
		}
	}()

	if err := client.Ping(ctx, readpref.Primary()); err != nil {
		panic(err)
	}

	log.Println("Successfully connected and pinged", viper.Get("host"))
	collection := client.Database(viper.GetString("database")).Collection(viper.GetString("collection"))

	go func() {
		ticker := time.NewTicker(time.Second * 10)
		for range ticker.C {
			_, err := collection.InsertOne(context.TODO(), bson.M{"name": "ege"})
			if err != nil {
				log.Printf("write failed: %v", err)
				continue
			}
			log.Println("write succeed")
		}
	}()

	go func() {
		ticker := time.NewTicker(time.Second)
		for range ticker.C {
			_, err := collection.Find(context.TODO(), bson.M{})
			if err != nil {
				log.Printf("read failed: %v", err)
				continue
			}
			log.Println("read succeed")
		}
	}()

	s := make(chan os.Signal, 1)
	signal.Notify(s, syscall.SIGINT, syscall.SIGTERM)
	<-s
}
