# Makefile pour Infra-Mapper Backend

.PHONY: help install test test-unit test-integration test-cov lint format clean

help:
	@echo "Commandes disponibles:"
	@echo "  install          - Installe les dépendances"
	@echo "  test             - Lance tous les tests"
	@echo "  test-unit        - Lance les tests unitaires"
	@echo "  test-integration - Lance les tests d'intégration"
	@echo "  test-cov         - Lance les tests avec couverture"
	@echo "  lint             - Vérifie le code"
	@echo "  format           - Formate le code"
	@echo "  clean            - Nettoie les fichiers temporaires"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v -m unit

test-integration:
	pytest tests/integration/ -v -m integration

test-cov:
	pytest tests/ --cov=. --cov-report=html --cov-report=term-missing

lint:
	ruff check .

format:
	ruff format .

clean:
	rm -rf __pycache__ .pytest_cache .coverage htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
