import requests
import json

BASE_URL = "http://127.0.0.1:8080/~/in-cse"
HEADERS_AE = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/json;ty=2"
}
HEADERS_CNT = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/json;ty=3"
}

def create_ae(ae_name, api_name):
    payload = {
        "m2m:ae": {
            "rn": ae_name,
            "api": api_name,
            "rr": True
        }
    }
    response = requests.post(BASE_URL, headers=HEADERS_AE, json=payload)
    print(f"[AE {ae_name}] Status: {response.status_code}")
    print(response.text)

def create_container(ae_name, cnt_name):
    url = f"{BASE_URL}/in-name/{ae_name}"
    payload = {
        "m2m:cnt": {
            "rn": cnt_name
        }
    }
    response = requests.post(url, headers=HEADERS_CNT, json=payload)
    print(f"[Container {cnt_name}] under AE {ae_name} → Status: {response.status_code}")
    print(response.text)

if __name__ == "__main__":
    # AE and Container for Fall Sensor
    create_ae("fall_sensor", "app-sensor")
    create_container("fall_sensor", "fall_data")

    # AE and Container for Voice Command
    create_ae("voice_command", "app-voice")
    create_container("voice_command", "command_data")
