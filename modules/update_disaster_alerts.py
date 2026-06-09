import os
import runpy
from datetime import datetime

from collectors.disaster_alert_collector import save_disaster_alerts


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RAW_ALERTS_PATH = os.path.join(
    BASE_DIR, "data", "raw", "disaster_alerts_raw.csv"
)

PROCESSED_ALERTS_PATH = os.path.join(
    BASE_DIR, "data", "processed", "disaster_alerts.csv"
)

ANALYZED_ALERTS_PATH = os.path.join(
    BASE_DIR, "data", "processed", "disaster_alerts_analyzed.csv"
)


def clear_runtime_caches():
    """
    긴급재난문자 CSV가 갱신된 뒤,
    서버 메모리에 남아 있을 수 있는 캐시를 초기화한다.
    """

    try:
        from modules.shelter_recommender import load_alerts_cached
        load_alerts_cached.cache_clear()
    except Exception:
        pass

    try:
        from modules.shelter_recommender import load_shelters_cached
        load_shelters_cached.cache_clear()
    except Exception:
        pass


def run_ai_analysis():
    """
    preprocess/apply_ai_analysis_to_alerts.py를 실행해서
    disaster_alerts.csv를 다시 분석하고
    disaster_alerts_analyzed.csv를 갱신한다.

    함수명이 달라도 작동하도록 runpy로 파일을 직접 실행한다.
    """

    runpy.run_path(
        os.path.join(
            BASE_DIR,
            "preprocess",
            "apply_ai_analysis_to_alerts.py"
        ),
        run_name="__main__"
    )


def update_disaster_alerts(days=7, region_name=None):
    """
    긴급재난문자 자동 업데이트 전체 흐름.

    1. 긴급재난문자 API 호출
    2. data/raw/disaster_alerts_raw.csv 저장
    3. data/processed/disaster_alerts.csv 저장
    4. AI 분석 재실행
    5. data/processed/disaster_alerts_analyzed.csv 갱신
    6. 캐시 초기화
    """

    started_at = datetime.now()

    processed_df = save_disaster_alerts(
        days=days,
        region_name=region_name,
        save_empty=True
    )

    collected_count = 0

    if processed_df is not None:
        try:
            collected_count = len(processed_df)
        except Exception:
            collected_count = 0

    run_ai_analysis()
    clear_runtime_caches()

    finished_at = datetime.now()

    return {
        "updated": True,
        "days": days,
        "region_name": region_name,
        "collected_count": collected_count,
        "raw_file": RAW_ALERTS_PATH,
        "processed_file": PROCESSED_ALERTS_PATH,
        "analyzed_file": ANALYZED_ALERTS_PATH,
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": finished_at.strftime("%Y-%m-%d %H:%M:%S"),
        "message": "긴급재난문자 수집 및 AI 분석이 완료되었습니다."
    }


if __name__ == "__main__":
    result = update_disaster_alerts(
        days=7,
        region_name=None
    )

    print(result)