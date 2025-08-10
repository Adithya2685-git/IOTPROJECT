# Smart Home for the Aged – IoT Project

An **IoT-based Smart Home system** designed to improve safety, comfort, and automation for elderly residents.  
The system integrates **voice-controlled appliances**, **environmental monitoring**, and **remote actuation** via the OM2M IoT platform.

---

## 🚀 Features

- **Voice-controlled appliances** using AI-based speech-to-text and command mapping.
- **Fan speed control** with precise calibration.
- **Solenoid door lock control** for secure access.
- **LED lighting control** via remote commands.
- **Gas sensor monitoring** with threshold detection and automated alerts.
- **Fall detection sensor** (calibrated for noise immunity).
- **Real-time data upload to MongoDB** for logging and analysis.
- **OM2M middleware** for device coordination.

---

## 🛠 Hardware Used

- **ESP8266 NodeMCU** boards (multiple nodes)
- **MAX9814 microphone module** (replacing faulty sound module)
- **Gas sensor** (MQ series)
- **Fall detection sensor**
- **PWM-controlled fan**
- **Solenoid lock**
- **LED indicators**

---

## 📡 Software Stack

- **Node firmware**: Arduino (C++) for ESP8266
- **Backend server**: Python  
  - AI-based speech recognition with two STT models  
  - Dictionary mapping from recognized text to IoT commands  
  - Data relay to OM2M  
  - MongoDB integration for data storage
- **OM2M IoT platform**
- **MongoDB** for backend storage

---

## ⚙ Node Overview

### **Main Node**
- Captures audio via MAX9814 microphone.
- Processes speech-to-text locally with two AI models.
- Maps commands via Python dictionary.
- Sends control instructions to OM2M.

### **LED Node**
- Polls OM2M for LED on/off state.
- Controls LED and reads gas sensor values.
- Posts gas data to OM2M with cooldown logic.

### **Fan & Solenoid Node**
- Fetches fan speed and solenoid lock state from OM2M.
- Controls PWM fan output and lock mechanism.

---

## 🧩 Challenges Faced

- **Microphone calibration**:  
  The original sound detection module failed despite resistor/capacitor adjustments; replaced with MAX9814 and custom soldering.
- **Noise filtering**:  
  Fine-tuning gain to differentiate speech from background noise.
- **Fan speed calibration**:  
  Back voltage interference required software and hardware tuning.
- **ESP8266 memory limits**:  
  Audio split into chunks for processing, merged on backend.
- **Fall sensor tuning**:  
  Calibrated to reduce false positives from vibration/noise.
- **Data management**:  
  Separate Python script uploads OM2M data to MongoDB.

---

## 📦 Installation & Setup

1. **Flash NodeMCU boards** with the provided firmware for each node.
2. **Run backend Python scripts**:
   ```bash
   python main_server.py  # handles audio processing and command mapping
   python upload_mongo.py # pushes OM2M data to MongoDB
