#define MIC_PIN         35    // ADC1_CH7
#define CAL_SAMPLES     500   // how many readings to average for bias
#define NOISE_GATE_THRESHOLD 500 // ignore |value| < this (zeros out small jitter)

// --- NEW: Threshold to detect speech ---
// Set this value ABOVE your observed noise peaks (~600)
// but BELOW your observed speech peaks (~1500).
// Adjust this value based on testing!
#define SPEECH_DETECT_THRESHOLD 800 // Example value, TUNE THIS!

int bias = 0;

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);   // 0–4095

  Serial.println("Calibrating bias...");
  // 1) Auto-calibrate bias
  long sum = 0;
  for (int i = 0; i < CAL_SAMPLES; i++) {
    sum += analogRead(MIC_PIN);
    delay(2); // Small delay between calibration readings
  }
  bias = sum / CAL_SAMPLES;
  Serial.print("Calibrated bias = ");
  Serial.println(bias);
  Serial.print("Speech detection threshold (absolute value) = ");
  Serial.println(SPEECH_DETECT_THRESHOLD);
  Serial.println("Starting detection loop. Output will only appear during speech.");
}

void loop() {
  // 2) Raw read
  int raw = analogRead(MIC_PIN);

  // 3) Center around zero
  int16_t centered = raw - bias;

  // 4) Noise-gate tiny jitter near zero (optional but often helpful)
  if (abs(centered) < NOISE_GATE_THRESHOLD) {
    centered = 0;
  }

  // 5) Emit ONLY if the signal magnitude is above the speech threshold
  if (abs(centered) > SPEECH_DETECT_THRESHOLD) {
    // Only print if the absolute value exceeds the threshold defined for speech
    Serial.println(centered);
  }
  // else {
    // If below the speech threshold, do nothing (no Serial output)
    // You could add alternative actions here if needed (e.g., turn off an LED)
  // }

  // NOTE: The delay(50) significantly limits your sampling rate to ~20Hz.
  // The original comment "// ~8 kHz sampling" is incorrect with this delay.
  // Reducing this delay allows faster sampling but might require adjusting thresholds.
  delayMicroseconds(300);
}