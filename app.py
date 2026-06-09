import os
import pandas as pd
from flask import Flask, render_template, request

from modules.safety_score import calculate_today_safety_score
from modules.shelter_recommender import recommend_shelters
from modules.action_guide_rag import generate_rag_answer
from modules.share_message import generate_share_message


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data", "processed")

RECOMMENDED_SHELTERS_PATH = os.path.join(
    DATA_DIR, "recommended_shelters.csv"
)

SHARE_MESSAGE_PATH = os.path.join(
    DATA_DIR, "share_message.txt"
)


app = Flask(__name__)



# 공통 함수


def safe_read_csv(path):
    """
    CSV 파일을 안전하게 읽는 함수
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
    DataFrame을 HTML에서 쓰기 쉬운 dict list로 변환
    """
    if df is None or df.empty:
        return []

    df = df.fillna("")
    return df.to_dict(orient="records")


def get_default_user_location():
    """
    테스트용 사용자 위치.
    실제 서비스에서는 브라우저 GPS 또는 지도 클릭 좌표로 대체 가능.
    """
    return {
        "lat": 37.2410,
        "lon": 127.1776,
        "region": "경기도 용인시"
    }



# 1. 메인 화면


@app.route("/")
def index():
    """
    SafeNavi 메인 페이지
    """
    user_location = get_default_user_location()

    return render_template(
        "index.html",
        user_location=user_location
    )



# 2. 오늘의 안전지수 화면


@app.route("/safety")
def safety():
    """
    오늘의 안전지수 결과 화면
    """

    try:
        result = calculate_today_safety_score()

        safety_result = {
            "safety_score": result.get("safety_score", 0),
            "risk_score": result.get("risk_score", 0),
            "safety_level": result.get("safety_level", "정보 없음"),
            "alert_risk_score": result.get("alert_risk_score", 0),
            "weather_warning_risk_score": result.get("weather_warning_risk_score", 0),
            "living_weather_risk_score": result.get("living_weather_risk_score", 0),
            "main_risk_types": result.get("main_risk_types", []),
            "recommended_actions": result.get("recommended_actions", []),
            "natural_alert_count": result.get("natural_alert_count", 0),
            "high_risk_alert_count": result.get("high_risk_alert_count", 0),
            "weather_warning_count": result.get("weather_warning_count", 0),
            "living_weather_count": result.get("living_weather_count", 0)
        }

    except Exception as e:
        print(f"[안전지수 오류] {e}")

        safety_result = {
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
            "natural_alert_count": 0,
            "high_risk_alert_count": 0,
            "weather_warning_count": 0,
            "living_weather_count": 0
        }

    return render_template(
        "safety.html",
        safety_result=safety_result
    )



# 3. 맞춤형 대피소 추천 화면


@app.route("/shelters", methods=["GET", "POST"])
def shelters():
    """
    사용자 위치 기반 대피소 추천 화면.

    속도 개선:
    - GET 요청에서는 대피소 추천 계산을 하지 않는다.
    - POST 요청, 즉 버튼을 눌렀을 때만 recommend_shelters()를 실행한다.
    """

    user_location = get_default_user_location()

    user_lat = user_location["lat"]
    user_lon = user_location["lon"]
    user_region = user_location["region"]

    selected_disaster_type = None
    shelters_result = []
    error_message = None
    has_searched = False

    # 처음 페이지 접속 시에는 계산하지 않고 입력 화면만 보여준다.
    if request.method == "GET":
        return render_template(
            "shelters.html",
            user_lat=user_lat,
            user_lon=user_lon,
            user_region=user_region,
            selected_disaster_type=selected_disaster_type,
            shelters=shelters_result,
            error_message=error_message,
            has_searched=has_searched
        )

    # 버튼을 눌렀을 때만 여기부터 실행
    has_searched = True

    try:
        user_lat = float(request.form.get("lat", user_lat))
        user_lon = float(request.form.get("lon", user_lon))
        user_region = request.form.get("region", user_region).strip()

        selected_disaster_type = request.form.get("disaster_type", "").strip()

        if selected_disaster_type == "":
            selected_disaster_type = None

    except Exception:
        error_message = "위도와 경도 값을 올바르게 입력해주세요."

        return render_template(
            "shelters.html",
            user_lat=user_lat,
            user_lon=user_lon,
            user_region=user_region,
            selected_disaster_type=selected_disaster_type,
            shelters=shelters_result,
            error_message=error_message,
            has_searched=has_searched
        )

    try:
        result_df = recommend_shelters(
            user_lat=user_lat,
            user_lon=user_lon,
            disaster_type=selected_disaster_type,
            top_n=3,
            max_distance_km=20
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
        selected_disaster_type=selected_disaster_type,
        shelters=shelters_result,
        error_message=error_message,
        has_searched=has_searched
    )



# 4. 행동요령 RAG 검색 화면


@app.route("/guide", methods=["GET", "POST"])
def guide():
    """
    사용자가 질문을 입력하면 행동요령 RAG 답변 생성
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
                rag_result = generate_rag_answer(
                    question=question,
                    top_n=3
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



# 5. 가족 안심 공유 문구 화면


@app.route("/share", methods=["GET", "POST"])
def share():
    """
    가족에게 보낼 안심 공유 문구 생성.

    속도 개선:
    - GET 요청에서는 공유 문구를 자동 생성하지 않는다.
    - POST 요청에서만 generate_share_message() 실행.
    """

    user_location = get_default_user_location()

    user_status = "안전"
    user_region = user_location["region"]
    tone = "normal"

    share_message = None
    short_share_message = None
    error_message = None
    has_generated = False

    # 처음 페이지 접속 시에는 생성하지 않고 입력 화면만 보여준다.
    if request.method == "GET":
        return render_template(
            "share.html",
            user_status=user_status,
            user_region=user_region,
            tone=tone,
            share_message=share_message,
            short_share_message=short_share_message,
            error_message=error_message,
            has_generated=has_generated
        )

    # 버튼을 눌렀을 때만 문구 생성
    has_generated = True

    user_status = request.form.get("user_status", "안전").strip()
    user_region = request.form.get("user_region", user_region).strip()
    tone = request.form.get("tone", "normal").strip()

    if user_status == "":
        user_status = "안전"

    if user_region == "":
        user_region = user_location["region"]

    try:
        share_message = generate_share_message(
            user_status=user_status,
            user_region=user_region,
            include_shelter=True,
            tone=tone
        )

        short_share_message = generate_share_message(
            user_status=user_status,
            user_region=user_region,
            include_shelter=True,
            tone="short"
        )

    except Exception as e:
        print(f"[안심 공유 문구 오류] {e}")
        error_message = str(e)

    return render_template(
        "share.html",
        user_status=user_status,
        user_region=user_region,
        tone=tone,
        share_message=share_message,
        short_share_message=short_share_message,
        error_message=error_message,
        has_generated=has_generated
    )



# 6. CSV 결과 확인용 

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
        selected_disaster_type=None,
        shelters=shelters_result,
        error_message=None,
        has_searched=True
    )


# 7. 상태 확인용 경로
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