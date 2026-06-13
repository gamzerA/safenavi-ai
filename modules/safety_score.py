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


def get_relevant_alerts(df):
    """
    안전점수에 반영할 재난문자를 반환한다.

    우선 is_relevant_disaster를 사용하고, 이전 CSV와의 호환을 위해
    is_natural_disaster=True 또는 재난유형이 화재·산불인 행도 포함한다.
    """
    if df.empty:
        return df.copy()

    mask = pd.Series(False, index=df.index)

    if "is_relevant_disaster" in df.columns:
        mask = mask | df["is_relevant_disaster"].apply(is_true_value)

    if "is_natural_disaster" in df.columns:
        mask = mask | df["is_natural_disaster"].apply(is_true_value)

    type_col = next(
        (col for col in ["ai_disaster_type", "disaster_type"] if col in df.columns),
        None
    )
    if type_col:
        mask = mask | df[type_col].fillna("").astype(str).isin(["화재", "산불"])

    return df[mask].copy()


def score_from_disaster_alerts(df):
    """
    AI 분석된 긴급재난문자 위험점수를 계산한다.

    자연재난과 주민 대피에 직접 영향을 주는 화재·산불을 포함한다.
    - 반영 대상 문자 1건당 5점
    - 위험도 '높음' 1건당 추가 3점
    - 최대 45점
    """
    relevant_df = get_relevant_alerts(df)

    if relevant_df.empty:
        return 0, {
            "relevant_alert_count": 0,
            "natural_alert_count": 0,
            "fire_alert_count": 0,
            "wildfire_alert_count": 0,
            "high_risk_alert_count": 0,
            "main_disaster_types": []
        }

    type_col = next(
        (col for col in ["ai_disaster_type", "disaster_type"] if col in relevant_df.columns),
        None
    )
    risk_col = next(
        (col for col in ["ai_risk_level", "risk_level"] if col in relevant_df.columns),
        None
    )

    relevant_count = len(relevant_df)
    high_risk_count = 0
    if risk_col:
        high_risk_count = relevant_df[risk_col].fillna("").astype(str).str.contains("높음", na=False).sum()

    fire_count = 0
    wildfire_count = 0
    main_types = []
    if type_col:
        types = relevant_df[type_col].fillna("").astype(str)
        fire_count = int((types == "화재").sum())
        wildfire_count = int((types == "산불").sum())
        main_types = types.replace("", pd.NA).dropna().value_counts().head(3).index.tolist()

    score = min(relevant_count * 5 + int(high_risk_count) * 3, 45)

    return score, {
        "relevant_alert_count": relevant_count,
        # 기존 app.py/템플릿 호환용 이름
        "natural_alert_count": relevant_count,
        "fire_alert_count": fire_count,
        "wildfire_alert_count": wildfire_count,
        "high_risk_alert_count": int(high_risk_count),
        "main_disaster_types": main_types
    }

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

    if "산불" in main_risk_types:
        recommendations.extend([
            "산림과 야산, 연기 발생 지역에서 즉시 벗어나세요.",
            "산불 진행 방향과 바람을 확인하고 지자체 대피 안내를 따르세요.",
            "차량보다 지정 대피장소나 안전한 실내시설을 우선 확인하세요."
        ])

    if "화재" in main_risk_types:
        recommendations.extend([
            "연기와 불길이 있는 방향을 피하고 낮은 자세로 이동하세요.",
            "엘리베이터 대신 비상계단과 비상구를 이용하세요.",
            "119와 현장 통제요원의 안내를 우선 따르세요."
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



def first_existing_row_value(row, columns, default=""):
    """
    여러 후보 컬럼 중 값이 존재하는 첫 번째 값을 반환한다.
    재난문자 CSV의 컬럼명이 수집 단계에 따라 달라도 화면에 표시할 수 있게 한다.
    """

    for col in columns:
        if col not in row.index:
            continue

        value = row.get(col, default)

        if value is None or pd.isna(value):
            continue

        text = str(value).strip()

        if text and text.lower() != "nan":
            return text

    return default


def format_alert_datetime(value):
    """
    재난문자 발송 시각을 화면 표시용 문자열로 정리한다.
    변환할 수 없으면 원본 문자열을 반환한다.
    """

    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if not text or text.lower() == "nan":
        return ""

    parsed = pd.to_datetime(text, errors="coerce")

    if pd.isna(parsed):
        return text

    return parsed.strftime("%Y-%m-%d %H:%M")


def find_alert_message_value(row):
    """
    재난문자 원문 컬럼명이 데이터 수집 방식에 따라 달라도
    실제 문자 본문을 최대한 찾아 반환한다.

    1. 알려진 메시지 컬럼명을 먼저 확인한다.
    2. 컬럼명에 msg/message/content/문자/내용이 포함된 컬럼을 확인한다.
    3. 그래도 찾지 못하면 메타데이터가 아닌 긴 문자열을 본문 후보로 사용한다.
    """

    known_candidates = [
        "message", "msg", "MSG_CN", "msg_cn", "msgCn",
        "message_content", "message_text", "msg_content",
        "content", "contents", "text", "body",
        "DSSTR_MSG_CN", "dsstr_msg_cn", "DISASTER_MSG",
        "재난문자", "문자내용", "내용"
    ]

    value = first_existing_row_value(row, known_candidates, default="")
    if value:
        return value

    keyword_candidates = []
    for col in row.index:
        normalized_col = str(col).lower().replace("_", "")
        if any(keyword in normalized_col for keyword in [
            "message", "msg", "content", "text", "body", "문자", "내용"
        ]):
            keyword_candidates.append(col)

    value = first_existing_row_value(row, keyword_candidates, default="")
    if value:
        return value

    excluded_columns = {
        "is_natural_disaster", "ai_disaster_type", "disaster_type",
        "ai_risk_level", "risk_level", "ai_region", "region",
        "RCPTN_RGN_NM", "rcptn_rgn_nm", "created_at", "date",
        "id", "sn", "serial_no", "source", "lat", "lon",
        "latitude", "longitude"
    }

    fallback_values = []

    for col in row.index:
        if str(col) in excluded_columns:
            continue

        raw_value = row.get(col, "")
        if raw_value is None or pd.isna(raw_value):
            continue

        text = str(raw_value).strip()
        if not text or text.lower() == "nan":
            continue

        # 실제 재난문자는 보통 비교적 긴 문장이다.
        if len(text) >= 20:
            fallback_values.append(text)

    if not fallback_values:
        return ""

    return max(fallback_values, key=len)


def build_local_alerts(alerts_df, limit=5):
    """
    선택 지역으로 필터링된 재난문자 중 안전점수에 반영되는
    안전점수 반영 재난문자 원문을 최신순으로 정리한다.

    동일한 문자 원문은 한 번만 표시한다.
    """

    if alerts_df.empty:
        return []

    natural_df = get_relevant_alerts(alerts_df)

    if natural_df.empty:
        return []

    datetime_candidates = [
        "created_at", "CREATED_AT", "crt_dt", "CRT_DT",
        "send_time", "sent_at", "reg_date", "date",
        "CREAT_DT", "create_date", "createdAt"
    ]

    sort_col = next(
        (candidate for candidate in datetime_candidates if candidate in natural_df.columns),
        None
    )

    if sort_col:
        natural_df["_alert_sort_time"] = pd.to_datetime(
            natural_df[sort_col],
            errors="coerce"
        )
        natural_df = natural_df.sort_values(
            by="_alert_sort_time",
            ascending=False,
            na_position="last"
        )

    region_candidates = [
        "ai_region", "region", "RCPTN_RGN_NM", "rcptn_rgn_nm",
        "area", "location", "AREA_NM", "region_name"
    ]
    disaster_candidates = [
        "ai_disaster_type", "disaster_type", "type"
    ]
    risk_candidates = [
        "ai_risk_level", "risk_level"
    ]
    summary_candidates = [
        "easy_summary", "summary", "ai_summary"
    ]

    seen_messages = set()
    local_alerts = []

    for _, row in natural_df.iterrows():
        message = find_alert_message_value(row)

        if not message:
            # 점수에는 포함됐지만 원문 컬럼을 찾지 못한 경우도
            # 화면에서 완전히 사라지지 않도록 안내 문구를 표시한다.
            message = "재난문자 원문 컬럼을 확인하지 못했습니다. 데이터 컬럼 구성을 확인해주세요."

        normalized_message = re.sub(r"\s+", " ", str(message)).strip()

        if normalized_message in seen_messages:
            continue

        seen_messages.add(normalized_message)

        created_at = first_existing_row_value(
            row,
            datetime_candidates,
            default=""
        )

        local_alerts.append(
            {
                "message": str(message),
                "created_at": format_alert_datetime(created_at),
                "region": first_existing_row_value(
                    row,
                    region_candidates,
                    default="지역 정보 없음"
                ),
                "disaster_type": first_existing_row_value(
                    row,
                    disaster_candidates,
                    default="재난"
                ),
                "risk_level": first_existing_row_value(
                    row,
                    risk_candidates,
                    default="주의"
                ),
                "easy_summary": first_existing_row_value(
                    row,
                    summary_candidates,
                    default=""
                )
            }
        )

        if len(local_alerts) >= limit:
            break

    return local_alerts


def get_score_formula_info():
    """
    화면 하단에 표시할 현재 안전점수 산출 기준을 반환한다.

    현재 모델은 정부기관의 단일 표준 산식이 아니라,
    공식 데이터의 위험 단계와 정보의 직접성을 이용한
    규칙 기반 가중합 휴리스틱 모델이다.
    """

    return {
        "model_name": "규칙 기반 가중합 위험평가 모델",
        "risk_formula": (
            "총 위험점수 = 재난문자 위험점수 + "
            "기상특보 위험점수 + 생활기상지수 위험점수"
        ),
        "safety_formula": "안전점수 = 100 - 총 위험점수",
        "alert_formula": (
            "재난문자 위험점수 = "
            "min(자연재난 문자 수 × 5 + 고위험 문자 수 × 3, 45)"
        ),
        "weather_formula": (
            "경보 25점, 주의보 15점, 예비특보·정보 8점의 합계 "
            "(최대 30점)"
        ),
        "living_formula": (
            "생활기상지수 값 80 이상 10점, 50 이상 6점, "
            "30 이상 3점의 합계(최대 25점)"
        ),
        "basis": (
            "긴급재난문자는 특정 지역의 실제 상황을 직접 전달하므로 "
            "가장 높은 최대 배점을 두고, 기상특보는 공식 주의보·경보 "
            "단계를 반영하며, 생활기상지수는 일상생활 위험을 보완하는 "
            "지표로 사용합니다."
        ),
        "notice": (
            "현재 세부 배점은 서비스 초기 설계를 위한 설명 가능한 "
            "휴리스틱 기준이며 정부의 공식 재난등급이나 피해예측 결과를 "
            "대체하지 않습니다."
        )
    }



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

    # 화면에 표시할 해당 지역 자연재난 문자 원문
    local_alerts = build_local_alerts(alerts_df, limit=5)

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

        "relevant_alert_count": alert_detail.get("relevant_alert_count", alert_detail["natural_alert_count"]),
        "natural_alert_count": alert_detail["natural_alert_count"],
        "fire_alert_count": alert_detail.get("fire_alert_count", 0),
        "wildfire_alert_count": alert_detail.get("wildfire_alert_count", 0),
        "high_risk_alert_count": alert_detail["high_risk_alert_count"],
        "weather_warning_count": weather_detail["weather_warning_count"],
        "living_weather_count": living_detail["living_weather_count"],

        "local_alerts": local_alerts,
        "score_formula": get_score_formula_info(),

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
