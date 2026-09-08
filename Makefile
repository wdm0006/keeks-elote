# Makefile for keeks-elote project

# Variables
PYTHON := python3
UV := uv
VENV_DIR := .venv

# Phony targets
.PHONY: all venv install test typecheck lint format check clean

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
	# keeks' multi_outcome API is not on PyPI yet (first ships in 0.8.0), so
	# install keeks from its git default branch. The 0.3.0 release task bumps
	# the keeks floor and retires this bridge.
	$(UV) pip install --python $(VENV_DIR)/bin/python 'keeks @ git+https://github.com/wdm0006/keeks.git'
	@echo "Dependencies installed."

# Run tests with coverage
# --no-sync: plain `uv run` would re-sync the environment to the committed
# uv.lock and silently replace the git-installed keeks with the PyPI pin.
test: install # Make test depend on install to ensure dev deps are present
	$(UV) run --no-sync --python $(VENV_DIR)/bin/python pytest --cov=keeks_elote tests/
	@echo "Tests completed."

# Type-check code
typecheck: install
	$(UV) run --no-sync --python $(VENV_DIR)/bin/python mypy keeks_elote/
	@echo "Type checking completed."

# Lint code
lint: install # Make lint depend on install
	$(UV) run --no-sync --python $(VENV_DIR)/bin/python ruff check .
	$(UV) run --no-sync --python $(VENV_DIR)/bin/python ruff format --check .
	@echo "Linting check completed."

# Format code
format: install # Make format depend on install
	$(UV) run --no-sync --python $(VENV_DIR)/bin/python ruff check --fix .
	$(UV) run --no-sync --python $(VENV_DIR)/bin/python ruff format .
	@echo "Code formatting completed."

# Run all non-mutating checks
check: lint

# Clean up virtual environment
clean:
	@echo "Cleaning up..."
	@rm -rf $(VENV_DIR)
	@echo "Removed $(VENV_DIR)"
