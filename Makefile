# Makefile for keeks-elote project

# Variables
PYTHON := python3
UV := uv
VENV_DIR := .venv

# Phony targets
.PHONY: all venv install test lint format check clean

# Default target
all: venv install

# Create virtual environment
venv: $(VENV_DIR)/bin/activate

$(VENV_DIR)/bin/activate:
	$(UV) venv $(VENV_DIR) --python $(PYTHON)
	@echo "Virtual environment created in $(VENV_DIR)"

# Install dependencies
install: venv pyproject.toml
	# Sync main and dev dependencies
	$(UV) pip install --python $(VENV_DIR)/bin/python -e '.[dev]'
	@echo "Dependencies installed."

# Run tests with coverage
test: install # Make test depend on install to ensure dev deps are present
	$(UV) run --python $(VENV_DIR)/bin/python pytest --cov=keeks_elote tests/
	@echo "Tests completed."

# Lint code
lint: install # Make lint depend on install
	$(UV) run --python $(VENV_DIR)/bin/python ruff check --fix .
	@echo "Linting check completed."

# Format code
format: install # Make format depend on install
	$(UV) run --python $(VENV_DIR)/bin/python ruff format .
	@echo "Code formatting completed."

# Run linting and formatting
check: lint format

# Clean up virtual environment
clean:
	@echo "Cleaning up..."
	@rm -rf $(VENV_DIR)
	@echo "Removed $(VENV_DIR)" 