#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>

// WiFi credentials
const char* ssid = "NORDCE2";
const char* password = "asdfghjk";

// OM2M server info
const char* server = "http://192.168.158.66:8080";
const char* lockResource = "/~/in-cse/in-name/solenoid/la";

// Solenoid lock pin
const int solenoidPin = D2;

WiFiClient client;
String lastCommand = "";

void setup() {
  Serial.begin(9600);
  delay(100);
  
  // Initialize solenoid lock pin as output and ensure it's locked initially
  pinMode(solenoidPin, OUTPUT);
  digitalWrite(solenoidPin, LOW);
  
  Serial.println("Connecting to WiFi");
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\nConnected to WiFi.");
  Serial.println("Solenoid lock controller ready.");
}

String extractCommand(String payload) {
  int conIndex = payload.indexOf("con");
  if (conIndex == -1) return "";
  
  String rest = payload.substring(conIndex + 3);
  if (rest.indexOf("ON") >= 0) return "ON";
  if (rest.indexOf("OFF") >= 0) return "OFF";
  
  return "";
}

void loop() {
  // Check Wi-Fi connection
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String(server) + lockResource;
    
    http.begin(client, url);
    http.addHeader("X-M2M-Origin", "admin:admin");
    http.addHeader("Accept", "application/json");
    
    int code = http.GET();
    
    if (code == 200) {
      String response = http.getString();
      String command = extractCommand(response);
      
      if (command != lastCommand && command != "") {
        Serial.println("Received lock command from OM2M: " + command);
        
        if (command == "ON") {
          digitalWrite(solenoidPin, HIGH);  // Unlock the solenoid
          Serial.println("🔓 Solenoid UNLOCKED");
        } 
        else if (command == "OFF") {
          digitalWrite(solenoidPin, LOW);   // Lock the solenoid
          Serial.println("🔒 Solenoid LOCKED");
        }
        
        lastCommand = command;
      }
    } 
    else {
      Serial.println("❌ Failed to fetch solenoid command, code: " + String(code));
    }
    
    http.end();
  } 
  else {
    Serial.println("❌ WiFi disconnected, trying to reconnect...");
    WiFi.begin(ssid, password);
  }
  
  delay(2000);  // Check for commands every 2 seconds
}