from collectors.disaster_alert_collector import save_disaster_alerts
from collectors.weather_warning_collector import save_weather_warnings
from collectors.living_weather_collector import save_living_weather


def main():

    print("SafeNavi API 데이터 연결 시작")


    print("\n[1] 긴급재난문자 데이터 수집")
    try:
        save_disaster_alerts(
            days=7,
            region_name=None
        )
    except Exception as e:
        print(f"[오류] 긴급재난문자 수집 실패: {e}")

    print("\n[2] 기상특보 데이터 수집")
    try:
        save_weather_warnings(
            stn_id="109"
        )
    except Exception as e:
        print(f"[오류] 기상특보 수집 실패: {e}")

    print("\n[3] 생활기상지수 데이터 수집")
    try:
        save_living_weather(
            area_no="4146355000"
        )
    except Exception as e:
        print(f"[오류] 생활기상지수 수집 실패: {e}")

    
    print("SafeNavi API 데이터 연결 종료")
    


if __name__ == "__main__":
    main()