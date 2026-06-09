import os
import sys
import pandas as pd


# 현재 파일 기준으로 프로젝트 루트 경로 잡기
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

# modules 폴더 import를 위해 프로젝트 루트를 경로에 추가
sys.path.append(PROJECT_ROOT)

from modules.ai_disaster_analyzer import analyze_disaster_message


INPUT_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "disaster_alerts.csv")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "disaster_alerts_analyzed.csv")


def find_column(df, candidates):
    """
    후보 컬럼명 중 실제 DataFrame에 존재하는 컬럼명을 찾는다.
    """
    for col in candidates:
        if col in df.columns:
            return col

    return None


def apply_ai_analysis_to_alerts(
    input_path=INPUT_PATH,
    output_path=OUTPUT_PATH
):
    """
    disaster_alerts.csv의 긴급재난문자에 AI 분석 결과 컬럼을 추가한다.

    입력:
    - data/processed/disaster_alerts.csv

    출력:
    - data/processed/disaster_alerts_analyzed.csv
    """

    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"입력 파일을 찾을 수 없습니다: {input_path}\n"
            "먼저 collectors/disaster_alert_collector.py를 실행해서 disaster_alerts.csv를 생성하세요."
        )

    df = pd.read_csv(input_path, encoding="utf-8-sig")

    if df.empty:
        print("[AI 분석] disaster_alerts.csv가 비어 있습니다.")
        print("[AI 분석] 빈 분석 결과 파일을 생성합니다.")

        empty_columns = [
            "is_natural_disaster",
            "ai_disaster_type",
            "ai_region",
            "ai_risk_level",
            "dangerous_action",
            "recommended_action",
            "easy_summary"
        ]

        for col in empty_columns:
            df[col] = ""

        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        return df

    message_col = find_column(
        df,
        ["message", "MSG_CN", "msgCn", "재난문자내용", "메시지내용", "내용"]
    )

    region_col = find_column(
        df,
        ["region", "RCPTN_RGN_NM", "rcptnRgnNm", "수신지역", "지역"]
    )

    if message_col is None:
        raise ValueError(
            "재난문자 내용 컬럼을 찾지 못했습니다.\n"
            "message 또는 MSG_CN 컬럼이 필요합니다.\n"
            f"현재 컬럼: {list(df.columns)}"
        )

    analyzed_rows = []

    print("======================================")
    print("[AI 분석] 긴급재난문자 분석 시작")
    print("======================================")
    print(f"입력 파일: {input_path}")
    print(f"전체 문자 수: {len(df):,}개")
    print(f"문자 컬럼: {message_col}")
    print(f"지역 컬럼: {region_col if region_col else '없음'}")
    print("======================================")

    for idx, row in df.iterrows():
        message = row.get(message_col, "")
        api_region = row.get(region_col, None) if region_col else None

        result = analyze_disaster_message(
            message=message,
            api_region=api_region
        )

        analyzed_rows.append(result)

        if (idx + 1) % 50 == 0:
            print(f"[AI 분석] {idx + 1:,}개 처리 완료")

    analysis_df = pd.DataFrame(analyzed_rows)

    df["is_natural_disaster"] = analysis_df["is_natural_disaster"]
    df["ai_disaster_type"] = analysis_df["disaster_type"]
    df["ai_region"] = analysis_df["region"]
    df["ai_risk_level"] = analysis_df["risk_level"]

    df["dangerous_action"] = analysis_df["dangerous_action"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else ""
    )

    df["recommended_action"] = analysis_df["recommended_action"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else ""
    )

    df["easy_summary"] = analysis_df["easy_summary"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print()
    print("======================================")
    print("[AI 분석] 긴급재난문자 분석 완료")
    print("======================================")
    print(f"저장 파일: {output_path}")
    print(f"전체 문자 수: {len(df):,}개")
    print()

    print("[AI 분석] 자연재난 여부")
    print(df["is_natural_disaster"].value_counts())
    print()

    print("[AI 분석] 재난 유형별 개수")
    print(df["ai_disaster_type"].value_counts())
    print()

    print("[AI 분석] 위험도별 개수")
    print(df["ai_risk_level"].value_counts())
    print()

    natural_df = df[df["is_natural_disaster"] == True]

    if not natural_df.empty:
        print("[AI 분석] 자연재난 문자 미리보기")
        preview_cols = [
            "created_at",
            "region",
            "disaster_category",
            "ai_disaster_type",
            "ai_risk_level",
            "easy_summary"
        ]

        existing_preview_cols = [col for col in preview_cols if col in df.columns]
        print(natural_df[existing_preview_cols].head(5))
    else:
        print("[AI 분석] 이번 수집 데이터에는 자연재난으로 분류된 문자가 없습니다.")
        print("화재, 정전, 붕괴, 실종자 등은 기타/제외로 분류됩니다.")

    return df


if __name__ == "__main__":
    apply_ai_analysis_to_alerts()