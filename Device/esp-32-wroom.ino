/*
 * ESP32 AI Assistant — Audio I/O Device
 *
 * Hardware:
 *   - INMP441 MEMS Microphone (I2S RX on I2S_NUM_0)
 *   - MAX98357A / PCM5102 DAC + Speaker (I2S TX on I2S_NUM_1)
 *
 * Network protocol (raw UDP, no headers):
 *   MIC  → PC :  16-bit signed PCM, little-endian, 16 kHz, mono
 *                 Sent to PC_IP : MIC_SEND_PORT
 *   PC  → SPK :  16-bit signed PCM, little-endian, 16 kHz, mono
 *                 ESP32 listens on SPEAKER_RECV_PORT
 *
 * The PC side handles everything: wake word, STT, LLM, TTS.
 * This device just streams mic out and plays audio in — no changes needed.
 */

#include <driver/i2s.h>
#include <WiFi.h>
#include <WiFiUdp.h>

// ===================== USER CONFIG =====================

const char* WIFI_SSID     = "11t";
const char* WIFI_PASSWORD = "123456789";

// phone
const char* PC_IP           = "10.72.61.7";

// router
// const char* PC_IP           = "172.16.255.98";

const int   MIC_SEND_PORT   = 12345;   // PC listens here for mic audio
const int   SPEAKER_RECV_PORT = 12346; // ESP32 listens here for playback audio

#define SAMPLE_RATE  16000

// 0.0 = mute, 1.0 = unity, up to ~3.0
float speakerGain = 2.0f;

// ================ INMP441 MIC PINS (I2S RX) ================

#define MIC_SCK   26
#define MIC_WS    25
#define MIC_SD    32
#define MIC_I2S   I2S_NUM_0

// ============= SPEAKER DAC PINS (I2S TX) =============

#define SPK_BCLK  12
#define SPK_LRC   14
#define SPK_DOUT  27
#define SPK_I2S   I2S_NUM_1

// ===================== INTERNALS =====================

#define MIC_BLOCK_SAMPLES 512

WiFiUDP micUdp;
WiFiUDP spkUdp;

// ----- I2S setup -----

void setupMicI2S() {
  i2s_config_t cfg = {
    .mode             = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate      = SAMPLE_RATE,
    .bits_per_sample  = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format   = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count    = 4,
    .dma_buf_len      = MIC_BLOCK_SAMPLES,
    .use_apll         = false
  };
  i2s_driver_install(MIC_I2S, &cfg, 0, NULL);

  i2s_pin_config_t pins = {
    .mck_io_num   = I2S_PIN_NO_CHANGE,
    .bck_io_num   = MIC_SCK,
    .ws_io_num    = MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = MIC_SD
  };
  i2s_set_pin(MIC_I2S, &pins);
  i2s_start(MIC_I2S);
}

void setupSpkI2S() {
  i2s_config_t cfg = {
    .mode             = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate      = SAMPLE_RATE,
    .bits_per_sample  = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format   = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = 0,
    .dma_buf_count    = 8,
    .dma_buf_len      = 1024,
    .use_apll         = false,
    .tx_desc_auto_clear = true,
    .fixed_mclk       = 0
  };
  i2s_driver_install(SPK_I2S, &cfg, 0, NULL);

  i2s_pin_config_t pins = {
    .mck_io_num   = I2S_PIN_NO_CHANGE,
    .bck_io_num   = SPK_BCLK,
    .ws_io_num    = SPK_LRC,
    .data_out_num = SPK_DOUT,
    .data_in_num  = I2S_PIN_NO_CHANGE
  };
  i2s_set_pin(SPK_I2S, &pins);
}

// ----- FreeRTOS tasks -----

// Core 1: read INMP441 → send UDP to PC
void micTask(void* param) {
  int32_t raw[MIC_BLOCK_SAMPLES];
  int16_t pcm[MIC_BLOCK_SAMPLES];

  while (true) {
    size_t bytesRead = 0;
    i2s_read(MIC_I2S, raw, sizeof(raw), &bytesRead, portMAX_DELAY);
    int samples = bytesRead / 4;

    // INMP441: 24-bit audio MSB-aligned in 32-bit frame (range ±2^30).
    // >> 16 maps to ±2^14 which fits int16_t without overflow.
    // >> 11 was causing wraparound clipping on loud sounds.
    for (int i = 0; i < samples; i++) {
      int32_t s = raw[i] >> 14;
      if (s >  32767) s =  32767;
      if (s < -32768) s = -32768;
      pcm[i] = (int16_t)s;
    }

    if (micUdp.beginPacket(PC_IP, MIC_SEND_PORT)) {
      micUdp.write((uint8_t*)pcm, samples * 2);
      micUdp.endPacket();
    } else {
      vTaskDelay(1);
    }
  }
}

// Core 0: receive UDP from PC → play on speaker
void spkTask(void* param) {
  uint8_t  packet[1460];
  int16_t  stereo[1460];  // 730 mono samples → 730 stereo frames (1460 int16s)

  while (true) {
    int pktSize = spkUdp.parsePacket();
    if (pktSize > 0) {
      int len = spkUdp.read(packet, sizeof(packet));
      int16_t* mono = (int16_t*)packet;
      int monoSamples = len / 2;

      for (int i = 0; i < monoSamples; i++) {
        int32_t s = (int32_t)(mono[i] * speakerGain);
        if (s >  32767) s =  32767;
        if (s < -32768) s = -32768;
        stereo[i * 2]     = (int16_t)s;
        stereo[i * 2 + 1] = (int16_t)s;
      }

      size_t written;
      i2s_write(SPK_I2S, stereo, monoSamples * 4, &written, portMAX_DELAY);
    } else {
      vTaskDelay(1);
    }
  }
}

// ----- Arduino entry points -----

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== ESP32 AI Assistant Audio I/O ===\n");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf(" OK  IP %s\n", WiFi.localIP().toString().c_str());

  setupMicI2S();
  setupSpkI2S();

  micUdp.begin(MIC_SEND_PORT);
  spkUdp.begin(SPEAKER_RECV_PORT);

  xTaskCreatePinnedToCore(micTask, "mic", 12288, NULL, 1, NULL, 1);
  xTaskCreatePinnedToCore(spkTask, "spk", 12288, NULL, 1, NULL, 0);

  Serial.printf("Mic  → %s:%d  (16-bit PCM, %d Hz, mono)\n", PC_IP, MIC_SEND_PORT, SAMPLE_RATE);
  Serial.printf("Spk  ← port %d        (16-bit PCM, %d Hz, mono)\n", SPEAKER_RECV_PORT, SAMPLE_RATE);
  Serial.println("\nReady.\n");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost — reconnecting...");
    WiFi.reconnect();
    while (WiFi.status() != WL_CONNECTED) delay(500);
    Serial.printf("Back online  IP %s\n", WiFi.localIP().toString().c_str());
  }
  delay(5000);
}
