import requests
import json

# OM2M base URL (update if your server IP is different)
OM2M_URL = "http://localhost:8080/~/in-cse/in-name/led"

# Headers required by OM2M
headers = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/vnd.onem2m-res+json; ty=4"
}

# Body with command
payload = {
    "m2m:cin": {
        "con": "ON"  # or "OFF"
    }
}

# Send POST request
response = requests.post(OM2M_URL, headers=headers, data=json.dumps(payload))

# Print response
print(f"Status Code: {response.status_code}")
print("Response:", response.text)
