"""KBO 기록실의 1군 정규시즌 기본 투수 기록 수집 및 저장."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from http.cookiejar import CookieJar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo_official_season_pitcher import KboOfficialSeasonPitcher

KBO_PITCHER_URL = "https://www.koreabaseball.com/Record/Player/PitcherBasic/Basic1.aspx"
KBO_PITCHER_DETAIL_URL = "https://www.koreabaseball.com/Record/Player/PitcherBasic/Basic2.aspx"
FORM_PREFIX = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$"
KBO_TEAMS = ("KT", "SS", "HT", "LG", "OB", "SK", "LT", "NC", "HH", "WO")


class OfficialPitchingError(RuntimeError):
    pass


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}
        self._select: str | None = None
        self._option: tuple[str, bool] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        value = dict(attrs)
        if tag == "input" and value.get("name"):
            self.values[value["name"]] = value.get("value") or ""
        elif tag == "select":
            self._select = value.get("name")
        elif tag == "option" and self._select:
            self._option = (value.get("value") or "", "selected" in value)

    def handle_data(self, data: str) -> None:
        if self._select and self._option and self._option[1]:
            self.values[self._select] = self._option[0]

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self._option = None
        elif tag == "select":
            self._select = None


class _RowsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_body = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._pitcher_id: str | None = None
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "tbody": self._in_body = True
        elif self._in_body and tag == "tr": self._row = []
        elif self._row is not None and tag == "td": self._cell = []
        elif self._cell is not None and tag == "a":
            href = values.get("href") or ""
            if "playerId=" in href: self._pitcher_id = href.split("playerId=", 1)[1].split("&", 1)[0]

    def handle_data(self, data: str) -> None:
        if self._cell is not None: self._cell.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell)); self._cell = None
        elif tag == "tr" and self._row is not None:
            if len(self._row) >= 16 and self._pitcher_id:
                self.rows.append(self._row); self.ids.append(self._pitcher_id)
            self._row = None; self._pitcher_id = None
        elif tag == "tbody": self._in_body = False


def _request_form(opener, url: str, payload: dict[str, str]) -> str:
    request = Request(url, data=urlencode(payload).encode(), headers={"User-Agent": "Mozilla/5.0", "Referer": url, "Content-Type": "application/x-www-form-urlencoded"})
    return opener.open(request, timeout=30).read().decode("utf-8")


def _fetch_pages(opener, url: str, season: int, team: str, series: str) -> list[tuple[list[str], str]]:
    initial = opener.open(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8")
    form = _FormParser(); form.feed(initial)
    team_control = f"{FORM_PREFIX}ddlTeam$ddlTeam"; series_control = f"{FORM_PREFIX}ddlSeries$ddlSeries"; season_control = f"{FORM_PREFIX}ddlSeason$ddlSeason"
    # KBO ASP.NET은 대회와 팀 변경을 한 요청에 넣으면 대회 변경을 무시한다.
    # 반드시 대회를 먼저 postback한 새 ViewState로 팀을 선택한다.
    series_payload = dict(form.values); series_payload.update({"__EVENTTARGET": series_control, "__EVENTARGUMENT": "", "__LASTFOCUS": "", season_control: str(season), series_control: series})
    series_html = _request_form(opener, url, series_payload)
    series_form = _FormParser(); series_form.feed(series_html)
    if series_form.values.get(series_control) != series:
        raise OfficialPitchingError(f"KBO 대회 선택 검증 실패: {series}")
    payload = dict(series_form.values); payload.update({"__EVENTTARGET": team_control, "__EVENTARGUMENT": "", "__LASTFOCUS": "", team_control: team})
    html = _request_form(opener, url, payload); rows = _RowsParser(); rows.feed(html)
    found: list[tuple[list[str], str]] = []; seen_pages: set[str] = set()
    while rows.rows:
        page_form = _FormParser(); page_form.feed(html); page = page_form.values.get(f"{FORM_PREFIX}hfPage", "")
        if page in seen_pages: break
        seen_pages.add(page); found.extend(zip(rows.rows, rows.ids, strict=True))
        next_payload = dict(page_form.values); next_payload.update({"__EVENTTARGET": f"{FORM_PREFIX}ucPager$btnNext", "__EVENTARGUMENT": "", "__LASTFOCUS": ""})
        next_html = _request_form(opener, url, next_payload); next_rows = _RowsParser(); next_rows.feed(next_html)
        next_form = _FormParser(); next_form.feed(next_html)
        if not next_rows.rows or next_form.values.get(f"{FORM_PREFIX}hfPage") in seen_pages: break
        html, rows = next_html, next_rows
    return found


SERIES_TYPES = {"REGULAR": "0", "WILDCARD": "4", "SEMIPLAYOFF": "3", "PLAYOFF": "5", "KOREAN_SERIES": "7"}


def fetch_official_pitchers(season: int = 2026, include_postseason: bool = False) -> list[dict]:
    """공식 KBO 1군 정규시즌 G/BB/SO를 팀별로 읽는다."""
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    result: list[dict] = []
    series_types = SERIES_TYPES if include_postseason else {"REGULAR": "0"}
    for season_type, series in series_types.items():
      for team in KBO_TEAMS:
        basic = _fetch_pages(opener, KBO_PITCHER_URL, season, team, series)
        detail = {pid: values for values, pid in _fetch_pages(opener, KBO_PITCHER_DETAIL_URL, season, team, series)}
        if not basic or not detail:
            if season_type != "REGULAR":
                continue
            raise OfficialPitchingError(f"KBO 공식 기록을 읽지 못했습니다: {team}")
        for values, pitcher_id in basic:
            extra = detail.get(pitcher_id)
            if extra is None:
                result.append({"season_type": season_type, "pitcher_id": pitcher_id, "pitcher_name": values[1], "team_code": team, "games": int(values[4]), "batters_faced": None, "walks": int(values[13]), "strikeouts": int(values[15]), "k_pct": None, "bb_pct": None, "k_minus_bb_pct": None})
                continue
            try:
                bf = int(extra[8]); so = int(values[15]); bb = int(values[13])
                result.append({"season_type": season_type, "pitcher_id": pitcher_id, "pitcher_name": values[1], "team_code": team, "games": int(values[4]), "batters_faced": bf, "walks": bb, "strikeouts": so, "k_pct": round(100 * so / bf, 2), "bb_pct": round(100 * bb / bf, 2), "k_minus_bb_pct": round(100 * (so - bb) / bf, 2)})
            except (IndexError, ValueError) as error: raise OfficialPitchingError(f"KBO 기록 행 형식 오류: {values!r}") from error
    return result


async def import_official_pitchers(db: AsyncSession, rows: list[dict], *, season: int) -> int:
    for row in rows:
        existing = await db.scalar(select(KboOfficialSeasonPitcher).where(KboOfficialSeasonPitcher.season == season, KboOfficialSeasonPitcher.season_type == row["season_type"], KboOfficialSeasonPitcher.pitcher_id == row["pitcher_id"], KboOfficialSeasonPitcher.team_code == row["team_code"]))
        if existing is None: db.add(KboOfficialSeasonPitcher(season=season, **row))
        else:
            for key, value in row.items(): setattr(existing, key, value)
    await db.commit()
    return len(rows)
