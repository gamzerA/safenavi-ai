import os
import math
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


def haversine_distance_km(lat1, lon1, lat2, lon2):
    """
    위도/경도 좌표 간 거리를 km 단위로 계산한다.
    """

    radius = 6371  # 지구 반지름 km

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


def get_latest_main_disaster_type(alerts_df):
    """
    AI 분석된 재난문자에서 가장 많이 나온 자연재난 유형을 가져온다.
    자연재난 데이터가 없으면 기본값으로 호우/침수를 사용한다.
    """

    if alerts_df.empty:
        return "호우/침수"

    if "is_natural_disaster" not in alerts_df.columns:
        return "호우/침수"

    # CSV에서 True가 문자열로 읽히는 경우도 대비
    natural_df = alerts_df[
        (alerts_df["is_natural_disaster"] == True)
        | (alerts_df["is_natural_disaster"].astype(str).str.lower() == "true")
    ]

    if natural_df.empty:
        return "호우/침수"

    if "ai_disaster_type" not in natural_df.columns:
        return "호우/침수"

    return natural_df["ai_disaster_type"].value_counts().idxmax()


def get_shelter_match_score(shelter_type, disaster_type):
    """
    재난 유형과 대피소 유형의 적합도 점수를 계산한다.
    최대 30점.

    안전성 기준:
    - 호우/침수, 태풍, 산사태는 옥외시설 점수를 낮게 준다.
    - 폭염/한파는 쉼터와 실내시설을 우선한다.
    - 지진은 옥외대피장소를 우선한다.
    """

    shelter_type = str(shelter_type)
    disaster_type = str(disaster_type)

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


def make_recommend_reason(row, disaster_type):
    """
    추천 사유 문장 생성.
    """

    name = row.get("name", "대피소")
    shelter_type = row.get("shelter_type", "대피시설")
    distance = row.get("distance_km", 0)
    address = get_display_address(row)

    if disaster_type == "호우/침수":
        return (
            f"현재 호우/침수 위험이 있어 실내 수용시설이나 공공시설을 우선 고려했습니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}, 대피소 유형은 {shelter_type}입니다."
        )

    if disaster_type == "태풍":
        return (
            f"현재 태풍 위험이 있어 외부 이동을 줄이고 안전한 실내 시설을 확인하는 것이 중요합니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}, 대피소 유형은 {shelter_type}입니다."
        )

    if disaster_type == "산사태":
        return (
            f"현재 산사태 위험이 있어 급경사지나 산비탈을 피하고 안전한 시설로 이동하는 것이 좋습니다. "
            f"{name}은 현재 위치 기준 약 {distance:.2f}km 거리에 있으며, "
            f"주소는 {address}입니다."
        )

    if disaster_type == "폭염":
        return (
            f"현재 폭염 위험이 있어 무더위쉼터 또는 실내 시설을 우선 추천했습니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}입니다."
        )

    if disaster_type == "한파":
        return (
            f"현재 한파 위험이 있어 한파쉼터 또는 실내 시설을 우선 추천했습니다. "
            f"{name}은 현재 위치에서 약 {distance:.2f}km 떨어져 있으며, "
            f"주소는 {address}입니다."
        )

    if disaster_type == "지진":
        return (
            f"현재 지진 관련 위험에 대비해 지진옥외대피장소 또는 넓은 대피공간을 우선 추천했습니다. "
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
    disaster_type=None,
    top_n=3,
    max_distance_km=20
):
    """
    사용자 위치와 재난 유형을 바탕으로 대피소 TOP N을 추천한다.

    Parameters
    ----------
    user_lat : float
        사용자 위도
    user_lon : float
        사용자 경도
    disaster_type : str | None
        재난 유형. None이면 최근 AI 재난문자에서 주요 유형을 자동 선택.
    top_n : int
        추천 개수
    max_distance_km : float
        최대 탐색 거리 km

    Returns
    -------
    pandas.DataFrame
        추천 대피소 결과
    """

    shelters_df = safe_read_csv(SHELTERS_PATH)
    alerts_df = safe_read_csv(ALERTS_ANALYZED_PATH)

    if shelters_df.empty:
        raise ValueError("shelters.csv가 비어 있거나 없습니다.")

    required_cols = ["name", "address", "lat", "lon", "shelter_type"]

    for col in required_cols:
        if col not in shelters_df.columns:
            raise ValueError(f"shelters.csv에 필요한 컬럼이 없습니다: {col}")

    if disaster_type is None:
        disaster_type = get_latest_main_disaster_type(alerts_df)

    shelters_df["lat"] = pd.to_numeric(shelters_df["lat"], errors="coerce")
    shelters_df["lon"] = pd.to_numeric(shelters_df["lon"], errors="coerce")

    shelters_df = shelters_df.dropna(subset=["lat", "lon"]).copy()

    distances = []

    for _, row in shelters_df.iterrows():
        distance = haversine_distance_km(
            user_lat,
            user_lon,
            row["lat"],
            row["lon"]
        )
        distances.append(distance)

    shelters_df["distance_km"] = distances

    # 너무 먼 시설 제외
    shelters_df = shelters_df[shelters_df["distance_km"] <= max_distance_km].copy()

    if shelters_df.empty:
        raise ValueError("설정한 거리 안에 추천 가능한 대피소가 없습니다.")

    shelters_df["distance_score"] = shelters_df["distance_km"].apply(get_distance_score)

    shelters_df["match_score"] = shelters_df["shelter_type"].apply(
        lambda x: get_shelter_match_score(x, disaster_type)
    )

    if "capacity" in shelters_df.columns:
        shelters_df["capacity_score"] = shelters_df["capacity"].apply(get_capacity_score)
    else:
        shelters_df["capacity_score"] = 3

    if "source" in shelters_df.columns:
        shelters_df["source_score"] = shelters_df["source"].apply(get_source_score)
    else:
        shelters_df["source_score"] = 6

    shelters_df["recommend_score"] = (
        shelters_df["distance_score"]
        + shelters_df["match_score"]
        + shelters_df["capacity_score"]
        + shelters_df["source_score"]
    )

    shelters_df = shelters_df.sort_values(
        by=["recommend_score", "distance_km"],
        ascending=[False, True]
    )

    result = shelters_df.head(top_n).copy()

    result["disaster_type"] = disaster_type

    result["display_address"] = result.apply(get_display_address, axis=1)

    result["recommend_reason"] = result.apply(
        lambda row: make_recommend_reason(row, disaster_type),
        axis=1
    )

    output_cols = [
        "disaster_type",
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
    print(f"기준 재난 유형: {disaster_type}")
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
    # 테스트용 사용자 위치
    # 실제 서비스에서는 사용자의 현재 위치 좌표를 여기에 넣으면 된다.
    # 아래 좌표는 용인 지역 테스트용 임시 좌표다.
    USER_LAT = 37.2410
    USER_LON = 127.1776

    result_df = recommend_shelters(
        user_lat=USER_LAT,
        user_lon=USER_LON,
        disaster_type=None,
        top_n=3,
        max_distance_km=20
    )

    print_recommendation_result(result_df)