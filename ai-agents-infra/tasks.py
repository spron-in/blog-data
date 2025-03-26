from crewai import Task
from agents import postgresql_reader_agent, linux_admin_agent, digitalocean_agent

postgresql_reader_task = Task(
    description=
    ("User just reached out with a task to help with a question about PostgreSQL:\n"
     "{inquiry}\n\n"
     "Your goal is to understand the request and help the user. Where necessary you can run "
     "PostgreSQL commands to get more information with a tool.\n"
     "User also provided you with infrastructure assets. You may need to connect to some of these assets.\n"
     "{user_assets}\n\n"
     """
     You only have read-only permissions to the database by default. You should not execute destructive commands like 
     DROP, DELETE, or UPDATE unless explicitly requested and confirmed by the user. Focus primarily on SELECT queries for 
     diagnostics and analysis.
     """
     """Never put placeholders like <table-name> or <column-name> in your SQL code.
                Always use LIMIT clauses when selecting from large tables to avoid overwhelming results.
                Be careful with resource-intensive operations like full table scans or complex joins.
                """
     """# Useful PostgreSQL commands
                    \l or SELECT datname FROM pg_database: List all databases on the server.
                    \dt or SELECT tablename FROM pg_tables: List all tables in the current database.
                    \d table_name or SELECT column_name, data_type FROM information_schema.columns: Show table structure and column details.
                    \d+ table_name: Display detailed table information including storage and indexes.
                    EXPLAIN (ANALYZE, BUFFERS): Analyze query execution plan for optimization.
                    SELECT * FROM pg_stat_activity: See active connections and queries.
                    SELECT * FROM pg_stat_database: Display database-wide statistics.
                    SHOW ALL: Show server configuration variables.
                    SELECT * FROM pg_indexes: Display index information for tables.
                    pg_stat_statements: Query execution statistics (if extension is enabled).
                    SELECT * FROM pg_locks: View lock information.
                    SELECT * FROM pg_stat_bgwriter: Check background writer statistics.
                    SELECT * FROM information_schema.tables: Get comprehensive table information."""
     ),
    expected_output=
    ("A concise and informative response to the users's inquiry that addresses all aspects of their PostgreSQL database question.\n"
     ),
    agent=postgresql_reader_agent)


linux_admin_task = Task(
    description=(
        "User just reached out with a task to help with a question about a Linux system:\n"
        "{inquiry}\n\n"
        "Your goal is to understand the request and provide a solution. Where necessary, you can run Linux commands to gather information using your tools.\n"
        "User also provided you with infrastructure assets. You may need to connect to some of these assets.\n"
        "{user_assets}\n\n"
        """
        Focus on diagnosing system issues and providing solutions. Prioritize using non-destructive commands to gather information.
        Avoid executing commands that could modify system configurations or data unless explicitly requested and confirmed by the user.
        Do not attempt to connect to databases, for that we have another agents.
        """
        """When providing command output, ensure it is relevant and concise. Do not include excessive output that does not directly answer the user's question.
           When suggesting commands to the user, explain why they are necessary and what information they will provide.
           Provide clear and step-by-step instructions when guiding the user through troubleshooting steps.
        """
        """# Useful Linux commands
           uptime: Show system uptime and load average.
           top or htop: Display real-time system resource usage.
           df -h: Show disk space usage.
           du -sh /path/to/directory: Show directory disk usage.
           free -m: Show memory usage.
           netstat -tulnp: List listening network ports.
           journalctl -xe: View system logs.
           systemctl status service_name: Check the status of a systemd service.
           ps aux: List running processes.
           grep "pattern" /path/to/file: Search for a pattern in a file.
           cat /etc/os-release: Get OS information.
           uname -a: Get kernel information.
           lsblk: List block devices.
           dmesg: show kernel messages.
           ss -tulnp: another way to show sockets.
        """
    ),
    expected_output=(
        "A clear, concise, and accurate response to the user's Linux system question, including any necessary troubleshooting steps or command output.\n"
    ),
    agent=linux_admin_agent,
)

digitalocean_task = Task(
    description=(
        "User just reached out with a task to help with a question about DigitalOcean resources:\n"
        "{inquiry}\n\n"
        "Your goal is to understand the request and manage or troubleshoot DigitalOcean resources as needed. You can use the DigitalOcean API tool to perform actions.\n"
        "User also provided you with infrastructure assets. You may need to connect to some of these assets.\n"
        "{user_assets}\n\n"
        """
        Focus on accurately interpreting the user's request and using the DigitalOcean API to provide the correct information or perform the requested action.
        Be mindful of the potential costs associated with DigitalOcean resources. Do not create or modify resources without explicit user confirmation, especially for tasks that may incur charges.
        """
        """When providing information about DigitalOcean resources, ensure it is up-to-date and accurate.
           When performing actions that modify resources (e.g., resizing, deleting), confirm with the user and clearly communicate the potential impact.
           When providing API output, ensure it is relevant and concise.
           When suggesting API commands, explain why they are necessary and what information they will provide.
        """
        """
        To get API endpoints you can either rely on your knowledge or the tool to search through the API reference.
        Useful DigitalOcean API endpoints:
        /v2/monitoring/alerts
        /v2/droplets
        /v2/firewalls
        """
    ),
    expected_output=(
        "A clear, concise, and accurate response to the user's DigitalOcean question, including any necessary API interactions or resource management actions.\n"
    ),
    agent=digitalocean_agent,
)