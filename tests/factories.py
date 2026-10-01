"""
Test factories using factory_boy.
"""
import factory
from django.contrib.auth import get_user_model

from sports_platform.sports.models import Competition, Country, Player, Sport, Team

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "TestPass123!")
        user = super()._create(model_class, *args, **kwargs)
        user.set_password(password)
        user.save()
        return user


class SportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Sport

    slug = factory.Sequence(lambda n: f"sport-{n}")
    name = factory.Sequence(lambda n: f"Sport {n}")
    is_active = True


class CountryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Country

    iso_code = factory.Sequence(lambda n: f"{n:03d}"[:3])
    name = factory.Sequence(lambda n: f"Country {n}")


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    sport = factory.SubFactory(SportFactory)
    name = factory.Sequence(lambda n: f"Team {n}")
    short_name = factory.Sequence(lambda n: f"T{n}")
    team_type = "club"
    is_active = True


class CompetitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Competition

    sport = factory.SubFactory(SportFactory)
    name = factory.Sequence(lambda n: f"Competition {n}")
    short_name = factory.Sequence(lambda n: f"C{n}")
    competition_type = "league"
    is_active = True


class PlayerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Player

    sport = factory.SubFactory(SportFactory)
    name = factory.Sequence(lambda n: f"Player {n}")
    position = "Forward"
    is_active = True


class MatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "matches.Match"

    sport = factory.SubFactory(SportFactory)
    competition = factory.SubFactory(CompetitionFactory, sport=factory.SelfAttribute("..sport"))
    home_team = factory.SubFactory(TeamFactory, sport=factory.SelfAttribute("..sport"))
    away_team = factory.SubFactory(TeamFactory, sport=factory.SelfAttribute("..sport"))
    scheduled_at = factory.LazyFunction(
        lambda: __import__("django.utils.timezone", fromlist=["now"]).now()
    )
    status = "scheduled"
    source_provider = "test_provider"
    provider_match_id = factory.Sequence(lambda n: f"match-{n}")


class MatchEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "matches.MatchEvent"

    match = factory.SubFactory(MatchFactory)
    sport = factory.SubFactory(SportFactory)
    event_type = "goal"
    event_sequence = factory.Sequence(lambda n: n)
    source_provider = "test_provider"
