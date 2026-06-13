
import os
import re
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACTION_GUIDES_PATH = os.path.join(
    BASE_DIR,
    "data",
    "processed",
    "action_guides.csv"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR,
    "data",
    "processed",
    "rag_search_results.csv"
)


# 기본 함수

def safe_read_csv(path):
    """CSV 파일을 불러온다."""
    if not os.path.exists(path):
        print(f"[행동요령 RAG] 파일 없음: {path}")
        return pd.DataFrame()

    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            return pd.read_csv(path, encoding="cp949")
        except Exception as e:
            print(f"[행동요령 RAG] CSV 인코딩 오류: {e}")
            return pd.DataFrame()
    except pd.errors.EmptyDataError:
        print(f"[행동요령 RAG] 빈 CSV 파일: {path}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[행동요령 RAG] CSV 읽기 오류: {e}")
        return pd.DataFrame()


def normalize_text(text):
    """검색 비교를 위해 텍스트를 정리한다."""
    text = "" if pd.isna(text) else str(text)
    text = text.lower()
    text = re.sub(r"[^가-힣a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_korean_simple(text):
    """간단한 키워드 토큰화 함수."""
    text = normalize_text(text)
    tokens = text.split()
    return [token for token in tokens if len(token) >= 2]


def contains_any(text, keywords):
    """텍스트에 키워드 중 하나라도 포함되어 있는지 확인한다."""
    text = "" if pd.isna(text) else str(text)
    return any(keyword in text for keyword in keywords)


def first_existing_value(row, columns):
    """여러 후보 컬럼 중 값이 존재하는 첫 번째 값을 반환한다."""
    for col in columns:
        if col in row.index:
            value = row.get(col, "")
            if not pd.isna(value) and str(value).strip():
                return value
    return ""



# CSV 컬럼 정리

def normalize_guide_columns(df):
    """
    action_guides.csv의 컬럼명이 프로젝트마다 달라도
    내부에서는 guide_id, disaster_type, title, content, easy_content, keywords로 통일한다.
    """
    required_cols = ["guide_id", "disaster_type", "title", "content", "easy_content", "keywords"]

    if df.empty:
        return pd.DataFrame(columns=required_cols)

    normalized_rows = []

    for idx, row in df.iterrows():
        disaster_type = first_existing_value(
            row,
            [
                "disaster_type",
                "재난유형",
                "재난 유형",
                "type",
                "category",
                "clsf",
                "dstype"
            ]
        )

        title = first_existing_value(
            row,
            [
                "title",
                "제목",
                "행동요령명",
                "요령명",
                "name",
                "subject"
            ]
        )

        content = first_existing_value(
            row,
            [
                "content",
                "내용",
                "행동요령",
                "국민행동요령",
                "manual",
                "detail",
                "description",
                "text"
            ]
        )

        easy_content = first_existing_value(
            row,
            [
                "easy_content",
                "쉬운내용",
                "요약",
                "summary",
                "simple_content"
            ]
        )

        keywords = first_existing_value(
            row,
            [
                "keywords",
                "keyword",
                "키워드",
                "검색어",
                "tags"
            ]
        )

        guide_id = first_existing_value(
            row,
            [
                "guide_id",
                "id",
                "번호",
                "콘텐츠번호",
                "content_id"
            ]
        )

        if not str(guide_id).strip():
            guide_id = f"csv_{idx + 1:05d}"

        combined_for_empty_check = f"{disaster_type} {title} {content} {easy_content} {keywords}".strip()
        if not combined_for_empty_check:
            continue

        normalized_rows.append(
            {
                "guide_id": str(guide_id),
                "disaster_type": str(disaster_type),
                "title": str(title),
                "content": str(content),
                "easy_content": str(easy_content),
                "keywords": str(keywords)
            }
        )

    return pd.DataFrame(normalized_rows, columns=required_cols).fillna("")



# 내장 행동요령
def get_builtin_guides():
    """
    action_guides.csv에 없는 생활안전/사회재난 행동요령을 보완하기 위한 내장 데이터.
    특히 화재는 자연재난 CSV에 없을 수 있어 기본 행동요령을 포함한다.
    """
    rows = [
        {
            "guide_id": "builtin_fire_001",
            "disaster_type": "화재",
            "title": "화재 발생 시 기본 행동요령",
            "content": (
                "화재가 발생하면 즉시 주변에 알리고 119에 신고합니다. "
                "젖은 수건이나 옷으로 코와 입을 가리고 낮은 자세로 비상구를 이용해 대피합니다. "
                "엘리베이터는 정전이나 연기 유입 위험이 있으므로 이용하지 않습니다. "
                "연기가 많거나 불길이 큰 경우 무리하게 진입하지 말고 안전한 장소로 이동합니다."
            ),
            "easy_content": (
                "화재가 나면 먼저 주변에 알리고 119에 신고하세요. "
                "연기가 있으면 낮은 자세로 이동하고, 젖은 수건 등으로 코와 입을 가립니다. "
                "엘리베이터는 사용하지 말고 계단과 비상구를 이용해 대피하세요."
            ),
            "keywords": "화재 불 연기 119 비상구 대피 엘리베이터 금지 낮은자세 젖은수건"
        },
        {
            "guide_id": "builtin_fire_002",
            "disaster_type": "화재",
            "title": "화재 시 연기 대피 행동요령",
            "content": (
                "화재로 연기가 발생하면 연기를 직접 마시지 않도록 코와 입을 막고 낮은 자세로 이동합니다. "
                "문을 열기 전 손잡이가 뜨거운지 확인하고, 뜨거우면 다른 대피로를 찾습니다. "
                "시야가 확보되지 않으면 벽을 짚고 이동하며, 안전한 장소에서 구조를 요청합니다."
            ),
            "easy_content": (
                "연기가 많을 때는 낮은 자세로 이동하고 코와 입을 막으세요. "
                "문손잡이가 뜨거우면 문을 열지 말고 다른 대피로를 찾으세요. "
                "안전한 곳에서 119에 구조를 요청하는 것이 좋습니다."
            ),
            "keywords": "화재 연기 대피 낮은자세 문손잡이 뜨거움 구조요청 119 질식"
        },
        {
            "guide_id": "builtin_fire_003",
            "disaster_type": "화재",
            "title": "소화기 사용 및 초기 화재 대응",
            "content": (
                "초기 화재이고 자신의 안전이 확보된 경우에만 소화기를 사용합니다. "
                "소화기는 안전핀을 뽑고, 노즐을 불이 난 곳의 아래쪽으로 향하게 한 뒤 손잡이를 눌러 사용합니다. "
                "불길이 커지거나 연기가 많으면 소화를 시도하지 말고 즉시 대피합니다."
            ),
            "easy_content": (
                "작은 초기 화재일 때만 소화기를 사용하세요. "
                "불길이 크거나 연기가 많으면 소화하려고 무리하지 말고 바로 대피해야 합니다."
            ),
            "keywords": "화재 소화기 초기화재 안전핀 노즐 대피 불길 연기 진압"
        }
    ]

    return pd.DataFrame(rows)



# 재난 유형 / 상황 유형 분석
def detect_disaster_type(question):
    """사용자 질문에서 재난 유형을 추정한다."""
    question = "" if pd.isna(question) else str(question)

    disaster_keywords = {
        "호우/침수": [
            "호우", "폭우", "집중호우", "침수", "홍수", "하천", "범람",
            "저지대", "지하차도", "침수도로", "침수된 도로", "물", "비", "장마", "빗물"
        ],
        "태풍": [
            "태풍", "강풍", "풍랑", "해안가", "간판", "창문", "유리창", "바람", "월파"
        ],
        "폭염": [
            "폭염", "무더위", "온열질환", "더위", "열사병", "일사병",
            "체감온도", "운동", "야외활동", "밖에서 운동"
        ],
        "한파": [
            "한파", "동파", "빙판", "저온", "강추위", "한랭질환", "추위"
        ],
        "대설": [
            "대설", "폭설", "눈", "눈길", "적설", "빙판길", "제설", "결빙"
        ],
        "지진": [
            "지진", "진도", "여진", "흔들림", "낙하물", "책상", "탁자"
        ],
        "지진해일": [
            "지진해일", "해일", "쓰나미", "연안", "해안", "방파제"
        ],
        "산사태": [
            "산사태", "토사", "급경사지", "비탈면", "옹벽", "산비탈"
        ],
        "낙뢰": [
            "낙뢰", "번개", "벼락", "천둥"
        ],
        "황사": [
            "황사", "미세먼지", "먼지", "마스크"
        ],
        "화재": [
            "화재", "불", "불이야", "연기", "소방", "소화기", "비상구",
            "119", "엘리베이터", "승강기", "가스", "폭발", "화상"
        ]
    }

    scores = {}

    for disaster_type, keywords in disaster_keywords.items():
        score = 0

        for keyword in keywords:
            if keyword in question:
                if keyword in [
                    "지하차도", "침수", "태풍", "폭염", "화재",
                    "연기", "소화기", "엘리베이터", "승강기"
                ]:
                    score += 3
                else:
                    score += 1

        if score > 0:
            scores[disaster_type] = score

    if not scores:
        return "기타"

    return max(scores, key=scores.get)


def detect_situation_type(question):
    """
    사용자 질문이 어느 시점의 행동요령을 묻는지 판단한다.

    반환값:
    - before: 사전준비 / 예보 시
    - during: 특보 중 / 발생 시
    - after: 이후 / 지나간 후
    - general: 일반 질문
    """
    question = "" if pd.isna(question) else str(question)

    before_keywords = [
        "미리", "준비", "사전", "예보", "오기 전", "발생 전", "대비", "준비물", "챙겨"
    ]

    during_keywords = [
        "때", "중", "발생", "특보", "지금", "현재", "해도", "되나요", "위험",
        "어떻게", "피해야", "가도", "지나가도", "있어도", "운동", "산책",
        "외출", "창문", "지하차도", "엘리베이터", "승강기", "연기", "불", "화재"
    ]

    after_keywords = [
        "이후", "끝난 후", "지나간 후", "지나간 뒤", "끝나고", "복구", "피해 신고", "정리"
    ]

    if any(keyword in question for keyword in after_keywords):
        return "after"

    if any(keyword in question for keyword in before_keywords):
        return "before"

    if any(keyword in question for keyword in during_keywords):
        return "during"

    return "general"


def detect_question_intents(question):
    """질문의 세부 의도를 분석한다."""
    question = "" if pd.isna(question) else str(question)
    intents = []

    if contains_any(question, ["지하차도", "침수도로", "침수된 도로", "도로 지나", "지나가도"]):
        intents.append("underground_road")

    if contains_any(question, ["창문", "유리창", "창가", "창문 근처"]):
        intents.append("window")

    if contains_any(question, ["운동", "야외활동", "밖에서", "산책", "외출"]):
        intents.append("outdoor_activity")

    if contains_any(question, ["엘리베이터", "승강기"]):
        intents.append("elevator")

    if contains_any(question, ["연기", "숨", "코", "입", "질식"]):
        intents.append("smoke")

    if contains_any(question, ["소화기", "불 끄", "꺼도", "진압"]):
        intents.append("fire_extinguisher")

    if contains_any(question, ["대피", "어디로", "비상구", "나가야"]):
        intents.append("evacuation")

    return intents



# 점수 계산
def calculate_keyword_score(question, guide_text):
    """질문과 행동요령 문서의 키워드 겹침 점수를 계산한다."""
    question_tokens = set(tokenize_korean_simple(question))
    guide_tokens = set(tokenize_korean_simple(guide_text))

    if not question_tokens or not guide_tokens:
        return 0

    intersection = question_tokens.intersection(guide_tokens)
    return len(intersection)


def get_situation_bonus(situation_type, title, content):
    """질문 상황과 행동요령 제목/내용이 맞으면 가산점을 준다."""
    title = "" if pd.isna(title) else str(title)
    content = "" if pd.isna(content) else str(content)
    combined = f"{title} {content}"

    before_title_keywords = ["사전", "준비", "예보", "예보시", "예보 시", "대비"]
    during_title_keywords = ["특보 중", "특보중", "발생 시", "발생시", "발생", "중 행동요령", "대피", "행동요령"]
    after_title_keywords = ["이후", "후 행동요령", "복구"]

    bonus = 0

    if situation_type == "before":
        if contains_any(combined, before_title_keywords):
            bonus += 20
        if contains_any(combined, after_title_keywords):
            bonus -= 10

    elif situation_type == "during":
        if contains_any(combined, during_title_keywords):
            bonus += 20
        if contains_any(combined, before_title_keywords):
            bonus -= 5
        if contains_any(combined, after_title_keywords):
            bonus -= 10

    elif situation_type == "after":
        if contains_any(combined, after_title_keywords):
            bonus += 20
        if contains_any(combined, before_title_keywords):
            bonus -= 5

    return bonus


def get_question_specific_bonus(question, title, content):
    """특정 질문 의도와 문서 내용이 맞을 때 추가 점수를 준다."""
    question = "" if pd.isna(question) else str(question)
    title = "" if pd.isna(title) else str(title)
    content = "" if pd.isna(content) else str(content)
    combined = f"{title} {content}"

    intents = detect_question_intents(question)
    bonus = 0

    if "underground_road" in intents:
        if "지하차도" in combined:
            bonus += 25
        if contains_any(combined, ["침수된 도로", "침수 도로", "침수도로"]):
            bonus += 20
        if contains_any(combined, ["통행", "진입"]):
            bonus += 10

    if "window" in intents:
        if "창문" in combined:
            bonus += 25
        if "유리창" in combined:
            bonus += 15
        if contains_any(combined, ["간판", "낙하물"]):
            bonus += 10

    if "outdoor_activity" in intents:
        if "야외활동" in combined:
            bonus += 25
        if "운동" in combined:
            bonus += 20
        if "외출" in combined:
            bonus += 15
        if contains_any(combined, ["무더위", "폭염"]):
            bonus += 10

    if "elevator" in intents:
        if contains_any(combined, ["엘리베이터", "승강기"]):
            bonus += 30
        if contains_any(combined, ["이용하지", "사용하지", "금지", "타지"]):
            bonus += 15

    if "smoke" in intents:
        if "연기" in combined:
            bonus += 25
        if "낮은 자세" in combined:
            bonus += 15
        if contains_any(combined, ["코와 입", "수건", "질식"]):
            bonus += 15

    if "fire_extinguisher" in intents:
        if "소화기" in combined:
            bonus += 30
        if contains_any(combined, ["초기 화재", "초기화재"]):
            bonus += 15
        if "대피" in combined:
            bonus += 5

    if "evacuation" in intents:
        if "대피" in combined:
            bonus += 20
        if "비상구" in combined:
            bonus += 20
        if "119" in combined:
            bonus += 10

    return bonus


def calculate_guide_score(question, detected_disaster_type, situation_type, row):
    """
    질문과 행동요령 한 건의 관련도 점수를 계산한다.
    최종 점수는 0~100점으로 제한한다.
    """
    disaster_type = str(row.get("disaster_type", ""))
    title = str(row.get("title", ""))
    content = str(row.get("content", ""))
    easy_content = str(row.get("easy_content", ""))
    keywords = str(row.get("keywords", ""))

    combined_text = f"{disaster_type} {title} {content} {easy_content} {keywords}"

    raw_score = 0

    # 재난 유형 일치 점수
    if detected_disaster_type != "기타":
        if detected_disaster_type in disaster_type:
            raw_score += 40
        elif detected_disaster_type in combined_text:
            raw_score += 25
        else:
            raw_score -= 15

    # 상황 단계 일치 점수
    raw_score += get_situation_bonus(situation_type, title, combined_text)

    # 질문별 세부 의도 점수
    raw_score += get_question_specific_bonus(question, title, combined_text)

    # 제목/키워드/본문 키워드 점수
    token_score = 0

    for token in tokenize_korean_simple(question):
        if token in title:
            token_score += 6
        if token in keywords:
            token_score += 5
        if token in content:
            token_score += 2
        if token in easy_content:
            token_score += 2

    raw_score += min(token_score, 20)

    # 전체 키워드 겹침 점수
    overlap_score = calculate_keyword_score(question, combined_text) * 3
    raw_score += min(overlap_score, 15)

    return max(0, min(100, int(raw_score)))


def get_matched_keywords(question, row):
    """질문과 문서 사이에 실제로 매칭된 키워드 목록을 반환한다."""
    title = str(row.get("title", ""))
    content = str(row.get("content", ""))
    easy_content = str(row.get("easy_content", ""))
    keywords = str(row.get("keywords", ""))

    combined_text = f"{title} {content} {easy_content} {keywords}"

    matched = []

    for token in tokenize_korean_simple(question):
        if token in combined_text and token not in matched:
            matched.append(token)

    return ", ".join(matched)



# 검색 / 답변 생성
def load_action_guides_with_builtin():
    """CSV 행동요령 + 내장 행동요령을 함께 불러온다."""
    csv_df = safe_read_csv(ACTION_GUIDES_PATH)
    guides_df = normalize_guide_columns(csv_df)

    builtin_df = get_builtin_guides()

    required_cols = ["guide_id", "disaster_type", "title", "content", "easy_content", "keywords"]

    guides_df = pd.concat(
        [
            guides_df[required_cols],
            builtin_df[required_cols]
        ],
        ignore_index=True
    )

    guides_df = guides_df.fillna("")
    guides_df = guides_df.drop_duplicates(subset=["guide_id", "title", "content"], keep="first")

    return guides_df


def search_action_guides(question, top_n=3):
    """사용자 질문과 관련 있는 행동요령 TOP N을 검색한다."""
    guides_df = load_action_guides_with_builtin()

    if guides_df.empty:
        raise ValueError("행동요령 데이터가 비어 있습니다.")

    detected_disaster_type = detect_disaster_type(question)
    situation_type = detect_situation_type(question)

    guides_df = guides_df.copy()

    guides_df["rag_score"] = guides_df.apply(
        lambda row: calculate_guide_score(
            question=question,
            detected_disaster_type=detected_disaster_type,
            situation_type=situation_type,
            row=row
        ),
        axis=1
    )

    # 화면 또는 app.py에서 score 이름으로 접근하는 경우를 대비해 둘 다 제공
    guides_df["score"] = guides_df["rag_score"]

    guides_df["matched_keywords"] = guides_df.apply(
        lambda row: get_matched_keywords(question, row),
        axis=1
    )

    result = guides_df.sort_values(
        by="rag_score",
        ascending=False
    ).head(top_n).copy()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    return detected_disaster_type, situation_type, result


def clean_answer_text(text, max_length=600):
    """답변용 텍스트를 너무 길지 않게 정리한다."""
    text = "" if pd.isna(text) else str(text)
    text = text.replace("\\n", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."

    return text


def situation_type_to_korean(situation_type):
    """상황 유형을 한국어 설명으로 변환한다."""
    mapping = {
        "before": "사전 대비 상황",
        "during": "재난 발생 중 또는 특보 중 상황",
        "after": "재난 이후 상황",
        "general": "일반 상황"
    }

    return mapping.get(situation_type, "일반 상황")


def build_direct_answer_intro(question, detected_disaster_type):
    """질문의 의도에 따라 직접적인 답변 문장을 생성한다."""
    question = "" if pd.isna(question) else str(question)
    intents = detect_question_intents(question)

    if detected_disaster_type == "호우/침수" and "underground_road" in intents:
        return (
            "결론부터 말하면, 호우나 침수 상황에서는 지하차도나 침수된 도로를 지나가면 안 됩니다. "
            "물이 조금만 차 있어 보여도 차량이 고립되거나 급격히 수위가 올라갈 수 있어 매우 위험합니다."
        )

    if detected_disaster_type == "태풍" and "window" in intents:
        return (
            "태풍이 올 때는 창문이나 유리창 근처에 머무르지 않는 것이 좋습니다. "
            "강풍으로 유리창이 파손되거나 외부 물체가 날아올 수 있으므로 창문에서 떨어져 있어야 합니다."
        )

    if detected_disaster_type == "폭염" and "outdoor_activity" in intents:
        return (
            "폭염 시에는 한낮의 야외 운동이나 장시간 외출을 피하는 것이 좋습니다. "
            "온열질환 위험이 높기 때문에 시원한 실내에서 휴식하고 물을 자주 마셔야 합니다."
        )

    if detected_disaster_type == "화재" and "elevator" in intents:
        return (
            "화재가 발생했을 때는 엘리베이터를 타면 안 됩니다. "
            "정전, 연기 유입, 갇힘 위험이 있으므로 계단과 비상구를 이용해 대피해야 합니다."
        )

    if detected_disaster_type == "화재" and "smoke" in intents:
        return (
            "화재 연기가 있을 때는 연기를 마시지 않도록 낮은 자세로 이동하고 코와 입을 막아야 합니다. "
            "연기가 심하면 무리하게 이동하지 말고 안전한 장소에서 구조를 요청해야 합니다."
        )

    if detected_disaster_type == "화재" and "fire_extinguisher" in intents:
        return (
            "소화기는 작은 초기 화재이고 본인의 안전이 확보된 경우에만 사용해야 합니다. "
            "불길이 커지거나 연기가 많다면 소화보다 즉시 대피가 우선입니다."
        )

    if detected_disaster_type == "화재":
        return (
            "화재 상황에서는 신속하게 주변에 알리고 119에 신고한 뒤, "
            "엘리베이터가 아닌 계단과 비상구를 이용해 대피하는 것이 중요합니다."
        )

    return ""



MIN_RAG_SCORE = 35


def unique_text_items(items, limit=5):
    """빈 값과 중복 문장을 제거하고 최대 개수만 반환한다."""
    result = []
    for item in items:
        text = re.sub(r"\s+", " ", str(item or "")).strip(" -•\t\n")
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def split_guide_sentences(text):
    """행동요령 본문을 짧은 문장 목록으로 분리한다."""
    cleaned = clean_answer_text(text, max_length=1200)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?다요])\s+|[•●▪■]|\n+", cleaned)
    return unique_text_items(parts, limit=12)


def get_structured_actions(disaster_type, intents, situation_type, guide_text=""):
    """재난 유형과 질문 의도에 맞는 즉시 행동·금지 행동을 반환한다."""
    presets = {
        "호우/침수": {
            "summary": "침수 위험지역에 진입하지 말고 높은 곳이나 안전한 실내로 이동하세요.",
            "do": ["지하차도와 침수도로에 진입하지 않습니다.", "하천변·저지대에서 즉시 벗어납니다.", "높은 곳이나 지정 대피소로 이동합니다."],
            "dont": ["물이 얕아 보여도 차량이나 도보로 통과하지 않습니다.", "하천 수위를 확인하려고 접근하지 않습니다."]},
        "태풍": {
            "summary": "외출을 줄이고 창문과 낙하물 위험이 없는 실내에 머무르세요.",
            "do": ["창문과 유리문에서 떨어져 머무릅니다.", "간판·가로수·해안가를 피합니다.", "공식 특보와 대피 안내를 확인합니다."],
            "dont": ["강풍 중 외출하거나 해안가에 접근하지 않습니다.", "창문을 열어 고정하려고 하지 않습니다."]},
        "폭염": {
            "summary": "한낮 야외활동을 중단하고 시원한 장소에서 수분을 보충하세요.",
            "do": ["물을 자주 마십니다.", "무더위쉼터나 냉방 가능한 실내로 이동합니다.", "어지럼증이 있으면 즉시 휴식하고 도움을 요청합니다."],
            "dont": ["한낮에 운동하거나 장시간 야외에 머무르지 않습니다.", "밀폐된 차량 안에 사람이나 동물을 두지 않습니다."]},
        "한파": {
            "summary": "보온을 유지하고 빙판길과 장시간 외출을 피하세요.",
            "do": ["여러 겹의 옷과 방한용품으로 체온을 유지합니다.", "수도계량기와 배관의 동파를 예방합니다.", "빙판길에서는 천천히 이동합니다."],
            "dont": ["장시간 야외에 머무르지 않습니다.", "결빙된 도로에서 급제동하지 않습니다."]},
        "대설": {
            "summary": "불필요한 이동을 줄이고 도로 통제와 교통정보를 확인하세요.",
            "do": ["외출 전 도로와 대중교통 상황을 확인합니다.", "보행 시 미끄럼 방지 신발을 착용합니다.", "차량의 월동장비를 점검합니다."],
            "dont": ["눈길에서 과속하거나 급제동하지 않습니다.", "붕괴 우려가 있는 지붕 아래에 머무르지 않습니다."]},
        "지진": {
            "summary": "머리를 보호하고 흔들림이 멈춘 뒤 계단으로 넓은 공간에 이동하세요.",
            "do": ["책상 아래에서 머리와 몸을 보호합니다.", "흔들림이 멈추면 가스와 전기를 확인합니다.", "계단을 이용해 넓은 공터나 지정 대피장소로 이동합니다."],
            "dont": ["엘리베이터를 이용하지 않습니다.", "건물 외벽·유리창·간판 주변에 머무르지 않습니다."]},
        "지진해일": {
            "summary": "해안과 저지대에서 즉시 벗어나 높은 곳으로 이동하세요.",
            "do": ["해안가를 즉시 이탈합니다.", "높은 지대나 지진해일 대피장소로 이동합니다.", "해제 안내 전까지 안전지역에 머무릅니다."],
            "dont": ["파도를 확인하려고 해안으로 가지 않습니다.", "차량 정체가 예상되면 무리하게 운전하지 않습니다."]},
        "산사태": {
            "summary": "산비탈과 급경사지에서 벗어나 안전한 건물이나 대피소로 이동하세요.",
            "do": ["산비탈·옹벽·급경사지에서 멀어집니다.", "토사 이동 방향의 옆쪽으로 신속히 대피합니다.", "지자체 대피 안내를 확인합니다."],
            "dont": ["토사 유출 지역을 가로질러 이동하지 않습니다.", "위험지역으로 되돌아가지 않습니다."]},
        "화재": {
            "summary": "주변에 화재를 알리고 119에 신고한 뒤 계단과 비상구로 대피하세요.",
            "do": ["큰 소리로 주변에 알리고 119에 신고합니다.", "코와 입을 가리고 낮은 자세로 이동합니다.", "계단과 비상구를 이용해 밖으로 대피합니다."],
            "dont": ["엘리베이터를 이용하지 않습니다.", "불길이나 연기가 큰 곳에 다시 들어가지 않습니다."]},
        "산불": {
            "summary": "산림과 연기 진행 방향에서 벗어나 지자체가 안내한 안전지역으로 이동하세요.",
            "do": ["산림·야산·연기 발생 지역에서 즉시 벗어납니다.", "바람과 연기의 진행 방향을 피해 이동합니다.", "지자체와 소방의 대피 명령을 따릅니다."],
            "dont": ["산불을 촬영하거나 확인하려고 접근하지 않습니다.", "산길이나 좁은 도로로 무리하게 차량 이동하지 않습니다."]}
    }
    preset = presets.get(disaster_type, {
        "summary": "공식 재난문자와 현장 안내를 확인하고 안전한 장소로 이동하세요.",
        "do": ["현재 위치의 위험요인을 확인합니다.", "지자체와 현장 안내에 따라 이동합니다."],
        "dont": ["통제구역에 진입하지 않습니다."]})
    guide_sentences = split_guide_sentences(guide_text)
    immediate = list(preset["do"])
    prohibited = list(preset["dont"])
    for sentence in guide_sentences:
        if contains_any(sentence, ["하지", "금지", "피하", "자제", "접근하지", "이용하지"]):
            prohibited.append(sentence)
        elif contains_any(sentence, ["이동", "대피", "확인", "신고", "보호", "마시", "유지"]):
            immediate.append(sentence)
    return preset["summary"], unique_text_items(immediate, 5), unique_text_items(prohibited, 4)


def generate_rag_answer(question, top_n=3):
    """사용자 질문에 대해 핵심 행동 중심의 구조화된 RAG 답변을 생성한다."""
    detected_disaster_type, situation_type, result_df = search_action_guides(
        question=question,
        top_n=top_n
    )
    situation_text = situation_type_to_korean(situation_type)
    intents = detect_question_intents(question)

    if result_df.empty:
        return {
            "question": question,
            "disaster_type": detected_disaster_type,
            "detected_disaster_type": detected_disaster_type,
            "situation_type": situation_type,
            "situation_type_korean": situation_text,
            "is_low_confidence": True,
            "summary": "질문과 정확히 일치하는 행동요령을 찾지 못했습니다.",
            "immediate_actions": ["지자체 재난문자와 현장 안내를 우선 확인하세요."],
            "prohibited_actions": [],
            "detail": "공식 재난안전 안내를 확인하고 위험지역에는 접근하지 마세요.",
            "answer": "관련 행동요령을 찾지 못했습니다. 공식 재난안전 안내와 지자체 문자를 확인하세요.",
            "references": []
        }

    best_row = result_df.iloc[0]
    best_score = int(best_row.get("rag_score", 0))
    best_title = str(best_row.get("title", "관련 행동요령"))
    best_content = best_row.get("easy_content", "")
    if pd.isna(best_content) or not str(best_content).strip():
        best_content = best_row.get("content", "")
    best_content = clean_answer_text(best_content, max_length=700)

    summary, immediate_actions, prohibited_actions = get_structured_actions(
        disaster_type=detected_disaster_type,
        intents=intents,
        situation_type=situation_type,
        guide_text=best_content
    )

    is_low_confidence = best_score < MIN_RAG_SCORE
    if is_low_confidence:
        summary = "질문과 완전히 일치하는 자료가 부족해 일반 안전수칙을 안내합니다."
        immediate_actions = ["지자체 재난문자와 현장 안내를 우선 확인하세요."]
        prohibited_actions = ["근거가 불확실한 정보만 믿고 위험지역에 접근하지 마세요."]

    references = []
    for _, row in result_df.iterrows():
        rag_score = int(row.get("rag_score", 0))
        references.append({
            "guide_id": row.get("guide_id", ""),
            "disaster_type": row.get("disaster_type", ""),
            "title": row.get("title", ""),
            "score": rag_score,
            "rag_score": rag_score,
            "matched_keywords": row.get("matched_keywords", "")
        })

    answer_parts = [summary]
    if immediate_actions:
        answer_parts.append("즉시 해야 할 행동: " + " ".join(immediate_actions))
    if prohibited_actions:
        answer_parts.append("하지 말아야 할 행동: " + " ".join(prohibited_actions))
    answer = "\n\n".join(answer_parts)

    return {
        "question": question,
        "disaster_type": detected_disaster_type,
        "detected_disaster_type": detected_disaster_type,
        "situation_type": situation_type,
        "situation_type_korean": situation_text,
        "is_low_confidence": is_low_confidence,
        "best_score": best_score,
        "summary": summary,
        "immediate_actions": immediate_actions,
        "prohibited_actions": prohibited_actions,
        "detail": best_content,
        "best_title": best_title,
        "answer": answer,
        "references": references
    }

def print_rag_result(result):
    """RAG 결과를 터미널에 출력한다."""
    print("======================================")
    print("SafeNavi 행동요령 RAG AI")
    print("======================================")
    print(f"질문: {result['question']}")
    print(f"분석된 재난 유형: {result['detected_disaster_type']}")
    print(f"분석된 상황 유형: {situation_type_to_korean(result['situation_type'])}")
    print()
    print("[답변]")
    print(result["answer"])
    print()
    print("[참고한 행동요령]")

    for idx, ref in enumerate(result["references"], start=1):
        print(
            f"{idx}. [{ref['disaster_type']}] {ref['title']} "
            f"(점수: {ref['score']}, 키워드: {ref.get('matched_keywords', '')})"
        )

    print("======================================")


if __name__ == "__main__":
    sample_questions = [
        "호우 때 지하차도 지나가도 돼?",
        "태풍이 올 때 창문 근처에 있어도 되나요?",
        "폭염일 때 밖에서 운동해도 되나요?",
        "태풍이 지나간 후에는 어떻게 해야 하나요?",
        "호우 오기 전에 미리 준비할 게 뭐야?",
        "화재가 나면 엘리베이터 타도 돼?",
        "연기가 날 때 어떻게 대피해야 해?",
        "소화기는 언제 사용해야 해?"
    ]

    for sample_question in sample_questions:
        rag_result = generate_rag_answer(sample_question, top_n=3)
        print_rag_result(rag_result)
        print()
