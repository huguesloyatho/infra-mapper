"""
Tests unitaires pour UserService.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from db.auth_models import User, RoleEnum
from services.user_service import UserService


pytestmark = pytest.mark.unit


class TestUserServiceCRUD:
    """Tests CRUD pour UserService."""

    async def test_create_user(self, db_session):
        """Test création d'un utilisateur."""
        service = UserService(db_session)

        user = await service.create_user(
            username="newuser",
            email="newuser@example.com",
            password="SecurePass123!",
            role=RoleEnum.VIEWER,
        )

        assert user is not None
        assert user.id is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.com"
        assert user.role == RoleEnum.VIEWER
        assert user.password_hash is not None

    async def test_create_user_without_password(self, db_session):
        """Test création utilisateur SSO (sans password)."""
        service = UserService(db_session)

        user = await service.create_user(
            username="ssouser",
            email="sso@example.com",
            password=None,
            role=RoleEnum.VIEWER,
            idp_id="google",
            external_id="123456",
        )

        assert user is not None
        assert user.password_hash is None
        assert user.idp_id == "google"
        assert user.external_id == "123456"

    async def test_create_user_weak_password_fails(self, db_session):
        """Test que les mots de passe faibles sont rejetés."""
        service = UserService(db_session)

        with pytest.raises(ValueError) as exc_info:
            await service.create_user(
                username="weakuser",
                email="weak@example.com",
                password="123",  # Trop simple
            )

        assert "invalide" in str(exc_info.value).lower()

    async def test_get_user(self, db_session, user_in_db):
        """Test récupération utilisateur par ID."""
        service = UserService(db_session)

        user = await service.get_user(user_in_db.id)

        assert user is not None
        assert user.id == user_in_db.id

    async def test_get_user_not_found(self, db_session):
        """Test récupération utilisateur inexistant."""
        service = UserService(db_session)

        user = await service.get_user("nonexistent")

        assert user is None

    async def test_get_user_by_username(self, db_session, user_in_db):
        """Test récupération par username."""
        service = UserService(db_session)

        user = await service.get_user_by_username(user_in_db.username)

        assert user is not None
        assert user.username == user_in_db.username

    async def test_get_user_by_email(self, db_session, user_in_db):
        """Test récupération par email."""
        service = UserService(db_session)

        user = await service.get_user_by_email(user_in_db.email)

        assert user is not None
        assert user.email == user_in_db.email

    async def test_update_user(self, db_session, user_in_db):
        """Test mise à jour utilisateur."""
        service = UserService(db_session)

        updated = await service.update_user(
            user_in_db.id,
            display_name="New Display Name",
            is_active=False,
        )

        assert updated is not None
        assert updated.display_name == "New Display Name"
        assert updated.is_active is False

    async def test_delete_user(self, db_session, user_in_db):
        """Test suppression utilisateur."""
        service = UserService(db_session)

        result = await service.delete_user(user_in_db.id)

        assert result is True

        # Vérifier suppression
        user = await service.get_user(user_in_db.id)
        assert user is None


class TestUserServiceList:
    """Tests pour le listing des utilisateurs."""

    async def test_list_users_empty(self, db_session):
        """Test listing sans utilisateurs."""
        service = UserService(db_session)

        users, total = await service.list_users()

        assert users == []
        assert total == 0

    async def test_list_users_with_data(self, db_session, user_in_db):
        """Test listing avec données."""
        service = UserService(db_session)

        users, total = await service.list_users()

        assert len(users) == 1
        assert total == 1

    async def test_list_users_with_role_filter(self, db_session, user_in_db):
        """Test listing avec filtre de rôle."""
        service = UserService(db_session)

        # Filtre correspondant
        users, total = await service.list_users(role=RoleEnum.ADMIN)
        assert len(users) == 1

        # Filtre non correspondant
        users, total = await service.list_users(role=RoleEnum.VIEWER)
        assert len(users) == 0

    async def test_list_users_with_search(self, db_session, user_in_db):
        """Test listing avec recherche."""
        service = UserService(db_session)

        # Recherche correspondante
        users, total = await service.list_users(search="test")
        assert len(users) == 1

        # Recherche non correspondante
        users, total = await service.list_users(search="nonexistent")
        assert len(users) == 0


class TestUserServicePassword:
    """Tests pour la gestion des mots de passe."""

    async def test_change_password_success(self, db_session):
        """Test changement de mot de passe réussi."""
        service = UserService(db_session)

        # Créer un utilisateur avec mot de passe
        user = await service.create_user(
            username="passtest",
            email="pass@test.com",
            password="OldPass123!",
        )

        # Changer le mot de passe
        success, error = await service.change_password(
            user.id,
            current_password="OldPass123!",
            new_password="NewPass456!",
        )

        assert success is True
        assert error is None

    async def test_change_password_wrong_current(self, db_session):
        """Test changement avec mauvais mot de passe actuel."""
        service = UserService(db_session)

        user = await service.create_user(
            username="passtest2",
            email="pass2@test.com",
            password="OldPass123!",
        )

        success, error = await service.change_password(
            user.id,
            current_password="WrongPassword!",
            new_password="NewPass456!",
        )

        assert success is False
        assert "incorrect" in error.lower()

    async def test_reset_password(self, db_session):
        """Test réinitialisation de mot de passe (admin)."""
        service = UserService(db_session)

        user = await service.create_user(
            username="resettest",
            email="reset@test.com",
            password="OldPass123!",
        )

        success, error = await service.reset_password(user.id, "NewReset123!")

        assert success is True
        assert error is None


class TestUserServiceRole:
    """Tests pour la gestion des rôles."""

    async def test_change_role(self, db_session, user_in_db):
        """Test changement de rôle."""
        service = UserService(db_session)

        updated = await service.change_role(user_in_db.id, RoleEnum.OPERATOR)

        assert updated is not None
        assert updated.role == RoleEnum.OPERATOR


class TestUserServiceAccountStatus:
    """Tests pour le statut des comptes."""

    async def test_activate_user(self, db_session, user_in_db):
        """Test activation utilisateur."""
        service = UserService(db_session)

        # Désactiver d'abord
        await service.update_user(user_in_db.id, is_active=False)

        # Réactiver
        user = await service.activate_user(user_in_db.id)

        assert user is not None
        assert user.is_active is True

    async def test_deactivate_user(self, db_session, user_in_db):
        """Test désactivation utilisateur."""
        service = UserService(db_session)

        user = await service.deactivate_user(user_in_db.id)

        assert user is not None
        assert user.is_active is False

    async def test_unlock_user(self, db_session, user_in_db):
        """Test déverrouillage utilisateur."""
        service = UserService(db_session)

        # Simuler un verrouillage
        user_in_db.is_locked = True
        user_in_db.failed_login_attempts = 5
        await db_session.commit()

        # Déverrouiller
        user = await service.unlock_user(user_in_db.id)

        assert user is not None
        assert user.is_locked is False
        assert user.failed_login_attempts == 0


class TestUserServiceSSO:
    """Tests pour la gestion des utilisateurs SSO."""

    async def test_find_or_create_sso_user_new(self, db_session):
        """Test création nouvel utilisateur SSO."""
        service = UserService(db_session)

        user = await service.find_or_create_sso_user(
            idp_id="google",
            external_id="google-123",
            email="ssonew@example.com",
            display_name="SSO User",
        )

        assert user is not None
        assert user.idp_id == "google"
        assert user.external_id == "google-123"
        assert user.email == "ssonew@example.com"

    async def test_find_or_create_sso_user_existing(self, db_session):
        """Test récupération utilisateur SSO existant."""
        service = UserService(db_session)

        # Créer d'abord
        user1 = await service.find_or_create_sso_user(
            idp_id="google",
            external_id="google-456",
            email="ssoexisting@example.com",
        )

        # Retrouver
        user2 = await service.find_or_create_sso_user(
            idp_id="google",
            external_id="google-456",
            email="ssoexisting@example.com",
        )

        assert user1.id == user2.id
