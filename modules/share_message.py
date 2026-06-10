import os
import re
import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RECOMMENDED_SHELTERS_PATH = os.path.join(
    BASE_DIR, "data", "processed", "recommended_shelters.csv"
)

ALERTS_ANALYZED_PATH = os.path.join(
    BASE_DIR, "data", "processed", "disaster_alerts_analyzed.csv"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "data", "processed", "share_message.txt"
)


def safe_read_csv(path):
    """
    CSV 파일을 불러온다.
    파일이 없거나 비어 있으면 빈 DataFrame을 반환한다.
    """

    if not os.path.exists(path):
        print(f"[안심 공유] 파일 없음: {path}")
        return pd.DataFrame()

    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def normalize_region_text(text):
    """
    지역명 비교를 위해 문자열을 정리한다.
    예:
    '경기도 용인시' -> '경기도용인시'
    """

    text = str(text)
    text = text.replace("nan", "")
    text = re.sub(r"[^가-힣a-zA-Z0-9]", "", text)
    return text


def make_region_keywords(user_region):
    """
    사용자 지역명에서 재난문자 비교용 키워드를 만든다.

    핵심:
    - '경기도' 같은 광역 지자체명만으로는 매칭하지 않는다.
    - 상세주소가 들어와도 '용인시', '처인구', '용인', '처인'처럼
      시/군/구 단위 키워드를 우선 사용한다.
    - 도로명, 번지, 숫자처럼 재난문자 지역명과 잘 맞지 않는 값은 제외한다.
    """

    if user_region is None or str(user_region).strip() == "":
        return []

    user_region = str(user_region).strip()

    broad_regions = [
        "서울특별시", "부산광역시", "대구광역시", "인천광역시",
        "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
        "경기도", "강원특별자치도", "강원도", "충청북도", "충청남도",
        "전북특별자치도", "전라북도", "전라남도",
        "경상북도", "경상남도", "제주특별자치도", "제주도"
    ]

    ignore_suffixes = ["로", "길", "번길", "대로"]
    keywords = set()
    parts = user_region.split()

    for part in parts:
        cleaned = normalize_region_text(part)

        if not cleaned:
            continue

        if cleaned in broad_regions:
            continue

        # 숫자/번지만 있는 값은 제외
        if cleaned.isdigit():
            continue

        # 도로명은 재난문자 지역 컬럼과 매칭률이 낮으므로 제외
        if any(cleaned.endswith(suffix) for suffix in ignore_suffixes):
            continue

        # 시/군/구/읍/면/동 단위는 적극 사용
        if cleaned.endswith(("시", "군", "구", "읍", "면", "동")):
            keywords.add(cleaned)
            if len(cleaned) > 1:
                keywords.add(cleaned[:-1])
            continue

        # 그 외 단어는 너무 짧은 값만 제외하고 보조 키워드로 사용
        if len(cleaned) >= 2:
            keywords.add(cleaned)

    return [keyword for keyword in keywords if keyword]

def region_matches(alert_region, user_region):
    """
    재난문자 지역이 사용자 지역과 관련 있는지 판단한다.

    개선점:
    - '경기도'만 같다고 같은 지역으로 보지 않는다.
    - '용인시', '용인' 같은 시/군/구 단위가 포함될 때만 매칭한다.
    """

    if user_region is None or str(user_region).strip() == "":
        return True

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


def get_latest_main_disaster_info(alerts_df, user_region=None):
    """
    AI 분석된 재난문자에서 사용자 지역 기준 주요 자연재난 정보를 가져온다.
    사용자 지역에 해당하는 자연재난 문자가 없으면 기본값을 반환한다.
    """

    default_result = {
        "has_local_alert": False,
        "main_disaster_type": "주변 직접 재난문자 없음",
        "risk_level": "낮음",
        "region": user_region if user_region else "사용자 위치 주변",
        "easy_summary": "현재 사용자 지역과 직접 관련된 자연재난 문자는 확인되지 않았습니다."
    }

    natural_df = filter_natural_alerts_by_region(
        alerts_df=alerts_df,
        user_region=user_region
    )

    if natural_df.empty:
        return default_result

    # created_at이 있으면 최신순 정렬
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
    easy_summary = latest.get("easy_summary", "")

    if pd.isna(easy_summary) or str(easy_summary).strip() == "":
        easy_summary = f"{region}에 {main_type} 관련 재난문자가 확인되었습니다."

    return {
        "has_local_alert": True,
        "main_disaster_type": str(main_type),
        "risk_level": str(risk_level),
        "region": str(region),
        "easy_summary": str(easy_summary)
    }


def get_top_shelter_info(recommended_df):
    """
    추천 대피소 결과에서 1순위 대피소 정보를 가져온다.
    """

    default_result = {
        "name": "추천 대피소 없음",
        "address": "주소 정보 없음",
        "distance_km": None,
        "shelter_type": "대피시설",
        "recommend_score": None
    }

    if recommended_df.empty:
        return default_result

    top = recommended_df.iloc[0]

    name = top.get("name", "추천 대피소 없음")

    address = top.get("display_address", top.get("address", "주소 정보 없음"))

    if pd.isna(address) or str(address).strip().lower() == "nan" or str(address).strip() == "":
        sido = top.get("sido", "")
        sigungu = top.get("sigungu", "")

        sido = "" if pd.isna(sido) else str(sido).strip()
        sigungu = "" if pd.isna(sigungu) else str(sigungu).strip()

        address = f"{sido} {sigungu}".strip()

        if address == "":
            address = "주소 정보 없음"

    distance_km = top.get("distance_km", None)
    shelter_type = top.get("shelter_type", "대피시설")
    recommend_score = top.get("recommend_score", None)

    return {
        "name": str(name),
        "address": str(address),
        "distance_km": distance_km,
        "shelter_type": str(shelter_type),
        "recommend_score": recommend_score
    }


def make_action_sentence(disaster_type, has_local_alert=True):
    """
    재난 유형에 맞는 행동 문장을 생성한다.
    """

    if not has_local_alert:
        return "현재 사용자 지역과 직접 관련된 자연재난 문자는 없지만, 주변 기상특보와 안전 안내를 계속 확인할 예정입니다."

    disaster_type = str(disaster_type)

    if disaster_type == "호우/침수":
        return "하천변, 지하차도, 저지대 이동은 피하고 안전한 곳에 머무를 예정입니다."

    if disaster_type == "태풍":
        return "외출을 줄이고 창문, 간판, 가로수 주변을 피하면서 실내에 머무를 예정입니다."

    if disaster_type == "산사태":
        return "산비탈, 급경사지, 토사 유출 위험지역을 피하고 안전한 장소로 이동할 예정입니다."

    if disaster_type == "폭염":
        return "야외활동을 줄이고 물을 자주 마시며 무더위쉼터나 실내에 머무를 예정입니다."

    if disaster_type == "한파":
        return "보온을 유지하고 빙판길 이동을 조심하며 장시간 외출을 피할 예정입니다."

    if disaster_type == "대설":
        return "눈길과 빙판길 이동을 조심하고 가능한 외출을 줄일 예정입니다."

    if disaster_type == "지진":
        return "낙하물과 건물 외벽을 피하고 넓은 공간 또는 지정 대피장소를 확인할 예정입니다."

    if disaster_type == "지진해일":
        return "해안가와 낮은 지역을 피하고 높은 곳이나 지정 대피장소로 이동할 예정입니다."

    return "주변 상황을 확인하고 지자체 안내에 따라 안전하게 이동할 예정입니다."


def format_distance(distance_km):
    """
    거리 값을 보기 좋은 문자열로 변환한다.
    """

    try:
        distance = float(distance_km)
        return f"약 {distance:.2f}km"
    except Exception:
        return "거리 정보 없음"


def format_score(score):
    """
    추천 점수를 보기 좋은 문자열로 변환한다.
    """

    try:
        value = float(score)
        return f"{value:.1f}점"
    except Exception:
        return "점수 정보 없음"


def generate_share_message(
    user_status="안전",
    user_region="경기도 용인시",
    include_shelter=True,
    tone="normal",
    recommended_df=None
):
    """
    가족에게 보낼 안심 공유 문구를 생성한다.

    Parameters
    ----------
    user_status : str
        사용자 상태. 예: 안전, 이동 중, 대피소 확인 완료
    user_region : str
        사용자 현재 위치 지역명. 예: 경기도 용인시
    include_shelter : bool
        추천 대피소 정보를 포함할지 여부
    tone : str
        normal 또는 short
    recommended_df : pandas.DataFrame or None
        공유 페이지에서 선택한 현재 위치/주소 기준으로 새로 계산한 추천 대피소 결과.
        None이면 기존 recommended_shelters.csv를 읽는다.
    """

    alerts_df = safe_read_csv(ALERTS_ANALYZED_PATH)

    if recommended_df is None:
        recommended_df = safe_read_csv(RECOMMENDED_SHELTERS_PATH)
    elif not isinstance(recommended_df, pd.DataFrame):
        recommended_df = pd.DataFrame(recommended_df)

    disaster_info = get_latest_main_disaster_info(
        alerts_df=alerts_df,
        user_region=user_region
    )

    shelter_info = get_top_shelter_info(recommended_df)

    has_local_alert = disaster_info["has_local_alert"]
    disaster_type = disaster_info["main_disaster_type"]
    region = disaster_info["region"]
    risk_level = disaster_info["risk_level"]
    easy_summary = disaster_info["easy_summary"]

    action_sentence = make_action_sentence(
        disaster_type=disaster_type,
        has_local_alert=has_local_alert
    )

    if tone == "short":
        if has_local_alert:
            first_line = f"나 {user_status}해요. 현재 {region}에 {disaster_type} 위험 알림이 있어 확인했습니다."
        else:
            first_line = f"나 {user_status}해요. 현재 {user_region} 주변에 직접 관련된 자연재난 문자는 확인되지 않았습니다."

        if include_shelter and shelter_info["name"] != "추천 대피소 없음":
            message = (
                f"[SafeNavi 안심 공유]\n"
                f"{first_line}\n"
                f"가까운 대피소는 {shelter_info['name']}이며, 현재 위치에서 {format_distance(shelter_info['distance_km'])} 떨어져 있습니다.\n"
                f"{action_sentence}"
            )
        else:
            message = (
                f"[SafeNavi 안심 공유]\n"
                f"{first_line}\n"
                f"{action_sentence}"
            )

        return message

    # default message
    message_lines = []

    message_lines.append("[SafeNavi 안심 공유]")
    message_lines.append(f"나 {user_status}해요.")
    message_lines.append("")

    if has_local_alert:
        message_lines.append(
            f"현재 {region}에 {disaster_type} 관련 알림이 확인되었습니다."
        )
        message_lines.append(f"위험도는 '{risk_level}'으로 분석되었습니다.")
        message_lines.append("")
        message_lines.append(f"재난문자 요약: {easy_summary}")
    else:
        message_lines.append(
            f"현재 {user_region} 주변에 직접 관련된 자연재난 문자는 확인되지 않았습니다."
        )
        message_lines.append("다만 주변 상황 확인을 위해 가까운 대피소와 안전 정보를 확인했습니다.")
        message_lines.append("")
        message_lines.append(f"안내 요약: {easy_summary}")

    message_lines.append("")

    if include_shelter and shelter_info["name"] != "추천 대피소 없음":
        message_lines.append("[확인한 대피소]")
        message_lines.append(f"- 대피소명: {shelter_info['name']}")
        message_lines.append(f"- 주소: {shelter_info['address']}")
        message_lines.append(f"- 유형: {shelter_info['shelter_type']}")
        message_lines.append(f"- 현재 위치와의 거리: {format_distance(shelter_info['distance_km'])}")
        message_lines.append(f"- 추천 점수: {format_score(shelter_info['recommend_score'])}")
        message_lines.append("")

    message_lines.append("[내 행동]")
    message_lines.append(action_sentence)
    message_lines.append("")
    message_lines.append("걱정하지 않도록 상황이 바뀌면 다시 연락할게요.")

    return "\n".join(message_lines)


def save_share_message(message):
    """
    생성된 공유 문구를 txt 파일로 저장한다.
    """

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        file.write(message)

    print(f"[안심 공유] 메시지 저장 완료: {OUTPUT_PATH}")


def print_share_message(message):
    """
    공유 문구를 터미널에 출력한다.
    """

    print("======================================")
    print("SafeNavi 가족 안심 공유 문구")
    print("======================================")
    print(message)
    print("======================================")


if __name__ == "__main__":
    # 사용자 현재 위치 지역명 기준으로 재난문자를 필터링
    # 테스트 좌표가 용인이므로 user_region도 용인으로 맞춤
    message = generate_share_message(
        user_status="안전",
        user_region="경기도 용인시",
        include_shelter=True,
        tone="normal"
    )

    print_share_message(message)
    save_share_message(message)

    print()
    print("[짧은 공유 문구]")
    short_message = generate_share_message(
        user_status="안전",
        user_region="경기도 용인시",
        include_shelter=True,
        tone="short"
    )
    print(short_message)