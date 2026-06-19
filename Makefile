PYTHON ?= python3

.PHONY: install install-hooks validate lint test

# Install the project (with dev extras) from the private Dependably registry.
# Uses ./pip.conf for the index; put your token in ~/.netrc (see pip.conf).
install:
	PIP_CONFIG_FILE=$(CURDIR)/pip.conf $(PYTHON) -m pip install -e ".[dev]"

install-hooks:
	git config core.hooksPath .githooks
	@echo "Git hooks installed (core.hooksPath -> .githooks)."

validate:
	$(PYTHON) src/checker.py --validate .

lint:
	black --check src/ tests/
	flake8 src/ tests/ --max-line-length=120
	mypy src/

test:
	$(PYTHON) -m pytest tests/
