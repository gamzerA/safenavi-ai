import os
import re
import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACTION_GUIDES_PATH = os.path.join(
    BASE_DIR, "data", "processed", "action_guides.csv"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "data", "processed", "rag_search_results.csv"
)


def safe_read_csv(path):
    """
    CSV 파일을 불러온다.
    """
    if not os.path.exists(path):
        print(f"[행동요령 RAG] 파일 없음: {path}")
        return pd.DataFrame()

    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def normalize_text(text):
    """
    검색 비교를 위해 텍스트를 정리한다.
    """
    text = str(text)
    text = text.lower()
    text = re.sub(r"[^가-힣a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_korean_simple(text):
    """
    간단한 키워드 토큰화 함수.
    """
    text = normalize_text(text)
    tokens = text.split()
    tokens = [token for token in tokens if len(token) >= 2]
    return tokens


def detect_disaster_type(question):
    """
    사용자 질문에서 재난 유형을 추정한다.
    """

    question = str(question)

    disaster_keywords = {
        "호우/침수": [
            "호우", "폭우", "집중호우", "침수", "홍수", "하천",
            "범람", "저지대", "지하차도", "물", "비"
        ],
        "태풍": [
            "태풍", "강풍", "풍랑", "해안가", "간판", "창문",
            "바람", "월파"
        ],
        "폭염": [
            "폭염", "무더위", "온열질환", "더위", "열사병",
            "일사병", "체감온도", "운동", "야외활동"
        ],
        "한파": [
            "한파", "동파", "빙판", "저온", "강추위",
            "한랭질환", "추위"
        ],
        "대설": [
            "대설", "폭설", "눈", "눈길", "적설", "빙판길",
            "제설"
        ],
        "지진": [
            "지진", "진도", "여진", "흔들림", "낙하물",
            "대피"
        ],
        "지진해일": [
            "지진해일", "해일", "쓰나미", "연안", "해안",
            "방파제"
        ],
        "산사태": [
            "산사태", "토사", "급경사지", "비탈면", "옹벽",
            "산비탈"
        ],
        "낙뢰": [
            "낙뢰", "번개", "벼락", "천둥"
        ],
        "황사": [
            "황사", "미세먼지", "먼지", "마스크"
        ]
    }

    scores = {}

    for disaster_type, keywords in disaster_keywords.items():
        score = 0

        for keyword in keywords:
            if keyword in question:
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

    question = str(question)

    before_keywords = [
        "미리", "준비", "사전", "예보", "오기 전", "발생 전",
        "대비", "준비물", "챙겨"
    ]

    during_keywords = [
        "때", "중", "발생", "특보", "지금", "현재", "해도", "되나요",
        "위험", "어떻게", "피해야", "가도", "지나가도", "있어도",
        "운동", "산책", "외출", "창문", "지하차도"
    ]

    after_keywords = [
        "이후", "끝난 후", "지나간 후", "지나간 뒤", "끝나고",
        "복구", "피해 신고", "정리"
    ]

    if any(keyword in question for keyword in after_keywords):
        return "after"

    if any(keyword in question for keyword in before_keywords):
        return "before"

    if any(keyword in question for keyword in during_keywords):
        return "during"

    return "general"


def calculate_keyword_score(question, guide_text):
    """
    질문과 행동요령 문서의 키워드 겹침 점수를 계산한다.
    """

    question_tokens = set(tokenize_korean_simple(question))
    guide_tokens = set(tokenize_korean_simple(guide_text))

    if not question_tokens or not guide_tokens:
        return 0

    intersection = question_tokens.intersection(guide_tokens)

    return len(intersection)


def get_situation_bonus(situation_type, title):
    """
    질문 상황과 행동요령 제목이 맞으면 가산점을 준다.
    """

    title = str(title)

    before_title_keywords = [
        "사전", "준비", "예보", "예보시", "예보 시", "대비"
    ]

    during_title_keywords = [
        "특보 중", "특보중", "발생 시", "발생시", "발생", "중 행동요령"
    ]

    after_title_keywords = [
        "이후", "후 행동요령", "복구"
    ]

    bonus = 0

    if situation_type == "before":
        if any(keyword in title for keyword in before_title_keywords):
            bonus += 35
        if any(keyword in title for keyword in during_title_keywords):
            bonus += 5
        if any(keyword in title for keyword in after_title_keywords):
            bonus -= 20

    elif situation_type == "during":
        if any(keyword in title for keyword in during_title_keywords):
            bonus += 40
        if any(keyword in title for keyword in before_title_keywords):
            bonus -= 10
        if any(keyword in title for keyword in after_title_keywords):
            bonus -= 25

    elif situation_type == "after":
        if any(keyword in title for keyword in after_title_keywords):
            bonus += 40
        if any(keyword in title for keyword in before_title_keywords):
            bonus -= 10
        if any(keyword in title for keyword in during_title_keywords):
            bonus += 5

    return bonus


def get_question_specific_bonus(question, title, content):
    """
    특정 질문 의도와 문서 내용이 맞을 때 추가 점수를 준다.
    예: 지하차도 질문이면 지하차도/침수도로 내용이 있는 문서 우선
    """

    question = str(question)
    title = str(title)
    content = str(content)

    combined = f"{title} {content}"

    bonus = 0

    if "지하차도" in question:
        if "지하차도" in combined:
            bonus += 30
        if "침수된 도로" in combined or "침수 도로" in combined:
            bonus += 15

    if "창문" in question:
        if "창문" in combined:
            bonus += 30
        if "유리창" in combined:
            bonus += 20
        if "간판" in combined or "낙하물" in combined:
            bonus += 10

    if "운동" in question or "야외활동" in question or "밖" in question:
        if "야외활동" in combined:
            bonus += 25
        if "운동" in combined:
            bonus += 20
        if "외출" in combined:
            bonus += 15
        if "무더위" in combined or "폭염" in combined:
            bonus += 10

    if "산책" in question:
        if "야외활동" in combined or "외출" in combined:
            bonus += 20

    return bonus


def calculate_guide_score(question, detected_disaster_type, situation_type, row):
    """
    질문과 행동요령 한 건의 관련도 점수를 계산한다.
    """

    disaster_type = str(row.get("disaster_type", ""))
    title = str(row.get("title", ""))
    content = str(row.get("content", ""))
    easy_content = str(row.get("easy_content", ""))
    keywords = str(row.get("keywords", ""))

    combined_text = f"{disaster_type} {title} {content} {easy_content} {keywords}"

    score = 0

    # 1. 재난 유형 일치 점수
    if detected_disaster_type != "기타" and detected_disaster_type in disaster_type:
        score += 50

    # 2. 상황 단계 일치 점수
    score += get_situation_bonus(situation_type, title)

    # 3. 질문별 세부 의도 점수
    score += get_question_specific_bonus(question, title, combined_text)

    # 4. 제목/키워드/본문 키워드 점수
    for token in tokenize_korean_simple(question):
        if token in title:
            score += 8
        if token in keywords:
            score += 5
        if token in content:
            score += 2
        if token in easy_content:
            score += 2

    # 5. 전체 키워드 겹침 점수
    score += calculate_keyword_score(question, combined_text) * 3

    return score


def search_action_guides(question, top_n=3):
    """
    사용자 질문과 관련 있는 행동요령 TOP N을 검색한다.
    """

    guides_df = safe_read_csv(ACTION_GUIDES_PATH)

    if guides_df.empty:
        raise ValueError("action_guides.csv가 비어 있거나 없습니다.")

    required_cols = [
        "guide_id",
        "disaster_type",
        "title",
        "content",
        "easy_content",
        "keywords"
    ]

    for col in required_cols:
        if col not in guides_df.columns:
            raise ValueError(f"action_guides.csv에 필요한 컬럼이 없습니다: {col}")

    detected_disaster_type = detect_disaster_type(question)
    situation_type = detect_situation_type(question)

    guides_df = guides_df.copy()

    guides_df["rag_score"] = guides_df.apply(
        lambda row: calculate_guide_score(
            question,
            detected_disaster_type,
            situation_type,
            row
        ),
        axis=1
    )

    result = guides_df.sort_values(
        by="rag_score",
        ascending=False
    ).head(top_n).copy()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    return detected_disaster_type, situation_type, result


def clean_answer_text(text, max_length=500):
    """
    답변용 텍스트를 너무 길지 않게 정리한다.
    """

    text = str(text)
    text = text.replace("\\n", " ")
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."

    return text


def situation_type_to_korean(situation_type):
    """
    상황 유형을 한국어 설명으로 변환한다.
    """

    mapping = {
        "before": "사전 대비 상황",
        "during": "재난 발생 중 또는 특보 중 상황",
        "after": "재난 이후 상황",
        "general": "일반 상황"
    }

    return mapping.get(situation_type, "일반 상황")


def generate_rag_answer(question, top_n=3):
    """
    사용자 질문에 대해 행동요령 기반 답변을 생성한다.
    """

    detected_disaster_type, situation_type, result_df = search_action_guides(
        question=question,
        top_n=top_n
    )

    if result_df.empty:
        return {
            "question": question,
            "detected_disaster_type": detected_disaster_type,
            "situation_type": situation_type,
            "answer": "관련 행동요령을 찾지 못했습니다. 공식 재난안전 안내와 지자체 문자를 확인하세요.",
            "references": []
        }

    best_row = result_df.iloc[0]

    best_title = best_row.get("title", "관련 행동요령")
    best_content = best_row.get("easy_content", "")

    if pd.isna(best_content) or str(best_content).strip() == "":
        best_content = best_row.get("content", "")

    best_content = clean_answer_text(best_content)

    references = []

    for _, row in result_df.iterrows():
        references.append(
            {
                "guide_id": row.get("guide_id", ""),
                "disaster_type": row.get("disaster_type", ""),
                "title": row.get("title", ""),
                "rag_score": row.get("rag_score", 0)
            }
        )

    situation_text = situation_type_to_korean(situation_type)

    answer = (
        f"질문에서 '{detected_disaster_type}' 관련 '{situation_text}'으로 판단했습니다.\n\n"
        f"가장 관련 있는 행동요령은 '{best_title}'입니다.\n\n"
        f"{best_content}\n\n"
        f"추가로 지자체 재난문자, 기상특보, 현장 안내를 함께 확인하는 것이 좋습니다."
    )

    return {
        "question": question,
        "detected_disaster_type": detected_disaster_type,
        "situation_type": situation_type,
        "answer": answer,
        "references": references
    }


def print_rag_result(result):
    """
    RAG 결과를 터미널에 출력한다.
    """

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
            f"(점수: {ref['rag_score']})"
        )
    print("======================================")


if __name__ == "__main__":
    sample_questions = [
        "호우 때 지하차도 지나가도 돼?",
        "태풍이 올 때 창문 근처에 있어도 되나요?",
        "폭염일 때 밖에서 운동해도 되나요?",
        "태풍이 지나간 후에는 어떻게 해야 하나요?",
        "호우 오기 전에 미리 준비할 게 뭐야?"
    ]

    for question in sample_questions:
        result = generate_rag_answer(question, top_n=3)
        print_rag_result(result)
        print()