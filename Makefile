.PHONY: test quality demo build

quality:
	ruff format --check .
	ruff check .
	mypy src/resolveops

test:
	pytest --cov=resolveops --cov-branch --cov-report=term-missing

demo:
	resolveops demo

build:
	python setup.py sdist bdist_wheel
