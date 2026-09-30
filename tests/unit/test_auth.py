"""
Unit & API tests for authentication endpoints and services.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from sports_platform.users.models import RefreshTokenRecord
from sports_platform.users.services import AuthService, UserService
from tests.factories import UserFactory

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory(email="john@example.com", username="johndoe", password="Password123!")


@pytest.mark.django_db
class TestAuthAPI:
    def test_register_success(self, api_client):
        url = reverse("api-v1:auth:register")
        payload = {
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "StrongPassword123!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "tokens" in response.data
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]
        assert response.data["user"]["email"] == "newuser@example.com"
        assert User.objects.filter(email="newuser@example.com").exists()

    def test_register_duplicate_email(self, api_client, user):
        url = reverse("api-v1:auth:register")
        payload = {
            "email": "john@example.com",
            "username": "anotheruser",
            "password": "StrongPassword123!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_success(self, api_client, user):
        url = reverse("api-v1:auth:login")
        payload = {
            "email": "john@example.com",
            "password": "Password123!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "tokens" in response.data
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]
        assert response.data["user"]["email"] == "john@example.com"

    def test_login_invalid_credentials(self, api_client, user):
        url = reverse("api-v1:auth:login")
        payload = {
            "email": "john@example.com",
            "password": "WrongPassword!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token(self, api_client, user):
        tokens = AuthService.issue_tokens(user)
        url = reverse("api-v1:auth:refresh")
        response = api_client.post(url, {"refresh": tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_logout_revokes_token(self, api_client, user):
        tokens = AuthService.issue_tokens(user)
        url = reverse("api-v1:auth:logout")
        response = api_client.post(url, {"refresh": tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert AuthService.is_token_revoked(tokens["refresh"]) is True
