.PHONY: all venv run test test-only perf update clean

# Engine is pure Python (see DECISIONS.md §1) — `make all` just sets up
# the venv. Kept as skill-canon naming so a fresh clone only needs `make`.
all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python play.py $(ARGS)

test: venv
	.venv/bin/python -m tests.qa

# Subset by name pattern. Usage: make test-only PAT=rotate
test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

perf: venv
	.venv/bin/python -m tests.perf

update:
	git pull
	.venv/bin/pip install -e .

clean:
	rm -rf .venv *.egg-info tests/out/*.svg tests/out/*.png
