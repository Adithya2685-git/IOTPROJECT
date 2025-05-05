import requests
import time

# OM2M server configuration
server_url = "http://192.168.158.66:8080"
resource_path = "/~/in-cse/in-name/solenoid"
content_instance_url = f"{server_url}{resource_path}"

# Authentication credentials
headers = {
    "X-M2M-Origin": "admin:admin",
    "Content-Type": "application/json;ty=4"
}

def post_command(command):
    """Post a command (ON/OFF) to the OM2M server"""
    data = {
        "m2m:cin": {
            "con": command
        }
    }
    
    try:
        response = requests.post(
            content_instance_url, 
            headers=headers, 
            json=data
        )
        
        if response.status_code == 201:
            print(f"Successfully posted command: {command}")
            print(f"Response: {response.text}")
        else:
            print(f"Failed to post command. Status code: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error occurred: {e}")

def test_lock_cycle():
    """Test a full lock/unlock cycle with delay"""
    # Unlock the solenoid
    print("Sending UNLOCK command (ON)...")
    post_command("ON")
    
    # Wait for 5 seconds
    print("Waiting 5 seconds...")
    time.sleep(5)
    
    # Lock the solenoid
    print("Sending LOCK command (OFF)...")
    post_command("OFF")

def manual_control():
    """Allow manual control of the solenoid lock"""
    while True:
        command = input("\nEnter command (ON=unlock, OFF=lock, exit to quit): ").strip().upper()
        
        if command == "EXIT":
            print("Exiting program...")
            break
        elif command in ["ON", "OFF"]:
            post_command(command)
        else:
            print("Invalid command. Please enter ON, OFF, or exit.")

if __name__ == "__main__":
    print("OM2M Solenoid Lock Control")
    print("=========================")
    
    choice = input("Choose mode:\n1. Test lock cycle (unlock/lock)\n2. Manual control\nYour choice (1/2): ")
    
    if choice == "1":
        test_lock_cycle()
    elif choice == "2":
        manual_control()
    else:
        print("Invalid choice. Exiting.")