.PHONY: all setup test run sample phase1 phase2 clean lint app ui doctor verify

VENV := .venv
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
STREAMLIT := $(VENV)/bin/streamlit

setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

all: test run

test:
	PYTHONPATH=src $(PYTEST) -v tests/

run:
	PYTHONPATH=src $(PYTHON) run_pipeline.py --all

doctor:
	$(PYTHON) scripts/check_inputs.py

phase1:
	PYTHONPATH=src $(PYTHON) run_pipeline.py --phase 1

phase2:
	PYTHONPATH=src $(PYTHON) run_pipeline.py --phase 2

sample:
	PYTHONPATH=src $(PYTHON) run_pipeline.py --sample 500

app:
	$(STREAMLIT) run app/main.py

ui:
	$(STREAMLIT) run app/main.py

lint:
	$(PYTHON) -m py_compile src/ptd/*.py tests/*.py scripts/*.py run_pipeline.py

clean:
	rm -rf data/interim/* data/output/* __pycache__ src/ptd/__pycache__ tests/__pycache__ .pytest_cache

verify:
	PYTHONPATH=src $(PYTEST) -v tests/test_ui.py -k fixtures
