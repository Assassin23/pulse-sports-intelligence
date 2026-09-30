"""
Unit and API tests for User Preferences and Follow system.
"""
import uuid
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from sports_platform.preferences.models import UserFollowedEntity, UserSportPreference
from sports_platform.preferences.services import PreferenceService
from tests.factories import (
    CompetitionFactory,
    CountryFactory,
    PlayerFactory,
    SportFactory,
    TeamFactory,
    UserFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory(email="sportsfan@example.com", username="sportsfan")


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
class TestPreferenceService:
    def test_max_3_sports_enforcement(self, user):
        s1 = SportFactory(slug="cricket", name="Cricket")
        s2 = SportFactory(slug="football", name="Football")
        s3 = SportFactory(slug="tennis", name="Tennis")
        s4 = SportFactory(slug="basketball", name="Basketball")

        t1 = TeamFactory(sport=s1, name="RCB")
        t2 = TeamFactory(sport=s2, name="Chelsea")
        t3 = TeamFactory(sport=s3, name="Player Federer")

        PreferenceService.follow_entity(user, "cricket", "team", t1.id)
        PreferenceService.follow_entity(user, "football", "team", t2.id)
        PreferenceService.follow_entity(user, "tennis", "team", t3.id)

        assert UserSportPreference.objects.filter(user=user).count() == 3

        # 4th sport should raise ValidationError
        t4 = TeamFactory(sport=s4, name="Lakers")
        with pytest.raises(ValidationError):
            PreferenceService.follow_entity(user, "basketball", "team", t4.id)

    def test_follow_and_unfollow_entity(self, user):
        sport = SportFactory(slug="cricket", name="Cricket")
        team = TeamFactory(sport=sport, name="RCB")

        res = PreferenceService.follow_entity(user, "cricket", "team", team.id)
        assert "Now following RCB" in res["message"]
        assert UserFollowedEntity.objects.filter(user=user, entity_id=team.id).exists()

        PreferenceService.unfollow_entity(user, "team", team.id)
        assert not UserFollowedEntity.objects.filter(user=user, entity_id=team.id).exists()

    def test_get_user_preferences_structure(self, user):
        sport = SportFactory(slug="cricket", name="Cricket")
        team = TeamFactory(sport=sport, name="RCB")
        comp = CompetitionFactory(sport=sport, name="IPL")

        PreferenceService.follow_entity(user, "cricket", "team", team.id)
        PreferenceService.follow_entity(user, "cricket", "competition", comp.id)

        data = PreferenceService.get_user_preferences(user)
        assert data["max_sports"] == 3
        assert data["sports_remaining"] == 2
        assert len(data["sports"]) == 1
        assert data["sports"][0]["sport"]["slug"] == "cricket"
        assert len(data["sports"][0]["following"]["teams"]) == 1
        assert len(data["sports"][0]["following"]["competitions"]) == 1


@pytest.mark.django_db
class TestPreferencesAPI:
    def test_get_preferences_authenticated(self, auth_client, user):
        response = auth_client.get("/api/v1/users/me/preferences/")
        assert response.status_code == status.HTTP_200_OK
        assert "sports" in response.data
        assert response.data["max_sports"] == 3

    def test_follow_entity_endpoint(self, auth_client, user):
        sport = SportFactory(slug="cricket", name="Cricket")
        team = TeamFactory(sport=sport, name="RCB")

        response = auth_client.post(
            "/api/v1/users/me/preferences/follow/",
            {"sport": "cricket", "entity_type": "team", "entity_id": str(team.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "message" in response.data

    def test_unfollow_entity_endpoint(self, auth_client, user):
        sport = SportFactory(slug="cricket", name="Cricket")
        team = TeamFactory(sport=sport, name="RCB")
        PreferenceService.follow_entity(user, "cricket", "team", team.id)

        response = auth_client.delete(
            f"/api/v1/users/me/preferences/follow/team/{team.id}/"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
