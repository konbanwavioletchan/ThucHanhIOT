// Bai thuc hanh IoT so 2 - Pham Gia Huy - B23DCAT131
// ESP32 (Wokwi) doc DHT22 + HC-SR04 va publish JSON len ThingsBoard Cloud qua MQTT.
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHTesp.h>
#include <time.h>

const char* STUDENT = "Pham Gia Huy - B23DCAT131";
const char* DEVICE_ID = "ESP32-B23DCAT131";

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// ThingsBoard Cloud: username MQTT = Access Token cua device
const char* MQTT_SERVER = "mqtt.thingsboard.cloud";
const int MQTT_PORT = 1883;
const char* TB_ACCESS_TOKEN = "huyB23DCAT131b30b2cd7f468";
const char* MQTT_TOPIC = "v1/devices/me/telemetry";

const int DHT_PIN = 15;
const int TRIG_PIN = 5;
const int ECHO_PIN = 18;
const int LED_PIN = 2;
const unsigned long SEND_INTERVAL_MS = 5000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
DHTesp dht;
unsigned long lastSend = 0;
unsigned long sequenceNo = 0;

void connectWiFi() {
  Serial.print("Connecting WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" connected");
  Serial.printf("IP: %s | RSSI: %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
}

void syncTime() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.print("Synchronizing time");
  for (int i = 0; i < 20 && time(nullptr) < 1700000000; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(time(nullptr) >= 1700000000 ? " NTP synchronized" : " NTP skipped");
}

void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.printf("Connecting MQTT (%s)...", MQTT_SERVER);
    String clientId = String(DEVICE_ID) + "-" + String((uint32_t)esp_random(), HEX);
    if (mqttClient.connect(clientId.c_str(), TB_ACCESS_TOKEN, nullptr)) {
      Serial.println(" connected");
    } else {
      Serial.printf(" failed, rc=%d. Retry in 2 s\n", mqttClient.state());
      delay(2000);
    }
  }
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return NAN;
  return duration * 0.0343f / 2.0f;
}

uint64_t epochMs() {
  struct timeval tv;
  if (gettimeofday(&tv, nullptr) != 0 || tv.tv_sec < 1700000000) return 0;
  return uint64_t(tv.tv_sec) * 1000ULL + tv.tv_usec / 1000ULL;
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  dht.setup(DHT_PIN, DHTesp::DHT22);

  Serial.println();
  Serial.println("==========================================");
  Serial.println(" BAI THUC HANH IoT SO 2 - ESP32 SENSOR NODE");
  Serial.printf(" Sinh vien: %s\n", STUDENT);
  Serial.println("==========================================");

  connectWiFi();
  syncTime();
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setBufferSize(512);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastSend < SEND_INTERVAL_MS) return;
  lastSend = now;

  TempAndHumidity data = dht.getTempAndHumidity();
  float distance = readDistanceCm();
  if (!isfinite(data.temperature) || !isfinite(data.humidity) || !isfinite(distance)) {
    Serial.println("Invalid sensor data - skip publish");
    return;
  }

  sequenceNo++;
  char payload[384];
  snprintf(payload, sizeof(payload),
    "{\"device_id\":\"%s\",\"temperature\":%.2f,\"humidity\":%.2f,\"distance_cm\":%.2f,"
    "\"rssi\":%d,\"sequence\":%lu,\"uptime_s\":%lu,\"sent_ms\":%llu}",
    DEVICE_ID, data.temperature, data.humidity, distance, WiFi.RSSI(),
    sequenceNo, millis() / 1000, epochMs());

  bool ok = mqttClient.publish(MQTT_TOPIC, payload);
  Serial.println("========== SENSOR ==========");
  Serial.printf("Sinh vien   : %s\n", STUDENT);
  Serial.printf("Temperature : %.2f C\n", data.temperature);
  Serial.printf("Humidity    : %.2f %%\n", data.humidity);
  Serial.printf("Distance    : %.2f cm\n", distance);
  Serial.printf("Sequence    : %lu\n", sequenceNo);
  Serial.printf("%s | publish=%s\n", payload, ok ? "OK" : "FAILED");
  if (ok) {
    digitalWrite(LED_PIN, HIGH);
    delay(80);
    digitalWrite(LED_PIN, LOW);
  }
}
