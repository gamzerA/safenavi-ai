import os
import time
from datetime import datetime

import requests
import pandas as pd
from dotenv import load_dotenv


load_dotenv()


RAW_OUTPUT_PATH = "data/raw/living_weather_raw.csv"
PROCESSED_OUTPUT_PATH = "data/processed/living_weather.csv"


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
    인증키가 전체 노출되지 않도록 일부만 표시한다.
    """
    if not key:
        return "없음"

    if len(key) <= 10:
        return "***"

    return key[:5] + "..." + key[-5:]


def get_latest_base_time():
    """
    생활기상지수 API 요청용 time 값을 만든다.
    형식: YYYYMMDDHH

    생활기상지수는 보통 3시간 단위 예측값을 사용하므로
    현재 시간을 3시간 단위로 내림 처리한다.
    """

    now = datetime.now()
    hour = now.hour

    base_hour = (hour // 3) * 3

    return now.strftime("%Y%m%d") + f"{base_hour:02d}"


def request_with_retry(url, params, max_retries=3, timeout=30):
    """
    API 요청 중 연결 오류나 시간 초과가 발생하면 재시도한다.
    """

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Connection": "close"
    }

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[생활기상지수] API 요청 시도 {attempt}/{max_retries}")

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout
            )

            print(f"[생활기상지수] HTTP 상태코드: {response.status_code}")

            response.raise_for_status()
            return response

        except requests.exceptions.ConnectionError as e:
            last_error = e
            print(f"[생활기상지수] 연결 오류 발생: {e}")
            print("[생활기상지수] 3초 후 재시도합니다.")
            time.sleep(3)

        except requests.exceptions.Timeout as e:
            last_error = e
            print(f"[생활기상지수] 시간 초과 발생: {e}")
            print("[생활기상지수] 3초 후 재시도합니다.")
            time.sleep(3)

        except requests.exceptions.HTTPError as e:
            last_error = e
            print(f"[생활기상지수] HTTP 오류 발생: {e}")
            break

    raise last_error


def parse_response_to_json(response):
    """
    응답을 JSON으로 변환한다.
    """

    try:
        return response.json()
    except Exception:
        print("[생활기상지수] JSON 변환 실패")
        print("[생활기상지수] 응답 원문 일부:")
        print(response.text[:1000])
        return {}


def check_living_weather_api_error(data):
    """
    생활기상지수 API 응답 상태를 확인한다.
    """

    if not isinstance(data, dict):
        return "OK"

    header = data.get("response", {}).get("header", {})

    result_code = str(header.get("resultCode", "")).strip()
    result_msg = str(header.get("resultMsg", "")).strip()

    if result_code in ["00", "0", "NORMAL_SERVICE", "NORMAL_CODE", ""]:
        return "OK"

    if result_code == "03":
        return "NO_DATA"

    raise ValueError(
        f"생활기상지수 API 오류 발생\n"
        f"resultCode: {result_code}\n"
        f"resultMsg: {result_msg}"
    )


def extract_items_from_response(data):
    """
    생활기상지수 API 응답에서 item 목록을 추출한다.
    """

    try:
        items = data["response"]["body"]["items"]["item"]

        if isinstance(items, list):
            return items

        if isinstance(items, dict):
            return [items]

    except (KeyError, TypeError):
        pass

    return []


def fetch_living_weather_index(
    index_type,
    endpoint,
    area_no="4146355000",
    time_value=None,
    num_rows=10,
    page_no=1
):
    """
    생활기상지수 API를 호출한다.

    Parameters
    ----------
    index_type : str
        지수 이름. 예: 자외선지수, 대기정체지수
    endpoint : str
        API 상세 기능명. 예: getUVIdxV5, getAirDiffusionIdxV5
    area_no : str
        지역 코드
    time_value : str | None
        YYYYMMDDHH 형식
    """

    service_key = get_env_value("LIVING_WEATHER_SERVICE_KEY")
    base_url = get_env_value("LIVING_WEATHER_BASE_URL")

    if not service_key:
        raise ValueError(".env에 LIVING_WEATHER_SERVICE_KEY가 없습니다.")

    if not base_url:
        raise ValueError(".env에 LIVING_WEATHER_BASE_URL이 없습니다.")

    if not base_url.startswith("http"):
        raise ValueError(
            "LIVING_WEATHER_BASE_URL은 http 또는 https로 시작해야 합니다.\n"
            "예: http://apis.data.go.kr/1360000/LivingWthrIdxServiceV5"
        )

    if time_value is None:
        time_value = get_latest_base_time()

    url = f"{base_url}/{endpoint}"

    params = {
        "ServiceKey": service_key,
        "pageNo": page_no,
        "numOfRows": num_rows,
        "dataType": "JSON",
        "areaNo": area_no,
        "time": time_value
    }

    print("======================================")
    print(f"[생활기상지수] {index_type} API 호출 정보")
    print("======================================")
    print(f"URL: {url}")
    print(f"서비스키: {mask_key(service_key)}")
    print(f"지역코드 areaNo: {area_no}")
    print(f"요청시간 time: {time_value}")
    print("======================================")

    response = request_with_retry(url, params=params)
    data = parse_response_to_json(response)

    if not data:
        return pd.DataFrame()

    status = check_living_weather_api_error(data)

    if status == "NO_DATA":
        print(f"[생활기상지수] {index_type} 조회 결과가 없습니다.")
        print("응답 일부:", str(data)[:1000])
        return pd.DataFrame()

    items = extract_items_from_response(data)

    if not items:
        print(f"[생활기상지수] {index_type} item 데이터가 없습니다.")
        print("응답 일부:", str(data)[:1000])
        return pd.DataFrame()

    df = pd.DataFrame(items)
    df["index_type"] = index_type

    print(f"[생활기상지수] {index_type} 원본 데이터 수: {len(df):,}개")
    print(f"[생활기상지수] {index_type} 원본 컬럼: {list(df.columns)}")

    return df


def normalize_living_weather(raw_df):
    """
    생활기상지수 원본 데이터를 SafeNavi 서비스용 컬럼으로 변환한다.

    최종 저장 컬럼:
    - index_type
    - area_no
    - request_time
    - today_value
    - tomorrow_value
    - after_tomorrow_value
    - raw_values
    """

    columns = [
        "index_type",
        "area_no",
        "request_time",
        "today_value",
        "tomorrow_value",
        "after_tomorrow_value",
        "raw_values"
    ]

    if raw_df.empty:
        return pd.DataFrame(columns=columns)

    result_rows = []

    for _, row in raw_df.iterrows():
        index_type = row.get("index_type", "")
        area_no = row.get("areaNo", row.get("area_no", ""))
        request_time = row.get("date", row.get("time", ""))

        # 생활기상지수 응답은 h0, h3, h6... 또는 today/tomorrow 형태가 섞일 수 있어서
        # 가능한 컬럼을 넓게 탐색한다.
        value_candidates = []

        for col in raw_df.columns:
            if col.lower().startswith("h"):
                value_candidates.append(col)

        # h0, h3, h6 같은 예측 컬럼이 있으면 앞의 값을 오늘 값으로 사용
        today_value = ""
        tomorrow_value = ""
        after_tomorrow_value = ""

        if value_candidates:
            sorted_cols = sorted(
                value_candidates,
                key=lambda x: int("".join(filter(str.isdigit, x)) or 0)
            )

            if len(sorted_cols) >= 1:
                today_value = row.get(sorted_cols[0], "")

            if len(sorted_cols) >= 9:
                tomorrow_value = row.get(sorted_cols[8], "")

            if len(sorted_cols) >= 17:
                after_tomorrow_value = row.get(sorted_cols[16], "")

        # 혹시 다른 컬럼명으로 올 경우 대비
        if today_value == "":
            today_value = row.get("today", row.get("todayValue", row.get("value", "")))

        if tomorrow_value == "":
            tomorrow_value = row.get("tomorrow", row.get("tomorrowValue", ""))

        if after_tomorrow_value == "":
            after_tomorrow_value = row.get("dayaftertomorrow", row.get("afterTomorrowValue", ""))

        raw_values = row.to_dict()

        result_rows.append(
            {
                "index_type": index_type,
                "area_no": area_no,
                "request_time": request_time,
                "today_value": today_value,
                "tomorrow_value": tomorrow_value,
                "after_tomorrow_value": after_tomorrow_value,
                "raw_values": str(raw_values)
            }
        )

    result = pd.DataFrame(result_rows)

    return result[columns]


def save_living_weather(
    area_no="4146355000",
    time_value=None,
    save_empty=True
):
    """
    생활기상지수 API 호출 후 raw/processed 파일 저장.

    현재 수집 지수:
    1. 자외선지수
    2. 대기정체지수
    """

    os.makedirs("data/raw", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    uv_df = fetch_living_weather_index(
        index_type="자외선지수",
        endpoint="getUVIdxV5",
        area_no=area_no,
        time_value=time_value
    )

    air_df = fetch_living_weather_index(
        index_type="대기정체지수",
        endpoint="getAirDiffusionIdxV5",
        area_no=area_no,
        time_value=time_value
    )

    raw_df = pd.concat([uv_df, air_df], ignore_index=True)

    if not raw_df.empty:
        raw_df.to_csv(RAW_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        print()
        print(f"[생활기상지수] 원본 저장 완료: {RAW_OUTPUT_PATH}")
        print(f"[생활기상지수] 원본 행 수: {len(raw_df):,}개")

    processed_df = normalize_living_weather(raw_df)

    if not processed_df.empty or save_empty:
        processed_df.to_csv(PROCESSED_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        print()
        print(f"[생활기상지수] 서비스용 저장 완료: {PROCESSED_OUTPUT_PATH}")
        print(f"[생활기상지수] 서비스용 행 수: {len(processed_df):,}개")

    if not processed_df.empty:
        print()
        print("[생활기상지수] 서비스용 컬럼")
        print(list(processed_df.columns))

        print()
        print("[생활기상지수] 미리보기")
        print(processed_df.head())

    else:
        print()
        print("[생활기상지수] 저장된 데이터가 없습니다.")
        print("가능한 원인:")
        print("1. areaNo 지역코드가 잘못됨")
        print("2. time 요청 시간이 API 기준과 맞지 않음")
        print("3. 인증키 또는 활용신청 상태 문제")
        print("4. API 서버 일시 장애")

    return processed_df


if __name__ == "__main__":
    # area_no는 지역코드다.
    # 우선 용인시 인근 코드로 테스트하고, 안 되면 공공데이터 문서의 areaNo를 확인해서 바꾸면 된다.
    save_living_weather(
        area_no="4146355000"
    )