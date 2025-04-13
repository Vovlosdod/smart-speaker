#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <LittleFS.h>
#include <Ticker.h>
#include <AudioFileSourceSPIFFS.h>
#include <AudioGeneratorMP3.h>
#include <AudioOutputI2S.h>

#define SPIFFS LittleFS

const char* ssid = "...";        
const char* password = "...";

const char* serverUrl = "http://...:5000/voice";

// #define BUZZER_PIN 5

#define SAMPLE_RATE 4000
#define RECORD_TIME 1
#define MIC_GAIN 60      // Усиление микрофона

#define I2S_BCLK 14      // D5 (MAX98357A BCLK)
#define I2S_LRC  12      // D6 (MAX98357A LRCLK)
#define I2S_DIN  15      // D8 (MAX98357A DIN)

Ticker sampler;
int16_t audioBuffer[SAMPLE_RATE * RECORD_TIME];
int bufferIndex = 0;
bool recording = false;

void setup() {
  Serial.begin(115200);
  // Инициализация SPIFFS
  if(!LittleFS.begin()){
    Serial.println("SPIFFS не запустился!");
    return;
  }
  
  // Подключение к Wi-Fi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nПодключено к Wi-Fi");

  // Настройка микрофона
  analogReference(DEFAULT); 
  pinMode(A0, INPUT);
  
  Serial.println("Запись начнется через 5 секунд...");
  delay(5000);
  startRecording();

}

void loop() {

  if (recording && bufferIndex >= (SAMPLE_RATE * RECORD_TIME)) {
    stopRecording();
    sendAudioToServer();
    playServerResponse();
    memset(audioBuffer, 0, sizeof(audioBuffer));
    startRecording();
  }
  
}

void startRecording() {
  bufferIndex = 0;
  recording = true;
  sampler.attach(1.0 / SAMPLE_RATE, sampleAudio);
  Serial.println("Запись начата");
}

void stopRecording() {
  sampler.detach();
  recording = false;
  Serial.println("Запись остановлена");
}

void sampleAudio() {
  if (bufferIndex < (SAMPLE_RATE * RECORD_TIME)) {
    int raw = analogRead(A0);
    audioBuffer[bufferIndex++] = (int16_t)((raw - 512) * 64); 
  }
}

void sendAudioToServer() {
  int retries = 0;
  bool success = false;

  while (retries < 3 && !success) {
    WiFiClient client;
    HTTPClient http;
    
    if (http.begin(client, serverUrl)) {
      http.addHeader("Content-Type", "audio/raw; rate=8000; channels=1; bits=16");
      int code = http.POST((uint8_t*)audioBuffer, bufferIndex * sizeof(int16_t));
      
      if (code == HTTP_CODE_OK) {
        // Сохранение MP3
        File mp3File = LittleFS.open("/response.mp3", "w");
        if (mp3File) {
          http.writeToStream(&mp3File);
          mp3File.close();
          success = true;
        }
      }
      http.end();
    }
    retries++;
    delay(1000);
  }
}

void playServerResponse() {
  Serial.println("Воспроизведение ответа...");
  
  // Настройка I2S
  AudioOutputI2S *out = new AudioOutputI2S();
  out->SetPinout(I2S_BCLK, I2S_LRC, I2S_DIN);
  out->SetGain(0.3); // Громкость 30%
  
  AudioGeneratorMP3 *mp3 = new AudioGeneratorMP3();
  AudioFileSourceSPIFFS *file = new AudioFileSourceSPIFFS("/response.mp3");
  
  if(mp3->begin(file, out)) {
    while(mp3->isRunning()) {
      if(!mp3->loop()) break;
    }
  }
  
  delete mp3;
  delete file;
  delete out;
  LittleFS.remove("/response.mp3");
  Serial.println("Файл response.mp3 удалён");
}