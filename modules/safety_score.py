import os
import re
import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DISASTER_ALERTS_ANALYZED_PATH = os.path.join(
    BASE_DIR, "data", "processed", "disaster_alerts_analyzed.csv"
)

WEATHER_WARNINGS_PATH = os.path.join(
    BASE_DIR, "data", "processed", "weather_warnings.csv"
)

LIVING_WEATHER_PATH = os.path.join(
    BASE_DIR, "data", "processed", "living_weather.csv"
)


BROAD_REGIONS = [
    "서울특별시", "서울", "부산광역시", "부산", "대구광역시", "대구",
    "인천광역시", "인천", "광주광역시", "광주", "대전광역시", "대전",
    "울산광역시", "울산", "세종특별자치시", "세종",
    "경기도", "경기", "강원특별자치도", "강원도", "강원",
    "충청북도", "충북", "충청남도", "충남",
    "전북특별자치도", "전라북도", "전북",
    "전라남도", "전남", "경상북도", "경북",
    "경상남도", "경남", "제주특별자치도", "제주도", "제주"
]


def safe_read_csv(path):
    """
    CSV 파일을 불러온다.
    파일이 없거나 비어 있으면 빈 DataFrame을 반환한다.
    """

    if not os.path.exists(path):
        print(f"[안전지수] 파일 없음: {path}")
        return pd.DataFrame()

    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as e:
        print(f"[안전지수] CSV 읽기 오류: {path} / {e}")
        return pd.DataFrame()


def normalize_region_text(text):
    """
    지역명 비교를 위해 공백과 특수문자를 제거한다.
    """

    text = str(text)
    text = text.replace("nan", "")
    text = re.sub(r"[^가-힣a-zA-Z0-9]", "", text)
    return text


def make_region_keywords(region_name):
    """
    선택 지역에서 지역 비교용 키워드를 만든다.

    예:
    '경기도 용인시 처인구' ->
    ['경기도용인시처인구', '용인시', '용인', '처인구', '처인']
    """

    if region_name is None or str(region_name).strip() == "":
        return []

    region_name = str(region_name).strip()

    if region_name in ["전국", "전체", "전국 기준"]:
        return []

    keywords = set()
    parts = region_name.split()

    for part in parts:
        cleaned = normalize_region_text(part)

        if not cleaned:
            continue

        keywords.add(cleaned)

        if cleaned.endswith("시") or cleaned.endswith("군") or cleaned.endswith("구"):
            keywords.add(cleaned[:-1])

    full_cleaned = normalize_region_text(region_name)

    if full_cleaned:
        keywords.add(full_cleaned)

    # '경기도 용인시'처럼 입력한 경우 광역지자체 단독 키워드만으로 매칭되면 너무 넓다.
    # 다만 사용자가 '경기도'만 선택한 경우는 경기도 전체 기준으로 계산해야 하므로 유지한다.
    if len(parts) >= 2:
        keywords = {
            keyword for keyword in keywords
            if keyword not in BROAD_REGIONS
        }

    return [keyword for keyword in keywords if keyword]


def row_matches_region(row, region_name):
    """
    한 행이 선택 지역과 관련 있는지 판단한다.
    가능한 지역 컬럼과 메시지 본문 컬럼을 폭넓게 확인한다.
    """

    if region_name is None or str(region_name).strip() == "":
        return True

    if str(region_name).strip() in ["전국", "전체", "전국 기준"]:
        return True

    keywords = make_region_keywords(region_name)

    if not keywords:
        return True

    candidate_columns = [
        "ai_region",
        "region",
        "RCPTN_RGN_NM",
        "rcptn_rgn_nm",
        "area",
        "sido",
        "sigungu",
        "city",
        "district",
        "location",
        "address",
        "msg",
        "message",
        "MSG_CN",
        "msg_cn",
        "content",
        "text"
    ]

    combined_values = []

    for col in candidate_columns:
        if col in row.index:
            value = row.get(col, "")
            if value is not None and not pd.isna(value):
                combined_values.append(str(value))

    # 컬럼명이 예상과 달라도 전체 행 값에서 한 번 더 확인한다.
    if not combined_values:
        combined_values = [
            str(value)
            for value in row.values
            if value is not None and not pd.isna(value)
        ]

    row_text = normalize_region_text(" ".join(combined_values))

    if not row_text:
        return False

    for keyword in keywords:
        if normalize_region_text(keyword) in row_text:
            return True

    return False


def filter_df_by_region(df, region_name=None):
    """
    DataFrame을 선택 지역 기준으로 필터링한다.
    지역이 비어 있으면 전체 데이터를 반환한다.
    """

    if df.empty:
        return df

    if region_name is None or str(region_name).strip() == "":
        return df

    if str(region_name).strip() in ["전국", "전체", "전국 기준"]:
        return df

    filtered_df = df[
        df.apply(
            lambda row: row_matches_region(row, region_name),
            axis=1
        )
    ].copy()

    return filtered_df


def is_true_value(value):
    """
    CSV의 boolean 값이 True인지 안전하게 판단한다.
    """

    if value is True:
        return True

    text = str(value).strip().lower()

    return text in ["true", "1", "yes", "y", "t"]


def score_from_disaster_alerts(df):
    """
    AI 분석된 긴급재난문자 데이터에서 위험 점수를 계산한다.

    점수 기준:
    - 자연재난 문자 1건당 5점
    - 위험도 '높음' 1건당 추가 3점
    - 최대 45점
    """

    if df.empty:
        return 0, {
            "natural_alert_count": 0,
            "high_risk_alert_count": 0,
            "main_disaster_types": []
        }

    if "is_natural_disaster" not in df.columns:
        return 0, {
            "natural_alert_count": 0,
            "high_risk_alert_count": 0,
            "main_disaster_types": []
        }

    natural_df = df[
        df["is_natural_disaster"].apply(is_true_value)
    ].copy()

    natural_count = len(natural_df)

    high_risk_count = 0
    if "ai_risk_level" in natural_df.columns:
        high_risk_count = len(
            natural_df[
                natural_df["ai_risk_level"].fillna("").astype(str).str.contains("높음", na=False)
            ]
        )

    score = natural_count * 5 + high_risk_count * 3
    score = min(score, 45)

    main_types = []

    if not natural_df.empty and "ai_disaster_type" in natural_df.columns:
        main_types = (
            natural_df["ai_disaster_type"]
            .dropna()
            .astype(str)
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .head(3)
            .index
            .tolist()
        )

    detail = {
        "natural_alert_count": natural_count,
        "high_risk_alert_count": high_risk_count,
        "main_disaster_types": main_types
    }

    return score, detail


def score_from_weather_warnings(df):
    """
    기상특보 데이터에서 위험 점수를 계산한다.

    점수 기준:
    - 경보: 25점
    - 주의보: 15점
    - 예비특보/정보: 8점
    - 최대 30점
    """

    if df.empty:
        return 0, {
            "weather_warning_count": 0,
            "warning_levels": [],
            "weather_risk_types": []
        }

    score = 0

    if "warning_level" in df.columns:
        for level in df["warning_level"].fillna("").astype(str):
            if "경보" in level:
                score += 25
            elif "주의보" in level:
                score += 15
            elif "예비" in level or "정보" in level:
                score += 8
    else:
        # 특보 파일에 등급 컬럼이 없더라도 행이 있으면 약한 위험으로 반영
        score += min(len(df) * 8, 20)

    score = min(score, 30)

    warning_levels = []
    if "warning_level" in df.columns:
        warning_levels = (
            df["warning_level"]
            .dropna()
            .astype(str)
            .value_counts()
            .head(3)
            .index
            .tolist()
        )

    risk_types = []
    if "weather_risk_type" in df.columns:
        risk_types = (
            df["weather_risk_type"]
            .dropna()
            .astype(str)
            .value_counts()
            .head(3)
            .index
            .tolist()
        )

    detail = {
        "weather_warning_count": len(df),
        "warning_levels": warning_levels,
        "weather_risk_types": risk_types
    }

    return score, detail


def convert_living_value_to_int(value):
    """
    생활기상지수 값을 숫자로 변환한다.
    변환이 안 되면 0으로 처리한다.
    """

    try:
        if pd.isna(value):
            return 0

        text = str(value).strip()

        if text == "":
            return 0

        return int(float(text))

    except Exception:
        return 0


def score_from_living_weather(df):
    """
    생활기상지수 데이터에서 위험 점수를 계산한다.

    점수 기준:
    - today_value가 80 이상: 10점
    - today_value가 50 이상: 6점
    - today_value가 30 이상: 3점
    - 최대 25점
    """

    if df.empty:
        return 0, {
            "living_weather_count": 0,
            "living_indexes": [],
            "living_values": {}
        }

    score = 0
    living_values = {}

    if "index_type" not in df.columns:
        return 0, {
            "living_weather_count": len(df),
            "living_indexes": [],
            "living_values": {}
        }

    for _, row in df.iterrows():
        index_type = row.get("index_type", "생활기상지수")
        value = convert_living_value_to_int(row.get("today_value", 0))

        living_values[index_type] = value

        if value >= 80:
            score += 10
        elif value >= 50:
            score += 6
        elif value >= 30:
            score += 3

    score = min(score, 25)

    detail = {
        "living_weather_count": len(df),
        "living_indexes": df["index_type"].dropna().unique().tolist(),
        "living_values": living_values
    }

    return score, detail


def get_safety_level(total_score):
    """
    총 위험 점수를 안전 단계로 변환한다.

    total_score는 위험 점수다.
    점수가 높을수록 위험하다.
    """

    if total_score >= 70:
        return "위험"
    if total_score >= 40:
        return "주의"
    return "안전"


def get_safety_score_number(total_risk_score):
    """
    위험 점수를 사용자에게 보여줄 안전 점수로 변환한다.

    위험 점수 0점 → 안전 점수 100점
    위험 점수 100점 → 안전 점수 0점
    """

    safety_score = 100 - total_risk_score

    if safety_score < 0:
        safety_score = 0

    if safety_score > 100:
        safety_score = 100

    return safety_score


def make_recommendations(level, main_risk_types):
    """
    안전 단계와 주요 위험 유형을 바탕으로 권장 행동을 만든다.
    """

    recommendations = []

    if "호우/침수" in main_risk_types:
        recommendations.extend([
            "하천변 접근을 피하세요.",
            "지하차도와 저지대 이동을 자제하세요.",
            "가까운 대피소를 확인하세요."
        ])

    if "태풍" in main_risk_types:
        recommendations.extend([
            "외출을 줄이고 실내에 머무르세요.",
            "간판, 가로수, 해안가 주변을 피하세요."
        ])

    if "산사태" in main_risk_types:
        recommendations.extend([
            "산비탈과 급경사지 주변 접근을 피하세요.",
            "토사 유출 위험지역에서 벗어나세요."
        ])

    if "폭염" in main_risk_types:
        recommendations.extend([
            "한낮 야외활동을 줄이세요.",
            "물을 자주 마시고 무더위쉼터를 확인하세요."
        ])

    if "한파" in main_risk_types:
        recommendations.extend([
            "보온을 유지하고 장시간 외출을 피하세요.",
            "빙판길 이동에 주의하세요."
        ])

    if "대설" in main_risk_types:
        recommendations.extend([
            "눈길과 빙판길 이동을 줄이고 미끄럼 사고에 주의하세요.",
            "차량 운행 전 도로 통제와 교통 상황을 확인하세요."
        ])

    if "지진" in main_risk_types:
        recommendations.extend([
            "실내에서는 머리를 보호하고 흔들림이 멈춘 뒤 넓은 공간으로 이동하세요.",
            "건물 외벽, 간판, 유리창 주변을 피하세요."
        ])

    if not recommendations:
        if level == "위험":
            recommendations.append("현재 위험 수준이 높으니 외출을 자제하고 공식 안내를 확인하세요.")
        elif level == "주의":
            recommendations.append("생활권 주변의 기상특보와 재난문자를 확인하세요.")
        else:
            recommendations.append("현재 큰 위험 요인은 없지만 최신 재난문자를 확인하세요.")

    unique_recommendations = []
    for item in recommendations:
        if item not in unique_recommendations:
            unique_recommendations.append(item)

    return unique_recommendations[:5]


def calculate_today_safety_score(region_name=None):
    """
    오늘의 안전지수를 계산한다.

    Parameters
    ----------
    region_name : str or None
        선택 지역명. 예: '경기도 용인시', '서울특별시', '처인구'
        None 또는 빈 문자열이면 전체 데이터 기준으로 계산한다.

    사용 데이터:
    - disaster_alerts_analyzed.csv
    - weather_warnings.csv
    - living_weather.csv
    """

    selected_region = "" if region_name is None else str(region_name).strip()

    if selected_region in ["전국", "전체", "전국 기준"]:
        selected_region = ""

    alerts_df = safe_read_csv(DISASTER_ALERTS_ANALYZED_PATH)
    weather_df = safe_read_csv(WEATHER_WARNINGS_PATH)
    living_df = safe_read_csv(LIVING_WEATHER_PATH)

    if selected_region:
        alerts_df = filter_df_by_region(alerts_df, selected_region)
        weather_df = filter_df_by_region(weather_df, selected_region)
        living_df = filter_df_by_region(living_df, selected_region)

    alert_score, alert_detail = score_from_disaster_alerts(alerts_df)
    weather_score, weather_detail = score_from_weather_warnings(weather_df)
    living_score, living_detail = score_from_living_weather(living_df)

    total_risk_score = alert_score + weather_score + living_score

    if total_risk_score > 100:
        total_risk_score = 100

    safety_score = get_safety_score_number(total_risk_score)
    safety_level = get_safety_level(total_risk_score)

    main_risk_types = []

    main_risk_types.extend(alert_detail["main_disaster_types"])
    main_risk_types.extend(weather_detail["weather_risk_types"])

    main_risk_types = list(
        dict.fromkeys(
            [x for x in main_risk_types if x and x != "기타" and str(x).strip() != ""]
        )
    )

    recommendations = make_recommendations(
        level=safety_level,
        main_risk_types=main_risk_types
    )

    result = {
        "selected_region": selected_region,
        "safety_score": safety_score,
        "risk_score": total_risk_score,
        "safety_level": safety_level,

        "main_risk_types": main_risk_types,
        "recommended_actions": recommendations,
        "recommendations": recommendations,

        "alert_risk_score": alert_score,
        "weather_warning_risk_score": weather_score,
        "living_weather_risk_score": living_score,

        "alert_score": alert_score,
        "weather_score": weather_score,
        "living_score": living_score,

        "natural_alert_count": alert_detail["natural_alert_count"],
        "high_risk_alert_count": alert_detail["high_risk_alert_count"],
        "weather_warning_count": weather_detail["weather_warning_count"],
        "living_weather_count": living_detail["living_weather_count"],

        "alert_detail": alert_detail,
        "weather_detail": weather_detail,
        "living_detail": living_detail
    }

    return result


def print_safety_score_result(result):
    """
    안전지수 결과를 터미널에 보기 좋게 출력한다.
    """

    print("======================================")
    print("SafeNavi 오늘의 안전지수")
    print("======================================")
    region = result.get("selected_region", "") or "전국"
    print(f"분석 지역: {region}")
    print(f"오늘의 안전 점수: {result['safety_score']}점")
    print(f"위험 점수: {result['risk_score']}점")
    print(f"안전 단계: {result['safety_level']}")
    print()

    print("[점수 구성]")
    print(f"- 긴급재난문자 위험 점수: {result['alert_risk_score']}점")
    print(f"- 기상특보 위험 점수: {result['weather_warning_risk_score']}점")
    print(f"- 생활기상지수 위험 점수: {result['living_weather_risk_score']}점")
    print()

    print("[주요 위험 유형]")
    if result["main_risk_types"]:
        print(", ".join(result["main_risk_types"]))
    else:
        print("주요 위험 유형 없음")
    print()

    print("[권장 행동]")
    for idx, item in enumerate(result["recommended_actions"], start=1):
        print(f"{idx}. {item}")

    print()
    print("[상세 정보]")
    print(f"- 자연재난 문자 수: {result['natural_alert_count']}건")
    print(f"- 고위험 자연재난 문자 수: {result['high_risk_alert_count']}건")
    print(f"- 기상특보 수: {result['weather_warning_count']}건")
    print(f"- 생활기상지수 수: {result['living_weather_count']}건")
    print("======================================")


if __name__ == "__main__":
    result = calculate_today_safety_score(region_name="경기도 용인시")
    print_safety_score_result(result)
