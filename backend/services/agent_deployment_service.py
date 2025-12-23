"""Service de déploiement et gestion des agents."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Vm, VmStatusEnum, OsTypeEnum
from config import get_settings
from .ssh_service import SshService
from .websocket_manager import ws_manager

logger = logging.getLogger(__name__)
settings = get_settings()


class AgentDeploymentService:
    """Service de déploiement et gestion des agents sur les VMs distantes."""

    AGENT_PATH = "/opt/infra-mapper-agent"
    AGENT_FILES = [
        "agent.py",
        "command_server.py",
        "config.py",
        "models.py",
        "requirements.txt",
        "Dockerfile",
    ]

    # Deployment steps with progress ranges (start%, end%)
    DEPLOY_STEPS = {
        "preparing": (0, 5),
        "detecting_os": (5, 10),
        "checking_docker": (10, 20),
        "uploading": (20, 40),
        "creating_config": (40, 45),
        "building": (45, 90),
        "starting": (90, 95),
        "verifying": (95, 100),
    }

    def __init__(self, db: AsyncSession, ssh: SshService):
        """
        Initialise le service.

        Args:
            db: Session de base de données
            ssh: Service SSH
        """
        self.db = db
        self.ssh = ssh
        # Chemin local des fichiers agent (monté depuis docker-compose)
        self.agent_source_path = Path("/app/agent")

    async def _update_progress(
        self,
        vm: Vm,
        step: str,
        sub_progress: int = 100,
        message: str = None
    ) -> None:
        """
        Met à jour la progression du déploiement et notifie via WebSocket.

        Args:
            vm: VM en cours de déploiement
            step: Étape actuelle (clé de DEPLOY_STEPS)
            sub_progress: Progression dans l'étape (0-100)
            message: Message détaillé optionnel
        """
        start, end = self.DEPLOY_STEPS.get(step, (0, 100))
        progress = start + (end - start) * sub_progress // 100

        vm.deployment_step = step
        vm.deployment_progress = progress
        vm.deployment_message = message
        await self.db.commit()

        await ws_manager.notify_deployment_progress(
            str(vm.id), step, progress, message
        )
        logger.debug(f"Deployment progress: {vm.name} - {step} {progress}%")

    async def deploy_agent(self, vm: Vm) -> dict:
        """
        Déploie l'agent sur une VM avec suivi de progression.

        Args:
            vm: VM cible

        Returns:
            Résultat du déploiement
        """
        logger.info(f"Début du déploiement sur {vm.name} ({vm.ip_address})")

        try:
            # 1. Préparation
            await self._update_progress(vm, "preparing", 0, "Initialisation du déploiement")
            vm.status = VmStatusEnum.DEPLOYING
            await self.db.commit()
            await self._update_progress(vm, "preparing", 100, "Prêt")

            # 2. Détecter l'OS si inconnu
            await self._update_progress(vm, "detecting_os", 0, "Détection du système d'exploitation")
            if vm.os_type == OsTypeEnum.UNKNOWN:
                os_type = await self._detect_os(vm)
                vm.os_type = os_type
                await self.db.commit()
            await self._update_progress(vm, "detecting_os", 100, f"OS détecté: {vm.os_type.value}")

            # 3. Vérifier/Installer Docker
            await self._update_progress(vm, "checking_docker", 0, "Vérification de Docker")
            docker_installed = await self._ensure_docker(vm)
            if not docker_installed:
                vm.status = VmStatusEnum.ERROR
                vm.deployment_message = "Impossible d'installer Docker"
                await self.db.commit()
                await ws_manager.notify_deployment_progress(
                    str(vm.id), "error", 0, "Impossible d'installer Docker"
                )
                return {
                    "status": "error",
                    "vm_id": vm.id,
                    "message": "Impossible d'installer Docker"
                }
            await self._update_progress(vm, "checking_docker", 100, "Docker disponible")

            # 4. Upload des fichiers agent
            await self._update_progress(vm, "uploading", 0, "Création du répertoire")
            await self.ssh.execute(
                vm.ip_address, vm.ssh_user, vm.ssh_port,
                f"mkdir -p {self.AGENT_PATH}"
            )
            await self._update_progress(vm, "uploading", 20, "Upload des fichiers agent")
            await self._upload_agent_files(vm)
            await self._update_progress(vm, "uploading", 100, "Fichiers uploadés")

            # 5. Créer les fichiers de configuration
            await self._update_progress(vm, "creating_config", 0, "Création docker-compose.yml")
            await self._create_docker_compose(vm)
            await self._update_progress(vm, "creating_config", 50, "Création .env")
            await self._create_env_file(vm)
            await self._update_progress(vm, "creating_config", 100, "Configuration créée")

            # 6. Build Docker (lance en arrière-plan et surveille la progression)
            await self._update_progress(vm, "building", 0, "Démarrage du build Docker")

            # Lancer le build en nohup
            await self.ssh.execute(
                vm.ip_address, vm.ssh_user, vm.ssh_port,
                f"cd {self.AGENT_PATH} && nohup docker compose up -d --build > /tmp/agent-deploy.log 2>&1 &",
                timeout=30
            )

            # Surveiller la progression du build
            build_complete = await self._monitor_build_progress(vm)

            if not build_complete:
                # Build toujours en cours après timeout, mais pas d'erreur
                await self._update_progress(vm, "building", 80, "Build en cours...")
                logger.info(f"Build long sur {vm.name}, en attente du premier rapport")
                return {
                    "status": "deploying",
                    "vm_id": vm.id,
                    "message": "Build Docker en cours. L'agent passera en ligne automatiquement."
                }

            # 7. Démarrage du container
            await self._update_progress(vm, "starting", 0, "Démarrage du container")
            await asyncio.sleep(5)
            await self._update_progress(vm, "starting", 100, "Container démarré")

            # 8. Vérification
            await self._update_progress(vm, "verifying", 0, "Vérification du démarrage")
            stdout, stderr, code = await self.ssh.execute(
                vm.ip_address, vm.ssh_user, vm.ssh_port,
                f"cd {self.AGENT_PATH} && docker compose ps --format json 2>/dev/null | head -1",
                timeout=30
            )

            if stdout and '"running"' in stdout.lower():
                vm.status = VmStatusEnum.ONLINE
                vm.agent_installed_at = datetime.utcnow()
                vm.deployment_step = None
                vm.deployment_progress = None
                vm.deployment_message = None
                await self.db.commit()

                await self._update_progress(vm, "verifying", 100, "Agent déployé avec succès")
                logger.info(f"Agent déployé avec succès sur {vm.name}")
                return {
                    "status": "deployed",
                    "vm_id": vm.id,
                    "message": "Agent déployé avec succès"
                }
            else:
                # Container pas encore running, agent passera online au premier rapport
                await self._update_progress(vm, "verifying", 100, "En attente du premier rapport")
                logger.info(f"Build terminé sur {vm.name}, en attente du premier rapport")
                return {
                    "status": "deploying",
                    "vm_id": vm.id,
                    "message": "Build terminé. En attente du premier rapport de l'agent."
                }

        except Exception as e:
            logger.error(f"Erreur déploiement sur {vm.name}: {e}")
            vm.status = VmStatusEnum.ERROR
            vm.deployment_message = str(e)
            await self.db.commit()
            await ws_manager.notify_deployment_progress(
                str(vm.id), "error", 0, str(e)
            )
            return {
                "status": "error",
                "vm_id": vm.id,
                "message": str(e)
            }

    async def _monitor_build_progress(self, vm: Vm, max_wait: int = 300) -> bool:
        """
        Surveille la progression du build Docker.

        Args:
            vm: VM en cours de déploiement
            max_wait: Temps maximum d'attente en secondes

        Returns:
            True si le build est terminé, False si timeout
        """
        start_time = asyncio.get_event_loop().time()
        last_progress = 0

        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            # Lire le log de déploiement
            stdout, stderr, code = await self.ssh.execute(
                vm.ip_address, vm.ssh_user, vm.ssh_port,
                "tail -5 /tmp/agent-deploy.log 2>/dev/null",
                timeout=10
            )

            # Vérifier si le build est terminé
            if stdout:
                if "Started" in stdout or "Running" in stdout:
                    await self._update_progress(vm, "building", 100, "Build terminé")
                    return True
                elif "error" in stdout.lower() and "ERROR" in stdout:
                    await self._update_progress(vm, "building", last_progress, "Erreur de build")
                    return False

                # Estimer la progression basée sur les étapes du build
                progress = self._estimate_build_progress(stdout)
                if progress > last_progress:
                    last_progress = progress
                    await self._update_progress(
                        vm, "building", progress,
                        self._get_build_step_message(stdout)
                    )

            # Vérifier si le container est déjà running
            stdout2, stderr2, code2 = await self.ssh.execute(
                vm.ip_address, vm.ssh_user, vm.ssh_port,
                f"docker ps --filter name=infra-mapper-agent --format '{{{{.Status}}}}' 2>/dev/null",
                timeout=10
            )
            if stdout2 and "Up" in stdout2:
                await self._update_progress(vm, "building", 100, "Build terminé")
                return True

            await asyncio.sleep(5)

        return False

    def _estimate_build_progress(self, log_output: str) -> int:
        """Estime la progression du build basée sur la sortie du log."""
        log_lower = log_output.lower()

        # Étapes typiques d'un build Docker
        if "downloading" in log_lower or "pulling" in log_lower:
            return 10
        elif "unpacking" in log_lower:
            return 25
        elif "setting up" in log_lower:
            return 40
        elif "installing" in log_lower or "pip install" in log_lower:
            return 55
        elif "copying" in log_lower or "copy" in log_lower:
            return 70
        elif "exporting" in log_lower:
            return 85
        elif "creating" in log_lower or "starting" in log_lower:
            return 95
        return 50

    def _get_build_step_message(self, log_output: str) -> str:
        """Extrait un message lisible de la sortie du log."""
        lines = log_output.strip().split('\n')
        if lines:
            last_line = lines[-1].strip()
            # Nettoyer la ligne (retirer les préfixes Docker)
            if '] ' in last_line:
                last_line = last_line.split('] ', 1)[-1]
            # Limiter la longueur
            if len(last_line) > 50:
                last_line = last_line[:47] + "..."
            return last_line or "Build en cours..."
        return "Build en cours..."

    async def _detect_os(self, vm: Vm) -> OsTypeEnum:
        """Détecte le type d'OS via SSH."""
        success, message, os_detected = await self.ssh.test_connection(
            vm.ip_address, vm.ssh_user, vm.ssh_port
        )

        if not success:
            return OsTypeEnum.UNKNOWN

        os_map = {
            "debian": OsTypeEnum.DEBIAN,
            "ubuntu": OsTypeEnum.UBUNTU,
            "centos": OsTypeEnum.CENTOS,
            "macos": OsTypeEnum.MACOS,
            "windows": OsTypeEnum.WINDOWS,
        }
        return os_map.get(os_detected, OsTypeEnum.UNKNOWN)

    async def _ensure_docker(self, vm: Vm) -> bool:
        """Vérifie et installe Docker si nécessaire."""
        # Vérifier si Docker est installé
        has_docker = await self.ssh.check_docker(
            vm.ip_address, vm.ssh_user, vm.ssh_port
        )
        if has_docker:
            return True

        logger.info(f"Installation de Docker sur {vm.name}")

        # Installer selon l'OS
        if vm.os_type in [OsTypeEnum.DEBIAN, OsTypeEnum.UBUNTU]:
            install_cmd = """
                apt-get update && \
                apt-get install -y docker.io docker-compose-plugin && \
                systemctl enable docker && \
                systemctl start docker
            """
        elif vm.os_type == OsTypeEnum.CENTOS:
            install_cmd = """
                yum install -y yum-utils && \
                yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo && \
                yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
                systemctl enable docker && \
                systemctl start docker
            """
        else:
            # macOS et Windows: Docker Desktop doit être installé manuellement
            logger.warning(f"Installation Docker non supportée sur {vm.os_type}")
            return False

        stdout, stderr, code = await self.ssh.execute(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            install_cmd,
            timeout=600  # 10 minutes pour l'installation Docker
        )

        return code == 0

    async def _upload_agent_files(self, vm: Vm) -> None:
        """Upload les fichiers de l'agent."""
        for filename in self.AGENT_FILES:
            local_path = self.agent_source_path / filename
            if local_path.exists():
                remote_path = f"{self.AGENT_PATH}/{filename}"
                await self.ssh.upload_file(
                    vm.ip_address, vm.ssh_user, vm.ssh_port,
                    str(local_path), remote_path
                )

        # Upload le répertoire collectors
        collectors_path = self.agent_source_path / "collectors"
        if collectors_path.exists():
            # Créer le répertoire collectors
            await self.ssh.execute(
                vm.ip_address, vm.ssh_user, vm.ssh_port,
                f"mkdir -p {self.AGENT_PATH}/collectors"
            )
            # Upload chaque fichier
            for py_file in collectors_path.glob("*.py"):
                remote_path = f"{self.AGENT_PATH}/collectors/{py_file.name}"
                await self.ssh.upload_file(
                    vm.ip_address, vm.ssh_user, vm.ssh_port,
                    str(py_file), remote_path
                )

    async def _create_docker_compose(self, vm: Vm) -> None:
        """Crée le fichier docker-compose.yml pour l'agent."""
        compose_content = """version: '3.8'

services:
  agent:
    build: .
    container_name: infra-mapper-agent
    restart: unless-stopped
    network_mode: host
    pid: host
    cap_add:
      - NET_ADMIN
      - NET_RAW
      - SYS_PTRACE
      - SYS_ADMIN
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /root:/root:ro
      - /home:/home:ro
      - /opt:/opt:ro
      - /srv:/srv:ro
      - /var/run/tailscale:/var/run/tailscale:ro
      - /proc:/host/proc:ro
    env_file:
      - .env
"""
        await self.ssh.upload_content(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            compose_content,
            f"{self.AGENT_PATH}/docker-compose.yml"
        )

    async def _create_env_file(self, vm: Vm) -> None:
        """Crée le fichier .env pour l'agent."""
        env_content = f"""MAPPER_BACKEND_URL={settings.backend_url}
MAPPER_API_KEY={settings.api_key}
MAPPER_SCAN_INTERVAL=30
MAPPER_LOG_LEVEL=INFO
MAPPER_TAILSCALE_ENABLED=true
MAPPER_TCPDUMP_ENABLED=true
MAPPER_TCPDUMP_MODE=intermittent
"""
        await self.ssh.upload_content(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            env_content,
            f"{self.AGENT_PATH}/.env"
        )

    async def start_agent(self, vm: Vm) -> dict:
        """Démarre l'agent sur une VM."""
        stdout, stderr, code = await self.ssh.execute(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            f"cd {self.AGENT_PATH} && docker compose start"
        )

        if code == 0:
            vm.status = VmStatusEnum.ONLINE
            await self.db.commit()
            return {"status": "started", "vm_id": vm.id}
        else:
            return {"status": "error", "vm_id": vm.id, "message": stderr}

    async def stop_agent(self, vm: Vm) -> dict:
        """Arrête l'agent sur une VM."""
        stdout, stderr, code = await self.ssh.execute(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            f"cd {self.AGENT_PATH} && docker compose stop"
        )

        if code == 0:
            vm.status = VmStatusEnum.OFFLINE
            await self.db.commit()
            return {"status": "stopped", "vm_id": vm.id}
        else:
            return {"status": "error", "vm_id": vm.id, "message": stderr}

    async def restart_agent(self, vm: Vm) -> dict:
        """Redémarre l'agent sur une VM."""
        stdout, stderr, code = await self.ssh.execute(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            f"cd {self.AGENT_PATH} && docker compose restart"
        )

        if code == 0:
            vm.status = VmStatusEnum.ONLINE
            await self.db.commit()
            return {"status": "restarted", "vm_id": vm.id}
        else:
            return {"status": "error", "vm_id": vm.id, "message": stderr}

    async def update_agent(self, vm: Vm) -> dict:
        """Met à jour l'agent sur une VM."""
        logger.info(f"Mise à jour de l'agent sur {vm.name}")

        try:
            # Upload les nouveaux fichiers
            await self._upload_agent_files(vm)

            # Mettre à jour le fichier .env (au cas où l'URL backend a changé)
            await self._create_env_file(vm)

            # Rebuild et restart
            stdout, stderr, code = await self.ssh.execute(
                vm.ip_address, vm.ssh_user, vm.ssh_port,
                f"cd {self.AGENT_PATH} && docker compose up -d --build",
                timeout=600  # 10 minutes pour le build
            )

            if code == 0:
                vm.status = VmStatusEnum.ONLINE
                await self.db.commit()
                return {"status": "updated", "vm_id": vm.id}
            else:
                return {"status": "error", "vm_id": vm.id, "message": stderr}

        except Exception as e:
            return {"status": "error", "vm_id": vm.id, "message": str(e)}

    async def delete_agent(self, vm: Vm) -> dict:
        """Supprime l'agent d'une VM."""
        logger.info(f"Suppression de l'agent sur {vm.name}")

        stdout, stderr, code = await self.ssh.execute(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            f"cd {self.AGENT_PATH} && docker compose down -v; rm -rf {self.AGENT_PATH}"
        )

        vm.status = VmStatusEnum.PENDING
        vm.agent_installed_at = None
        await self.db.commit()

        return {"status": "deleted", "vm_id": vm.id}

    async def get_agent_logs(self, vm: Vm, lines: int = 100) -> str:
        """Récupère les logs de l'agent."""
        stdout, stderr, code = await self.ssh.execute(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            f"cd {self.AGENT_PATH} && docker compose logs --tail={lines} 2>&1"
        )

        if code == 0:
            return stdout
        else:
            return f"Erreur: {stderr}"

    async def get_agent_status(self, vm: Vm) -> dict:
        """Récupère le statut de l'agent."""
        stdout, stderr, code = await self.ssh.execute(
            vm.ip_address, vm.ssh_user, vm.ssh_port,
            f"cd {self.AGENT_PATH} && docker compose ps --format json 2>/dev/null"
        )

        if code == 0 and stdout:
            return {"status": "running", "output": stdout}
        else:
            return {"status": "not_running", "output": stderr}
