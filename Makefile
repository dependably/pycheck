PYTHON ?= python3

.PHONY: install-hooks validate lint test

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
