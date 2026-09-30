"""
User business logic service layer.
Keeps views thin. All business rules live here.
"""
import hashlib
import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from sports_platform.users.models import RefreshTokenRecord

User = get_user_model()
logger = logging.getLogger(__name__)


def _hash_jti(jti: str) -> str:
    """SHA-256 hash of a token JTI — never store raw JTIs."""
    return hashlib.sha256(jti.encode()).hexdigest()


class AuthService:
    """
    Handles authentication-related business logic.
    """

    @staticmethod
    def issue_tokens(user: User) -> dict:
        """
        Issue a new access + refresh token pair for a user.
        Records the refresh token in the DB for revocation tracking.
        """
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        # Record in DB for revocation tracking
        jti = str(refresh["jti"])
        AuthService._record_refresh_token(user=user, jti=jti, refresh=refresh)

        logger.info(
            "tokens_issued",
            extra={"user_id": str(user.id), "username": user.username},
        )

        return {
            "access": str(access),
            "refresh": str(refresh),
        }

    @staticmethod
    def _record_refresh_token(user: User, jti: str, refresh: RefreshToken):
        """Store a hashed JTI in DB for future revocation checks."""
        from datetime import datetime, timezone as dt_timezone

        expires_at = datetime.fromtimestamp(refresh["exp"], tz=dt_timezone.utc)
        RefreshTokenRecord.objects.create(
            user=user,
            jti_hash=_hash_jti(jti),
            expires_at=expires_at,
        )

    @staticmethod
    def revoke_refresh_token(refresh_token_str: str) -> bool:
        """
        Revoke a refresh token by blacklisting it.
        1. Validates the token
        2. Marks it as revoked in DB
        3. Blacklists it via simplejwt's built-in blacklist
        Returns True on success, False on failure.
        """
        try:
            token = RefreshToken(refresh_token_str)
            jti = str(token["jti"])

            # Blacklist via simplejwt's built-in blacklist app
            token.blacklist()

            # Also mark in our DB
            jti_hash = _hash_jti(jti)
            RefreshTokenRecord.objects.filter(jti_hash=jti_hash).update(
                revoked_at=timezone.now()
            )

            logger.info("token_revoked", extra={"jti_hash": jti_hash[:8]})
            return True
        except Exception as e:
            logger.warning("token_revocation_failed", extra={"error": str(e)})
            return False

    @staticmethod
    def update_last_login(user: User):
        """Update the user's last login timestamp."""
        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at", "updated_at"])


class UserService:
    """
    User management business logic.
    """

    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[User]:
        try:
            return User.objects.get(id=user_id, deleted_at__isnull=True)
        except User.DoesNotExist:
            return None

    @staticmethod
    def change_password(user: User, current_password: str, new_password: str) -> bool:
        """
        Change password with current-password verification.
        Returns True on success, False if current password is wrong.
        """
        if not user.check_password(current_password):
            logger.warning(
                "password_change_failed_wrong_current",
                extra={"user_id": str(user.id)},
            )
            return False

        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        logger.info("password_changed", extra={"user_id": str(user.id)})
        return True

    @staticmethod
    def soft_delete_user(user: User):
        """
        GDPR-compliant user deletion.
        Marks the user as deleted without removing data.
        """
        user.soft_delete()
        logger.info("user_soft_deleted", extra={"user_id": str(user.id)})
