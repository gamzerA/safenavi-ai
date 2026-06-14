"""
SafeNavi 긴급재난문자 자동 업데이트 오케스트레이터

수집 → 병합 → AI 분석 → 캐시 초기화 과정을 한 번에 수행한다.
중복 실행을 막기 위해 잠금 파일을 사용한다.
"""

from __future__ import annotations

import os
import runpy
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors.disaster_alert_collector import save_disaster_alerts


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_ALERTS_PATH = (
    BASE_DIR / "data" / "raw" / "disaster_alerts_raw.csv"
)
PROCESSED_ALERTS_PATH = (
    BASE_DIR / "data" / "processed" / "disaster_alerts.csv"
)
ANALYZED_ALERTS_PATH = (
    BASE_DIR / "data" / "processed"
    / "disaster_alerts_analyzed.csv"
)
AI_ANALYSIS_SCRIPT = (
    BASE_DIR / "preprocess" / "apply_ai_analysis_to_alerts.py"
)
LOCK_PATH = BASE_DIR / "data" / ".disaster_alert_update.lock"


class UpdateAlreadyRunningError(RuntimeError):
    """다른 업데이트 작업이 진행 중일 때 발생한다."""


def get_positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()

    try:
        number = int(value)
        return number if number > 0 else default
    except (TypeError, ValueError):
        return default


def acquire_lock(stale_seconds: int = 600) -> None:
    """
    잠금 파일을 원자적으로 생성한다.
    오래된 잠금 파일은 비정상 종료 잔여물로 보고 제거한다.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    if LOCK_PATH.exists():
        age = time.time() - LOCK_PATH.stat().st_mtime

        if age > stale_seconds:
            print(
                "[긴급재난문자] 오래된 잠금 파일을 제거합니다."
            )
            LOCK_PATH.unlink(missing_ok=True)

    try:
        file_descriptor = os.open(
            LOCK_PATH,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError as error:
        raise UpdateAlreadyRunningError(
            "긴급재난문자 업데이트가 이미 실행 중입니다."
        ) from error

    with os.fdopen(file_descriptor, "w", encoding="utf-8") as lock_file:
        lock_file.write(
            f"pid={os.getpid()}\n"
            f"started_at={datetime.now().isoformat()}\n"
        )


def release_lock() -> None:
    LOCK_PATH.unlink(missing_ok=True)


def clear_runtime_caches() -> None:
    """업데이트 후 가능한 데이터 로딩 캐시를 초기화한다."""
    cache_targets = [
        ("modules.shelter_recommender", "load_alerts_cached"),
        ("modules.shelter_recommender", "load_shelters_cached"),
        ("modules.safety_score", "load_alerts_cached"),
        ("modules.safety_score", "load_data_cached"),
    ]

    for module_name, function_name in cache_targets:
        try:
            module = __import__(
                module_name,
                fromlist=[function_name],
            )
            function = getattr(module, function_name, None)
            cache_clear = getattr(function, "cache_clear", None)

            if callable(cache_clear):
                cache_clear()
        except Exception:
            # 해당 함수가 없는 프로젝트 버전에서도 동작하도록 한다.
            continue


def run_ai_analysis() -> None:
    """전처리 스크립트를 실행해 분석 CSV를 다시 생성한다."""
    if not AI_ANALYSIS_SCRIPT.exists():
        raise FileNotFoundError(
            "AI 분석 스크립트를 찾을 수 없습니다: "
            f"{AI_ANALYSIS_SCRIPT}"
        )

    if not PROCESSED_ALERTS_PATH.exists():
        raise FileNotFoundError(
            "분석할 긴급재난문자 파일이 없습니다: "
            f"{PROCESSED_ALERTS_PATH}"
        )

    runpy.run_path(
        str(AI_ANALYSIS_SCRIPT),
        run_name="__main__",
    )

    if not ANALYZED_ALERTS_PATH.exists():
        raise RuntimeError(
            "AI 분석이 실행됐지만 분석 결과 파일이 생성되지 않았습니다."
        )


def update_disaster_alerts(
    days: int | None = None,
    region_name: str | None = None,
) -> dict[str, Any]:
    """긴급재난문자 자동 업데이트 전체 작업을 실행한다."""
    if days is None:
        days = get_positive_int_env(
            "DISASTER_UPDATE_DAYS",
            2,
        )

    started_at = datetime.now()
    acquire_lock()

    try:
        processed_df = save_disaster_alerts(
            days=days,
            region_name=region_name,
            save_empty=False,
            merge_existing=True,
        )

        run_ai_analysis()
        clear_runtime_caches()

        finished_at = datetime.now()

        return {
            "updated": True,
            "days": days,
            "region_name": region_name,
            "total_processed_count": int(len(processed_df)),
            "raw_file": str(RAW_ALERTS_PATH),
            "processed_file": str(PROCESSED_ALERTS_PATH),
            "analyzed_file": str(ANALYZED_ALERTS_PATH),
            "started_at": started_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "finished_at": finished_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "elapsed_seconds": round(
                (finished_at - started_at).total_seconds(),
                2,
            ),
            "message": (
                "긴급재난문자 수집·병합·AI 분석이 "
                "완료되었습니다."
            ),
        }

    finally:
        release_lock()


if __name__ == "__main__":
    print(
        update_disaster_alerts(
            days=None,
            region_name=None,
        )
    )
