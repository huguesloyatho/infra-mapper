"""Collecteur d'informations Tailscale."""

import subprocess
import json
import logging
from typing import Optional

from models import TailscaleInfo

logger = logging.getLogger(__name__)


class TailscaleCollector:
    """Collecte les informations Tailscale de l'hôte."""

    def __init__(self):
        """Initialise le collecteur Tailscale."""
        pass

    def collect(self) -> Optional[TailscaleInfo]:
        """Collecte les informations Tailscale."""
        if not self._is_tailscale_installed():
            return TailscaleInfo(enabled=False)

        try:
            status = self._get_status()
            if not status:
                return TailscaleInfo(enabled=False)

            # Récupérer les informations de l'hôte
            self_info = status.get("Self", {})

            # Récupérer les peers
            peers = {}
            peer_data = status.get("Peer", {})
            for peer_id, peer_info in peer_data.items():
                hostname = peer_info.get("HostName", "")
                ips = peer_info.get("TailscaleIPs", [])
                if hostname and ips:
                    peers[hostname] = ips[0]  # Première IP

            return TailscaleInfo(
                enabled=True,
                ip=self_info.get("TailscaleIPs", [None])[0],
                hostname=self_info.get("HostName"),
                tailnet=status.get("MagicDNSSuffix", "").replace(".ts.net", ""),
                peers=peers,
            )

        except Exception as e:
            logger.error(f"Erreur lors de la collecte Tailscale: {e}")
            return TailscaleInfo(enabled=False)

    def _is_tailscale_installed(self) -> bool:
        """Vérifie si Tailscale est installé."""
        try:
            result = subprocess.run(
                ["which", "tailscale"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_status(self) -> Optional[dict]:
        """Récupère le status Tailscale en JSON."""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.warning(f"tailscale status a échoué: {result.stderr}")
                return None

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            logger.error("Timeout lors de l'exécution de tailscale status")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON Tailscale: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur Tailscale: {e}")
            return None

    def get_ip_mapping(self) -> dict[str, str]:
        """Retourne un mapping hostname -> IP Tailscale pour tous les peers."""
        info = self.collect()
        if info and info.enabled:
            return info.peers
        return {}
