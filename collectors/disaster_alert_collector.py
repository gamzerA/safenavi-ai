import os
import time
from datetime import datetime, timedelta

import requests
import pandas as pd
from dotenv import load_dotenv


load_dotenv()


RAW_OUTPUT_PATH = "data/raw/disaster_alerts_raw.csv"
PROCESSED_OUTPUT_PATH = "data/processed/disaster_alerts.csv"


def get_env_value(name):
    """
    .env 파일에서 값을 가져오고 앞뒤 공백을 제거한다.
    """
    value = os.getenv(name)

    if value is None:
        return None

    return value.strip()


def mask_key(key):
    """
    인증키를 출력할 때 전체가 노출되지 않도록 일부만 보여준다.
    """
    if not key:
        return "없음"

    if len(key) <= 10:
        return "***"

    return key[:5] + "..." + key[-5:]


def request_with_retry(url, params, max_retries=3, timeout=30):
    """
    API 요청 중 연결이 끊기거나 시간이 초과되면 재시도한다.
    """

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Connection": "close"
    }

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[긴급재난문자] API 요청 시도 {attempt}/{max_retries}")

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout
            )

            print(f"[긴급재난문자] HTTP 상태코드: {response.status_code}")

            response.raise_for_status()
            return response

        except requests.exceptions.ConnectionError as e:
            last_error = e
            print(f"[긴급재난문자] 연결 오류 발생: {e}")
            print("[긴급재난문자] 3초 후 재시도합니다.")
            time.sleep(3)

        except requests.exceptions.Timeout as e:
            last_error = e
            print(f"[긴급재난문자] 시간 초과 발생: {e}")
            print("[긴급재난문자] 3초 후 재시도합니다.")
            time.sleep(3)

        except requests.exceptions.HTTPError as e:
            last_error = e
            print(f"[긴급재난문자] HTTP 오류 발생: {e}")
            break

    raise last_error


def extract_items_from_response(data):
    """
    긴급재난문자 API 응답 구조에서 실제 데이터 목록을 추출한다.
    """

    possible_paths = [
        ["body"],
        ["data"],
        ["items"],
        ["item"],
        ["response", "body", "items", "item"],
        ["response", "body", "items"],
        ["response", "body"],
        ["result"],
        ["list"],
    ]

    for path in possible_paths:
        current = data

        try:
            for key in path:
                current = current[key]

            if isinstance(current, list):
                return current

            if isinstance(current, dict):
                return [current]

        except (KeyError, TypeError):
            continue

    if isinstance(data, list):
        return data

    return []


def find_column(df, candidates):
    """
    후보 컬럼명 중 실제 DataFrame에 존재하는 컬럼명을 찾는다.
    """
    for col in candidates:
        if col in df.columns:
            return col

    return None


def check_api_error(data):
    """
    API 응답의 오류 메시지를 확인한다.
    """

    if not isinstance(data, dict):
        return

    header = data.get("header") or data.get("response", {}).get("header", {})

    result_code = str(header.get("resultCode", "")).strip()
    result_msg = str(header.get("resultMsg", "")).strip()
    error_msg = str(header.get("errorMsg", "")).strip()

    if not result_code:
        return

    if result_code in ["00", "0", "NORMAL_CODE", "NORMAL_SERVICE"]:
        return

    if result_code == "30":
        raise ValueError(
            "긴급재난문자 API 인증키 오류입니다.\n"
            "resultCode: 30\n"
            "원인: 등록되지 않은 서비스키입니다.\n"
            "확인할 것:\n"
            "1. DISASTER_SERVICE_KEY에 긴급재난문자 API용 인증키를 넣었는지 확인\n"
            "2. 기상특보/생활기상지수 인증키를 잘못 넣지 않았는지 확인\n"
            "3. 긴급재난문자 API 활용신청이 승인 상태인지 확인"
        )

    raise ValueError(
        f"긴급재난문자 API 오류 발생\n"
        f"resultCode: {result_code}\n"
        f"resultMsg: {result_msg}\n"
        f"errorMsg: {error_msg}"
    )


def parse_response_to_json(response):
    """
    API 응답을 JSON으로 변환한다.
    JSON이 아니면 원문 일부를 출력하고 빈 dict를 반환한다.
    """

    try:
        return response.json()
    except Exception:
        print("[긴급재난문자] JSON 변환 실패")
        print("[긴급재난문자] 응답 원문 일부:")
        print(response.text[:1000])
        return {}


def fetch_disaster_alerts(
    target_date=None,
    num_rows=100,
    page_no=1,
    region_name=None
):
    """
    긴급재난문자 API를 호출한다.

    기본 설정:
    - 지역 조건 없이 전체 재난문자 조회
    - 특정 지역을 넣고 싶을 때만 region_name 사용

    Parameters
    ----------
    target_date : str | None
        YYYYMMDD 형식. None이면 오늘 날짜 사용.
    num_rows : int
        한 번에 가져올 행 수
    page_no : int
        페이지 번호
    region_name : str | None
        지역명. None이면 지역 조건 없이 전체 조회.

    Returns
    -------
    pandas.DataFrame
        API 원본 데이터
    """

    service_key = get_env_value("DISASTER_SERVICE_KEY")
    api_url = get_env_value("DISASTER_ALERT_API_URL")

    if not service_key:
        raise ValueError(".env에 DISASTER_SERVICE_KEY가 없습니다.")

    if not api_url:
        raise ValueError(".env에 DISASTER_ALERT_API_URL이 없습니다.")

    if not api_url.startswith("http"):
        raise ValueError(
            "DISASTER_ALERT_API_URL은 http 또는 https로 시작해야 합니다.\n"
            "예: https://www.safetydata.go.kr/V2/api/DSSP-IF-00247"
        )

    if target_date is None:
        target_date = datetime.now().strftime("%Y%m%d")

    print("======================================")
    print("[긴급재난문자] API 호출 정보")
    print("======================================")
    print(f"URL: {api_url}")
    print(f"서비스키: {mask_key(service_key)}")
    print(f"조회일자: {target_date}")

    if region_name:
        print(f"조회지역: {region_name}")
    else:
        print("조회지역: 전체 조회")
    print("======================================")

    # 핵심 수정 부분:
    # rgnNm을 기본적으로 넣지 않는다.
    params = {
        "serviceKey": service_key,
        "numOfRows": num_rows,
        "pageNo": page_no,
        "returnType": "json",
        "crtDt": target_date
    }

    # 필요할 때만 지역 조건 추가
    if region_name:
        params["rgnNm"] = region_name

    response = request_with_retry(api_url, params=params)

    data = parse_response_to_json(response)

    if not data:
        return pd.DataFrame()

    check_api_error(data)

    total_count = data.get("totalCount", None)
    if total_count is not None:
        print(f"[긴급재난문자] totalCount: {total_count}")

    items = extract_items_from_response(data)

    if not items:
        print("[긴급재난문자] 조회 결과가 없습니다.")
        print("[긴급재난문자] 응답 일부:")
        print(str(data)[:1000])
        return pd.DataFrame()

    raw_df = pd.DataFrame(items)

    print(f"[긴급재난문자] 원본 데이터 수: {len(raw_df):,}개")
    print(f"[긴급재난문자] 원본 컬럼: {list(raw_df.columns)}")

    return raw_df


def fetch_disaster_alerts_recent_days(
    days=7,
    num_rows=100,
    region_name=None
):
    """
    최근 N일간의 긴급재난문자를 날짜별로 호출해서 합친다.

    기본값:
    - region_name=None
    - 지역 조건 없이 전체 조회
    """

    all_dataframes = []

    for i in range(days):
        target_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")

        print()
        print(f"[긴급재난문자] {target_date} 데이터 조회 시작")

        try:
            df = fetch_disaster_alerts(
                target_date=target_date,
                num_rows=num_rows,
                page_no=1,
                region_name=region_name
            )

            if not df.empty:
                all_dataframes.append(df)

        except Exception as e:
            print(f"[긴급재난문자] {target_date} 조회 실패: {e}")

    if not all_dataframes:
        return pd.DataFrame()

    merged_df = pd.concat(all_dataframes, ignore_index=True)
    merged_df = merged_df.drop_duplicates()

    return merged_df


def normalize_disaster_alerts(raw_df):
    """
    긴급재난문자 원본 데이터를 SafeNavi 서비스용 컬럼으로 변환한다.

    최종 저장 컬럼:
    - alert_id
    - created_at
    - region
    - message
    - emergency_level
    - disaster_category
    """

    columns = [
        "alert_id",
        "created_at",
        "region",
        "message",
        "emergency_level",
        "disaster_category"
    ]

    if raw_df.empty:
        return pd.DataFrame(columns=columns)

    col_id = find_column(
        raw_df,
        ["SN", "sn", "MD101_SN", "md101Sn", "alert_id", "일련번호"]
    )

    col_created = find_column(
        raw_df,
        [
            "CRT_DT", "crtDt",
            "CREAT_DT", "creatDt",
            "created_at",
            "REG_YMD", "regYmd",
            "생성일시", "등록일시"
        ]
    )

    col_region = find_column(
        raw_df,
        [
            "RCPTN_RGN_NM", "rcptnRgnNm",
            "RCPTN_RGN", "rcptnRgn",
            "RCPNT_RGN_NM", "rcpntRgnNm",
            "region",
            "수신지역", "지역"
        ]
    )

    col_message = find_column(
        raw_df,
        [
            "MSG_CN", "msgCn",
            "MSG_CNTS", "msgCnts",
            "message",
            "메시지내용",
            "재난문자내용",
            "내용"
        ]
    )

    col_level = find_column(
        raw_df,
        [
            "EMRG_STEP_NM", "emrgStepNm",
            "emergency_level",
            "긴급단계명"
        ]
    )

    col_category = find_column(
        raw_df,
        [
            "DST_SE_NM", "dstSeNm",
            "DSSTR_SE_NM", "dsstrSeNm",
            "disaster_category",
            "재해구분명",
            "재난구분명"
        ]
    )

    result = pd.DataFrame()

    result["alert_id"] = raw_df[col_id] if col_id else range(1, len(raw_df) + 1)
    result["created_at"] = raw_df[col_created] if col_created else ""
    result["region"] = raw_df[col_region] if col_region else "지역 미확인"
    result["message"] = raw_df[col_message] if col_message else ""
    result["emergency_level"] = raw_df[col_level] if col_level else ""
    result["disaster_category"] = raw_df[col_category] if col_category else ""

    result["region"] = result["region"].fillna("지역 미확인").astype(str)
    result["message"] = result["message"].fillna("").astype(str)
    result["created_at"] = result["created_at"].fillna("").astype(str)
    result["emergency_level"] = result["emergency_level"].fillna("").astype(str)
    result["disaster_category"] = result["disaster_category"].fillna("").astype(str)

    # message가 완전히 비어 있는 행은 제거
    result = result[result["message"].str.strip() != ""]

    return result[columns]


def save_disaster_alerts(
    days=7,
    region_name=None,
    save_empty=True
):
    """
    최근 N일치 긴급재난문자 API 호출 후 raw/processed 파일 저장.

    기본값:
    - 지역 조건 없이 전체 조회
    - 최근 7일 조회
    """

    os.makedirs("data/raw", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    raw_df = fetch_disaster_alerts_recent_days(
        days=days,
        num_rows=100,
        region_name=region_name
    )

    if not raw_df.empty:
        raw_df.to_csv(RAW_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        print()
        print(f"[긴급재난문자] 원본 저장 완료: {RAW_OUTPUT_PATH}")
        print(f"[긴급재난문자] 원본 행 수: {len(raw_df):,}개")

    processed_df = normalize_disaster_alerts(raw_df)

    if not processed_df.empty or save_empty:
        processed_df.to_csv(PROCESSED_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        print()
        print(f"[긴급재난문자] 서비스용 저장 완료: {PROCESSED_OUTPUT_PATH}")
        print(f"[긴급재난문자] 서비스용 행 수: {len(processed_df):,}개")

    if not processed_df.empty:
        print()
        print("[긴급재난문자] 서비스용 컬럼")
        print(list(processed_df.columns))

        print()
        print("[긴급재난문자] 미리보기")
        print(processed_df.head(5))

        print()
        print("[긴급재난문자] 지역별 개수")
        print(processed_df["region"].value_counts().head(10))

    else:
        print()
        print("[긴급재난문자] 저장된 데이터가 없습니다.")
        print("가능한 원인:")
        print("1. 최근 조회 기간에 전체 재난문자가 없음")
        print("2. API 파라미터명이 문서와 다름")
        print("3. 인증키 또는 활용신청 상태 문제")
        print("4. API 서버 연결 차단 또는 일시 장애")

    return processed_df


if __name__ == "__main__":
    # 지역 조건 없이 최근 7일 전체 긴급재난문자 조회
    save_disaster_alerts(
        days=7,
        region_name=None
    )