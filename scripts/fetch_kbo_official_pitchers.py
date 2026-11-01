
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait


BASE_URL = (
    "https://www.koreabaseball.com"
    "/Record/Player/PitcherBasic/Basic1.aspx"
)

TEAM_CODES = [
    "LG", "HH", "SK", "SS", "NC",
    "KT", "LT", "HT", "OB", "WO",
]

SEASON_SELECT_ID = (
    "cphContents_cphContents_cphContents_ddlSeason_ddlSeason"
)

TEAM_SELECT_ID = (
    "cphContents_cphContents_cphContents_ddlTeam_ddlTeam"
)

SERIES_SELECT_ID = (
    "cphContents_cphContents_cphContents_ddlSeries_ddlSeries"
)

TABLE_SELECTOR = "table.tData01"

OUTPUT_DIR = Path("data/private")


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,1000")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)

    return driver


def save_debug_html(driver, name: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    path = OUTPUT_DIR / f"debug_kbo_{name}.html"
    path.write_text(
        driver.page_source,
        encoding="utf-8",
    )

    print(f"디버그 HTML 저장: {path}")
    return path


def get_table_rows(driver):
    return driver.find_elements(
        By.CSS_SELECTOR,
        f"{TABLE_SELECTOR} tbody tr",
    )



def table_signature(driver):
    soup = BeautifulSoup(
        driver.page_source,
        "html.parser",
    )

    table = soup.select_one(TABLE_SELECTOR)

    if table is None:
        return None

    rows = table.select("tbody tr")

    if not rows:
        return None

    return tuple(
        row.get_text(" ", strip=True)
        for row in rows
    )


def wait_for_table_data(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda d: len(get_table_rows(d)) > 0
    )


def find_year_select(driver, season: int):
    element = driver.find_element(
        By.ID,
        SEASON_SELECT_ID,
    )

    values = [
        option.get_attribute("value")
        for option in Select(element).options
    ]

    if str(season) not in values:
        raise ValueError(
            f"{season}년은 선택 가능한 시즌이 아닙니다."
        )

    return SEASON_SELECT_ID


def select_filter(driver, select_id, value):
    element = WebDriverWait(driver, 20).until(
        lambda d: d.find_element(By.ID, select_id)
    )

    current = Select(element).first_selected_option
    current_value = current.get_attribute("value")

    if current_value == str(value):
        return

    Select(element).select_by_value(str(value))

    # ASP.NET postback 후 화면이 갱신될 시간을 준다.
    WebDriverWait(driver, 20).until(
        lambda d: (
            Select(
                d.find_element(By.ID, select_id)
            ).first_selected_option.get_attribute("value")
            == str(value)
        )
    )

    time.sleep(0.8)


def configure_filters(driver, season, team_code, page="Basic1"):
    driver.get(
        f"https://www.koreabaseball.com/"
        f"Record/Player/PitcherBasic/{page}.aspx"
    )

    wait = WebDriverWait(driver, 20)

    wait.until(
        lambda d: d.find_elements(By.ID, SEASON_SELECT_ID)
    )

    # KBO 기록실은 시즌 → 대회 → 팀 순서로 선택한다.
    select_filter(driver, SEASON_SELECT_ID, season)
    select_filter(driver, SERIES_SELECT_ID, "0")
    select_filter(driver, TEAM_SELECT_ID, team_code)

    expected = [
        (SEASON_SELECT_ID, str(season)),
        (SERIES_SELECT_ID, "0"),
        (TEAM_SELECT_ID, team_code),
    ]

    for select_id, value in expected:
        selected = Select(
            driver.find_element(By.ID, select_id)
        ).first_selected_option.get_attribute("value")

        if selected != value:
            save_debug_html(
                driver,
                f"{season}_{team_code}_filter_error",
            )

            raise RuntimeError(
                f"필터 적용 실패: {select_id} "
                f"expected={value}, actual={selected}"
            )

    try:
        wait_for_table_data(driver, timeout=20)
    except TimeoutException as error:
        save_debug_html(
            driver,
            f"{season}_{team_code}_empty",
        )

        raise RuntimeError(
            f"{season}년 {team_code} 정규시즌 "
            "선수 기록이 로딩되지 않았습니다."
        ) from error


def extract_player_id(tr):
    # 선수 상세 페이지 링크는 일반 URL 또는
    # javascript 함수 호출 형태일 수 있다.
    for link in tr.select("a"):
        href = link.get("href", "")
        onclick = link.get("onclick", "")

        match = re.search(
            r"playerId=(\d+)",
            href + " " + onclick,
            re.IGNORECASE,
        )

        if match:
            return match.group(1)

        match = re.search(
            r"(?:player|popup|detail)[^(]*\(\s*['\"]?(\d{5})['\"]?",
            href + " " + onclick,
            re.IGNORECASE,
        )

        if match:
            return match.group(1)

    return None


def parse_records(html: str, team_code: str):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(TABLE_SELECTOR)

    if table is None:
        raise ValueError("KBO 기록 테이블이 없습니다.")

    headers = [
        th.get_text(" ", strip=True)
        for th in table.select("thead th")
    ]

    required_columns = {"선수명"}

    if not required_columns.issubset(set(headers)):
        raise ValueError(
            "필요한 기록 컬럼이 없습니다. "
            f"확인된 컬럼: {headers}"
        )

    records = []

    for tr in table.select("tbody tr"):
        cells = tr.find_all("td", recursive=False)

        if len(cells) != len(headers):
            continue

        values = [
            cell.get_text(" ", strip=True)
            for cell in cells
        ]

        record = dict(zip(headers, values))
        player_id = extract_player_id(tr)

        if not player_id:
            raise ValueError(
                f"{team_code}: 선수 ID를 추출할 수 없습니다. "
                f"선수명={record.get('선수명')}"
            )

        record["player_id"] = player_id
        record["team_code"] = team_code

        records.append(record)

    return records



def find_next_page_button(driver, next_page):
    button_id = (
        "cphContents_cphContents_cphContents_"
        f"ucPager_btnNo{next_page}"
    )

    buttons = driver.find_elements(
        By.ID,
        button_id,
    )

    if not buttons:
        return None

    button = buttons[0]

    if not button.is_displayed():
        return None

    return button


def collect_team(
    driver, 
    season: int, 
    team_code: str,
    page: str = "Basic1",
    ):
    configure_filters(driver, season, team_code, page)

    records = {}
    page_number = 1

    while True:
        try:
            page_records = parse_records(
                driver.page_source,
                team_code,
            )
        except ValueError:
            save_debug_html(
                driver,
                f"{season}_{team_code}_page{page_number}",
            )
            raise

        if not page_records:
            save_debug_html(
                driver,
                f"{season}_{team_code}_page{page_number}",
            )

            raise RuntimeError(
                f"{team_code}: {page_number}페이지 "
                "선수 기록이 없습니다."
            )

        for record in page_records:
            player_id = record["player_id"]

            if player_id in records:
                raise RuntimeError(
                    f"{team_code}: 페이지 간 중복 선수 "
                    f"ID={player_id}"
                )

            records[player_id] = record

        print(
            f"  {team_code} {page_number}페이지: "
            f"{len(page_records)}명"
        )

        next_page = page_number + 1
        next_button = find_next_page_button(
            driver,
            next_page,
        )

        if next_button is None:
            # 다음 버튼을 찾지 못한 경우에도 페이지가
            # 더 있을 수 있으므로 페이지 구조 확인이 필요하다.
            break

        before = table_signature(driver)
        next_button.click()

        try:
            WebDriverWait(driver, 20).until(
                lambda d: (
                    len(get_table_rows(d)) > 0
                    and table_signature(d) != before
                )
            )
        except TimeoutException as error:
            save_debug_html(
                driver,
                f"{season}_{team_code}_page{next_page}",
            )
            raise RuntimeError(
                f"{team_code}: {next_page}페이지 "
                "이동 결과를 확인하지 못했습니다."
            ) from error

        page_number = next_page

    return list(records.values())


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--season",
        type=int,
        default=2026,
    )

    args = parser.parse_args()

    output = OUTPUT_DIR / (
    f"kbo_official_pitchers_merged_{args.season}.json"
)

    if output.exists():
        raise FileExistsError(
            f"기존 병합 파일을 보호하기 위해 중단합니다: {output}"
        )

    driver = create_driver()

    results = {}

    try:
        for page in ("Basic1", "Basic2"):
            all_records = {}

            for team_code in TEAM_CODES:
                team_records = collect_team(
                    driver,
                    args.season,
                    team_code,
                    page=page,
                )

                print(
                    f"[{page}] {team_code}: "
                    f"{len(team_records)}명"
                )

                for record in team_records:
                    key = (
                        record["team_code"],
                        record["player_id"],
                    )

                    if key in all_records:
                        raise RuntimeError(
                            f"{page}: 중복 선수 기록 {key}"
                        )

                    all_records[key] = record

            results[page] = all_records

    finally:
        driver.quit()
    
    basic1 = results["Basic1"]
    basic2 = results["Basic2"]

    merged = []

    missing_tbf = []

    for key, record in basic1.items():
        detail = basic2.get(key)

        if detail is None or not detail.get("TBF"):
            missing_tbf.append(key)
            continue

        try:
            games = int(record["G"].replace(",", ""))
            walks = int(record["BB"].replace(",", ""))
            strikeouts = int(record["SO"].replace(",", ""))
            batters_faced = int(detail["TBF"].replace(",", ""))
        except (ValueError, KeyError) as error:
            raise ValueError(
                f"선수 기록 숫자 변환 실패: {key}"
            ) from error

        if batters_faced <= 0:
            missing_tbf.append(key)
            continue

        merged.append({
            "player_id": record["player_id"],
            "player_name": record["선수명"],
            "team_code": record["team_code"],
            "games": games,
            "batters_faced": batters_faced,
            "walks": walks,
            "strikeouts": strikeouts,
            "k_pct": round(
                strikeouts / batters_faced * 100, 2
            ),
            "bb_pct": round(
                walks / batters_faced * 100, 2
            ),
            "k_minus_bb_pct": round(
                (strikeouts - walks) / batters_faced * 100, 2
            ),
        })

    if missing_tbf:
        raise RuntimeError(
            f"TBF 병합에 실패한 선수: {missing_tbf[:20]} "
            f"(총 {len(missing_tbf)}명)"
        )

    print(f"병합 성공: {len(merged)}명")

    result = {
        "season": args.season,
        "season_type": "REGULAR",
        "source": "KBO_RECORD_ROOM_BASIC1_BASIC2",
        "collected_at": datetime.now().isoformat(),
        "records": merged,
    }

    output = OUTPUT_DIR / (
        f"kbo_official_pitchers_merged_{args.season}.json"
    )

    output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n총 병합 선수 기록: {len(merged)}명")
    print(f"저장 완료: {output}")


if __name__ == "__main__":
    main()