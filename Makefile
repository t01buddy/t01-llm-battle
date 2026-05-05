.PHONY: clean

clean:
	find . -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} +
	find . -name "*.pyc" -not -path "./.git/*" -delete
