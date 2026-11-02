PYTHON ?= python
export PYTHONPATH := src
.PHONY: test validate train publish monitor airflow

test:
	$(PYTHON) -m pytest -q
validate:
	$(PYTHON) -m inventory.cli validate
train:
	$(PYTHON) -m inventory.cli train
publish:
	$(PYTHON) -m inventory.cli publish
monitor:
	$(PYTHON) -m inventory.cli monitor --publication $(PUBLICATION)
airflow:
	docker compose up --build -d
