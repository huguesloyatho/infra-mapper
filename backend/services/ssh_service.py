"""Service SSH pour exécution de commandes distantes."""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Tuple

import asyncssh

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SshService:
    """Service SSH pour exécution de commandes distantes via asyncssh."""

    def __init__(self):
        """Initialise le service SSH."""
        self.ssh_key_path = Path(settings.ssh_key_path)

    async def execute(
        self,
        host: str,
        user: str,
        port: int,
        command: str,
        timeout: int = 60
    ) -> Tuple[str, str, int]:
        """
        Exécute une commande SSH et retourne (stdout, stderr, return_code).

        Args:
            host: Adresse IP ou hostname
            user: Utilisateur SSH
            port: Port SSH
            command: Commande à exécuter
            timeout: Timeout en secondes

        Returns:
            Tuple (stdout, stderr, return_code)
        """
        try:
            async with asyncssh.connect(
                host,
                port=port,
                username=user,
                client_keys=[str(self.ssh_key_path)] if self.ssh_key_path.exists() else None,
                known_hosts=None,  # Désactive la vérification des hosts connus
                connect_timeout=30,
            ) as conn:
                result = await asyncio.wait_for(
                    conn.run(command, check=False),
                    timeout=timeout
                )
                return (
                    result.stdout or "",
                    result.stderr or "",
                    result.returncode or 0
                )
        except asyncssh.Error as e:
            logger.error(f"Erreur SSH vers {user}@{host}:{port}: {e}")
            return "", str(e), -1
        except asyncio.TimeoutError:
            logger.error(f"Timeout SSH vers {user}@{host}:{port}")
            return "", "Connection timeout", -1
        except Exception as e:
            logger.error(f"Erreur inattendue SSH: {e}")
            return "", str(e), -1

    async def upload_file(
        self,
        host: str,
        user: str,
        port: int,
        local_path: str,
        remote_path: str
    ) -> bool:
        """
        Upload un fichier via SCP.

        Args:
            host: Adresse IP ou hostname
            user: Utilisateur SSH
            port: Port SSH
            local_path: Chemin local du fichier
            remote_path: Chemin distant

        Returns:
            True si succès
        """
        try:
            async with asyncssh.connect(
                host,
                port=port,
                username=user,
                client_keys=[str(self.ssh_key_path)] if self.ssh_key_path.exists() else None,
                known_hosts=None,
                connect_timeout=30,
            ) as conn:
                await asyncssh.scp(local_path, (conn, remote_path))
                return True
        except Exception as e:
            logger.error(f"Erreur SCP vers {user}@{host}:{port}: {e}")
            return False

    async def upload_content(
        self,
        host: str,
        user: str,
        port: int,
        content: str,
        remote_path: str
    ) -> bool:
        """
        Upload du contenu texte dans un fichier distant.

        Args:
            host: Adresse IP ou hostname
            user: Utilisateur SSH
            port: Port SSH
            content: Contenu à écrire
            remote_path: Chemin distant

        Returns:
            True si succès
        """
        try:
            async with asyncssh.connect(
                host,
                port=port,
                username=user,
                client_keys=[str(self.ssh_key_path)] if self.ssh_key_path.exists() else None,
                known_hosts=None,
                connect_timeout=30,
            ) as conn:
                async with conn.start_sftp_client() as sftp:
                    async with sftp.open(remote_path, "w") as f:
                        await f.write(content)
                return True
        except Exception as e:
            logger.error(f"Erreur upload content vers {user}@{host}:{port}: {e}")
            return False

    async def test_connection(
        self,
        host: str,
        user: str,
        port: int
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Teste la connectivité SSH et détecte l'OS.

        Args:
            host: Adresse IP ou hostname
            user: Utilisateur SSH
            port: Port SSH

        Returns:
            Tuple (success, message, os_detected)
        """
        try:
            stdout, stderr, code = await self.execute(
                host, user, port,
                "cat /etc/os-release 2>/dev/null || sw_vers 2>/dev/null || ver 2>/dev/null",
                timeout=15
            )

            if code == -1:
                return False, stderr, None

            # Détecter l'OS
            os_detected = None
            output_lower = stdout.lower()
            if "debian" in output_lower:
                os_detected = "debian"
            elif "ubuntu" in output_lower:
                os_detected = "ubuntu"
            elif "centos" in output_lower or "rhel" in output_lower or "rocky" in output_lower:
                os_detected = "centos"
            elif "macos" in output_lower or "darwin" in output_lower or "productname" in output_lower:
                os_detected = "macos"
            elif "windows" in output_lower:
                os_detected = "windows"
            else:
                os_detected = "unknown"

            return True, "Connexion réussie", os_detected

        except Exception as e:
            return False, str(e), None

    async def check_docker(self, host: str, user: str, port: int) -> bool:
        """Vérifie si Docker est installé sur l'hôte distant."""
        stdout, stderr, code = await self.execute(
            host, user, port,
            "docker --version",
            timeout=15
        )
        return code == 0


