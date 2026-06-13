import re


def extract_region(message, api_region=None):
    """API 지역명을 우선 사용하고, 없으면 문자 원문에서 지역명을 추출한다."""
    if api_region is not None and str(api_region).strip():
        return str(api_region).strip()

    message = str(message)
    two_words = r"([가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도|시)\s+[가-힣]+(?:시|군|구))"
    match = re.search(two_words, message)
    if match:
        return match.group(1)

    one_word = r"([가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도|시|군|구))"
    match = re.search(one_word, message)
    return match.group(1) if match else "지역 미확인"


def contains_any(text, keywords):
    text = str(text)
    return any(keyword in text for keyword in keywords)


def _set_disaster(result, disaster_type, category, risk_level, dangerous, recommended):
    """분석 결과에 공통 재난 정보를 기록한다."""
    result["is_relevant_disaster"] = True
    result["is_natural_disaster"] = category == "자연재난"
    result["disaster_category"] = category
    result["disaster_type"] = disaster_type
    result["risk_level"] = risk_level
    result["dangerous_action"] = dangerous
    result["recommended_action"] = recommended


def analyze_disaster_message(message, api_region=None):
    """
    긴급재난문자를 SafeNavi 서비스용 정보로 변환한다.

    자연재난뿐 아니라 주민 대피와 이동 안전에 직접 영향을 주는
    산불·화재도 '관련 재난'으로 포함한다.
    """
    message = str(message)
    result = {
        "is_relevant_disaster": False,
        "is_natural_disaster": False,
        "disaster_category": "기타",
        "disaster_type": "기타/제외",
        "region": extract_region(message, api_region),
        "risk_level": "낮음",
        "dangerous_action": [],
        "recommended_action": [],
        "easy_summary": ""
    }

    # 산불은 '화재'라는 단어를 함께 포함하는 경우가 많으므로 일반 화재보다 먼저 판정한다.
    if contains_any(message, [
        "산불", "산림화재", "산림 화재", "야산 화재", "야산불",
        "산불 확산", "산불대피", "산림 인접지역", "산림 인접 지역"
    ]):
        _set_disaster(
            result, "산불", "사회재난", "높음",
            ["산림·야산 접근", "연기 진행 방향 이동", "산불 진행 방향으로 대피"],
            ["산림과 인접지역에서 즉시 이탈", "바람을 등지지 말고 산불 진행 방향과 수직으로 이동", "지자체 대피 안내 확인", "가까운 실내 대피시설 확인"]
        )

    # 건축물·시설 화재. 단순 '화재 예방' 홍보문보다 실제 발생·대피 문맥을 우선한다.
    elif contains_any(message, [
        "화재 발생", "불이 났", "불이 나", "건물 화재", "공장 화재",
        "주택 화재", "창고 화재", "시장 화재", "연기 다량", "연기 확산",
        "화재로 인해", "화재 진압", "인근 주민 대피", "대피 바랍니다"
    ]) or ("화재" in message and contains_any(message, ["대피", "연기", "진압", "통제", "발생", "접근 금지"])):
        _set_disaster(
            result, "화재", "사회재난", "높음",
            ["연기 발생 지역 접근", "엘리베이터 이용", "불길이 있는 방향으로 이동"],
            ["119 신고 및 주변에 알리기", "낮은 자세로 비상구·계단 이용", "연기 반대 방향으로 이동", "현장 통제와 지자체 안내 확인"]
        )

    else:
        # 실종·훈련·범죄 등 서비스 목적과 무관한 문자만 제외한다.
        exclude_keywords = [
            "실종", "찾습니다", "배회", "목격", "보이스피싱",
            "훈련", "민방위", "집회", "행사", "범죄", "용의자", "실종자"
        ]
        if contains_any(message, exclude_keywords):
            result["easy_summary"] = make_easy_summary(result)
            return result

        if contains_any(message, ["호우", "폭우", "집중호우", "침수", "하천", "범람", "저지대", "지하차도", "하수도", "배수", "홍수"]):
            _set_disaster(result, "호우/침수", "자연재난", "높음",
                          ["하천변 접근", "지하차도 통행", "저지대 이동"],
                          ["이동 자제", "높은 곳으로 이동", "가까운 대피소 확인"])
        elif contains_any(message, ["폭염", "무더위", "온열질환", "체감온도", "더위", "열사병", "일사병"]):
            _set_disaster(result, "폭염", "자연재난", "주의",
                          ["장시간 야외활동", "한낮 산책", "무리한 운동"],
                          ["무더위쉼터 이동", "수분 섭취", "야외활동 자제"])
        elif contains_any(message, ["한파", "동파", "빙판", "저온", "강추위", "결빙", "한랭질환"]):
            _set_disaster(result, "한파", "자연재난", "주의",
                          ["장시간 외출", "빙판길 이동", "보온 부족"],
                          ["보온 유지", "한파쉼터 확인", "외출 자제"])
        elif contains_any(message, ["지진", "진도", "여진", "흔들림", "낙하물"]):
            _set_disaster(result, "지진", "자연재난", "높음",
                          ["엘리베이터 이용", "건물 외벽 접근", "낙하물 주변 이동"],
                          ["책상 아래 대피", "넓은 공터 이동", "지진옥외대피장소 확인"])
        elif contains_any(message, ["태풍", "강풍", "풍랑", "해안가", "간판", "월파", "높은 파도"]):
            _set_disaster(result, "태풍", "자연재난", "높음",
                          ["외출", "간판 주변 이동", "해안가 접근"],
                          ["실내 대기", "창문 주변 피하기", "안전한 장소 이동"])
        elif contains_any(message, ["대설", "폭설", "눈길", "적설", "빙판길", "제설"]):
            _set_disaster(result, "대설", "자연재난", "주의",
                          ["눈길 운전", "빙판길 보행", "급제동"],
                          ["대중교통 이용", "미끄럼 주의", "외출 자제"])
        elif contains_any(message, ["지진해일", "해일", "쓰나미", "연안 침수"]):
            _set_disaster(result, "지진해일", "자연재난", "높음",
                          ["해안가 접근", "저지대 체류", "방파제 주변 이동"],
                          ["높은 곳으로 이동", "해안가 즉시 이탈", "지진해일 대피장소 확인"])
        elif contains_any(message, ["산사태", "토사", "급경사지", "비탈면", "옹벽"]):
            _set_disaster(result, "산사태", "자연재난", "높음",
                          ["산비탈 접근", "급경사지 주변 이동", "토사 유출 지역 체류"],
                          ["산사태 위험지역 이탈", "안전한 실내 또는 대피소 이동", "지자체 안내 확인"])

    result["easy_summary"] = make_easy_summary(result)
    return result


def make_easy_summary(result):
    if not result.get("is_relevant_disaster", result.get("is_natural_disaster", False)):
        return "이 문자는 SafeNavi 안전점수와 대피소 추천 대상에서 제외됩니다."

    region = result["region"]
    disaster_type = result["disaster_type"]
    recommended = ", ".join(result["recommended_action"])

    if disaster_type == "산불":
        return f"{region}에 산불 관련 위험이 있습니다. 산림과 연기 발생 지역에서 벗어나고, {recommended}을 실천하세요."
    if disaster_type == "화재":
        return f"{region}에 화재 관련 위험이 있습니다. 연기와 불길이 있는 방향을 피하고, {recommended}을 실천하세요."
    if disaster_type == "호우/침수":
        return f"{region}에 침수 위험이 있습니다. 하천변·지하차도·저지대는 피하고, {recommended}을 실천하세요."
    if disaster_type == "폭염":
        return f"{region}에 폭염 위험이 있습니다. 한낮 야외활동을 피하고, {recommended}을 실천하세요."
    if disaster_type == "한파":
        return f"{region}에 한파 위험이 있습니다. 빙판길과 장시간 외출을 조심하고, {recommended}을 실천하세요."
    if disaster_type == "지진":
        return f"{region}에 지진 관련 위험이 있습니다. 엘리베이터와 낙하물을 피하고, {recommended}을 실천하세요."
    if disaster_type == "태풍":
        return f"{region}에 태풍 위험이 있습니다. 외출과 해안가 접근을 피하고, {recommended}을 실천하세요."
    if disaster_type == "대설":
        return f"{region}에 대설 위험이 있습니다. 눈길과 빙판길 이동에 주의하고, {recommended}을 실천하세요."
    if disaster_type == "지진해일":
        return f"{region}에 지진해일 위험이 있습니다. 해안가와 저지대를 벗어나고, {recommended}을 실천하세요."
    if disaster_type == "산사태":
        return f"{region}에 산사태 위험이 있습니다. 산비탈과 급경사지를 피하고, {recommended}을 실천하세요."

    return f"{region}에 {disaster_type} 위험이 있습니다. {recommended}을 실천하세요."


def analyze_alert_row(row, message_col="message", region_col="region"):
    return analyze_disaster_message(row.get(message_col, ""), api_region=row.get(region_col, None))


def result_to_display_text(result):
    relevant = "안전점수 반영" if result.get("is_relevant_disaster") else "기타/제외"
    return (
        f"반영 여부: {relevant}\n"
        f"재난 분류: {result.get('disaster_category', '기타')}\n"
        f"재난 유형: {result['disaster_type']}\n"
        f"지역: {result['region']}\n"
        f"위험도: {result['risk_level']}\n"
        f"권장 행동: {', '.join(result['recommended_action']) if result['recommended_action'] else '없음'}\n"
        f"쉬운 설명: {result['easy_summary']}"
    )


if __name__ == "__main__":
    for sample in [
        "용인시 집중호우로 저지대 침수 우려. 지하차도 통행을 자제 바랍니다.",
        "울산시 산불 확산 중이니 인근 주민은 즉시 대피 바랍니다.",
        "수원시 공장 화재로 연기가 확산 중이니 주변 접근을 금지합니다."
    ]:
        print(result_to_display_text(analyze_disaster_message(sample)))
        print("-" * 40)
