"""
User admin configuration.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from sports_platform.users.models import RefreshTokenRecord, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "is_active", "is_staff", "created_at", "deleted_at"]
    list_filter = ["is_active", "is_staff", "is_superuser", "created_at"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["-created_at"]
    readonly_fields = ["id", "created_at", "updated_at", "last_login_at"]

    fieldsets = (
        (None, {"fields": ("id", "email", "username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login_at", "created_at", "updated_at", "deleted_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "password1", "password2"),
            },
        ),
    )


@admin.register(RefreshTokenRecord)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "is_revoked", "expires_at", "created_at"]
    list_filter = ["revoked_at"]
    search_fields = ["user__username", "user__email", "jti_hash"]
    readonly_fields = ["id", "created_at"]
    raw_id_fields = ["user"]
