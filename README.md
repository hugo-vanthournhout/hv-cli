# HV clients cli
## Description
This is a command line interface for the hv typer CLI. It allows you to automate action from the command line.
The hv tools box dont have a clear use case, it is a personal project that I use to automate some actions that I do frequently. 
Some of the tech stack that I use is:
- mac os, vscode
- gcloud, bigquery
- gitlab
- docker
- dbt
- uv
- asana, slack, zoom and other tools

# hv

Personal CLI for automation of daily tasks.

## Install
```bash
uv venv
source .venv/bin/activate
uv pip install -e .
uv ruff check .
```

## Setup
1. Copy `credentials.example.yaml` to `credentials.yaml` and `variables.example.yaml` to `variables.yaml`
2. Add your tokens and variables

## Commands & Aliases

### GitLab (`gl`, `gitlab`)
- Default: Process Renovate MRs
```bash
hv gl                 # Same as hv gl renovate
hv gl renovate|ren    # Process Renovate MRs
hv gl reviews|rev     # List your review MRs
```

### Asana (`as`, `asana`)
- Default: List my tasks
```bash
hv as                     # Same as hv as my-tasks
hv as my-tasks           # List your tasks
hv as all-tasks          # List all project tasks
hv as update|us          # Update task status
```

### Git (`g`, `git`)
- Default: Sync with main
```bash
hv g                  # Same as hv g sync
hv g sync             # Sync with main
hv g squash           # Squash branch commits
hv g check-commits    # Validate conventional commits
hv g reset-history|rh # Reset git history
```

### AI (`a`, `ai`)
- Default: Process project & open Claude
```bash
hv ai                      # Same as hv ai pc
hv ai process_and_claude|pc # Process & open Claude
hv ai print_project|pp     # Print project files
hv ai claude|c             # Open Claude with context

# Exclude files:
hv ai pp --ignore-patterns "Makefile"
hv ai pc --ignore-patterns "Makefile"

# Multiple ignores:
hv ai pc --ignore-patterns "Makefile" "*.mk" "make/*"
```

### Zoom (`z`, `zoom`)
- Default: Join daily meeting
```bash
hv z                  # Same as hv z daily
hv z daily            # Join daily meeting
hv z meeting|m        # Join specific meeting
```

### gcloud
- Default: list policy tag id
```bash
hv gcloud policy_id
```

## Configuration
- `src/hv/config/command.yaml`: Define aliases and defaults
- `src/hv/config/variables.yaml`: Tool configuration
- `src/hv/config/credentials.yaml`: API tokens