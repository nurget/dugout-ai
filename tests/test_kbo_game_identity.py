from datetime import date

import pytest

from app.services.kbo_game_identity import canonical_game_pk, game_pk_candidates


def candidates(game_pk, **overrides):
    scope = {"season": 2026, "game_date": date(2026, 7, 26), "home_team_code": "KIA", "away_team_code": "WO"}
    return game_pk_candidates(game_pk, **{**scope, **overrides})


@pytest.mark.parametrize("game_pk", ["20260726WOHT0", "20260726WOHT02026"])
def test_verified_pbp_season_suffix_and_kbo_id_have_exactly_two_read_aliases(game_pk):
    assert canonical_game_pk(game_pk) == "20260726WOHT0"
    assert candidates(game_pk) == ("20260726WOHT0", "20260726WOHT02026")


@pytest.mark.parametrize("game_pk", ["20260726WOHT02025", "20260726WOHT020262026", "20260230WOHT0", "20260726ZZHT0", "20260726HTHT0", "20260726WOHT3", "20260726WOHT0trailing", "g-box"])
def test_unverified_identifiers_are_never_shortened_or_expanded(game_pk):
    assert canonical_game_pk(game_pk) is None
    assert candidates(game_pk) == (game_pk,)


@pytest.mark.parametrize("overrides", [{"season": 2025}, {"game_date": date(2026, 7, 25)}, {"home_team_code": "LG"}, {"away_team_code": "SS"}])
def test_aliases_require_the_same_season_date_and_both_clubs(overrides):
    assert candidates("20260726WOHT0", **overrides) == ("20260726WOHT0",)
