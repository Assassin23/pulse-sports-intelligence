"""
Auth views: register, login, token refresh, logout.
"""
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from sports_platform.users.serializers import RegisterSerializer, UserProfileSerializer
from sports_platform.users.services import AuthService

logger = logging.getLogger(__name__)


class AuthRateThrottle(AnonRateThrottle):
    """Stricter throttle for auth endpoints to prevent brute-force."""

    scope = "auth"


class RegisterView(APIView):
    """
    POST /api/v1/auth/register

    Creates a new user account and returns JWT tokens.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        tokens = AuthService.issue_tokens(user)

        logger.info(
            "user_registered",
            extra={
                "user_id": str(user.id),
                "username": user.username,
                "ip": request.META.get("REMOTE_ADDR"),
            },
        )

        return Response(
            {
                "user": UserProfileSerializer(user).data,
                "tokens": tokens,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login

    Returns access + refresh tokens + user profile.
    Uses the CustomTokenObtainPairSerializer which includes user data.
    """

    throttle_classes = [AuthRateThrottle]

    def post(self, request: Request, *args, **kwargs) -> Response:
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            logger.info(
                "user_logged_in",
                extra={"ip": request.META.get("REMOTE_ADDR")},
            )
        return response


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout

    Revokes the provided refresh token (blacklists it).
    Access tokens expire naturally (15 min TTL).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": {"code": "MISSING_REFRESH_TOKEN", "message": "refresh token is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success = AuthService.revoke_refresh_token(refresh_token)
        if success:
            logger.info(
                "user_logged_out",
                extra={"user_id": str(request.user.id)},
            )
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {"error": {"code": "INVALID_TOKEN", "message": "Token is invalid or already revoked"}},
            status=status.HTTP_400_BAD_REQUEST,
        )


class TokenRefreshViewCustom(TokenRefreshView):
    """
    POST /api/v1/auth/refresh

    Returns a new access token using a valid refresh token.
    simplejwt handles rotation and blacklisting automatically.
    """

    pass
