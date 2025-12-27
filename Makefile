# Arnold Makefile
# Convenience commands for common operations

# Environment detection
CONDA := $(shell command -v conda 2> /dev/null)
ENV_NAME := arnold
CONDA_ENV_PATH := $(shell conda env list 2>/dev/null | grep '^$(ENV_NAME) ' | awk '{print $$2}')
VENV_PATH := .venv

# Determine which environment system to use
ifdef CONDA
	ENV_TYPE := conda
	ACTIVATE := source $$(conda info --base)/etc/profile.d/conda.sh && conda activate $(ENV_NAME) &&
	ENV_EXISTS := $(CONDA_ENV_PATH)
	PYTHON := $(ACTIVATE) python
	PIP := $(ACTIVATE) pip
else
	ENV_TYPE := venv
	ACTIVATE := source $(VENV_PATH)/bin/activate &&
	ENV_EXISTS := $(wildcard $(VENV_PATH)/bin/python)
	PYTHON := $(ACTIVATE) python
	PIP := $(ACTIVATE) pip
endif

.PHONY: help env-info env-create env-remove install setup import validate clean docker-start docker-stop quickstart

help:
	@echo "Arnold - Expert Exercise System"
	@echo "================================"
	@echo ""
	@echo "Environment Management:"
	@echo "  make env-info      - Show environment information"
	@echo "  make env-create    - Create isolated Python environment"
	@echo "  make env-remove    - Remove the environment"
	@echo ""
	@echo "Setup Commands:"
	@echo "  make quickstart    - Complete setup (creates env, installs, imports)"
	@echo "  make install       - Install Python dependencies (in isolated env)"
	@echo "  make setup         - Initialize Neo4j database schema"
	@echo "  make import        - Import all data (anatomy, exercises, profile)"
	@echo "  make validate      - Run Phase 1 validation queries"
	@echo ""
	@echo "Database Commands:"
	@echo "  make docker-start  - Start Neo4j via Docker"
	@echo "  make docker-stop   - Stop Neo4j Docker container"
	@echo "  make clean         - Clear all data from database (DESTRUCTIVE!)"
	@echo ""
	@echo "Current environment: $(ENV_TYPE)"
	@echo ""

env-info:
	@echo "Environment Information"
	@echo "======================="
	@echo "Environment type: $(ENV_TYPE)"
ifdef CONDA
	@echo "Using: conda"
	@echo "Environment name: $(ENV_NAME)"
	@if [ -n "$(ENV_EXISTS)" ]; then \
		echo "Status: ✓ Environment exists at $(CONDA_ENV_PATH)"; \
	else \
		echo "Status: ✗ Environment not created yet"; \
		echo "Run: make env-create"; \
	fi
else
	@echo "Using: venv"
	@echo "Environment path: $(VENV_PATH)"
	@if [ -n "$(ENV_EXISTS)" ]; then \
		echo "Status: ✓ Environment exists"; \
	else \
		echo "Status: ✗ Environment not created yet"; \
		echo "Run: make env-create"; \
	fi
endif
	@echo ""
	@echo "To activate manually:"
ifdef CONDA
	@echo "  conda activate $(ENV_NAME)"
else
	@echo "  source $(VENV_PATH)/bin/activate"
endif

env-create:
	@echo "Creating isolated Python environment..."
ifdef CONDA
	@if [ -z "$(ENV_EXISTS)" ]; then \
		echo "Creating conda environment: $(ENV_NAME)"; \
		conda create -y -n $(ENV_NAME) python=3.10; \
		echo "✓ Conda environment created"; \
	else \
		echo "✓ Conda environment already exists"; \
	fi
else
	@if [ ! -d "$(VENV_PATH)" ]; then \
		echo "Creating venv at: $(VENV_PATH)"; \
		python3 -m venv $(VENV_PATH); \
		echo "✓ Virtual environment created"; \
	else \
		echo "✓ Virtual environment already exists"; \
	fi
endif
	@echo ""
	@$(MAKE) env-info

env-remove:
	@echo "⚠️  This will remove the Python environment for Arnold"
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(MAKE) _do-env-remove; \
	else \
		echo "Cancelled."; \
	fi

_do-env-remove:
ifdef CONDA
	@if [ -n "$(ENV_EXISTS)" ]; then \
		echo "Removing conda environment: $(ENV_NAME)"; \
		conda env remove -n $(ENV_NAME) -y; \
		echo "✓ Environment removed"; \
	else \
		echo "Environment doesn't exist"; \
	fi
else
	@if [ -d "$(VENV_PATH)" ]; then \
		echo "Removing venv: $(VENV_PATH)"; \
		rm -rf $(VENV_PATH); \
		echo "✓ Environment removed"; \
	else \
		echo "Environment doesn't exist"; \
	fi
endif

install: env-create
	@echo "Installing dependencies in isolated environment..."
	@$(PIP) install -r requirements.txt
	@echo "✓ Dependencies installed"

setup: env-create
	@echo "Initializing Neo4j database..."
	@$(PYTHON) scripts/setup_neo4j.py

import: env-create
	@echo "Importing UBERON anatomy..."
	@$(PYTHON) scripts/import_uberon.py
	@echo ""
	@echo "Importing exercises..."
	@$(PYTHON) scripts/import_exercises.py
	@echo ""
	@echo "Importing user profile..."
	@$(PYTHON) scripts/import_user_profile.py
	@echo ""
	@echo "✓ All imports complete"

validate: env-create
	@$(PYTHON) scripts/validate_phase1.py

clean:
	@echo "⚠️  This will DELETE all data from the database!"
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(PYTHON) scripts/setup_neo4j.py --clear; \
	else \
		echo "Cancelled."; \
	fi

docker-start:
	@echo "Starting Neo4j container..."
	@if [ -z "$$NEO4J_PASSWORD" ]; then \
		echo "Error: NEO4J_PASSWORD not set"; \
		echo ""; \
		echo "Set it first:"; \
		echo "  export NEO4J_PASSWORD=your_password"; \
		echo "Or create .env file with NEO4J_PASSWORD=your_password"; \
		exit 1; \
	fi
	@echo "Using password from environment..."
	@docker run -d \
		--name arnold-neo4j \
		-p 7474:7474 -p 7687:7687 \
		-e NEO4J_AUTH=neo4j/$$NEO4J_PASSWORD \
		-e NEO4J_PLUGINS='["apoc"]' \
		-v $$HOME/neo4j/arnold:/data \
		neo4j:latest 2>/dev/null || \
		(echo "Container already exists, starting..." && docker start arnold-neo4j)
	@echo "✓ Neo4j started"
	@echo "  Browser: http://localhost:7474"
	@echo "  Bolt: bolt://localhost:7687"
	@sleep 2
	@echo ""
	@echo "Waiting for Neo4j to be ready..."
	@for i in 1 2 3 4 5; do \
		if docker logs arnold-neo4j 2>&1 | grep -q "Started"; then \
			echo "✓ Neo4j is ready"; \
			break; \
		fi; \
		echo "  Waiting... ($$i/5)"; \
		sleep 2; \
	done

docker-stop:
	@docker stop arnold-neo4j 2>/dev/null || echo "Container not running"
	@docker rm arnold-neo4j 2>/dev/null || echo "Container already removed"
	@echo "✓ Neo4j stopped"

# Complete setup from scratch
quickstart: env-create docker-start
	@echo ""
	@echo "================================================"
	@echo "Arnold Phase 1 Quickstart"
	@echo "================================================"
	@echo ""
	@$(MAKE) install
	@echo ""
	@echo "Setting up .env file..."
	@if [ ! -f .env ]; then \
		if [ -n "$$NEO4J_PASSWORD" ]; then \
			cp .env.example .env; \
			echo "NEO4J_PASSWORD=$$NEO4J_PASSWORD" >> .env; \
			echo "✓ .env file created"; \
		else \
			echo "⚠️  Warning: .env file not found and NEO4J_PASSWORD not set"; \
			echo "   Copy .env.example to .env and set your password"; \
		fi; \
	else \
		echo "✓ .env file exists"; \
	fi
	@echo ""
	@echo "Checking for user profile..."
	@if [ ! -f data/user/profile.yaml ]; then \
		echo "⚠️  No user profile found"; \
		echo "   Copy and customize: cp data/user/profile.yaml.example data/user/profile.yaml"; \
		echo "   Skipping profile import for now"; \
	fi
	@echo ""
	@$(MAKE) setup
	@echo ""
	@$(MAKE) import
	@echo ""
	@$(MAKE) validate
	@echo ""
	@echo "================================================"
	@echo "✓ Arnold Phase 1 setup complete!"
	@echo "================================================"
	@echo ""
	@echo "Environment: $(ENV_TYPE)"
ifdef CONDA
	@echo "To activate: conda activate $(ENV_NAME)"
else
	@echo "To activate: source $(VENV_PATH)/bin/activate"
endif
	@echo ""
	@echo "Next steps:"
	@echo "  1. Open Neo4j Browser: http://localhost:7474"
	@echo "  2. Customize your profile: data/user/profile.yaml"
	@echo "  3. Try example queries from docs/schema.md"
	@echo ""
