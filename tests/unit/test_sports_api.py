"""
Sports reference data API tests.
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    CompetitionFactory,
    CompetitionTeamFactory,
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
    return UserFactory()


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
class TestSportsSearchEndpoints:
    def test_list_sports(self, auth_client):
        SportFactory(slug="cricket", name="Cricket", is_active=True)
        SportFactory(slug="football", name="Football", is_active=True)
        response = auth_client.get("/api/v1/sports/")
        assert response.status_code == status.HTTP_200_OK
        slugs = [s["slug"] for s in response.data["sports"]]
        assert "cricket" in slugs
        assert "football" in slugs

    def test_inactive_sports_excluded(self, auth_client):
        SportFactory(slug="inactive-sport", name="Inactive", is_active=False)
        response = auth_client.get("/api/v1/sports/")
        slugs = [s["slug"] for s in response.data["sports"]]
        assert "inactive-sport" not in slugs

    def test_team_list_by_sport(self, auth_client):
        sport = SportFactory(slug="football", name="Football")
        TeamFactory(sport=sport, name="Chelsea FC")
        TeamFactory(sport=sport, name="Arsenal")

        response = auth_client.get("/api/v1/sports/football/teams/")
        assert response.status_code == status.HTTP_200_OK
        names = [t["name"] for t in response.data["teams"]]
        assert "Chelsea FC" in names
        assert "Arsenal" in names

    def test_team_search_by_name(self, auth_client):
        sport = SportFactory(slug="football2", name="Football")
        TeamFactory(sport=sport, name="Chelsea FC")
        TeamFactory(sport=sport, name="Arsenal")

        response = auth_client.get("/api/v1/sports/football2/teams/?q=chels")
        assert response.status_code == status.HTTP_200_OK
        names = [t["name"] for t in response.data["teams"]]
        assert "Chelsea FC" in names
        assert "Arsenal" not in names

    def test_team_filter_by_type(self, auth_client):
        sport = SportFactory(slug="cricket2", name="Cricket")
        TeamFactory(sport=sport, name="RCB", team_type="club")
        TeamFactory(sport=sport, name="India", team_type="national")

        response = auth_client.get("/api/v1/sports/cricket2/teams/?type=national")
        assert response.status_code == status.HTTP_200_OK
        names = [t["name"] for t in response.data["teams"]]
        assert "India" in names
        assert "RCB" not in names

    def test_competition_list_by_sport(self, auth_client):
        sport = SportFactory(slug="cricket3", name="Cricket")
        CompetitionFactory(sport=sport, name="IPL", season="2026")
        CompetitionFactory(sport=sport, name="BBL", season="2025")

        response = auth_client.get("/api/v1/sports/cricket3/competitions/")
        assert response.status_code == status.HTTP_200_OK
        names = [c["name"] for c in response.data["competitions"]]
        assert "IPL" in names
        assert "BBL" in names

    def test_competition_filter_by_season(self, auth_client):
        sport = SportFactory(slug="cricket4", name="Cricket")
        CompetitionFactory(sport=sport, name="IPL", season="2026")
        CompetitionFactory(sport=sport, name="IPL", season="2025")

        response = auth_client.get("/api/v1/sports/cricket4/competitions/?season=2026")
        names = [c["name"] for c in response.data["competitions"]]
        assert len(response.data["competitions"]) == 1

    def test_player_list_by_sport(self, auth_client):
        sport = SportFactory(slug="football3", name="Football")
        PlayerFactory(sport=sport, name="Virat Kohli", position="Batsman")

        response = auth_client.get("/api/v1/sports/football3/players/")
        assert response.status_code == status.HTTP_200_OK
        names = [p["name"] for p in response.data["players"]]
        assert "Virat Kohli" in names

    def test_unauthenticated_returns_401(self, api_client):
        response = api_client.get("/api/v1/sports/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_competition_teams_list(self, auth_client):
        sport = SportFactory(slug="football-comp-test", name="Football")
        comp = CompetitionFactory(sport=sport, name="Premier League")
        t1 = TeamFactory(sport=sport, name="Arsenal", team_type="club")
        t2 = TeamFactory(sport=sport, name="Chelsea", team_type="club")
        t3 = TeamFactory(sport=sport, name="Bayern Munich", team_type="club")

        CompetitionTeamFactory(competition=comp, team=t1)
        CompetitionTeamFactory(competition=comp, team=t2)

        url = f"/api/v1/sports/football-comp-test/competitions/{comp.id}/teams/"
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        names = [t["name"] for t in response.data["teams"]]
        assert "Arsenal" in names
        assert "Chelsea" in names
        assert "Bayern Munich" not in names
        assert response.data["count"] == 2

    def test_team_filter_by_competition_id(self, auth_client):
        sport = SportFactory(slug="cricket-comp-test", name="Cricket")
        comp = CompetitionFactory(sport=sport, name="IPL")
        rcb = TeamFactory(sport=sport, name="RCB")
        csk = TeamFactory(sport=sport, name="CSK")
        england = TeamFactory(sport=sport, name="England", team_type="national")

        CompetitionTeamFactory(competition=comp, team=rcb)
        CompetitionTeamFactory(competition=comp, team=csk)

        url = f"/api/v1/sports/cricket-comp-test/teams/?competition_id={comp.id}"
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        names = [t["name"] for t in response.data["teams"]]
        assert "RCB" in names
        assert "CSK" in names
        assert "England" not in names

    def test_unknown_sport_returns_404(self, auth_client):
        response = auth_client.get("/api/v1/sports/unknown-sport/teams/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
