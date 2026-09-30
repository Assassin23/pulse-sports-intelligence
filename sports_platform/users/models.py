"""
User models.

Custom User model using UUID primary key and email-based auth.
Also defines RefreshToken for JWT token tracking and blacklisting.
"""
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    """
    Custom manager for email-based authentication.
    """

    def create_user(self, email: str, username: str, password: str, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        if not username:
            raise ValueError("Users must have a username")

        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, username: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model.

    Uses UUID as primary key and email as the authentication field.
    Soft-delete via deleted_at timestamp.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=100, unique=True, db_index=True)

    # Profile
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(
                fields=["email"],
                name="idx_users_email_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.username} <{self.email}>"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def soft_delete(self):
        """Mark user as deleted without removing from DB (GDPR compliance)."""
        from django.utils import timezone

        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=["deleted_at", "is_active", "updated_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class RefreshTokenRecord(models.Model):
    """
    Tracks issued refresh tokens for revocation support.

    When a user logs out, their refresh token is added here.
    On refresh, we check this table (and Redis for speed).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    # Store SHA-256 of the JTI (never the raw token)
    jti_hash = models.CharField(max_length=64, unique=True, db_index=True)
    device_info = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "refresh_tokens"
        indexes = [
            models.Index(
                fields=["jti_hash"],
                name="idx_refresh_tokens_jti_active",
                condition=models.Q(revoked_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"Token {self.jti_hash[:8]}... for {self.user.username}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return self.expires_at < timezone.now()
