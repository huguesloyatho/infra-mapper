"""Service TOTP pour l'authentification à deux facteurs."""

import base64
import hashlib
import io
import secrets
from typing import Optional, List, Tuple

import pyotp
import qrcode
from qrcode.image.pil import PilImage

from config import get_settings

settings = get_settings()


class TOTPService:
    """Service pour la gestion du 2FA via TOTP."""

    # Nombre de codes de secours à générer
    BACKUP_CODES_COUNT = 10
    # Longueur d'un code de secours
    BACKUP_CODE_LENGTH = 8

    def __init__(self):
        """Initialise le service TOTP."""
        self.issuer = settings.app_name

    def generate_secret(self) -> str:
        """
        Génère un nouveau secret TOTP.

        Returns:
            Secret encodé en base32
        """
        return pyotp.random_base32()

    def get_totp(self, secret: str) -> pyotp.TOTP:
        """Crée un objet TOTP à partir du secret."""
        return pyotp.TOTP(secret)

    def verify_code(self, secret: str, code: str) -> bool:
        """
        Vérifie un code TOTP.

        Args:
            secret: Secret TOTP de l'utilisateur
            code: Code à 6 chiffres saisi

        Returns:
            True si le code est valide
        """
        if not secret or not code:
            return False

        totp = self.get_totp(secret)
        # valid_window=1 permet d'accepter le code précédent/suivant (30s de marge)
        return totp.verify(code, valid_window=1)

    def get_provisioning_uri(self, secret: str, username: str, email: str) -> str:
        """
        Génère l'URI de provisioning pour les apps authenticator.

        Args:
            secret: Secret TOTP
            username: Nom d'utilisateur
            email: Email de l'utilisateur

        Returns:
            URI otpauth://
        """
        totp = self.get_totp(secret)
        # Utiliser l'email comme identifiant pour plus de clarté
        return totp.provisioning_uri(name=email, issuer_name=self.issuer)

    def generate_qr_code(self, secret: str, username: str, email: str) -> str:
        """
        Génère un QR code en base64 pour l'enregistrement.

        Args:
            secret: Secret TOTP
            username: Nom d'utilisateur
            email: Email

        Returns:
            QR code en base64 (data URI)
        """
        uri = self.get_provisioning_uri(secret, username, email)

        # Créer le QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        # Générer l'image PNG avec Pillow
        img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")

        # Convertir en base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return f"data:image/png;base64,{img_base64}"

    def generate_backup_codes(self) -> Tuple[List[str], List[str]]:
        """
        Génère des codes de secours.

        Returns:
            Tuple (codes_en_clair, codes_hashés)
            - codes_en_clair: à afficher à l'utilisateur une seule fois
            - codes_hashés: à stocker en base de données
        """
        plain_codes = []
        hashed_codes = []

        for _ in range(self.BACKUP_CODES_COUNT):
            # Générer un code aléatoire
            code = secrets.token_hex(self.BACKUP_CODE_LENGTH // 2).upper()
            # Formater avec un tiret au milieu pour lisibilité
            formatted_code = f"{code[:4]}-{code[4:]}"
            plain_codes.append(formatted_code)

            # Hasher pour le stockage
            hashed = self._hash_backup_code(code)
            hashed_codes.append(hashed)

        return plain_codes, hashed_codes

    def _hash_backup_code(self, code: str) -> str:
        """Hash un code de secours pour le stockage."""
        # Nettoyer le code (retirer les tirets, mettre en majuscule)
        clean_code = code.replace("-", "").upper()
        return hashlib.sha256(clean_code.encode()).hexdigest()

    def verify_backup_code(self, code: str, hashed_codes: List[str]) -> Tuple[bool, Optional[int]]:
        """
        Vérifie un code de secours.

        Args:
            code: Code saisi par l'utilisateur
            hashed_codes: Liste des codes hashés stockés

        Returns:
            Tuple (is_valid, index_du_code_utilisé)
            L'index permet de retirer le code après utilisation
        """
        if not code or not hashed_codes:
            return False, None

        # Nettoyer le code
        clean_code = code.replace("-", "").replace(" ", "").upper()
        hashed_input = self._hash_backup_code(clean_code)

        for i, stored_hash in enumerate(hashed_codes):
            if stored_hash == hashed_input:
                return True, i

        return False, None

    def get_current_code(self, secret: str) -> str:
        """
        Récupère le code TOTP actuel (pour tests/debug).

        Args:
            secret: Secret TOTP

        Returns:
            Code actuel à 6 chiffres
        """
        totp = self.get_totp(secret)
        return totp.now()
