import os
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

    natural_df = df[df["is_natural_disaster"] == True]

    natural_count = len(natural_df)

    high_risk_count = 0
    if "ai_risk_level" in natural_df.columns:
        high_risk_count = len(natural_df[natural_df["ai_risk_level"] == "높음"])

    score = natural_count * 5 + high_risk_count * 3
    score = min(score, 45)

    main_types = []

    if not natural_df.empty and "ai_disaster_type" in natural_df.columns:
        main_types = (
            natural_df["ai_disaster_type"]
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

    score = min(score, 30)

    warning_levels = []
    if "warning_level" in df.columns:
        warning_levels = (
            df["warning_level"]
            .dropna()
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

    if not recommendations:
        if level == "위험":
            recommendations.append("현재 위험 수준이 높으니 외출을 자제하고 공식 안내를 확인하세요.")
        elif level == "주의":
            recommendations.append("생활권 주변의 기상특보와 재난문자를 확인하세요.")
        else:
            recommendations.append("현재 큰 위험 요인은 없지만 최신 재난문자를 확인하세요.")

    # 중복 제거
    unique_recommendations = []
    for item in recommendations:
        if item not in unique_recommendations:
            unique_recommendations.append(item)

    return unique_recommendations[:5]


def calculate_today_safety_score():
    """
    오늘의 안전지수를 계산한다.

    사용 데이터:
    - disaster_alerts_analyzed.csv
    - weather_warnings.csv
    - living_weather.csv
    """

    alerts_df = safe_read_csv(DISASTER_ALERTS_ANALYZED_PATH)
    weather_df = safe_read_csv(WEATHER_WARNINGS_PATH)
    living_df = safe_read_csv(LIVING_WEATHER_PATH)

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

    # 중복 제거
    main_risk_types = list(dict.fromkeys([x for x in main_risk_types if x and x != "기타"]))

    recommendations = make_recommendations(
        level=safety_level,
        main_risk_types=main_risk_types
    )

    result = {
        "safety_score": safety_score,
        "risk_score": total_risk_score,
        "safety_level": safety_level,
        "main_risk_types": main_risk_types,
        "recommendations": recommendations,
        "alert_score": alert_score,
        "weather_score": weather_score,
        "living_score": living_score,
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
    print(f"오늘의 안전 점수: {result['safety_score']}점")
    print(f"위험 점수: {result['risk_score']}점")
    print(f"안전 단계: {result['safety_level']}")
    print()

    print("[점수 구성]")
    print(f"- 긴급재난문자 위험 점수: {result['alert_score']}점")
    print(f"- 기상특보 위험 점수: {result['weather_score']}점")
    print(f"- 생활기상지수 위험 점수: {result['living_score']}점")
    print()

    print("[주요 위험 유형]")
    if result["main_risk_types"]:
        print(", ".join(result["main_risk_types"]))
    else:
        print("주요 위험 유형 없음")
    print()

    print("[권장 행동]")
    for idx, item in enumerate(result["recommendations"], start=1):
        print(f"{idx}. {item}")

    print()
    print("[상세 정보]")
    print(f"- 자연재난 문자 수: {result['alert_detail']['natural_alert_count']}건")
    print(f"- 고위험 자연재난 문자 수: {result['alert_detail']['high_risk_alert_count']}건")
    print(f"- 기상특보 수: {result['weather_detail']['weather_warning_count']}건")
    print(f"- 생활기상지수 수: {result['living_detail']['living_weather_count']}건")
    print("======================================")


if __name__ == "__main__":
    result = calculate_today_safety_score()
    print_safety_score_result(result)