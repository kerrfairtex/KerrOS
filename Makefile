.PHONY: install test test-unit clean

install:
	pip install -r requirements.txt
	pip install python-dotenv certifi pytest

test:
	python3 -m pytest tests/unit/ -v

test-unit:
	python3 -m pytest tests/unit/ -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
