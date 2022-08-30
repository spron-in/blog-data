# About

Supporting scripts for the blog post utilizing Percona Monitoring and Management (PMM) Database-as-a-service with API.

* [Percona Monitoring and Management](https://www.percona.com/software/database-tools/percona-monitoring-and-management)
* [PMM DBaaS documentation](https://docs.percona.com/percona-monitoring-and-management/using/dbaas.html)

See the demo of *the experimental* command line tool which interracts with PMM API:

[![asciicast](https://asciinema.org/a/qkWV2NY0y5vaSnFP4K6jQHHLJ.png)](https://asciinema.org/a/qkWV2NY0y5vaSnFP4K6jQHHLJ)

# CLI

## Prerequisites

* Tool is in python3. See requirements.txt file for required packages.
* You will need a working PMM server 

## Usage

* Download the tool
* Run ./percona-dbaas-cli --help

On the first run it will ask for PMM server address and token key. Once you provide it, they are going to be saved in your HOME dir.

See the demo for more details.

