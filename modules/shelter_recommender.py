import os
import math
import re
from functools import lru_cache

import numpy as np
import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHELTERS_PATH = os.path.join(
    BASE_DIR, "data", "processed", "shelters.csv"
)

ALERTS_ANALYZED_PATH = os.path.join(
    BASE_DIR, "data", "processed", "disaster_alerts_analyzed.csv"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "data", "processed", "recommended_shelters.csv"
)


def safe_read_csv(path):
    """
    CSV 파일을 안전하게 불러온다.
    파일이 없거나 비어 있으면 빈 DataFrame을 반환한다.
    """
    if not os.path.exists(path):
        print(f"[대피소 추천] 파일 없음: {path}")
        return pd.DataFrame()

    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as e:
        print(f"[대피소 추천] CSV 읽기 오류: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=1)
def load_shelters_cached():
    """
    shelters.csv를 한 번만 읽고 메모리에 저장한다.
    웹에서 대피소 추천을 여러 번 요청할 때 속도를 줄이기 위한 캐시 함수다.
    """

    df = safe_read_csv(SHELTERS_PATH)

    if df.empty:
        return df

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")

    df = df.dropna(subset=["lat", "lon"]).copy()

    return df


@lru_cache(maxsize=1)
def load_alerts_cached():
    """
    AI 분석된 재난문자 CSV를 한 번만 읽고 메모리에 저장한다.
    """

    return safe_read_csv(ALERTS_ANALYZED_PATH)


def normalize_region_text(text):
    """
    지역명 비교를 위해 문자열을 정리한다.
    예: '경기도 용인시' -> '경기도용인시'
    """

    text = str(text)
    text = text.replace("nan", "")
    text = re.sub(r"[^가-힣a-zA-Z0-9]", "", text)
    return text


def make_region_keywords(user_region):
    """
    사용자 지역명에서 시/군/구 단위 키워드를 만든다.

    예:
    user_region = '경기도 용인시'
    -> ['용인시', '용인']

    '경기도' 같은 광역 지자체명만으로는 매칭하지 않는다.
    """

    if user_region is None or str(user_region).strip() == "":
        return []

    user_region = str(user_region).strip()

    broad_regions = [
        "서울특별시", "부산광역시", "대구광역시", "인천광역시",
        "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
        "경기도", "강원특별자치도", "강원도", "충청북도", "충청남도",
        "전북특별자치도", "전라북도", "전라남도",
        "경상북도", "경상남도", "제주특별자치도"
    ]

    keywords = set()
    parts = user_region.split()

    for part in parts:
        cleaned = normalize_region_text(part)

        if not cleaned:
            continue

        if cleaned in broad_regions:
            continue

        keywords.add(cleaned)

        if cleaned.endswith("시") or cleaned.endswith("군") or cleaned.endswith("구"):
            keywords.add(cleaned[:-1])

    full_cleaned = normalize_region_text(user_region)

    if full_cleaned and full_cleaned not in broad_regions:
        keywords.add(full_cleaned)

    return [keyword for keyword in keywords if keyword]


def region_matches(alert_region, user_region):
    """
    재난문자 지역이 사용자 지역과 관련 있는지 판단한다.
    '경기도'만 같다고 같은 지역으로 보지 않고, 시/군/구 단위로 비교한다.
    """

    if user_region is None or str(user_region).strip() == "":
        return False

    alert_region_text = normalize_region_text(alert_region)
    keywords = make_region_keywords(user_region)

    if not alert_region_text or not keywords:
        return False

    for keyword in keywords:
        if keyword in alert_region_text:
            return True

    return False


def filter_natural_alerts_by_region(alerts_df, user_region=None):
    """
    AI 분석된 재난문자 중 자연재난 문자만 추출하고,
    user_region이 있으면 해당 지역 관련 문자만 필터링한다.
    """

    if alerts_df.empty:
        return pd.DataFrame()

    if "is_natural_disaster" not in alerts_df.columns:
        return pd.DataFrame()

    natural_df = alerts_df[
        (alerts_df["is_natural_disaster"] == True)
        | (alerts_df["is_natural_disaster"].astype(str).str.lower() == "true")
    ].copy()

    if natural_df.empty:
        return pd.DataFrame()

    if user_region is None or str(user_region).strip() == "":
        return natural_df

    region_col = None

    for candidate in ["ai_region", "region", "RCPTN_RGN_NM"]:
        if candidate in natural_df.columns:
            region_col = candidate
            break

    if region_col is None:
        return pd.DataFrame()

    filtered_df = natural_df[
        natural_df[region_col].apply(
            lambda x: region_matches(x, user_region)
        )
    ].copy()

    return filtered_df


def get_local_disaster_info(alerts_df, user_region=None):
    """
    사용자 지역 기준으로 실제 자연재난 문자가 있는지 확인한다.

    반환값:
    {
        "has_local_alert": bool,
        "main_disaster_type": str,
        "risk_level": str,
        "region": str
    }
    """

    default_result = {
        "has_local_alert": False,
        "main_disaster_type": "일반 대비",
        "risk_level": "낮음",
        "region": user_region if user_region else "사용자 위치 주변"
    }

    natural_df = filter_natural_alerts_by_region(
        alerts_df=alerts_df,
        user_region=user_region
    )

    if natural_df.empty:
        return default_result

    if "created_at" in natural_df.columns:
        natural_df["created_at_sort"] = pd.to_datetime(
            natural_df["created_at"],
            errors="coerce"
        )

        natural_df = natural_df.sort_values(
            by="created_at_sort",
            ascending=False
        )

    latest = natural_df.iloc[0]

    main_type = latest.get("ai_disaster_type", "자연재난")
    risk_level = latest.get("ai_risk_level", "주의")
    region = latest.get("ai_region", latest.get("region", user_region or "지역 미확인"))

    return {
        "has_local_alert": True,
        "main_disaster_type": str(main_type),
        "risk_level": str(risk_level),
        "region": str(region)
    }


def haversine_distance_km(lat1, lon1, lat2, lon2):
    """
    위도/경도 좌표 간 거리를 km 단위로 계산한다.
    단일 거리 계산용 함수다.
    """

    radius = 6371

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius * c


def calculate_distance_vectorized(candidate_df, user_lat, user_lon):
    """
    pandas/numpy를 사용해 여러 대피소와의 거리를 한 번에 계산한다.
    반복문보다 훨씬 빠르다.
    """

    earth_radius = 6371

    lat1 = np.radians(float(user_lat))
    lon1 = np.radians(float(user_lon))

    lat2 = np.radians(candidate_df["lat"].astype(float))
    lon2 = np.radians(candidate_df["lon"].astype(float))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    )

    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    return earth_radius * c


def get_shelter_match_score(shelter_type, disaster_type):
    """
    재난 유형과 대피소 유형의 적합도 점수를 계산한다.
    최대 30점.

    안전성 기준:
    - 호우/침수, 태풍, 산사태는 옥외시설 점수를 낮게 준다.
    - 폭염/한파는 쉼터와 실내시설을 우선한다.
    - 지진은 옥외대피장소를 우선한다.
    - 일반 대비 상황은 거리와 수용 가능성을 중심으로 계산한다.
    """

    shelter_type = str(shelter_type)
    disaster_type = str(disaster_type)

    # 실제 위험 문자가 없는 일반 대비 상황
    if disaster_type == "일반 대비":
        if "학교" in shelter_type or "공공" in shelter_type or "시설" in shelter_type:
            return 22
        if "수용" in shelter_type:
            return 20
        if "실내" in shelter_type:
            return 20
        if "옥외" in shelter_type:
            return 12
        return 15

    # 폭염
    if disaster_type == "폭염":
        if "무더위" in shelter_type:
            return 30
        if "실내" in shelter_type or "수용" in shelter_type or "공공" in shelter_type:
            return 22
        if "옥외" in shelter_type:
            return 5
        return 10

    # 한파
    if disaster_type == "한파":
        if "한파" in shelter_type:
            return 30
        if "실내" in shelter_type or "수용" in shelter_type or "공공" in shelter_type:
            return 22
        if "옥외" in shelter_type:
            return 5
        return 10

    # 지진
    if disaster_type == "지진":
        if "지진옥외" in shelter_type or "옥외" in shelter_type:
            return 30
        if "학교" in shelter_type or "공터" in shelter_type:
            return 22
        if "실내" in shelter_type:
            return 10
        return 12

    # 지진해일
    if disaster_type == "지진해일":
        if "지진해일" in shelter_type or "해일" in shelter_type:
            return 30
        if "옥외" in shelter_type:
            return 10
        if "실내" in shelter_type or "수용" in shelter_type:
            return 15
        return 5

    # 호우/침수
    if disaster_type == "호우/침수":
        if "옥외" in shelter_type:
            return 3
        if "실내" in shelter_type:
            return 30
        if "수용" in shelter_type:
            return 27
        if "공공" in shelter_type or "학교" in shelter_type or "시설" in shelter_type:
            return 22
        if "무더위" in shelter_type or "한파" in shelter_type:
            return 12
        return 10

    # 태풍
    if disaster_type == "태풍":
        if "옥외" in shelter_type:
            return 3
        if "실내" in shelter_type:
            return 30
        if "수용" in shelter_type:
            return 27
        if "공공" in shelter_type or "학교" in shelter_type or "시설" in shelter_type:
            return 22
        return 10

    # 산사태
    if disaster_type == "산사태":
        if "옥외" in shelter_type:
            return 5
        if "실내" in shelter_type or "수용" in shelter_type:
            return 28
        if "공공" in shelter_type or "학교" in shelter_type or "시설" in shelter_type:
            return 22
        return 10

    return 10


def get_distance_score(distance_km):
    """
    거리 점수 계산.
    가까울수록 높은 점수.
    최대 45점.
    """

    if distance_km <= 0.5:
        return 45
    if distance_km <= 1:
        return 40
    if distance_km <= 2:
        return 32
    if distance_km <= 3:
        return 25
    if distance_km <= 5:
        return 15
    return 5


def get_capacity_score(capacity):
    """
    수용 가능 인원 점수.
    최대 15점.
    """

    try:
        value = float(capacity)

        if value >= 500:
            return 15
        if value >= 200:
            return 12
        if value >= 100:
            return 9
        if value > 0:
            return 6

    except Exception:
        pass

    return 3


def get_source_score(source):
    """
    데이터 출처 점수.
    최대 10점.
    """

    source = str(source)

    if "수용" in source or "capacity" in source.lower():
        return 10
    if "통합" in source or "shelter" in source.lower():
        return 8

    return 6


def get_display_address(row):
    """
    주소가 비어 있으면 sido + sigungu로 대체한다.
    그래도 없으면 '주소 정보 없음'을 반환한다.
    """

    address = row.get("address", "")

    if pd.isna(address) or str(address).strip().lower() == "nan" or str(address).strip() == "":
        sido = row.get("sido", "")
        sigungu = row.get("sigungu", "")

        sido = "" if pd.isna(sido) else str(sido).strip()
        sigungu = "" if pd.isna(sigungu) else str(sigungu).strip()

        fallback = f"{sido} {sigungu}".strip()

        if fallback:
            return fallback

        return "주소 정보 없음"

    return str(address)


def make_recommend_reason(row, disaster_type, has_local_alert=False, user_region=None):
    """
    추천 사유 문장 생성.

    has_local_alert가 False이면 실제 위험이 있다고 단정하지 않는다.
    """

    name = row.get("name", "대피소")
    shelter_type = row.get("shelter_type", "대피시설")
    distance = row.get("distance_km", 0)
    address = get_display_address(row)

    if not has_local_alert:
        region_text = user_region if user_region else "사용자 지역"

        return (
            f"현재 {region_text}에 직접 확인된 자연재난 문자는 없지만, "
            f"비상 상황에 대비해 현재 위치에서 가까운 대피소를 안내합니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}, 대피소 유형은 {shelter_type}입니다."
        )

    if disaster_type == "호우/침수":
        return (
            f"현재 호우/침수 위험이 확인되어 실내 수용시설이나 공공시설을 우선 고려했습니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}, 대피소 유형은 {shelter_type}입니다."
        )

    if disaster_type == "태풍":
        return (
            f"현재 태풍 위험이 확인되어 외부 이동을 줄이고 안전한 실내 시설을 확인하는 것이 중요합니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}, 대피소 유형은 {shelter_type}입니다."
        )

    if disaster_type == "산사태":
        return (
            f"현재 산사태 위험이 확인되어 급경사지나 산비탈을 피하고 안전한 시설로 이동하는 것이 좋습니다. "
            f"{name}은 현재 위치 기준 약 {distance:.2f}km 거리에 있으며, "
            f"주소는 {address}입니다."
        )

    if disaster_type == "폭염":
        return (
            f"현재 폭염 위험이 확인되어 무더위쉼터 또는 실내 시설을 우선 추천했습니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}입니다."
        )

    if disaster_type == "한파":
        return (
            f"현재 한파 위험이 확인되어 한파쉼터 또는 실내 시설을 우선 추천했습니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}입니다."
        )

    if disaster_type == "지진":
        return (
            f"현재 지진 관련 위험이 확인되어 지진옥외대피장소 또는 넓은 대피공간을 우선 추천했습니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}입니다."
        )

    return (
        f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
        f"주소는 {address}입니다."
    )


def recommend_shelters(
    user_lat,
    user_lon,
    user_region=None,
    disaster_type=None,
    top_n=3,
    max_distance_km=10
):
    """
    사용자 위치와 재난 유형을 바탕으로 대피소 TOP N을 추천한다.

    속도 개선 방식:
    1. shelters.csv 캐싱
    2. 사용자 위치 기준 위도/경도 박스 필터링
    3. 후보 대피소만 거리 계산
    4. 후보 대피소만 점수 계산
    """

    shelters_df = load_shelters_cached().copy()
    alerts_df = load_alerts_cached()

    if shelters_df.empty:
        raise ValueError("shelters.csv가 비어 있거나 없습니다.")

    required_cols = ["name", "address", "lat", "lon", "shelter_type"]

    for col in required_cols:
        if col not in shelters_df.columns:
            raise ValueError(f"shelters.csv에 필요한 컬럼이 없습니다: {col}")

    user_lat = float(user_lat)
    user_lon = float(user_lon)

    local_disaster_info = get_local_disaster_info(
        alerts_df=alerts_df,
        user_region=user_region
    )

    has_local_alert = local_disaster_info["has_local_alert"]

    # 사용자가 직접 재난 유형을 선택한 경우
    if disaster_type is not None and str(disaster_type).strip() != "":
        selected_disaster_type = str(disaster_type).strip()

        # 사용자가 직접 선택한 경우에도 실제 위험이 있다고 단정하지 않는다.
        # 단, 해당 지역에 실제 재난문자가 있고 유형이 같으면 위험 확인으로 본다.
        if (
            has_local_alert
            and local_disaster_info["main_disaster_type"] == selected_disaster_type
        ):
            reason_has_local_alert = True
        else:
            reason_has_local_alert = False

    else:
        # 자동 선택인 경우: 사용자 지역 재난문자가 있으면 그 유형, 없으면 일반 대비
        selected_disaster_type = local_disaster_info["main_disaster_type"]
        reason_has_local_alert = has_local_alert

    # 1차 후보 필터링: 사용자 위치 주변 대피소만 추림
    lat_range = max_distance_km / 111

    cos_value = np.cos(np.radians(user_lat))

    if abs(cos_value) < 0.0001:
        lon_range = max_distance_km / 111
    else:
        lon_range = max_distance_km / (111 * cos_value)

    candidate_df = shelters_df[
        (shelters_df["lat"] >= user_lat - lat_range)
        & (shelters_df["lat"] <= user_lat + lat_range)
        & (shelters_df["lon"] >= user_lon - lon_range)
        & (shelters_df["lon"] <= user_lon + lon_range)
    ].copy()

    if candidate_df.empty:
        raise ValueError("설정한 거리 안에 추천 가능한 대피소가 없습니다.")

    # 벡터 방식 거리 계산
    candidate_df["distance_km"] = calculate_distance_vectorized(
        candidate_df=candidate_df,
        user_lat=user_lat,
        user_lon=user_lon
    )

    # 실제 거리 기준으로 다시 필터링
    candidate_df = candidate_df[
        candidate_df["distance_km"] <= max_distance_km
    ].copy()

    if candidate_df.empty:
        raise ValueError("설정한 거리 안에 추천 가능한 대피소가 없습니다.")

    candidate_df["distance_score"] = candidate_df["distance_km"].apply(get_distance_score)

    candidate_df["match_score"] = candidate_df["shelter_type"].apply(
        lambda x: get_shelter_match_score(x, selected_disaster_type)
    )

    if "capacity" in candidate_df.columns:
        candidate_df["capacity_score"] = candidate_df["capacity"].apply(get_capacity_score)
    else:
        candidate_df["capacity_score"] = 3

    if "source" in candidate_df.columns:
        candidate_df["source_score"] = candidate_df["source"].apply(get_source_score)
    else:
        candidate_df["source_score"] = 6

    candidate_df["recommend_score"] = (
        candidate_df["distance_score"]
        + candidate_df["match_score"]
        + candidate_df["capacity_score"]
        + candidate_df["source_score"]
    )

    candidate_df = candidate_df.sort_values(
        by=["recommend_score", "distance_km"],
        ascending=[False, True]
    )

    result = candidate_df.head(top_n).copy()

    result["disaster_type"] = selected_disaster_type
    result["has_local_alert"] = reason_has_local_alert
    result["user_region"] = user_region if user_region else "사용자 위치 주변"
    result["display_address"] = result.apply(get_display_address, axis=1)

    result["recommend_reason"] = result.apply(
        lambda row: make_recommend_reason(
            row=row,
            disaster_type=selected_disaster_type,
            has_local_alert=reason_has_local_alert,
            user_region=user_region
        ),
        axis=1
    )

    output_cols = [
        "disaster_type",
        "has_local_alert",
        "user_region",
        "name",
        "display_address",
        "address",
        "sido",
        "sigungu",
        "lat",
        "lon",
        "shelter_type",
        "capacity",
        "distance_km",
        "distance_score",
        "match_score",
        "capacity_score",
        "source_score",
        "recommend_score",
        "recommend_reason"
    ]

    existing_cols = [col for col in output_cols if col in result.columns]
    result = result[existing_cols]

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    return result


def print_recommendation_result(result):
    """
    추천 결과를 터미널에 보기 좋게 출력한다.
    """

    print("======================================")
    print("SafeNavi 맞춤형 대피소 TOP 3 추천")
    print("======================================")

    if result.empty:
        print("추천 결과가 없습니다.")
        return

    disaster_type = result.iloc[0].get("disaster_type", "재난")
    has_local_alert = result.iloc[0].get("has_local_alert", False)

    print(f"기준 재난 유형: {disaster_type}")
    print(f"지역 재난문자 확인 여부: {has_local_alert}")
    print()

    for idx, (_, row) in enumerate(result.iterrows(), start=1):
        print(f"{idx}. {row.get('name', '이름 없음')}")
        print(f"   주소: {row.get('display_address', get_display_address(row))}")
        print(f"   유형: {row.get('shelter_type', '유형 없음')}")
        print(f"   거리: {row.get('distance_km', 0):.2f}km")
        print(f"   거리 점수: {row.get('distance_score', 0):.1f}점")
        print(f"   유형 적합도 점수: {row.get('match_score', 0):.1f}점")
        print(f"   수용 점수: {row.get('capacity_score', 0):.1f}점")
        print(f"   종합 추천 점수: {row.get('recommend_score', 0):.1f}점")
        print(f"   추천 사유: {row.get('recommend_reason', '')}")
        print()

    print(f"저장 파일: {OUTPUT_PATH}")
    print("======================================")


if __name__ == "__main__":
    USER_LAT = 37.2410
    USER_LON = 127.1776
    USER_REGION = "경기도 용인시"

    result_df = recommend_shelters(
        user_lat=USER_LAT,
        user_lon=USER_LON,
        user_region=USER_REGION,
        disaster_type=None,
        top_n=3,
        max_distance_km=10
    )

    print_recommendation_result(result_df)