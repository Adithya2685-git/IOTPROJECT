#include <WiFi.h>
#include <HTTPClient.h>
#include <base64.h>
#include <Wire.h>
#include <MPU6050.h>
#include <math.h>  // Added for sqrt()

MPU6050 mpu;

const char* ssid = "NORDCE2";
const char* password = "asdfghjk";
const char* audio_server = "http://192.168.158.66:8080/~/in-cse/in-name/voice_command/audio_upload";
const char* fall_server = "http://192.168.158.66:8080/~/in-cse/in-name/fall_sensor/fall_data";
// 22 is SCL and 21 is SDA
#define TOUCH_PIN T0
#define MIC_PIN 35
#define SPEAKER_PIN 25

// Updated fall detection parameters
#define FREE_FALL_THRESHOLD 4500  // When total acceleration drops below, assume free fall
#define IMPACT_THRESHOLD    500   // Lowered threshold for more sensitive impact detection 
#define FREE_FALL_TIME      280   // Duration in ms required for free fall confirmation
#define FALL_TIME_WINDOW    2000  // Maximum time window after free fall for impact detection

bool isRecording = false;
bool mpuConnected = false;
const int SAMPLE_RATE = 8000;
const int DURATION_SECONDS = 3;
const int NUM_SAMPLES = SAMPLE_RATE * DURATION_SECONDS;
int16_t audioBuffer[NUM_SAMPLES];

// WAV header size
#define WAV_HEADER_SIZE 44

// Updated fall detection state variables
unsigned long freeFallStartTime = 0;
bool freeFallDetected = false;

void setup() {
  Serial.begin(115200);
  pinMode(SPEAKER_PIN, OUTPUT);
  
  // Initialize MPU6050 with error handling
  Wire.begin();
  mpu.initialize();
  
  if (!mpu.testConnection()) {
    Serial.println("MPU6050 connection failed!");
    signalError();
    mpuConnected = false;
  } else {
    Serial.println("MPU6050 initialized successfully");
    mpuConnected = true;
  }
  
  // Connect to WiFi with timeout
  int wifiTimeout = 0;
  Serial.printf("Connecting to WiFi: %s\n", ssid);
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED && wifiTimeout < 20) {
    Serial.print(".");
    delay(500);
    wifiTimeout++;
  }
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nWiFi connection failed! Operating in offline mode.");
    signalError();
  } else {
    Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());
    signalSuccess();
  }
}

void loop() {
  if (mpuConnected) {
    checkFall();
  }
  checkTouch();
  delay(100); // Polling delay
}

// Updated fall detection function
void checkFall() {
  int16_t ax, ay, az;
  mpu.getAcceleration(&ax, &ay, &az);
  
  // Compute the total acceleration vector magnitude
  float A_total = sqrt((long)ax * ax + (long)ay * ay + (long)az * az);
  
  unsigned long currentTime = millis();

  // Step 1: Detect the free fall phase
  if (A_total < FREE_FALL_THRESHOLD) {
    if (!freeFallDetected) {
      freeFallDetected = true;
      freeFallStartTime = currentTime;
    }
    else if (currentTime - freeFallStartTime >= FREE_FALL_TIME) {
      Serial.println("Free Fall Confirmed! Awaiting Impact...");
    }
  }
  // Step 2: Handle recovery or potential impact detection
  else {
    if (freeFallDetected) {
      if (currentTime - freeFallStartTime >= FREE_FALL_TIME) {
        if ((currentTime - freeFallStartTime) <= (FREE_FALL_TIME + FALL_TIME_WINDOW)) {
          if (A_total > IMPACT_THRESHOLD) {
            Serial.print("Impact Acceleration: ");
            Serial.println(A_total);
            Serial.println("FALL DETECTED!");
            
            playAlertSound();
            char fallData[100];
            sprintf(fallData, "FALL_DETECTED: accel=%.2f", A_total);
            uploadDataToOM2M(fall_server, fallData);
            
            freeFallDetected = false;
          }
        }
        else {
          freeFallDetected = false;
        }
      }
      else {
        freeFallDetected = false;
      }
    }
  }
}

void checkTouch() {
  if (touchRead(TOUCH_PIN) < 30 && !isRecording) {
    Serial.println("Touch detected. Start recording.");
    isRecording = true;
    playStartRecordSound();
    recordAudio();
    Serial.println("Recording done. Uploading...");
    uploadAudio();
    isRecording = false;
  }
}

void recordAudio() {
  analogReadResolution(12);
  
  Serial.println("Recording started...");
  
  // MAX9814 optimized settings
  const uint16_t BIAS = 0;
  const uint16_t NOISE_THRESHOLD = 300; // Lowered from 650 to capture more voice detail
  
  // Pre-filter the first few milliseconds to establish a better noise floor
  float noise_floor = 0;
  int calibration_samples = 50;
  
  for (int i = 0; i < calibration_samples; i++) {
    noise_floor += abs(analogRead(MIC_PIN));
    delayMicroseconds(100);
  }
  noise_floor = noise_floor / calibration_samples * 1.5f; // Add 50% margin
  
  Serial.printf("Detected noise floor: %.2f\n", noise_floor);
  
  // Use dynamic noise threshold if detected level is below our static threshold
  if (noise_floor < NOISE_THRESHOLD) {
    Serial.println("Using detected noise floor");
  } else {
    noise_floor = NOISE_THRESHOLD;
    Serial.println("Using default noise threshold");
  }
  
  // Optimized sampling with minimal delay
  uint32_t start_time = micros();
  uint32_t sample_interval = 1000000 / SAMPLE_RATE; // Interval in microseconds
  uint32_t next_sample = start_time;
  
  // Two-stage filtering for better audio quality
  float filtered_value = 0;
  float prev_value = 0;
  const float ALPHA = 0.7f;    // Reduced for more smoothing (was 0.85)
  const float BETA = 0.4f;     // Secondary filter for high-frequency noise
  
  // Anti-jitter buffer
  const int JITTER_BUFFER_SIZE = 3;
  float jitter_buffer[JITTER_BUFFER_SIZE] = {0};
  int jitter_index = 0;
  
  for (int i = 0; i < NUM_SAMPLES; i++) {
    // Precise timing to reduce jitter
    while (micros() < next_sample) {
      // Empty loop - minimizes timing jitter
    }
    
    // Take multiple readings and average them to reduce noise
    int sum_readings = 0;
    const int NUM_READINGS = 2; // Number of readings to average
    
    for (int j = 0; j < NUM_READINGS; j++) {
      sum_readings += analogRead(MIC_PIN);
      // Small delay between readings
      delayMicroseconds(5);
    }
    
    int reading = sum_readings / NUM_READINGS;
    
    // First stage filter - basic low pass to smooth signal
    filtered_value = ALPHA * reading + (1.0f - ALPHA) * filtered_value;
    
    // Second stage filter - removes high frequency oscillations
    float smoothed = BETA * filtered_value + (1.0f - BETA) * prev_value;
    prev_value = filtered_value;
    
    // Anti-jitter processing - rolling average of last few samples
    jitter_buffer[jitter_index] = smoothed;
    jitter_index = (jitter_index + 1) % JITTER_BUFFER_SIZE;
    
    float avg_value = 0;
    for (int j = 0; j < JITTER_BUFFER_SIZE; j++) {
      avg_value += jitter_buffer[j];
    }
    avg_value /= JITTER_BUFFER_SIZE;
    
    // Apply improved noise gate with adjustable threshold
    if (abs(avg_value) <= noise_floor) {
      avg_value = 0;
    } else {
      // Soft noise gate to avoid harsh transitions
      float gate_factor = min(1.0f, (abs(avg_value) - noise_floor) / (noise_floor * 0.5f));
      avg_value *= gate_factor;
    }
    
    // High-pass filter to reduce low-frequency rumble (improves voice clarity)
    static float last_sample = 0;
    float highpassed = avg_value - last_sample;
    last_sample = avg_value * 0.85f; // Cutoff frequency control
    
    // Apply gain and enhance mid-frequencies (voice range)
    // Voice sits around 300-3000Hz range, so we boost this selectively
    static float voice_emphasis = 0;
    voice_emphasis = voice_emphasis * 0.5f + highpassed * 0.5f;
    float enhanced = highpassed + voice_emphasis * 0.3f;
    
    // Store final value with appropriate gain
    audioBuffer[i] = (int16_t)(enhanced * 20.0f);
    
    // Calculate next sample time precisely
    next_sample += sample_interval;
  }
  
  // Collect audio statistics
  int32_t sum = 0;
  int16_t min_val = 32767;
  int16_t max_val = -32768;
  int num_zeros = 0;
  
  for (int i = 0; i < NUM_SAMPLES; i++) {
    // Calculate statistics
    min_val = min(min_val, audioBuffer[i]);
    max_val = max(max_val, audioBuffer[i]);
    sum += abs(audioBuffer[i]);
    if (audioBuffer[i] == 0) num_zeros++;
  }
  
  float zero_percent = 100.0f * num_zeros / NUM_SAMPLES;
  
  Serial.printf("Audio stats - Min: %d, Max: %d, Avg magnitude: %d, Zeros: %.1f%%\n", 
                min_val, max_val, sum/NUM_SAMPLES, zero_percent);
  
  // Apply automatic level adjustment if signal is too quiet
  float avg_magnitude = (float)sum / NUM_SAMPLES;
  if (avg_magnitude < 100.0f && zero_percent < 80.0f) { // Only boost if not mostly silence
    // Avoid division by zero
    float safe_magnitude = avg_magnitude > 1.0f ? avg_magnitude : 1.0f;
    float boost_factor = 200.0f / safe_magnitude; // Target average of ~200
    
    // Limit the boost
    if (boost_factor > 4.0f) {
      boost_factor = 4.0f;
    }
    
    Serial.printf("Applying automatic level boost: %.2f\n", boost_factor);
    
    for (int i = 0; i < NUM_SAMPLES; i++) {
      audioBuffer[i] = (int16_t)(audioBuffer[i] * boost_factor);
    }
  }
  
  // Final pass to improve dynamics
  int16_t abs_max = max(abs(min_val), abs(max_val));
  if (abs_max > 10) {  // Only process if we have meaningful audio
    // Compression to even out loud and soft parts
    for (int i = 0; i < NUM_SAMPLES; i++) {
      float sample = audioBuffer[i];
      // Soft knee compression
      if (abs(sample) > 5000) {
        float gain_reduction = 1.0f - (abs(sample) - 5000) / 20000.0f;
        if (gain_reduction < 0.5f) gain_reduction = 0.5f;
        sample *= gain_reduction;
        audioBuffer[i] = (int16_t)sample;
      }
    }
  }
  
  playEndRecordSound();
  Serial.println("Recording completed");
}
// Create WAV header
void createWavHeader(uint8_t* header, uint32_t totalDataLen) {
  // WAV Header Structure
  uint32_t dataSize = totalDataLen - 44;  // Data size (total size - header size)
  uint32_t byteRate = SAMPLE_RATE * 2;    // 16-bit = 2 bytes per sample
  
  // RIFF header
  header[0] = 'R';
  header[1] = 'I';
  header[2] = 'F';
  header[3] = 'F';
  header[4] = (totalDataLen & 0xff);
  header[5] = ((totalDataLen >> 8) & 0xff);
  header[6] = ((totalDataLen >> 16) & 0xff);
  header[7] = ((totalDataLen >> 24) & 0xff);
  
  // WAVE header
  header[8] = 'W';
  header[9] = 'A';
  header[10] = 'V';
  header[11] = 'E';
  
  // FMT subchunk
  header[12] = 'f';
  header[13] = 'm';
  header[14] = 't';
  header[15] = ' ';
  header[16] = 16;  // Subchunk1Size is 16
  header[17] = 0;
  header[18] = 0;
  header[19] = 0;
  header[20] = 1;   // PCM = 1
  header[21] = 0;
  header[22] = 1;   // Mono = 1 channel
  header[23] = 0;
  header[24] = (SAMPLE_RATE & 0xff);
  header[25] = ((SAMPLE_RATE >> 8) & 0xff);
  header[26] = 0;
  header[27] = 0;
  header[28] = (byteRate & 0xff);
  header[29] = ((byteRate >> 8) & 0xff);
  header[30] = 0;
  header[31] = 0;
  header[32] = 2;   // Block align
  header[33] = 0;
  header[34] = 16;  // Bits per sample
  header[35] = 0;
  
  // DATA subchunk
  header[36] = 'd';
  header[37] = 'a';
  header[38] = 't';
  header[39] = 'a';
  header[40] = (dataSize & 0xff);
  header[41] = ((dataSize >> 8) & 0xff);
  header[42] = ((dataSize >> 16) & 0xff);
  header[43] = ((dataSize >> 24) & 0xff);
}

// Updated audio upload with WAV format
void uploadAudio() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected. Cannot upload audio.");
    signalError();
    return;
  }
  
  // Create a unique identifier for this audio session
  String sessionId = String(millis());
  Serial.printf("Creating new audio upload session: %s\n", sessionId.c_str());
  
  // Fixed 4 chunks for audio data
  const int TOTAL_CHUNKS = 4;
  int samplesPerChunk = (NUM_SAMPLES + TOTAL_CHUNKS - 1) / TOTAL_CHUNKS;
  
  Serial.printf("Using %d chunks with %d samples per chunk\n", 
                TOTAL_CHUNKS, samplesPerChunk);
  
  // Upload WAV header first
  uint8_t header[WAV_HEADER_SIZE];
  int audioDataSize = NUM_SAMPLES * 2;  
  int totalSize = audioDataSize + WAV_HEADER_SIZE;
  createWavHeader(header, totalSize);
  
  String headerEncoded = base64::encode(header, WAV_HEADER_SIZE);
  String headerMsg = "AUDIO_START:" + sessionId + ":" + String(TOTAL_CHUNKS) + ":" + headerEncoded;
  uploadDataToOM2M(audio_server, headerMsg);
  
  // Now upload audio data in chunks
  uint8_t* chunk = (uint8_t*)malloc(samplesPerChunk * 2);
  if (!chunk) {
    Serial.println("Failed to allocate memory for chunk buffer");
    signalError();
    return;
  }
  
  for (int chunkIndex = 0; chunkIndex < TOTAL_CHUNKS; chunkIndex++) {
    int startSample = chunkIndex * samplesPerChunk;
    int endSample = min(startSample + samplesPerChunk, NUM_SAMPLES);
    int samplesToProcess = endSample - startSample;
    int bytesToProcess = samplesToProcess * 2;
    
    // Fill the chunk buffer with audio data
    for (int i = 0; i < samplesToProcess; i++) {
      chunk[i*2] = audioBuffer[startSample + i] & 0xFF;
      chunk[i*2+1] = (audioBuffer[startSample + i] >> 8) & 0xFF;
    }
    
    // Base64 encode this chunk
    String chunkEncoded = base64::encode(chunk, bytesToProcess);
    
    // Upload this chunk
    String chunkMsg = "AUDIO_CHUNK:" + sessionId + ":" + String(chunkIndex) + ":" + chunkEncoded;
    Serial.printf("Uploading chunk %d/%d...\n", chunkIndex+1, TOTAL_CHUNKS);
    uploadDataToOM2M(audio_server, chunkMsg);
    
    yield();  // Allow other processes to run
  }
  
  free(chunk);  // Free allocated memory
  
  // Send end marker
  String endMsg = "AUDIO_END:" + sessionId;
  uploadDataToOM2M(audio_server, endMsg);
  
  Serial.printf("Audio upload complete. %d chunks sent.\n", TOTAL_CHUNKS);
}

void uploadDataToOM2M(const char* server_url, String msg) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected. Cannot upload data.");
    return;
  }
  
  HTTPClient http;
  http.begin(server_url);
  http.addHeader("X-M2M-Origin", "admin:admin");
  http.addHeader("Content-Type", "application/json;ty=4");
  
  // Escape any characters that could break JSON format
  msg.replace("\\", "\\\\"); // Replace \ with \\
  msg.replace("\"", "\\\""); // Replace " with \"
  
  // Construct the JSON payload
  String payload = "{\"m2m:cin\": {\"con\": \"" + msg + "\"}}";
  
  // Show a sample of the payload for debugging
  Serial.println("First 100 chars of payload:");
  Serial.println(payload.substring(0, 100));
  
  int retries = 0;
  int httpCode = -1;
  
  while (retries < 2 && httpCode != 201) {
    httpCode = http.POST(payload);
    Serial.printf("Status code: %d\n", httpCode);
    
    if (httpCode == 201) {
      Serial.println("Upload successful");
      signalSuccess();
      break;
    } else {
      retries++;
      Serial.printf("Upload failed with code %d. Retrying... (%d/2)\n", httpCode, retries);
      String response = http.getString();
      Serial.println("Server response: " + response);
      delay(500);
      
      if (retries == 2) {
        signalError();
      }
    }
  }
  
  http.end();
}

// Helper function to check if there's enough memory for operations
bool checkMemory(int requiredBytes) {
  uint32_t freeHeap = ESP.getFreeHeap();
  Serial.printf("Free heap: %d bytes, Required: %d bytes\n", freeHeap, requiredBytes);
  
  if (freeHeap < requiredBytes) {
    Serial.println("WARNING: Not enough memory available!");
    return false;
  }
  return true;
}

// Optional optimization - helper function for creating larger chunks
void createChunk(uint8_t* chunk, int startSample, int endSample) {
  int sampleIndex = 0;
  for (int i = startSample; i < endSample; i++) {
    // Little-endian format (LSB first)
    chunk[sampleIndex++] = audioBuffer[i] & 0xFF;
    chunk[sampleIndex++] = (audioBuffer[i] >> 8) & 0xFF;
  }
}
void playSimpleTone(int freqHz, int durationMs) {
  int halfPeriodUs = 500000 / freqHz;
  unsigned long endTime = millis() + durationMs;
  
  while (millis() < endTime) {
    digitalWrite(SPEAKER_PIN, HIGH);
    delayMicroseconds(halfPeriodUs);
    digitalWrite(SPEAKER_PIN, LOW);
    delayMicroseconds(halfPeriodUs);
  }
}

void signalSuccess() {
  playSimpleTone(1500, 150);
  delay(100);
  playSimpleTone(2000, 150);
}

void signalError() {
  playSimpleTone(500, 250);
  delay(100);
  playSimpleTone(500, 250);
}

void playStartRecordSound() {
  playSimpleTone(800, 100);
  delay(50);
  playSimpleTone(1200, 100);
}

void playEndRecordSound() {
  playSimpleTone(1200, 100);
  delay(50);
  playSimpleTone(800, 100);
}

void playAlertSound() {
  for (int i = 0; i < 3; i++) {
    playSimpleTone(2000, 200);
    delay(200);
  }
}

void playSpeaker(String msg) {
  Serial.printf("Playing audio message: %s\n", msg.c_str());
  playSimpleTone(1000, 300);
  delay(300);
  
  if (msg.indexOf("Fall") >= 0) {
    playAlertSound();
  } else if (msg.indexOf("error") >= 0 || msg.indexOf("fail") >= 0) {
    signalError();
  } else {
    for (int i = 0; i < 2; i++) {
      playSimpleTone(1200, 100);
      delay(150);
    }
  }
}