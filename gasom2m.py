import requests
import json

OM2M_IP = "127.0.0.1"  # Replace with your OM2M IP if different
HEADERS = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/json;ty=2"  # AE creation
}

# Create AE (Application Entity)
ae_data = {
    "m2m:ae": {
        "rn": "gas_sensor",
        "api": "app-gas",
        "rr": True
    }
}

ae_url = f"http://{OM2M_IP}:8080/~/in-cse/in-name"
resp = requests.post(ae_url, headers=HEADERS, data=json.dumps(ae_data))
print("AE Creation:", resp.status_code, resp.text)

# Create container 'data' inside gas_sensor
HEADERS["Content-Type"] = "application/json;ty=3"  # Container creation
cnt_data = {
    "m2m:cnt": {
        "rn": "data"
    }
}

cnt_url = f"http://{OM2M_IP}:8080/~/in-cse/in-name/gas_sensor"
resp = requests.post(cnt_url, headers=HEADERS, data=json.dumps(cnt_data))
print("Container Creation:", resp.status_code, resp.text)
