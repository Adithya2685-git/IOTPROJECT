import requests
import json

OM2M_URL = "http://localhost:8080/~/in-cse/in-name/fan"

headers = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/vnd.onem2m-res+json;ty=4"  # Content Instance
}

payload = {
    "m2m:cin": {
        "con": "2"  # Change this to "1", "2", "3", or "OFF"
    }
}

response = requests.post(OM2M_URL, headers=headers, data=json.dumps(payload))

print(f"Status Code: {response.status_code}")
print("Response:", response.text)
