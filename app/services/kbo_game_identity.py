"""Read aliases for the strictly identified KBO game ID and PBP year suffix."""
import re
from datetime import date

from app.services.team_codes import normalize_official_team_code


_GAME_ID = re.compile(r"(?P<day>\d{8})(?P<away>[A-Z]{2})(?P<home>[A-Z]{2})(?P<game>[012])(?P<season>\d{4})?")
_TEAM_CODES = {"HT", "SK", "SS", "LG", "KT", "NC", "OB", "LT", "HH", "WO"}


def canonical_game_pk(game_pk: str) -> str | None:
    match = _GAME_ID.fullmatch(game_pk)
    if not match or match["away"] not in _TEAM_CODES or match["home"] not in _TEAM_CODES or match["away"] == match["home"]:
        return None
    try:
        game_day = date.fromisoformat(f"{match['day'][:4]}-{match['day'][4:6]}-{match['day'][6:]}")
    except ValueError:
        return None
    if match["season"] is not None and int(match["season"]) != game_day.year:
        return None
    return f"{match['day']}{match['away']}{match['home']}{match['game']}"


def game_pk_candidates(
    game_pk: str, *, season: int, game_date: date,
    home_team_code: str, away_team_code: str,
) -> tuple[str, ...]:
    """Expand only when the parsed ID, season, date and both clubs agree."""
    canonical = canonical_game_pk(game_pk)
    if canonical is None:
        return (game_pk,)
    match = _GAME_ID.fullmatch(canonical)
    if (
        game_date.year != season
        or match["day"] != game_date.strftime("%Y%m%d")
        or match["home"] != normalize_official_team_code(home_team_code)
        or match["away"] != normalize_official_team_code(away_team_code)
    ):
        return (game_pk,)
    return canonical, f"{canonical}{season}"
