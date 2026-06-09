import re


def extract_region(message, api_region=None):
    """
    재난문자에서 지역명을 추출한다.

    우선순위
    1. API에서 받은 수신지역명(api_region)을 사용
    2. 문자 내용에서 '경기도 용인시', '서울특별시 강남구' 같은 2단어 지역 추출
    3. 문자 내용에서 '용인시', '처인구', '경기도' 같은 단일 지역 추출
    4. 찾지 못하면 '지역 미확인' 반환

    Parameters
    ----------
    message : str
        긴급재난문자 원문
    api_region : str | None
        API에서 제공하는 수신지역명. 예: RCPTN_RGN_NM

    Returns
    -------
    str
        추출된 지역명
    """

    # 1. API에서 받은 지역명이 있으면 가장 우선 사용
    if api_region is not None and str(api_region).strip():
        return str(api_region).strip()

    message = str(message)

    # 2. 광역 + 기초 지역 형태 추출
    # 예: 경기도 용인시, 서울특별시 강남구, 부산광역시 해운대구
    pattern_two_words = r"([가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도|시)\s+[가-힣]+(?:시|군|구))"
    match = re.search(pattern_two_words, message)

    if match:
        return match.group(1)

    # 3. 단일 지역명 추출
    # 예: 용인시, 처인구, 경기도
    pattern_one_word = r"([가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도|시|군|구))"
    match = re.search(pattern_one_word, message)

    if match:
        return match.group(1)

    return "지역 미확인"


def contains_any(text, keywords):
    """
    문장에 특정 키워드가 하나라도 포함되어 있는지 확인한다.
    """
    text = str(text)
    return any(keyword in text for keyword in keywords)


def analyze_disaster_message(message, api_region=None):
    """
    긴급재난문자 내용을 분석하여 SafeNavi 서비스용 결과로 변환한다.

    Parameters
    ----------
    message : str
        긴급재난문자 원문
    api_region : str | None
        API에서 제공하는 수신지역명. 예: RCPTN_RGN_NM

    Returns
    -------
    dict
        분석 결과
    """

    message = str(message)

    result = {
        "is_natural_disaster": False,
        "disaster_type": "기타/제외",
        "region": extract_region(message, api_region),
        "risk_level": "낮음",
        "dangerous_action": [],
        "recommended_action": [],
        "easy_summary": ""
    }

    # 먼저 서비스 제외 문자 판단
    exclude_keywords = [
        "실종", "찾습니다", "배회", "목격", "보이스피싱",
        "훈련", "민방위", "교통통제", "집회", "행사",
        "화재", "산불", "범죄", "용의자", "실종자"
    ]

    # 단, 산불/화재는 사회재난으로 볼 수 있으므로 현재 자연재난 중심 서비스에서는 제외 처리
    if contains_any(message, exclude_keywords):
        result["is_natural_disaster"] = False
        result["disaster_type"] = "기타/제외"
        result["risk_level"] = "낮음"
        result["dangerous_action"] = []
        result["recommended_action"] = []
        result["easy_summary"] = make_easy_summary(result)
        return result

    # 1. 호우/침수
    if contains_any(
        message,
        ["호우", "폭우", "집중호우", "침수", "하천", "범람", "저지대", "지하차도", "하수도", "배수", "홍수"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "호우/침수"
        result["risk_level"] = "높음"
        result["dangerous_action"] = [
            "하천변 접근",
            "지하차도 통행",
            "저지대 이동"
        ]
        result["recommended_action"] = [
            "이동 자제",
            "높은 곳으로 이동",
            "가까운 대피소 확인"
        ]

    # 2. 폭염
    elif contains_any(
        message,
        ["폭염", "무더위", "온열질환", "체감온도", "더위", "열사병", "일사병"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "폭염"
        result["risk_level"] = "주의"
        result["dangerous_action"] = [
            "장시간 야외활동",
            "한낮 산책",
            "무리한 운동"
        ]
        result["recommended_action"] = [
            "무더위쉼터 이동",
            "수분 섭취",
            "야외활동 자제"
        ]

    # 3. 한파
    elif contains_any(
        message,
        ["한파", "동파", "빙판", "저온", "강추위", "결빙", "한랭질환"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "한파"
        result["risk_level"] = "주의"
        result["dangerous_action"] = [
            "장시간 외출",
            "빙판길 이동",
            "보온 부족"
        ]
        result["recommended_action"] = [
            "보온 유지",
            "한파쉼터 확인",
            "외출 자제"
        ]

    # 4. 지진
    elif contains_any(
        message,
        ["지진", "진도", "여진", "흔들림", "낙하물"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "지진"
        result["risk_level"] = "높음"
        result["dangerous_action"] = [
            "엘리베이터 이용",
            "건물 외벽 접근",
            "낙하물 주변 이동"
        ]
        result["recommended_action"] = [
            "책상 아래 대피",
            "넓은 공터 이동",
            "지진옥외대피장소 확인"
        ]

    # 5. 태풍
    elif contains_any(
        message,
        ["태풍", "강풍", "풍랑", "해안가", "간판", "월파", "높은 파도"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "태풍"
        result["risk_level"] = "높음"
        result["dangerous_action"] = [
            "외출",
            "간판 주변 이동",
            "해안가 접근"
        ]
        result["recommended_action"] = [
            "실내 대기",
            "창문 주변 피하기",
            "안전한 장소 이동"
        ]

    # 6. 대설
    elif contains_any(
        message,
        ["대설", "폭설", "눈길", "적설", "빙판길", "제설"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "대설"
        result["risk_level"] = "주의"
        result["dangerous_action"] = [
            "눈길 운전",
            "빙판길 보행",
            "급제동"
        ]
        result["recommended_action"] = [
            "대중교통 이용",
            "미끄럼 주의",
            "외출 자제"
        ]

    # 7. 지진해일/해일
    elif contains_any(
        message,
        ["지진해일", "해일", "쓰나미", "연안 침수"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "지진해일"
        result["risk_level"] = "높음"
        result["dangerous_action"] = [
            "해안가 접근",
            "저지대 체류",
            "방파제 주변 이동"
        ]
        result["recommended_action"] = [
            "높은 곳으로 이동",
            "해안가 즉시 이탈",
            "지진해일 대피장소 확인"
        ]

    # 8. 산사태
    elif contains_any(
        message,
        ["산사태", "토사", "급경사지", "비탈면", "옹벽"]
    ):
        result["is_natural_disaster"] = True
        result["disaster_type"] = "산사태"
        result["risk_level"] = "높음"
        result["dangerous_action"] = [
            "산비탈 접근",
            "급경사지 주변 이동",
            "토사 유출 지역 체류"
        ]
        result["recommended_action"] = [
            "산사태 위험지역 이탈",
            "안전한 실내 또는 대피소 이동",
            "지자체 안내 확인"
        ]

    # 9. 기타 자연재난으로 판단하기 어려운 경우
    else:
        result["is_natural_disaster"] = False
        result["disaster_type"] = "기타/제외"
        result["risk_level"] = "낮음"
        result["dangerous_action"] = []
        result["recommended_action"] = []

    result["easy_summary"] = make_easy_summary(result)

    return result


def make_easy_summary(result):
    """
    분석 결과를 바탕으로 사용자가 이해하기 쉬운 문장을 만든다.
    """

    if not result["is_natural_disaster"]:
        return "이 문자는 자연재난 관련 문자가 아니므로 대피소 추천 대상에서 제외됩니다."

    region = result["region"]
    disaster_type = result["disaster_type"]
    dangerous = ", ".join(result["dangerous_action"])
    recommended = ", ".join(result["recommended_action"])

    if disaster_type == "호우/침수":
        return (
            f"{region}에 비가 많이 와서 침수 위험이 있습니다. "
            f"{dangerous}은 위험할 수 있으니 피하는 것이 좋습니다. "
            f"{recommended}을 실천하고 가까운 대피소를 확인하세요."
        )

    if disaster_type == "폭염":
        return (
            f"{region}에 폭염 위험이 있습니다. "
            f"한낮 야외활동이나 무리한 운동은 피하는 것이 좋습니다. "
            f"{recommended}을 실천하고 가까운 무더위쉼터를 확인하세요."
        )

    if disaster_type == "한파":
        return (
            f"{region}에 한파 위험이 있습니다. "
            f"빙판길 이동과 장시간 외출을 조심해야 합니다. "
            f"{recommended}을 실천하고 가까운 한파쉼터를 확인하세요."
        )

    if disaster_type == "지진":
        return (
            f"{region}에 지진 관련 위험이 있습니다. "
            f"엘리베이터 이용은 피하고 낙하물에 주의해야 합니다. "
            f"{recommended}을 실천하세요."
        )

    if disaster_type == "태풍":
        return (
            f"{region}에 태풍 위험이 있습니다. "
            f"외출을 줄이고 간판, 가로수, 해안가 주변은 피하는 것이 좋습니다. "
            f"{recommended}을 실천하세요."
        )

    if disaster_type == "대설":
        return (
            f"{region}에 대설 위험이 있습니다. "
            f"눈길과 빙판길 이동에 주의해야 합니다. "
            f"{recommended}을 실천하세요."
        )

    if disaster_type == "지진해일":
        return (
            f"{region}에 지진해일 또는 해일 위험이 있습니다. "
            f"해안가와 낮은 지역은 위험할 수 있으니 즉시 벗어나는 것이 좋습니다. "
            f"{recommended}을 실천하세요."
        )

    if disaster_type == "산사태":
        return (
            f"{region}에 산사태 위험이 있습니다. "
            f"산비탈, 급경사지, 토사 유출 지역은 피하는 것이 좋습니다. "
            f"{recommended}을 실천하세요."
        )

    return (
        f"{region}에 {disaster_type} 위험이 있습니다. "
        f"{dangerous}은 위험할 수 있으니 피하고, "
        f"{recommended}을 실천하세요."
    )


def analyze_alert_row(row, message_col="message", region_col="region"):
    """
    DataFrame의 한 행(row)을 분석할 때 사용하는 보조 함수.

    예:
    result = analyze_alert_row(row)

    Parameters
    ----------
    row : pandas.Series 또는 dict
        재난문자 데이터 한 행
    message_col : str
        재난문자 내용 컬럼명
    region_col : str
        지역 컬럼명

    Returns
    -------
    dict
        AI 분석 결과
    """

    message = row.get(message_col, "")
    api_region = row.get(region_col, None)

    return analyze_disaster_message(message, api_region=api_region)


def result_to_display_text(result):
    """
    웹 화면이나 터미널에서 보기 좋게 출력하기 위한 문자열 생성 함수.
    """

    natural_text = "자연재난" if result["is_natural_disaster"] else "기타/제외"

    return (
        f"자연재난 여부: {natural_text}\n"
        f"재난 유형: {result['disaster_type']}\n"
        f"지역: {result['region']}\n"
        f"위험도: {result['risk_level']}\n"
        f"위험 행동: {', '.join(result['dangerous_action']) if result['dangerous_action'] else '없음'}\n"
        f"권장 행동: {', '.join(result['recommended_action']) if result['recommended_action'] else '없음'}\n"
        f"쉬운 설명: {result['easy_summary']}"
    )


if __name__ == "__main__":
    sample_message = (
        "용인시 집중호우로 하천 수위 상승, 저지대 침수 우려. "
        "하천변 및 지하차도 통행을 자제하시기 바랍니다."
    )

    sample_result = analyze_disaster_message(
        message=sample_message,
        api_region=None
    )

    print("AI 재난문자 분석 결과")
    print(result_to_display_text(sample_result))

    print("\n----------------------------------\n")

    sample_result_with_api_region = analyze_disaster_message(
        message="집중호우로 하천 수위 상승, 저지대 침수 우려. 지하차도 통행을 자제하시기 바랍니다.",
        api_region="경기도 용인시"
    )

    print("API 지역값 우선 적용 테스트")
    print(result_to_display_text(sample_result_with_api_region))