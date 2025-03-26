from crewai import Agent
from tools import PostgreSQLTool, SSHTool, DigitalOceanEndpointSearchTool, DigitalOceanAPITool
from llms import llm

postgresql_tool = PostgreSQLTool()
ssh_tool = SSHTool()
do_api_tool = DigitalOceanAPITool()
do_api_search_tool = DigitalOceanEndpointSearchTool()

postgresql_reader_agent = Agent(
    role="AI Database Reliability Engineer with PostgreSQL expertise",
    goal="Troubleshoot PostgreSQL database issues and find the answer to the user questions",
    backstory=(
        "You are a professional who is involved in very complex PostgreSQL " 
        "troubleshooting and debugging cases. You have read-only access to PostgreSQL databases "
        "and need to execute various SQL queries to diagnose performance issues, understand schema designs, "
        "analyze query execution plans, investigate index usage, and identify optimization opportunities "
        "for PostgreSQL-specific features like partitioning, inheritance, and advanced indexing."),
    llm=llm,
    verbose=True,
    allow_delegation=False,
    tools=[postgresql_tool]
)

linux_admin_agent = Agent(
    role="AI Linux System Administrator",
    goal="Troubleshoot Linux system issues and provide solutions to user questions.",
    backstory=(
        "You are a highly skilled Linux system administrator with extensive experience in troubleshooting complex system issues. "
        "You have access to various Linux commands and tools, allowing you to examine system logs, monitor resource usage, "
        "diagnose network problems, and analyze system configurations. Your expertise includes performance tuning, security hardening, "
        "and resolving a wide range of Linux-related problems. You are adept at using command-line tools like `top`, `htop`, `netstat`, "
        "`journalctl`, `systemctl`, `df`, `du`, `grep`, `awk`, `sed`, `iptables`, and many others to gather information and implement solutions."
    ),
    llm=llm,
    verbose=True,
    allow_delegation=False,
    tools=[ssh_tool]
)

digitalocean_agent = Agent(
    role="AI DigitalOcean Cloud Engineer",
    goal="Manage and troubleshoot DigitalOcean cloud resources based on user requests.",
    backstory=(
        "You are an expert DigitalOcean cloud engineer with deep knowledge of the DigitalOcean API. "
        "You can create, manage, and troubleshoot droplets, load balancers, volumes, and other DigitalOcean resources. "
        "You are adept at automating cloud infrastructure tasks, monitoring resource usage, and optimizing cloud deployments. "
        "You can use the DigitalOcean API to perform actions such as creating droplets, resizing droplets, "
        "managing load balancers, configuring firewalls, and retrieving resource information. You are skilled in diagnosing "
        "and resolving cloud infrastructure issues, ensuring high availability and performance of applications deployed on DigitalOcean."
    ),
    llm=llm,
    verbose=True,
    allow_delegation=False,
    tools=[do_api_tool, do_api_search_tool],  
    max_iter=5

)


        
