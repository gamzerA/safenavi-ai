from collectors.disaster_alert_collector import save_disaster_alerts
from collectors.weather_warning_collector import save_weather_warnings


def main():

    print("SafeNavi API 데이터 연결 시작")


    print("\n[1] 긴급재난문자 데이터 수집")
    try:
        save_disaster_alerts(region_name="용인시")
    except Exception as e:
        print(f"[오류] 긴급재난문자 수집 실패: {e}")

    print("\n[2] 기상특보 데이터 수집")
    try:
        save_weather_warnings(stn_id="109")
    except Exception as e:
        print(f"[오류] 기상특보 수집 실패: {e}")


    print("SafeNavi API 데이터 연결 종료")



if __name__ == "__main__":
    main()