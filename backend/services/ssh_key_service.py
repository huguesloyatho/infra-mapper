"""Service de gestion des clés SSH pour le backend."""

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SshKeyService:
    """Service de gestion des clés SSH."""

    def __init__(self):
        """Initialise le service."""
        self.ssh_dir = Path(settings.ssh_key_path).parent
        self.private_key_path = Path(settings.ssh_key_path)
        self.public_key_path = Path(f"{settings.ssh_key_path}.pub")

    def key_exists(self) -> bool:
        """Vérifie si une clé SSH existe."""
        return self.private_key_path.exists() and self.public_key_path.exists()

    def get_public_key(self) -> Optional[str]:
        """Retourne la clé publique."""
        if not self.public_key_path.exists():
            return None
        return self.public_key_path.read_text().strip()

    def generate_key(self, force: bool = False) -> Tuple[bool, str]:
        """
        Génère une nouvelle paire de clés SSH.

        Args:
            force: Si True, écrase les clés existantes

        Returns:
            Tuple (success, message)
        """
        if self.key_exists() and not force:
            return False, "Une clé SSH existe déjà. Utilisez force=True pour la régénérer."

        try:
            # Créer le répertoire .ssh si nécessaire
            self.ssh_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.ssh_dir, 0o700)

            # Supprimer les anciennes clés si force
            if force:
                if self.private_key_path.exists():
                    self.private_key_path.unlink()
                if self.public_key_path.exists():
                    self.public_key_path.unlink()

            # Générer la nouvelle clé
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-t", "ed25519",
                    "-f", str(self.private_key_path),
                    "-N", "",  # Pas de passphrase
                    "-C", "infra-mapper-backend",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return False, f"Erreur génération clé: {result.stderr}"

            # Définir les permissions correctes
            os.chmod(self.private_key_path, 0o600)
            os.chmod(self.public_key_path, 0o644)

            logger.info(f"Clé SSH générée: {self.private_key_path}")
            return True, "Clé SSH générée avec succès"

        except Exception as e:
            logger.error(f"Erreur génération clé SSH: {e}")
            return False, str(e)

    async def deploy_key_to_host(
        self,
        host: str,
        user: str,
        port: int,
        password: str,
    ) -> Tuple[bool, str]:
        """
        Déploie la clé publique sur un hôte distant via ssh-copy-id.

        Args:
            host: Adresse IP ou hostname
            user: Utilisateur SSH
            port: Port SSH
            password: Mot de passe pour l'authentification initiale

        Returns:
            Tuple (success, message)
        """
        if not self.key_exists():
            success, msg = self.generate_key()
            if not success:
                return False, f"Impossible de générer la clé: {msg}"

        public_key = self.get_public_key()
        if not public_key:
            return False, "Impossible de lire la clé publique"

        try:
            # Utiliser sshpass + ssh pour déployer la clé
            # On ne peut pas utiliser ssh-copy-id directement car il attend un TTY
            command = f"""
mkdir -p ~/.ssh && chmod 700 ~/.ssh && \
echo '{public_key}' >> ~/.ssh/authorized_keys && \
chmod 600 ~/.ssh/authorized_keys && \
sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys
"""

            process = await asyncio.create_subprocess_exec(
                "sshpass", "-p", password,
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-p", str(port),
                f"{user}@{host}",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                if "Permission denied" in error_msg:
                    return False, "Mot de passe incorrect ou accès refusé"
                if "Connection refused" in error_msg:
                    return False, f"Connexion refusée sur le port {port}"
                if "No route to host" in error_msg:
                    return False, "Hôte inaccessible"
                return False, f"Erreur: {error_msg}"

            logger.info(f"Clé SSH déployée sur {user}@{host}:{port}")
            return True, "Clé SSH déployée avec succès"

        except asyncio.TimeoutError:
            return False, "Timeout lors du déploiement de la clé"
        except FileNotFoundError:
            # sshpass n'est pas installé, essayer une méthode alternative
            return await self._deploy_key_without_sshpass(host, user, port, password, public_key)
        except Exception as e:
            logger.error(f"Erreur déploiement clé: {e}")
            return False, str(e)

    async def _deploy_key_without_sshpass(
        self,
        host: str,
        user: str,
        port: int,
        password: str,
        public_key: str,
    ) -> Tuple[bool, str]:
        """
        Méthode alternative sans sshpass (utilise expect ou paramiko).
        """
        try:
            import asyncssh

            async with asyncssh.connect(
                host,
                port=port,
                username=user,
                password=password,
                known_hosts=None,
                connect_timeout=30,
            ) as conn:
                # Créer .ssh et ajouter la clé
                commands = [
                    "mkdir -p ~/.ssh",
                    "chmod 700 ~/.ssh",
                    f"echo '{public_key}' >> ~/.ssh/authorized_keys",
                    "chmod 600 ~/.ssh/authorized_keys",
                    "sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys",
                ]

                for cmd in commands:
                    result = await conn.run(cmd, check=False)
                    if result.returncode != 0:
                        return False, f"Erreur: {result.stderr}"

                logger.info(f"Clé SSH déployée sur {user}@{host}:{port} (via asyncssh)")
                return True, "Clé SSH déployée avec succès"

        except Exception as e:
            logger.error(f"Erreur déploiement clé (asyncssh): {e}")
            return False, str(e)

    def get_key_info(self) -> dict:
        """Retourne les informations sur la clé SSH actuelle."""
        if not self.key_exists():
            return {
                "exists": False,
                "public_key": None,
                "fingerprint": None,
            }

        public_key = self.get_public_key()

        # Obtenir l'empreinte de la clé
        fingerprint = None
        try:
            result = subprocess.run(
                ["ssh-keygen", "-lf", str(self.public_key_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                fingerprint = result.stdout.strip()
        except Exception:
            pass

        return {
            "exists": True,
            "public_key": public_key,
            "fingerprint": fingerprint,
        }
