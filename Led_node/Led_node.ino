#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>

// WiFi credentials
const char* ssid = "NORDCE2";
const char* password = "asdfghjk";

// OM2M server info
const char* server = "http://192.168.158.66:8080";
const char* ledResource = "/~/in-cse/in-name/led/la";
const char* gasResource = "/~/in-cse/in-name/gas_sensor/data";

// LED from OM2M logic
const int ledPin = D2;
WiFiClient client;
String lastCommand = "";

// Gas sensor logic
const int gasPin = A0;
const int greenLED = D1;
const int redLED = D3;
int sensorThreshold = 400;
bool gasCooldown = false;
unsigned long gasCooldownStart = 0;
const unsigned long gasCooldownDuration = 30000; // 30 seconds

void setup() {
  Serial.begin(9600);
  delay(100);

  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);

  pinMode(gasPin, INPUT);
  pinMode(greenLED, OUTPUT);
  pinMode(redLED, OUTPUT);
  digitalWrite(greenLED, HIGH);
  digitalWrite(redLED, LOW);

  Serial.println("Warming up gas sensor...");
  delay(20000);
  Serial.println("Sensor ready.");

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected to WiFi.");
}

String extractCommand(String payload) {
  int conIndex = payload.indexOf("con");
  if (conIndex == -1) return "";
  String rest = payload.substring(conIndex + 3);
  if (rest.indexOf("ON") >= 0) return "ON";
  if (rest.indexOf("OFF") >= 0) return "OFF";
  return "";
}

void postGasData(int gasValue) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String(server) + gasResource;
    http.begin(client, url);
    http.addHeader("X-M2M-Origin", "admin:admin");
    http.addHeader("Content-Type", "application/json;ty=4");

    String payload = "{\"m2m:cin\": {\"con\": \"" + String(gasValue) + "\"}}";
    int httpCode = http.POST(payload);

    if (httpCode > 0) {
      Serial.println("🔥 Smoke detected! Gas data POSTed: " + String(gasValue));
    } else {
      Serial.println("❌ Failed to POST gas data. HTTP code: " + String(httpCode));
    }

    http.end();
  } else {
    Serial.println("❌ WiFi not connected, can't post gas data.");
  }
}

void handleGasSensor() {
  // Check if sensor is in cooldown
  if (gasCooldown) {
    if (millis() - gasCooldownStart >= gasCooldownDuration) {
      gasCooldown = false;
      Serial.println("✅ Gas sensor re-enabled.");
    }
    return;
  }

  int gasValue = analogRead(gasPin);
  Serial.print("Gas sensor value: ");
  Serial.println(gasValue);

  if (gasValue > sensorThreshold) {
    Serial.println("⚠️ Gas level above threshold!");
    digitalWrite(greenLED, LOW);
    digitalWrite(redLED, HIGH);

    postGasData(gasValue);
    gasCooldown = true;
    gasCooldownStart = millis();
  } else {
    digitalWrite(greenLED, HIGH);
    digitalWrite(redLED, LOW);
  }
}

void loop() {
  // LED OM2M logic
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String(server) + ledResource;
    http.begin(client, url);
    http.addHeader("X-M2M-Origin", "admin:admin");
    http.addHeader("Accept", "application/json");

    int code = http.GET();
    if (code == 200) {
      String response = http.getString();
      String command = extractCommand(response);
      if (command != lastCommand && command != "") {
        Serial.println("Received command from OM2M: " + command);
        if (command == "ON") digitalWrite(ledPin, HIGH);
        else if (command == "OFF") digitalWrite(ledPin, LOW);
        lastCommand = command;
      }
    } else {
      Serial.println("Failed to fetch LED command, code: " + String(code));
    }

    http.end();
  }

  handleGasSensor();  // runs every loop

  delay(2000);
}
