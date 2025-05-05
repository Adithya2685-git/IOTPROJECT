import requests

base_url = "http://127.0.0.1:8080/~/in-cse/in-name"
headers = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/vnd.onem2m-res+json; ty=3"
}

def create_container(name):
    data = {
        "m2m:cnt": {
            "rn": name
        }
    }
    url = f"{base_url}"
    response = requests.post(url, json=data, headers=headers)
    print(f"Container '{name}':", response.status_code, response.text)

# Create containers
create_container("led")
create_container("fan")
create_container("solenoid")
