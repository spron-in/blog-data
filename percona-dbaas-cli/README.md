# About

Supporting scripts for the blog post utilizing Percona Monitoring and Management (PMM) Database-as-a-service with API.

* [Percona Monitoring and Management](https://www.percona.com/software/database-tools/percona-monitoring-and-management)
* [PMM DBaaS documentation](https://docs.percona.com/percona-monitoring-and-management/using/dbaas.html)

See the demo of *the experimental* command line tool which interracts with PMM API:

[![asciicast](https://asciinema.org/a/FhXGLVgAa6DdZ8C7sdu0OxMOf.png)](https://asciinema.org/a/FhXGLVgAa6DdZ8C7sdu0OxMOf)

# CLI

## Prerequisites

* Tool is written in python3. See requirements.txt file for required python packages.
* You will need a working PMM server 

## Quick start

Download requirements and dbaas tool:
```
wget -c https://raw.githubusercontent.com/spron-in/blog-data/master/percona-dbaas-cli/percona-dbaas-cli
chmod +x percona-dbaas-cli
wget -c https://raw.githubusercontent.com/spron-in/blog-data/master/percona-dbaas-cli/requirements.txt
```

Install required Python packages:
```
pip3 install -r requirements.txt
```

Use the tool
```
./percona-dbaas-cli 
```

On the first run it will ask for PMM server address and token key. Once you provide it, they are going to be saved in your HOME dir.

See the demo for more details.

