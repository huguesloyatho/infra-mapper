"""Collecteur de fichiers docker-compose."""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class ComposeCollector:
    """Collecte et parse les fichiers docker-compose.yml."""

    def __init__(self, search_paths: list[str] = None):
        """Initialise le collecteur."""
        self.search_paths = search_paths or ["/root", "/home", "/opt", "/srv"]
        self._compose_cache: dict[str, dict] = {}

    def find_compose_files(self) -> list[str]:
        """Trouve tous les fichiers docker-compose.yml."""
        compose_files = []

        for base_path in self.search_paths:
            if not os.path.exists(base_path):
                continue

            try:
                result = subprocess.run(
                    ["find", base_path, "-name", "docker-compose.yml", "-o", "-name", "docker-compose.yaml"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                    compose_files.extend(files)

            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout lors de la recherche dans {base_path}")
            except Exception as e:
                logger.warning(f"Erreur lors de la recherche dans {base_path}: {e}")

        return list(set(compose_files))  # Dédupliquer

    def parse_compose_file(self, filepath: str) -> Optional[dict]:
        """Parse un fichier docker-compose.yml."""
        try:
            with open(filepath, "r") as f:
                content = yaml.safe_load(f)
                self._compose_cache[filepath] = content
                return content
        except yaml.YAMLError as e:
            logger.warning(f"Erreur YAML dans {filepath}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Erreur lecture {filepath}: {e}")
            return None

    def get_service_dependencies(self, filepath: str) -> dict[str, list[str]]:
        """
        Extrait les dépendances entre services d'un fichier compose.

        Retourne: {service_name: [liste des dépendances]}
        """
        dependencies = {}

        content = self._compose_cache.get(filepath) or self.parse_compose_file(filepath)
        if not content:
            return dependencies

        services = content.get("services", {})

        for service_name, service_config in services.items():
            deps = []

            # depends_on
            depends_on = service_config.get("depends_on", [])
            if isinstance(depends_on, list):
                deps.extend(depends_on)
            elif isinstance(depends_on, dict):
                deps.extend(depends_on.keys())

            # links (legacy)
            links = service_config.get("links", [])
            for link in links:
                # Format: service ou service:alias
                dep_name = link.split(":")[0]
                if dep_name not in deps:
                    deps.append(dep_name)

            # Analyser les variables d'environnement pour les dépendances implicites
            env = service_config.get("environment", {})
            if isinstance(env, list):
                env = {e.split("=")[0]: e.split("=")[1] if "=" in e else "" for e in env}

            for key, value in env.items():
                if isinstance(value, str):
                    # Chercher des références à d'autres services
                    for other_service in services.keys():
                        if other_service != service_name and other_service in value:
                            if other_service not in deps:
                                deps.append(other_service)

            dependencies[service_name] = deps

        return dependencies

    def get_project_name(self, filepath: str) -> str:
        """Détermine le nom du projet compose."""
        # Le nom du projet est généralement le nom du dossier parent
        return Path(filepath).parent.name

    def collect_all_dependencies(self) -> dict[str, dict[str, list[str]]]:
        """
        Collecte toutes les dépendances de tous les fichiers compose.

        Retourne: {project_name: {service: [deps]}}
        """
        all_deps = {}

        compose_files = self.find_compose_files()

        for filepath in compose_files:
            project_name = self.get_project_name(filepath)
            deps = self.get_service_dependencies(filepath)

            if deps:
                all_deps[project_name] = deps

        return all_deps

    def get_dependencies_for_container(
        self,
        compose_project: Optional[str],
        compose_service: Optional[str]
    ) -> list[str]:
        """
        Retourne les dépendances déclarées pour un conteneur spécifique.
        """
        if not compose_project or not compose_service:
            return []

        # Chercher dans le cache
        for filepath, content in self._compose_cache.items():
            if self.get_project_name(filepath) == compose_project:
                deps = self.get_service_dependencies(filepath)
                return deps.get(compose_service, [])

        # Sinon, chercher le fichier
        compose_files = self.find_compose_files()
        for filepath in compose_files:
            if self.get_project_name(filepath) == compose_project:
                deps = self.get_service_dependencies(filepath)
                return deps.get(compose_service, [])

        return []
