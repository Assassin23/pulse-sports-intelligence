"""
User profile views.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sports_platform.users.serializers import (
    ChangePasswordSerializer,
    UserProfileSerializer,
    UserUpdateSerializer,
)
from sports_platform.users.services import UserService

logger = logging.getLogger(__name__)


class MeView(APIView):
    """
    GET  /api/v1/users/me  — retrieve own profile
    PATCH /api/v1/users/me  — update own profile (first/last name)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request: Request) -> Response:
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserProfileSerializer(request.user).data)


class ChangePasswordView(APIView):
    """
    POST /api/v1/users/me/change-password
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        success = UserService.change_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )

        if not success:
            return Response(
                {
                    "error": {
                        "code": "WRONG_PASSWORD",
                        "message": "Current password is incorrect.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info("password_changed", extra={"user_id": str(request.user.id)})
        return Response({"message": "Password changed successfully."})


class DeleteAccountView(APIView):
    """
    DELETE /api/v1/users/me  — soft-delete account (GDPR)
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request: Request) -> Response:
        UserService.soft_delete_user(request.user)
        logger.info("account_deleted", extra={"user_id": str(request.user.id)})
        return Response(status=status.HTTP_204_NO_CONTENT)
