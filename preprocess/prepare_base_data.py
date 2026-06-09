import os
import re
import pandas as pd


RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"

GUIDE_PATH = os.path.join(RAW_DIR, "자연재난_국민행동요령_전체.csv")
SHELTER_PATH = os.path.join(RAW_DIR, "통합대피소_전체.csv")
CAPACITY_PATH = os.path.join(RAW_DIR, "수용공간시설_전체.csv")

OUTPUT_SHELTERS = os.path.join(PROCESSED_DIR, "shelters.csv")
OUTPUT_GUIDES = os.path.join(PROCESSED_DIR, "action_guides.csv")


def split_address(address: str):
    """
    주소에서 시도, 시군구를 간단히 분리한다.
    예: 경기도 용인시 처인구 중부대로 1199
    → sido=경기도, sigungu=용인시 처인구
    """
    if pd.isna(address):
        return "", ""

    parts = str(address).strip().split()

    if len(parts) == 0:
        return "", ""

    sido = parts[0]

    if len(parts) >= 3 and (parts[1].endswith("시") or parts[1].endswith("군")) and parts[2].endswith("구"):
        sigungu = parts[1] + " " + parts[2]
    elif len(parts) >= 2:
        sigungu = parts[1]
    else:
        sigungu = ""

    return sido, sigungu


def normalize_disaster_type(value: str):
    """
    행동요령/RAG/추천에서 사용할 재난유형명을 통일한다.
    """
    if pd.isna(value):
        return "기타"

    text = str(value)

    if "호우" in text or "홍수" in text or "침수" in text:
        return "호우/침수"
    if "폭염" in text or "무더위" in text:
        return "폭염"
    if "한파" in text:
        return "한파"
    if "지진해일" in text:
        return "지진해일"
    if "지진" in text:
        return "지진"
    if "태풍" in text:
        return "태풍"
    if "대설" in text or "폭설" in text:
        return "대설"
    if "강풍" in text:
        return "강풍"
    if "풍랑" in text:
        return "풍랑"
    if "낙뢰" in text:
        return "낙뢰"
    if "산사태" in text:
        return "산사태"
    if "해일" in text:
        return "해일"
    if "가뭄" in text:
        return "가뭄"
    if "황사" in text:
        return "황사"
    if "화산" in text:
        return "화산폭발"

    return text


def classify_capacity_shelter_type(name: str, detail_code=None):
    """
    수용공간시설 데이터의 시설명을 보고 추천에 쓰기 좋은 shelter_type으로 변환한다.
    """
    name = "" if pd.isna(name) else str(name)

    if "학교" in name or "초등" in name or "중학교" in name or "고등학교" in name or "대학교" in name:
        return "학교"
    if "체육관" in name or "강당" in name:
        return "실내수용시설"
    if "공원" in name or "운동장" in name:
        return "옥외수용시설"
    if "복지" in name or "센터" in name or "회관" in name:
        return "공공시설"

    return "수용시설"


def make_coord_key(lat, lon):
    """
    같은 좌표 중복 확인용 키.
    """
    try:
        return f"{float(lat):.6f}_{float(lon):.6f}"
    except Exception:
        return ""


def prepare_integrated_shelters():
    """
    통합대피소_전체.csv를 SafeNavi 표준 대피소 컬럼으로 변환한다.
    """
    df = pd.read_csv(SHELTER_PATH, encoding="utf-8-sig")

    result = pd.DataFrame()
    result["shelter_id"] = df["MNG_SN"].astype(str)
    result["name"] = df["REARE_NM"].fillna("")
    result["address"] = df["RONA_DADDR"].fillna("")
    result["lat"] = pd.to_numeric(df["LAT"], errors="coerce")
    result["lon"] = pd.to_numeric(df["LOT"], errors="coerce")
    result["shelter_type"] = df["SHLT_SE_NM"].fillna("통합대피소")
    result["capacity"] = ""
    result["source"] = "통합대피소"

    sido_sigungu = result["address"].apply(split_address)
    result["sido"] = sido_sigungu.apply(lambda x: x[0])
    result["sigungu"] = sido_sigungu.apply(lambda x: x[1])

    result["coord_key"] = result.apply(
        lambda row: make_coord_key(row["lat"], row["lon"]),
        axis=1
    )

    result = result[
        [
            "shelter_id", "name", "address", "sido", "sigungu",
            "lat", "lon", "shelter_type", "capacity", "source", "coord_key"
        ]
    ]

    return result


def prepare_capacity_shelters():
    """
    수용공간시설_전체.csv를 SafeNavi 표준 대피소 컬럼으로 변환한다.
    """
    df = pd.read_csv(CAPACITY_PATH, encoding="utf-8-sig")

    result = pd.DataFrame()
    result["shelter_id"] = "CAP_" + df["ACTC_FCLT_SN"].astype(str)
    result["name"] = df["DSSTR_ACTC_FCLT_NM"].fillna("")
    result["address"] = df["RONA_DADDR"].fillna(df["DADDR"].fillna(""))
    result["lat"] = pd.to_numeric(df["LAT"], errors="coerce")
    result["lon"] = pd.to_numeric(df["LOT"], errors="coerce")

    result["shelter_type"] = df.apply(
        lambda row: classify_capacity_shelter_type(
            row.get("DSSTR_ACTC_FCLT_NM", ""),
            row.get("ACTC_FCLT_SE_CD", "")
        ),
        axis=1
    )

    result["capacity"] = pd.to_numeric(df["DSSTR_ACTC_PSBLTY_TNOP"], errors="coerce")
    result["source"] = "수용공간시설"

    sido_sigungu = result["address"].apply(split_address)
    result["sido"] = sido_sigungu.apply(lambda x: x[0])
    result["sigungu"] = sido_sigungu.apply(lambda x: x[1])

    result["coord_key"] = result.apply(
        lambda row: make_coord_key(row["lat"], row["lon"]),
        axis=1
    )

    result = result[
        [
            "shelter_id", "name", "address", "sido", "sigungu",
            "lat", "lon", "shelter_type", "capacity", "source", "coord_key"
        ]
    ]

    return result


def is_valid_korea_coordinate(lat, lon):
    """
    한국 위경도 범위 안에 있는 좌표만 사용한다.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return False

    return 33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.0


def prepare_shelters():
    """
    통합대피소 + 수용공간시설을 합쳐 shelters.csv를 만든다.
    """
    print("[1] 통합대피소 변환 중...")
    integrated = prepare_integrated_shelters()
    print(f"통합대피소: {len(integrated):,}개")

    print("[2] 수용공간시설 변환 중...")
    capacity = prepare_capacity_shelters()
    print(f"수용공간시설: {len(capacity):,}개")

    shelters = pd.concat([integrated, capacity], ignore_index=True)

    before = len(shelters)

    # 좌표 결측 제거
    shelters = shelters.dropna(subset=["lat", "lon"])

    # 한국 범위 외 좌표 제거
    shelters = shelters[
        shelters.apply(lambda row: is_valid_korea_coordinate(row["lat"], row["lon"]), axis=1)
    ]

    # 이름, 좌표, 출처 기준 중복 제거
    shelters = shelters.drop_duplicates(
        subset=["name", "lat", "lon", "source"],
        keep="first"
    )

    after = len(shelters)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    shelters.to_csv(OUTPUT_SHELTERS, index=False, encoding="utf-8-sig")

    print("[완료] shelters.csv 생성")
    print(f"처리 전: {before:,}개")
    print(f"처리 후: {after:,}개")
    print(f"저장 위치: {OUTPUT_SHELTERS}")

    print("\n대피소 유형별 개수")
    print(shelters["shelter_type"].value_counts().head(20))

    return shelters


def make_easy_guide(content: str):
    """
    행동요령 원문을 쉬운 설명 컬럼으로 사용하기 위한 간단한 변환.
    나중에 LLM/RAG 답변 생성에서는 content를 직접 검색하고,
    easy_content는 사용자 화면에 간단히 보여줄 때 사용한다.
    """
    if pd.isna(content):
        return ""

    text = str(content).strip()

    # 앞에 붙은 불릿 기호 정리
    text = re.sub(r"^[\-\*\•\·]\s*", "", text)

    return text


def prepare_action_guides():
    """
    자연재난_국민행동요령_전체.csv를 RAG 검색용 action_guides.csv로 변환한다.
    """
    df = pd.read_csv(GUIDE_PATH, encoding="utf-8-sig")

    # 행동요령 내용 없는 행 제거
    df = df.dropna(subset=["actRmks"])

    result = pd.DataFrame()
    result["guide_id"] = range(1, len(df) + 1)

    # 요청카테고리명과 safety_cate_nm2가 약간 다를 수 있어 요청카테고리명을 우선 사용
    result["disaster_type"] = df["요청카테고리명"].apply(normalize_disaster_type)
    result["title"] = df["safety_cate_nm3"].fillna(df["요청카테고리명"].fillna(""))
    result["content"] = df["actRmks"].fillna("").astype(str)
    result["easy_content"] = result["content"].apply(make_easy_guide)

    result["keywords"] = (
        df["요청카테고리명"].fillna("").astype(str)
        + " "
        + df["safety_cate_nm2"].fillna("").astype(str)
        + " "
        + df["safety_cate_nm3"].fillna("").astype(str)
        + " "
        + result["disaster_type"].fillna("").astype(str)
    )

    result["source"] = "자연재난 국민행동요령"

    result = result[
        [
            "guide_id", "disaster_type", "title", "content",
            "easy_content", "keywords", "source"
        ]
    ]

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    result.to_csv(OUTPUT_GUIDES, index=False, encoding="utf-8-sig")

    print("[완료] action_guides.csv 생성")
    print(f"행동요령 수: {len(result):,}개")
    print(f"저장 위치: {OUTPUT_GUIDES}")

    print("\n재난유형별 행동요령 개수")
    print(result["disaster_type"].value_counts())

    return result


def main():
    print("======================================")
    print("SafeNavi 기본 데이터 전처리 시작")
    print("======================================")

    shelters = prepare_shelters()
    guides = prepare_action_guides()

    print("======================================")
    print("SafeNavi 기본 데이터 전처리 완료")
    print("======================================")
    print(f"shelters.csv: {len(shelters):,}개")
    print(f"action_guides.csv: {len(guides):,}개")


if __name__ == "__main__":
    main()