# About

Data in this repo supports the blog post "Create AI expert with open source tools and pgvector".

Structure:
* install - a collection of commands to install GPU drivers and python tools on Ubuntu
* python - code examples
  * config.py - database credentials
  * 01-pg-provision.py - create table, function and index for vectors
  * 02-put.py - parse Percona docs and blog posts and put them into pgvector
  * 03-simple-search.py - quickly search through pgvector and find most relevant data
  * 04-context-search.py - search with the context and generate a response
* k8s-operator
  * Everything you need to install Percona Operator for PostgreSQL and pgvector on Kubernetes 
