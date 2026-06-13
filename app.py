import os
import requests
import pandas as pd
from flask import Flask, render_template, request

from modules.safety_score import calculate_today_safety_score
from modules.shelter_recommender import recommend_shelters
from modules.action_guide_rag import generate_rag_answer
from modules.share_message import generate_share_message
from modules.update_disaster_alerts import update_disaster_alerts


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data", "processed")

RECOMMENDED_SHELTERS_PATH = os.path.join(
    DATA_DIR, "recommended_shelters.csv"
)

SHARE_MESSAGE_PATH = os.path.join(
    DATA_DIR, "share_message.txt"
)

KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")


app = Flask(__name__)



# 공통 함수

def safe_read_csv(path):
    """
    CSV 파일을 읽는 함수.
    파일이 없거나 비어 있으면 빈 DataFrame을 반환한다.
    """
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as e:
        print(f"[CSV 읽기 오류] {path}: {e}")
        return pd.DataFrame()


def dataframe_to_dict_list(df):
    """
    DataFrame을 HTML에서 사용하기 쉬운 dict list로 변환한다.
    """
    if df is None or df.empty:
        return []

    df = df.fillna("")
    return df.to_dict(orient="records")


def safe_int(value, default=0):
    """
    None, 빈 문자열, NaN, 숫자 문자열을 안전한 정수로 변환한다.
    화면에서 값이 없을 때 빈칸 대신 0을 표시하기 위해 사용한다.
    """
    try:
        if value is None:
            return default

        if pd.isna(value):
            return default

        text = str(value).strip()

        if text == "":
            return default

        return int(float(text))

    except (TypeError, ValueError):
        return default


def safe_list(value):
    """None 또는 비목록 값을 안전한 목록으로 변환한다."""
    return value if isinstance(value, list) else []


def get_default_user_location():
    """
    테스트용 기본 사용자 위치.
    실제 서비스에서는 브라우저 GPS 좌표 또는 주소 검색 좌표가 POST 요청으로 들어온다.
    """
    return {
        "lat": 37.2410,
        "lon": 127.1776,
        "region": "경기도 용인시"
    }


def build_kakao_region(address_data):
    """
    Kakao 주소 응답에서 안전지수 지역 필터에 사용할 행정구역명을 만든다.

    예:
    경기도 + 용인시 처인구 + 역북동
    -> 경기도 용인시 처인구 역북동
    """

    if not isinstance(address_data, dict):
        return ""

    region_parts = [
        str(address_data.get("region_1depth_name", "")).strip(),
        str(address_data.get("region_2depth_name", "")).strip(),
        str(address_data.get("region_3depth_name", "")).strip()
    ]

    return " ".join(part for part in region_parts if part)




# 주소 변환 API

@app.route("/api/geocode")
def geocode_address():
    """
    주소를 위도·경도로 변환한다.
    주소 검색 기반 대피소 추천에서 사용한다.
    """

    address = request.args.get("address", "").strip()

    if address == "":
        return {
            "status": "error",
            "message": "주소가 비어 있습니다."
        }, 400

    if not KAKAO_REST_API_KEY:
        return {
            "status": "error",
            "message": "KAKAO_REST_API_KEY가 설정되어 있지 않습니다."
        }, 500

    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers={
                "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"
            },
            params={
                "query": address
            },
            timeout=5
        )

        response.raise_for_status()

        data = response.json()
        documents = data.get("documents", [])

        if not documents:
            return {
                "status": "error",
                "message": "주소 좌표를 찾지 못했습니다."
            }, 404

        first = documents[0]
        address_info = first.get("address") or {}
        road_address_info = first.get("road_address") or {}

        region_name = build_kakao_region(address_info)

        if not region_name:
            region_name = build_kakao_region(road_address_info)

        return {
            "status": "success",
            "address": first.get("address_name", address),
            "region": region_name or address,
            "lat": first.get("y"),
            "lon": first.get("x")
        }

    except Exception as e:
        print(f"[주소 좌표 변환 오류] {e}")

        return {
            "status": "error",
            "message": "주소 좌표 변환 중 오류가 발생했습니다."
        }, 500


@app.route("/api/reverse-geocode")
def reverse_geocode():
    """
    위도·경도를 주소로 변환한다.
    현재 위치 기반 대피소 추천 표시용, 가족 안심 공유 위치 입력용으로 사용한다.
    """

    lat = request.args.get("lat", "").strip()
    lon = request.args.get("lon", "").strip()

    if lat == "" or lon == "":
        return {
            "status": "error",
            "message": "위치 좌표가 비어 있습니다."
        }, 400

    if not KAKAO_REST_API_KEY:
        return {
            "status": "error",
            "message": "KAKAO_REST_API_KEY가 설정되어 있지 않습니다."
        }, 500

    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/local/geo/coord2address.json",
            headers={
                "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"
            },
            params={
                "x": lon,
                "y": lat
            },
            timeout=5
        )

        response.raise_for_status()

        data = response.json()
        documents = data.get("documents", [])

        if not documents:
            return {
                "status": "error",
                "message": "현재 위치의 주소를 찾지 못했습니다."
            }, 404

        first = documents[0]

        road_address = first.get("road_address")
        jibun_address = first.get("address")

        address_name = ""

        if road_address:
            address_name = road_address.get("address_name", "")

        if address_name == "" and jibun_address:
            address_name = jibun_address.get("address_name", "")

        if address_name == "":
            address_name = "현재 위치"

        region_name = build_kakao_region(jibun_address or {})

        if not region_name:
            region_name = build_kakao_region(road_address or {})

        return {
            "status": "success",
            "lat": lat,
            "lon": lon,
            "address": address_name,
            "region": region_name or address_name
        }

    except Exception as e:
        print(f"[현재 위치 주소 변환 오류] {e}")

        return {
            "status": "error",
            "message": "현재 위치 주소 변환 중 오류가 발생했습니다."
        }, 500


# RAG 결과 화면 표시용 정규화 함수

def infer_disaster_type_from_text(text):
    """
    질문 또는 답변 문장에서 재난 유형을 추정한다.
    RAG 결과에 disaster_type 값이 없을 때 화면 표시용으로 사용한다.
    """
    text = str(text)

    keyword_map = {
        "호우/침수": ["호우", "침수", "폭우", "지하차도", "하천", "홍수"],
        "태풍": ["태풍", "강풍", "바람"],
        "폭염": ["폭염", "더위", "무더위", "온열"],
        "한파": ["한파", "추위", "동파"],
        "대설": ["대설", "폭설", "눈", "결빙"],
        "지진": ["지진", "흔들림"],
        "지진해일": ["지진해일", "해일", "쓰나미"],
        "산사태": ["산사태", "토사", "비탈", "급경사지"],
        "낙뢰": ["낙뢰", "번개", "천둥"],
        "황사": ["황사", "미세먼지"],
        "화재": ["화재", "불", "연기", "소화기", "119", "엘리베이터"]
    }

    for disaster_type, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword in text:
                return disaster_type

    return "분석 정보 없음"


def get_first_value(data, keys, default=""):
    """
    dict에서 여러 후보 키 중 첫 번째로 존재하는 값을 가져온다.
    값이 None이거나 빈 문자열이면 다음 후보 키를 확인한다.
    """
    if not isinstance(data, dict):
        return default

    for key in keys:
        value = data.get(key)

        if value is not None and str(value).strip() != "":
            return value

    return default


def normalize_reference_item(item):
    """
    RAG 참고 문헌 1개를 화면에서 쓰기 쉬운 구조로 변환한다.
    """

    if not isinstance(item, dict):
        return {
            "disaster_type": infer_disaster_type_from_text(str(item)),
            "title": str(item),
            "score": "점수 정보 없음"
        }

    ref_disaster_type = get_first_value(
        item,
        [
            "disaster_type",
            "detected_disaster_type",
            "query_disaster_type",
            "main_disaster_type",
            "disaster_category",
            "category",
            "type",
            "재난유형"
        ],
        default=""
    )

    ref_title = get_first_value(
        item,
        [
            "title",
            "guide_title",
            "manual_title",
            "name",
            "action_title",
            "content_title",
            "행동요령명",
            "제목"
        ],
        default="행동요령 제목 없음"
    )

    ref_score = get_first_value(
        item,
        [
            "score",
            "final_score",
            "similarity_score",
            "total_score",
            "match_score",
            "rag_score",
            "search_score",
            "keyword_score",
            "점수"
        ],
        default=""
    )

    if ref_disaster_type == "":
        ref_disaster_type = infer_disaster_type_from_text(ref_title)

    if ref_score == "":
        ref_score = "점수 정보 없음"

    return {
        "disaster_type": ref_disaster_type,
        "title": ref_title,
        "score": ref_score
    }


def normalize_rag_result(rag_result, question=""):
    """
    action_guide_rag.py에서 반환한 결과를 guide.html에서 쓰기 쉬운 구조로 정리한다.
    """

    if rag_result is None:
        return None

    if not isinstance(rag_result, dict):
        answer_text = str(rag_result)

        return {
            "disaster_type": infer_disaster_type_from_text(question + " " + answer_text),
            "situation_type": "일반 상황",
            "answer": answer_text,
            "references": []
        }

    answer = get_first_value(
        rag_result,
        ["answer", "response", "result", "message", "content"],
        default=""
    )

    situation_type = get_first_value(
        rag_result,
        ["situation_type_korean", "situation_type", "situation", "stage", "context_type"],
        default="일반 상황"
    )

    disaster_type = get_first_value(
        rag_result,
        [
            "disaster_type",
            "detected_disaster_type",
            "query_disaster_type",
            "main_disaster_type",
            "disaster_category",
            "category",
            "type"
        ],
        default=""
    )

    references = get_first_value(
        rag_result,
        [
            "references",
            "reference_list",
            "top_guides",
            "results",
            "search_results",
            "matched_guides",
            "retrieved_guides"
        ],
        default=[]
    )

    if references is None:
        references = []

    normalized_references = []

    if isinstance(references, list):
        for item in references:
            normalized_references.append(
                normalize_reference_item(item)
            )

    if disaster_type == "":
        if normalized_references:
            disaster_type = normalized_references[0].get("disaster_type", "")

        if disaster_type == "" or disaster_type == "재난유형 미분류":
            disaster_type = infer_disaster_type_from_text(question + " " + answer)

    if answer == "":
        answer = "답변을 생성하지 못했습니다."

    return {
        "disaster_type": disaster_type,
        "situation_type": situation_type,
        "answer": answer,
        "summary": rag_result.get("summary", answer),
        "immediate_actions": rag_result.get("immediate_actions", []) or [],
        "prohibited_actions": rag_result.get("prohibited_actions", []) or [],
        "detail": rag_result.get("detail", ""),
        "best_title": rag_result.get("best_title", ""),
        "best_score": rag_result.get("best_score", 0),
        "is_low_confidence": bool(rag_result.get("is_low_confidence", False)),
        "references": normalized_references
    }


# 메인 화면

@app.route("/")
def index():
    """
    SafeNavi 메인 페이지.
    """
    user_location = get_default_user_location()

    return render_template(
        "index.html",
        user_location=user_location
    )


# 오늘의 안전지수 화면

@app.route("/safety", methods=["GET", "POST"])
def safety():
    """
    오늘의 안전지수 결과 화면.

    지원 방식:
    1. 사용자가 지역명 또는 주소를 검색
    2. 브라우저 현재 위치를 주소로 변환하여 조회
    3. 전국 기준 조회

    실제 안전점수 계산에는 최종적으로 확인된 행정구역명(region)을 사용한다.
    """

    region_options = [
        "서울특별시",
        "부산광역시",
        "대구광역시",
        "인천광역시",
        "광주광역시",
        "대전광역시",
        "울산광역시",
        "세종특별자치시",
        "경기도",
        "경기도 용인시",
        "경기도 수원시",
        "경기도 성남시",
        "경기도 고양시",
        "경기도 화성시",
        "경기도 안양시",
        "강원특별자치도",
        "충청북도",
        "충청남도",
        "전북특별자치도",
        "전라남도",
        "경상북도",
        "경상남도",
        "제주특별자치도"
    ]

    selected_region = request.values.get("region", "").strip()
    selected_address = request.values.get("address", "").strip()
    search_mode = request.values.get("mode", "region").strip()
    latitude = request.values.get("lat", "").strip()
    longitude = request.values.get("lon", "").strip()
    error_message = None

    if selected_region in ["전국", "전체", "전국 기준"]:
        selected_region = ""
        selected_address = ""
        search_mode = "all"

    try:
        result = calculate_today_safety_score(
            region_name=selected_region
        )

        alert_detail = result.get("alert_detail", {}) or {}
        weather_detail = result.get("weather_detail", {}) or {}
        living_detail = result.get("living_detail", {}) or {}

        safety_result = {
            "selected_region": result.get("selected_region", selected_region),
            "safety_score": safe_int(result.get("safety_score", 0)),
            "risk_score": safe_int(result.get("risk_score", 0)),
            "safety_level": result.get("safety_level", "정보 없음") or "정보 없음",
            "alert_risk_score": safe_int(
                result.get("alert_risk_score", result.get("alert_score", 0))
            ),
            "weather_warning_risk_score": safe_int(
                result.get(
                    "weather_warning_risk_score",
                    result.get("weather_score", 0)
                )
            ),
            "living_weather_risk_score": safe_int(
                result.get(
                    "living_weather_risk_score",
                    result.get("living_score", 0)
                )
            ),
            "main_risk_types": safe_list(result.get("main_risk_types", [])),
            "recommended_actions": safe_list(
                result.get(
                    "recommended_actions",
                    result.get("recommendations", [])
                )
            ),
            "relevant_alert_count": safe_int(
                result.get(
                    "relevant_alert_count",
                    alert_detail.get(
                        "relevant_alert_count",
                        result.get("natural_alert_count", 0)
                    )
                )
            ),
            "natural_alert_count": safe_int(
                result.get(
                    "natural_alert_count",
                    alert_detail.get("natural_alert_count", 0)
                )
            ),
            "high_risk_alert_count": safe_int(
                result.get(
                    "high_risk_alert_count",
                    alert_detail.get("high_risk_alert_count", 0)
                )
            ),
            "fire_alert_count": safe_int(
                result.get(
                    "fire_alert_count",
                    alert_detail.get("fire_alert_count", 0)
                )
            ),
            "wildfire_alert_count": safe_int(
                result.get(
                    "wildfire_alert_count",
                    alert_detail.get("wildfire_alert_count", 0)
                )
            ),
            "weather_warning_count": safe_int(
                result.get(
                    "weather_warning_count",
                    weather_detail.get("weather_warning_count", 0)
                )
            ),
            "living_weather_count": safe_int(
                result.get(
                    "living_weather_count",
                    living_detail.get("living_weather_count", 0)
                )
            ),
            "local_alerts": safe_list(result.get("local_alerts", [])),
            "score_formula": result.get("score_formula", {}) or {}
        }

    except Exception as e:
        print(f"[안전지수 오류] {e}")
        error_message = str(e)

        safety_result = {
            "selected_region": selected_region,
            "safety_score": 0,
            "risk_score": 0,
            "safety_level": "계산 실패",
            "alert_risk_score": 0,
            "weather_warning_risk_score": 0,
            "living_weather_risk_score": 0,
            "main_risk_types": [],
            "recommended_actions": [
                "안전지수 계산 중 오류가 발생했습니다.",
                "data/processed 폴더에 필요한 CSV 파일이 있는지 확인하세요."
            ],
            "relevant_alert_count": 0,
            "natural_alert_count": 0,
            "high_risk_alert_count": 0,
            "fire_alert_count": 0,
            "wildfire_alert_count": 0,
            "weather_warning_count": 0,
            "living_weather_count": 0,
            "local_alerts": [],
            "score_formula": {}
        }

    return render_template(
        "safety.html",
        safety_result=safety_result,
        selected_region=selected_region,
        selected_address=selected_address,
        search_mode=search_mode,
        latitude=latitude,
        longitude=longitude,
        region_options=region_options,
        error_message=error_message
    )


# 맞춤형 대피소 추천 화면

@app.route("/shelters", methods=["GET", "POST"])
def shelters():
    """
    맞춤형 대피소 추천 화면.

    GET:
    - 처음 접속 시 추천 계산을 하지 않고 입력 화면만 보여준다.

    POST:
    - 현재 위치 또는 주소 검색으로 전달된 좌표를 기준으로 대피소를 추천한다.
    """

    user_location = get_default_user_location()

    user_lat = user_location["lat"]
    user_lon = user_location["lon"]
    user_region = user_location["region"]

    selected_disaster_type = None
    shelters_result = []
    error_message = None
    has_searched = False

    search_mode = "default"
    user_address = ""

    if request.method == "GET":
        return render_template(
            "shelters.html",
            user_lat=user_lat,
            user_lon=user_lon,
            user_region=user_region,
            user_address=user_address,
            search_mode=search_mode,
            selected_disaster_type=selected_disaster_type,
            shelters=shelters_result,
            error_message=error_message,
            has_searched=has_searched
        )

    has_searched = True

    try:
        lat_value = (request.form.get("lat") or "").strip()
        lon_value = (request.form.get("lon") or "").strip()

        if lat_value == "" or lon_value == "":
            raise ValueError("위치 좌표가 비어 있습니다.")

        user_lat = float(lat_value)
        user_lon = float(lon_value)

        user_region = (request.form.get("region") or user_region).strip()
        user_address = (request.form.get("user_address") or "").strip()
        search_mode = (request.form.get("search_mode") or "default").strip()

        selected_disaster_type = (request.form.get("disaster_type") or "").strip()

        if selected_disaster_type == "":
            selected_disaster_type = None

        if user_address != "":
            user_region = user_address

    except Exception:
        error_message = "위치 정보를 가져오지 못했습니다. 현재 위치를 허용하거나 주소를 다시 선택해주세요."

        return render_template(
            "shelters.html",
            user_lat=user_lat,
            user_lon=user_lon,
            user_region=user_region,
            user_address=user_address,
            search_mode=search_mode,
            selected_disaster_type=selected_disaster_type,
            shelters=shelters_result,
            error_message=error_message,
            has_searched=has_searched
        )

    try:
        result_df = recommend_shelters(
            user_lat=user_lat,
            user_lon=user_lon,
            user_region=user_region,
            disaster_type=selected_disaster_type,
            top_n=3,
            max_distance_km=10
        )

        shelters_result = dataframe_to_dict_list(result_df)

    except Exception as e:
        print(f"[대피소 추천 오류] {e}")
        error_message = str(e)
        shelters_result = []

    return render_template(
        "shelters.html",
        user_lat=user_lat,
        user_lon=user_lon,
        user_region=user_region,
        user_address=user_address,
        search_mode=search_mode,
        selected_disaster_type=selected_disaster_type,
        shelters=shelters_result,
        error_message=error_message,
        has_searched=has_searched
    )


# 행동요령 RAG 검색 화면

@app.route("/guide", methods=["GET", "POST"])
def guide():
    """
    사용자가 질문을 입력하면 자연재난 국민행동요령 기반 RAG 답변을 생성한다.
    """

    question = ""
    rag_result = None
    error_message = None
    has_searched = False

    if request.method == "POST":
        has_searched = True
        question = request.form.get("question", "").strip()

        if question == "":
            error_message = "질문을 입력해주세요."
        else:
            try:
                raw_rag_result = generate_rag_answer(
                    question=question,
                    top_n=3
                )

                rag_result = normalize_rag_result(
                    rag_result=raw_rag_result,
                    question=question
                )

            except Exception as e:
                print(f"[행동요령 RAG 오류] {e}")
                error_message = str(e)

    return render_template(
        "guide.html",
        question=question,
        rag_result=rag_result,
        error_message=error_message,
        has_searched=has_searched
    )


# 가족 안심 공유 문구 화면

@app.route("/share", methods=["GET", "POST"])
def share():
    """
    가족에게 보낼 안심 공유 문구 생성 화면.

    GET:
    - 처음 접속 시 자동 생성하지 않는다.

    POST:
    - 현재 위치 또는 주소 검색으로 전달된 좌표가 있으면 그 위치 기준으로 대피소를 다시 추천한다.
    - 선택한 위치명(user_region)을 기준으로 자연재난문자도 필터링한다.
    """

    user_location = get_default_user_location()

    user_status = "안전"
    user_region = user_location["region"]
    user_lat = ""
    user_lon = ""
    search_mode = "manual"
    tone = "normal"

    share_message = None
    short_share_message = None
    error_message = None
    has_generated = False

    if request.method == "GET":
        return render_template(
            "share.html",
            user_status=user_status,
            user_region=user_region,
            user_lat=user_lat,
            user_lon=user_lon,
            search_mode=search_mode,
            tone=tone,
            share_message=share_message,
            short_share_message=short_share_message,
            error_message=error_message,
            has_generated=has_generated
        )

    has_generated = True

    user_status = request.form.get("user_status", "안전").strip()
    user_region = request.form.get("user_region", user_region).strip()
    user_lat = request.form.get("lat", "").strip()
    user_lon = request.form.get("lon", "").strip()
    search_mode = request.form.get("search_mode", "manual").strip()
    tone = request.form.get("tone", "normal").strip()

    if user_status == "":
        user_status = "안전"

    if user_region == "":
        user_region = user_location["region"]

    recommended_df = None

    try:
        # 현재 위치/주소 검색으로 좌표가 들어온 경우, 공유 문구 생성 전에 대피소를 그 위치 기준으로 다시 계산한다.
        if user_lat != "" and user_lon != "":
            recommended_df = recommend_shelters(
                user_lat=float(user_lat),
                user_lon=float(user_lon),
                user_region=user_region,
                disaster_type=None,
                top_n=3,
                max_distance_km=10
            )

        share_message = generate_share_message(
            user_status=user_status,
            user_region=user_region,
            include_shelter=True,
            tone=tone,
            recommended_df=recommended_df
        )

        short_share_message = generate_share_message(
            user_status=user_status,
            user_region=user_region,
            include_shelter=True,
            tone="short",
            recommended_df=recommended_df
        )

    except Exception as e:
        print(f"[안심 공유 문구 오류] {e}")
        error_message = str(e)

    return render_template(
        "share.html",
        user_status=user_status,
        user_region=user_region,
        user_lat=user_lat,
        user_lon=user_lon,
        search_mode=search_mode,
        tone=tone,
        share_message=share_message,
        short_share_message=short_share_message,
        error_message=error_message,
        has_generated=has_generated
    )


# CSV 결과 확인용 화면

@app.route("/data/shelters")
def data_shelters():
    """
    이미 생성된 recommended_shelters.csv 결과 확인용 화면.
    이 경로는 추천 계산을 새로 하지 않고 CSV만 읽는다.
    """

    df = safe_read_csv(RECOMMENDED_SHELTERS_PATH)
    shelters_result = dataframe_to_dict_list(df)

    user_location = get_default_user_location()

    return render_template(
        "shelters.html",
        user_lat=user_location["lat"],
        user_lon=user_location["lon"],
        user_region=user_location["region"],
        user_address=user_location["region"],
        search_mode="csv",
        selected_disaster_type=None,
        shelters=shelters_result,
        error_message=None,
        has_searched=True
    )


# 긴급재난문자 자동 업데이트 경로

@app.route("/update-alerts")
def update_alerts():
    """
    긴급재난문자 자동 업데이트용 관리자 경로.

    사용 예:
    /update-alerts?key=설정한비밀키
    """

    secret_key = os.environ.get("UPDATE_SECRET_KEY")
    request_key = request.args.get("key")

    if not secret_key:
        return {
            "status": "error",
            "message": "UPDATE_SECRET_KEY가 설정되어 있지 않습니다."
        }, 500

    if request_key != secret_key:
        return {
            "status": "error",
            "message": "잘못된 접근입니다."
        }, 403

    try:
        result = update_disaster_alerts(
            days=7,
            region_name=None
        )

        return {
            "status": "success",
            "message": "긴급재난문자 업데이트가 완료되었습니다.",
            "result": result
        }

    except Exception as e:
        print(f"[긴급재난문자 업데이트 오류] {e}")

        return {
            "status": "error",
            "message": str(e)
        }, 500


# 상태 확인용 경로

@app.route("/health")
def health():
    """
    서버가 정상 작동하는지 확인하는 간단한 경로.
    """
    return {
        "status": "ok",
        "service": "SafeNavi"
    }


# 서버 실행

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )