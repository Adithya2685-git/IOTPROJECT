import requests
import json

# Parent directory where we want to create the new container
parent_url = "http://192.168.158.66:8080/~/in-cse/in-name/voice_command"

# Name of the new container
new_container_name = "audio_upload"

# Headers for OM2M
headers = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/json;ty=3",  # ty=3 for container
    "Accept": "application/json"
}

# Body to define the new container
payload = {
    "m2m:cnt": {
        "rn": new_container_name,     # resource name (directory name)
        "mni": 10,                    # max number of instances (optional)
        "mbs": 100000                 # max byte size for all content instances (adjust as needed)
    }
}

def create_container():
    try:
        response = requests.post(parent_url, headers=headers, data=json.dumps(payload), timeout=10)
        print("Status Code:", response.status_code)
        if response.status_code == 201:
            print(f"Container '{new_container_name}' created successfully.")
        else:
            print("Error Response:", response.text)
    except Exception as e:
        print("Error during container creation:", e)

if __name__ == "__main__":
    create_container()
