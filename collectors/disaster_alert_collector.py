"""
SafeNavi 긴급재난문자 수집기

주요 기능
1. 행정안전부 긴급재난문자 API 호출
2. 최근 N일 데이터를 날짜별·페이지별로 수집
3. API 원본 컬럼을 SafeNavi 공통 컬럼으로 정규화
4. 기존 CSV와 신규 데이터를 병합
5. 중복 제거 후 원자적으로 파일 저장
6. API 오류나 빈 응답 발생 시 기존 데이터를 보호
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_OUTPUT_PATH = BASE_DIR / "data" / "raw" / "disaster_alerts_raw.csv"
PROCESSED_OUTPUT_PATH = (
    BASE_DIR / "data" / "processed" / "disaster_alerts.csv"
)

DEFAULT_NUM_ROWS = 100
DEFAULT_MAX_PAGES = 10


def get_env_value(name: str) -> str | None:
    """환경변수를 읽고 앞뒤 공백을 제거한다."""
    value = os.getenv(name)

    if value is None:
        return None

    value = value.strip()
    return value or None


def get_positive_int_env(name: str, default: int) -> int:
    """양의 정수 환경변수를 안전하게 읽는다."""
    value = get_env_value(name)

    if value is None:
        return default

    try:
        number = int(value)
        return number if number > 0 else default
    except (TypeError, ValueError):
        return default


def mask_key(key: str | None) -> str:
    """로그에 API 키 전체가 노출되지 않도록 일부만 표시한다."""
    if not key:
        return "없음"

    if len(key) <= 10:
        return "***"

    return f"{key[:5]}...{key[-5:]}"


def safe_read_csv(path: Path) -> pd.DataFrame:
    """CSV가 없거나 손상된 경우 빈 DataFrame을 반환한다."""
    if not path.exists():
        return pd.DataFrame()

    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
        except Exception as error:
            print(f"[긴급재난문자] CSV 읽기 오류: {path} / {error}")
            return pd.DataFrame()

    return pd.DataFrame()


def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """
    임시 파일에 먼저 저장한 후 교체한다.
    저장 중 장애가 발생해 기존 파일이 깨지는 것을 방지한다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    df.to_csv(temp_path, index=False, encoding="utf-8-sig")
    os.replace(temp_path, path)


def request_with_retry(
    url: str,
    params: dict[str, Any],
    max_retries: int = 3,
    timeout: int = 30,
) -> requests.Response:
    """연결 오류·시간 초과·일시적 서버 오류에 재시도한다."""
    headers = {
        "User-Agent": "SafeNavi/1.0",
        "Accept": "application/json, text/plain, */*",
        "Connection": "close",
    }

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            print(
                "[긴급재난문자] API 요청 "
                f"{attempt}/{max_retries}, page={params.get('pageNo')}"
            )

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            )

            print(
                "[긴급재난문자] HTTP 상태코드: "
                f"{response.status_code}"
            )

            # 429 및 5xx는 일시 오류일 수 있으므로 재시도한다.
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()

            response.raise_for_status()
            return response

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError,
        ) as error:
            last_error = error

            retryable = (
                isinstance(
                    error,
                    (
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                    ),
                )
                or getattr(error.response, "status_code", 0) == 429
                or getattr(error.response, "status_code", 0) >= 500
            )

            print(f"[긴급재난문자] 요청 오류: {error}")

            if not retryable or attempt >= max_retries:
                break

            wait_seconds = min(2 ** attempt, 10)
            print(
                f"[긴급재난문자] {wait_seconds}초 후 재시도합니다."
            )
            time.sleep(wait_seconds)

    if last_error is not None:
        raise last_error

    raise RuntimeError("긴급재난문자 API 요청에 실패했습니다.")


def parse_response_to_json(response: requests.Response) -> Any:
    """API 응답을 JSON으로 변환한다."""
    try:
        return response.json()
    except Exception as error:
        preview = response.text[:1000]
        raise ValueError(
            "긴급재난문자 API 응답이 JSON 형식이 아닙니다.\n"
            f"응답 일부: {preview}"
        ) from error


def check_api_error(data: Any) -> None:
    """공공 API의 결과코드와 오류 메시지를 검사한다."""
    if not isinstance(data, dict):
        return

    response_data = data.get("response")
    response_header = (
        response_data.get("header", {})
        if isinstance(response_data, dict)
        else {}
    )
    header = data.get("header") or response_header or {}

    result_code = str(
        header.get("resultCode")
        or data.get("resultCode")
        or ""
    ).strip()

    result_msg = str(
        header.get("resultMsg")
        or header.get("errorMsg")
        or data.get("resultMsg")
        or data.get("errorMsg")
        or ""
    ).strip()

    if not result_code:
        return

    normal_codes = {
        "00",
        "0",
        "NORMAL_CODE",
        "NORMAL_SERVICE",
        "SUCCESS",
    }

    if result_code in normal_codes:
        return

    if result_code == "30":
        raise ValueError(
            "긴급재난문자 API 인증키 오류입니다. "
            "DISASTER_SERVICE_KEY와 API 활용승인 상태를 확인하세요."
        )

    raise ValueError(
        "긴급재난문자 API 오류: "
        f"resultCode={result_code}, message={result_msg}"
    )


def _walk_path(data: Any, path: list[str]) -> Any:
    current = data

    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def extract_items_from_response(data: Any) -> list[dict[str, Any]]:
    """여러 형태의 공공 API 응답에서 실제 목록을 추출한다."""
    possible_paths = [
        ["body"],
        ["data"],
        ["items"],
        ["item"],
        ["result"],
        ["list"],
        ["response", "body", "items", "item"],
        ["response", "body", "items"],
        ["response", "body"],
    ]

    for path in possible_paths:
        current = _walk_path(data, path)

        if isinstance(current, list):
            return [
                item
                for item in current
                if isinstance(item, dict)
            ]

        if isinstance(current, dict):
            # items 안에 item이 한 번 더 들어간 구조를 처리한다.
            nested_item = current.get("item")

            if isinstance(nested_item, list):
                return [
                    item
                    for item in nested_item
                    if isinstance(item, dict)
                ]

            if isinstance(nested_item, dict):
                return [nested_item]

            # 본문 dict 자체가 한 건의 데이터인 경우
            if any(
                key in current
                for key in (
                    "MSG_CN",
                    "msgCn",
                    "message",
                    "RCPTN_RGN_NM",
                )
            ):
                return [current]

    if isinstance(data, list):
        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    return []


def extract_total_count(data: Any) -> int | None:
    """응답에서 전체 건수를 찾는다."""
    candidates = [
        data.get("totalCount") if isinstance(data, dict) else None,
        _walk_path(data, ["body", "totalCount"]),
        _walk_path(data, ["response", "body", "totalCount"]),
    ]

    for value in candidates:
        try:
            if value is not None and str(value).strip() != "":
                return int(value)
        except (TypeError, ValueError):
            continue

    return None


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    """후보 컬럼 중 실제 존재하는 첫 번째 컬럼을 찾는다."""
    normalized_map = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:
        actual = normalized_map.get(candidate.strip().lower())

        if actual is not None:
            return actual

    return None


def fetch_disaster_alerts(
    target_date: str | None = None,
    num_rows: int = DEFAULT_NUM_ROWS,
    page_no: int = 1,
    region_name: str | None = None,
) -> tuple[pd.DataFrame, int | None]:
    """특정 날짜·페이지의 긴급재난문자를 조회한다."""
    service_key = get_env_value("DISASTER_SERVICE_KEY")
    api_url = get_env_value("DISASTER_ALERT_API_URL")

    if not service_key:
        raise ValueError(
            "DISASTER_SERVICE_KEY 환경변수가 설정되지 않았습니다."
        )

    if not api_url:
        raise ValueError(
            "DISASTER_ALERT_API_URL 환경변수가 설정되지 않았습니다."
        )

    if not api_url.startswith(("http://", "https://")):
        raise ValueError(
            "DISASTER_ALERT_API_URL은 http:// 또는 https://로 "
            "시작해야 합니다."
        )

    if target_date is None:
        target_date = datetime.now().strftime("%Y%m%d")

    params: dict[str, Any] = {
        "serviceKey": service_key,
        "numOfRows": num_rows,
        "pageNo": page_no,
        "returnType": "json",
        "crtDt": target_date,
    }

    if region_name:
        params["rgnNm"] = region_name

    print("======================================")
    print("[긴급재난문자] API 호출")
    print(f"URL: {api_url}")
    print(f"서비스키: {mask_key(service_key)}")
    print(f"조회일자: {target_date}")
    print(f"페이지: {page_no}")
    print(f"지역: {region_name or '전체'}")
    print("======================================")

    response = request_with_retry(api_url, params=params)
    data = parse_response_to_json(response)
    check_api_error(data)

    items = extract_items_from_response(data)
    total_count = extract_total_count(data)

    if not items:
        return pd.DataFrame(), total_count

    raw_df = pd.DataFrame(items)

    print(
        "[긴급재난문자] 조회 건수: "
        f"{len(raw_df):,}, totalCount={total_count}"
    )

    return raw_df, total_count


def fetch_disaster_alerts_for_date(
    target_date: str,
    num_rows: int = DEFAULT_NUM_ROWS,
    max_pages: int = DEFAULT_MAX_PAGES,
    region_name: str | None = None,
) -> pd.DataFrame:
    """한 날짜의 데이터를 페이지 끝까지 수집한다."""
    frames: list[pd.DataFrame] = []
    total_count: int | None = None

    for page_no in range(1, max_pages + 1):
        page_df, page_total = fetch_disaster_alerts(
            target_date=target_date,
            num_rows=num_rows,
            page_no=page_no,
            region_name=region_name,
        )

        if total_count is None:
            total_count = page_total

        if page_df.empty:
            break

        frames.append(page_df)

        fetched_count = sum(len(frame) for frame in frames)

        if len(page_df) < num_rows:
            break

        if total_count is not None and fetched_count >= total_count:
            break

        # 공공 API에 과도한 연속 요청을 보내지 않도록 짧게 대기한다.
        time.sleep(0.15)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True).drop_duplicates()


def fetch_disaster_alerts_recent_days(
    days: int = 2,
    num_rows: int = DEFAULT_NUM_ROWS,
    max_pages: int = DEFAULT_MAX_PAGES,
    region_name: str | None = None,
) -> pd.DataFrame:
    """최근 N일의 데이터를 날짜별로 수집한다."""
    if days < 1:
        raise ValueError("days는 1 이상의 정수여야 합니다.")

    frames: list[pd.DataFrame] = []
    failed_dates: list[str] = []

    for offset in range(days):
        target_date = (
            datetime.now() - timedelta(days=offset)
        ).strftime("%Y%m%d")

        print(f"[긴급재난문자] {target_date} 조회 시작")

        try:
            day_df = fetch_disaster_alerts_for_date(
                target_date=target_date,
                num_rows=num_rows,
                max_pages=max_pages,
                region_name=region_name,
            )

            if not day_df.empty:
                frames.append(day_df)

        except Exception as error:
            failed_dates.append(target_date)
            print(
                f"[긴급재난문자] {target_date} 조회 실패: {error}"
            )

    if not frames:
        failed_text = ", ".join(failed_dates) or "없음"
        raise RuntimeError(
            "최근 긴급재난문자를 한 건도 수집하지 못했습니다. "
            f"실패 날짜: {failed_text}"
        )

    merged = pd.concat(frames, ignore_index=True)
    return merged.drop_duplicates()


def normalize_disaster_alerts(
    raw_df: pd.DataFrame,
) -> pd.DataFrame:
    """API 원본 데이터를 SafeNavi 공통 컬럼으로 변환한다."""
    columns = [
        "alert_id",
        "created_at",
        "region",
        "message",
        "emergency_level",
        "disaster_category",
    ]

    if raw_df.empty:
        return pd.DataFrame(columns=columns)

    col_id = find_column(
        raw_df,
        [
            "SN",
            "sn",
            "MD101_SN",
            "md101Sn",
            "alert_id",
            "일련번호",
        ],
    )
    col_created = find_column(
        raw_df,
        [
            "CRT_DT",
            "crtDt",
            "CREAT_DT",
            "creatDt",
            "created_at",
            "REG_YMD",
            "regYmd",
            "생성일시",
            "등록일시",
        ],
    )
    col_region = find_column(
        raw_df,
        [
            "RCPTN_RGN_NM",
            "rcptnRgnNm",
            "RCPTN_RGN",
            "rcptnRgn",
            "RCPNT_RGN_NM",
            "rcpntRgnNm",
            "region",
            "수신지역",
            "지역",
        ],
    )
    col_message = find_column(
        raw_df,
        [
            "MSG_CN",
            "msgCn",
            "MSG_CNTS",
            "msgCnts",
            "message",
            "메시지내용",
            "재난문자내용",
            "내용",
        ],
    )
    col_level = find_column(
        raw_df,
        [
            "EMRG_STEP_NM",
            "emrgStepNm",
            "emergency_level",
            "긴급단계명",
        ],
    )
    col_category = find_column(
        raw_df,
        [
            "DST_SE_NM",
            "dstSeNm",
            "DSSTR_SE_NM",
            "dsstrSeNm",
            "disaster_category",
            "재해구분명",
            "재난구분명",
        ],
    )

    result = pd.DataFrame(index=raw_df.index)

    if col_id:
        result["alert_id"] = raw_df[col_id]
    else:
        # ID가 없는 API 응답은 이후 메시지·시각·지역 조합으로 중복 제거한다.
        result["alert_id"] = ""

    result["created_at"] = (
        raw_df[col_created] if col_created else ""
    )
    result["region"] = (
        raw_df[col_region] if col_region else "지역 미확인"
    )
    result["message"] = (
        raw_df[col_message] if col_message else ""
    )
    result["emergency_level"] = (
        raw_df[col_level] if col_level else ""
    )
    result["disaster_category"] = (
        raw_df[col_category] if col_category else ""
    )

    for column in columns:
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    result.loc[
        result["region"].eq(""),
        "region",
    ] = "지역 미확인"

    result = result[result["message"].ne("")].copy()

    # 정렬을 위해 파싱 가능한 시간 컬럼을 임시 생성한다.
    parsed_time = pd.to_datetime(
        result["created_at"],
        errors="coerce",
    )
    result["_parsed_time"] = parsed_time

    result = deduplicate_alerts(result)
    result = result.sort_values(
        by="_parsed_time",
        ascending=False,
        na_position="last",
    ).drop(columns=["_parsed_time"], errors="ignore")

    return result[columns].reset_index(drop=True)


def deduplicate_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """문자 ID 또는 시각·지역·내용 조합으로 중복을 제거한다."""
    if df.empty:
        return df

    result = df.copy()

    for column in ("alert_id", "created_at", "region", "message"):
        if column not in result.columns:
            result[column] = ""
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    has_id = result["alert_id"].ne("")
    with_id = result[has_id].drop_duplicates(
        subset=["alert_id"],
        keep="last",
    )
    without_id = result[~has_id].drop_duplicates(
        subset=["created_at", "region", "message"],
        keep="last",
    )

    result = pd.concat(
        [with_id, without_id],
        ignore_index=True,
        sort=False,
    )

    return result.drop_duplicates(
        subset=["created_at", "region", "message"],
        keep="last",
    )


def merge_processed_alerts(
    existing_df: pd.DataFrame,
    new_df: pd.DataFrame,
    retention_days: int = 30,
) -> pd.DataFrame:
    """기존 데이터와 신규 데이터를 합치고 보관기간을 적용한다."""
    if existing_df.empty:
        merged = new_df.copy()
    elif new_df.empty:
        merged = existing_df.copy()
    else:
        merged = pd.concat(
            [existing_df, new_df],
            ignore_index=True,
            sort=False,
        )

    expected_columns = [
        "alert_id",
        "created_at",
        "region",
        "message",
        "emergency_level",
        "disaster_category",
    ]

    for column in expected_columns:
        if column not in merged.columns:
            merged[column] = ""

    merged = deduplicate_alerts(merged)

    parsed_time = pd.to_datetime(
        merged["created_at"],
        errors="coerce",
    )

    if retention_days > 0 and parsed_time.notna().any():
        cutoff = pd.Timestamp.now() - pd.Timedelta(
            days=retention_days
        )

        # 날짜 파싱이 안 되는 기존 데이터는 보존한다.
        keep_mask = parsed_time.isna() | parsed_time.ge(cutoff)
        merged = merged.loc[keep_mask].copy()
        parsed_time = parsed_time.loc[keep_mask]

    merged["_parsed_time"] = parsed_time
    merged = merged.sort_values(
        "_parsed_time",
        ascending=False,
        na_position="last",
    )
    merged = merged.drop(
        columns=["_parsed_time"],
        errors="ignore",
    )

    return merged[expected_columns].reset_index(drop=True)


def save_disaster_alerts(
    days: int = 2,
    region_name: str | None = None,
    save_empty: bool = False,
    merge_existing: bool = True,
    retention_days: int | None = None,
) -> pd.DataFrame:
    """
    최근 긴급재난문자를 수집하고 기존 파일과 안전하게 병합한다.

    API가 비어 있거나 실패한 경우 기존 CSV를 빈 파일로 덮어쓰지 않는다.
    """
    retention_days = retention_days or get_positive_int_env(
        "DISASTER_RETENTION_DAYS",
        30,
    )
    num_rows = get_positive_int_env(
        "DISASTER_NUM_ROWS",
        DEFAULT_NUM_ROWS,
    )
    max_pages = get_positive_int_env(
        "DISASTER_MAX_PAGES",
        DEFAULT_MAX_PAGES,
    )

    RAW_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_df = fetch_disaster_alerts_recent_days(
        days=days,
        num_rows=num_rows,
        max_pages=max_pages,
        region_name=region_name,
    )

    if raw_df.empty:
        existing = safe_read_csv(PROCESSED_OUTPUT_PATH)

        if not existing.empty:
            print(
                "[긴급재난문자] 신규 데이터가 없어 기존 파일을 유지합니다."
            )
            return existing

        if save_empty:
            empty_df = normalize_disaster_alerts(pd.DataFrame())
            atomic_write_csv(empty_df, PROCESSED_OUTPUT_PATH)
            return empty_df

        raise RuntimeError("수집된 긴급재난문자가 없습니다.")

    atomic_write_csv(raw_df, RAW_OUTPUT_PATH)

    new_processed_df = normalize_disaster_alerts(raw_df)
    existing_processed_df = (
        safe_read_csv(PROCESSED_OUTPUT_PATH)
        if merge_existing
        else pd.DataFrame()
    )

    final_df = merge_processed_alerts(
        existing_processed_df,
        new_processed_df,
        retention_days=retention_days,
    )

    if final_df.empty and not save_empty:
        raise RuntimeError(
            "정규화 후 저장할 긴급재난문자가 없습니다."
        )

    atomic_write_csv(final_df, PROCESSED_OUTPUT_PATH)

    print(
        "[긴급재난문자] 업데이트 완료: "
        f"신규 {len(new_processed_df):,}건, "
        f"최종 {len(final_df):,}건"
    )
    print(f"[긴급재난문자] 저장 위치: {PROCESSED_OUTPUT_PATH}")

    return final_df


if __name__ == "__main__":
    update_days = get_positive_int_env(
        "DISASTER_UPDATE_DAYS",
        2,
    )

    save_disaster_alerts(
        days=update_days,
        region_name=None,
        save_empty=False,
        merge_existing=True,
    )
