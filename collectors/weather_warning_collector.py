import os
from datetime import datetime, timedelta
import requests
import pandas as pd
from dotenv import load_dotenv


load_dotenv()


RAW_OUTPUT_PATH = "data/raw/weather_warnings_raw.csv"
PROCESSED_OUTPUT_PATH = "data/processed/weather_warnings.csv"


def get_env_value(name):
    """
    .env에서 값을 가져오고 앞뒤 공백을 제거한다.
    """
    value = os.getenv(name)

    if value is None:
        return None

    return value.strip()


def extract_items_from_response(data):
    """
    기상청 API 응답에서 item 목록을 추출한다.
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


def check_weather_api_error(data):
    """
    기상청 API 응답 상태를 확인한다.
    resultCode 03은 NO_DATA이므로 오류가 아니라 빈 데이터로 처리한다.
    """

    header = data.get("response", {}).get("header", {})

    result_code = str(header.get("resultCode", "")).strip()
    result_msg = str(header.get("resultMsg", "")).strip()

    if result_code == "03":
        return "NO_DATA"

    if result_code and result_code not in ["00", "0", "NORMAL_SERVICE"]:
        raise ValueError(
            f"기상특보 API 오류 발생\n"
            f"resultCode: {result_code}\n"
            f"resultMsg: {result_msg}"
        )

    return "OK"


def extract_weather_risk_type(text):
    """
    특보 제목에서 재난 유형을 추출한다.
    """
    text = str(text)

    if "호우" in text or "홍수" in text or "침수" in text:
        return "호우/침수"
    if "폭염" in text:
        return "폭염"
    if "한파" in text:
        return "한파"
    if "대설" in text:
        return "대설"
    if "태풍" in text:
        return "태풍"
    if "강풍" in text:
        return "강풍"
    if "풍랑" in text:
        return "풍랑"
    if "지진해일" in text:
        return "지진해일"
    if "건조" in text:
        return "건조"
    if "황사" in text:
        return "황사"
    if "폭풍해일" in text:
        return "폭풍해일"

    return "기타"


def extract_warning_level(text):
    """
    특보 제목에서 주의보/경보/해제 여부를 추출한다.
    """
    text = str(text)

    if "경보" in text:
        return "경보"
    if "주의보" in text:
        return "주의보"
    if "해제" in text:
        return "해제"
    if "예비" in text:
        return "예비특보"

    return "정보"


def fetch_weather_warning_list(
    stn_id="109",
    from_date=None,
    to_date=None,
    num_rows=100,
    page_no=1
):
    """
    기상특보목록조회 API 호출.

    사용 API:
    - 기상청_기상특보 조회서비스
    - getWthrWrnList

    Parameters
    ----------
    stn_id : str
        발표 관서 ID. 109는 보통 전국/기상청 기준으로 사용.
    from_date : str | None
        YYYYMMDD 형식
    to_date : str | None
        YYYYMMDD 형식
    """

    service_key = get_env_value("WEATHER_WARNING_SERVICE_KEY")
    base_url = get_env_value("WEATHER_WARNING_BASE_URL")

    if not service_key:
        raise ValueError(".env에 WEATHER_WARNING_SERVICE_KEY가 없습니다.")

    if not base_url:
        raise ValueError(".env에 WEATHER_WARNING_BASE_URL이 없습니다.")

    if not base_url.startswith("http"):
        raise ValueError(
            "WEATHER_WARNING_BASE_URL은 http 또는 https로 시작해야 합니다.\n"
            "예: http://apis.data.go.kr/1360000/WthrWrnInfoService"
        )

    if to_date is None:
        to_date = datetime.now().strftime("%Y%m%d")

    if from_date is None:
        from_date = (datetime.now() - timedelta(days=6)).strftime("%Y%m%d")

    url = f"{base_url}/getWthrWrnList"

    params = {
        "ServiceKey": service_key,
        "pageNo": page_no,
        "numOfRows": num_rows,
        "dataType": "JSON",
        "stnId": stn_id,
        "fromTmFc": from_date,
        "toTmFc": to_date
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    try:
        data = response.json()
    except Exception:
        print("[기상특보] JSON 변환 실패")
        print(response.text[:1000])
        return pd.DataFrame()

    status = check_weather_api_error(data)

    if status == "NO_DATA":
        print("[기상특보] 조회 결과가 없습니다.")
        print("응답 일부:", str(data)[:1000])
        return pd.DataFrame()

    items = extract_items_from_response(data)

    if not items:
        print("[기상특보] item 데이터가 없습니다.")
        print("응답 일부:", str(data)[:1000])
        return pd.DataFrame()

    return pd.DataFrame(items)


def normalize_weather_warnings(raw_df):
    """
    기상특보 원본 데이터를 SafeNavi 서비스용 컬럼으로 변환한다.

    최종 저장 컬럼:
    - warning_id
    - title
    - stn_id
    - announced_at
    - weather_risk_type
    - warning_level
    """

    columns = [
        "warning_id",
        "title",
        "stn_id",
        "announced_at",
        "weather_risk_type",
        "warning_level"
    ]

    if raw_df.empty:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame()

    result["warning_id"] = raw_df["tmSeq"] if "tmSeq" in raw_df.columns else range(1, len(raw_df) + 1)
    result["title"] = raw_df["title"] if "title" in raw_df.columns else ""
    result["stn_id"] = raw_df["stnId"] if "stnId" in raw_df.columns else ""
    result["announced_at"] = raw_df["tmFc"] if "tmFc" in raw_df.columns else ""

    result["title"] = result["title"].fillna("")
    result["weather_risk_type"] = result["title"].apply(extract_weather_risk_type)
    result["warning_level"] = result["title"].apply(extract_warning_level)

    return result[columns]


def save_weather_warnings(
    stn_id="109",
    from_date=None,
    to_date=None,
    save_empty=True
):
    """
    기상특보 API 호출 후 raw/processed 파일 저장.
    """

    os.makedirs("data/raw", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    raw_df = fetch_weather_warning_list(
        stn_id=stn_id,
        from_date=from_date,
        to_date=to_date,
        num_rows=100,
        page_no=1
    )

    if not raw_df.empty:
        raw_df.to_csv(RAW_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        print(f"[기상특보] 원본 저장 완료: {RAW_OUTPUT_PATH}")
        print(f"[기상특보] 원본 행 수: {len(raw_df):,}개")

    processed_df = normalize_weather_warnings(raw_df)

    if not processed_df.empty or save_empty:
        processed_df.to_csv(PROCESSED_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        print(f"[기상특보] 서비스용 저장 완료: {PROCESSED_OUTPUT_PATH}")
        print(f"[기상특보] 서비스용 행 수: {len(processed_df):,}개")

    if not processed_df.empty:
        print()
        print("[기상특보] 유형별 개수")
        print(processed_df["weather_risk_type"].value_counts())
        print()
        print("[기상특보] 단계별 개수")
        print(processed_df["warning_level"].value_counts())
        print()
        print("[기상특보] 미리보기")
        print(processed_df.head(3))

    return processed_df


if __name__ == "__main__":
    save_weather_warnings(stn_id="109")