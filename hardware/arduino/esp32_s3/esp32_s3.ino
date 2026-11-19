#include "esp_camera.h"
#include "esp_http_server.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <time.h>
#include "secrets.h"

#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1

#define XCLK_GPIO_NUM     15
#define SIOD_GPIO_NUM      4
#define SIOC_GPIO_NUM      5

#define Y9_GPIO_NUM       16
#define Y8_GPIO_NUM       17
#define Y7_GPIO_NUM       18
#define Y6_GPIO_NUM       12
#define Y5_GPIO_NUM       10
#define Y4_GPIO_NUM        8
#define Y3_GPIO_NUM        9
#define Y2_GPIO_NUM       11

#define VSYNC_GPIO_NUM     6
#define HREF_GPIO_NUM      7
#define PCLK_GPIO_NUM     13

#define FLASH_LED_PIN      2
#define RESET_PIN          0

#define FRAME_W 320
#define FRAME_H 240

const char* DEVICE_ID = "esp32s3-camera";
const char* PATH_API = "/deteksi";
const unsigned long JEDA_ULANG_KIRIM = 3000;
const unsigned long JEDA_DETEKSI = 800;
const time_t WAKTU_TLS_MINIMUM = 1780000000;

const char SERTIFIKAT_ROOT_YE[] PROGMEM = R"PEM(
-----BEGIN CERTIFICATE-----
MIICpjCCAiugAwIBAgIRAIchZfw0tuX7qK3Vs3BftTowCgYIKoZIzj0EAwMwTzEL
MAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2VhcmNo
IEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDIwHhcNMjYwNTEzMDAwMDAwWhcN
MzIwOTAyMjM1OTU5WjAuMQswCQYDVQQGEwJVUzENMAsGA1UEChMESVNSRzEQMA4G
A1UEAxMHUm9vdCBZRTB2MBAGByqGSM49AgEGBSuBBAAiA2IABDwS/6vhrcVqcbBo
+wgdI3fwn9x7DNJJOY/lTOti0vkwuRN87RhEhTH17E7XyFjWsPYhIPt/wzOqxTd2
b+4ZJNy9ID04YywF9U5zasDVyGSNErVNtz8uSGh5izW87j77GaOB6zCB6DAOBgNV
HQ8BAf8EBAMCAQYwEwYDVR0lBAwwCgYIKwYBBQUHAwEwDwYDVR0TAQH/BAUwAwEB
/zAdBgNVHQ4EFgQUo8gmWo6hTNA1Y/ybI8g6rlbzT1YwHwYDVR0jBBgwFoAUfEKW
rt5LSDv6kviejM9ti6lyN5UwMgYIKwYBBQUHAQEEJjAkMCIGCCsGAQUFBzAChhZo
dHRwOi8veDIuaS5sZW5jci5vcmcvMBMGA1UdIAQMMAowCAYGZ4EMAQIBMCcGA1Ud
HwQgMB4wHKAaoBiGFmh0dHA6Ly94Mi5jLmxlbmNyLm9yZy8wCgYIKoZIzj0EAwMD
aQAwZgIxAMU19WCtmxVND8UHBZRoma49Z7jPs64Dma0eTu1OChVbB/2J7GV3nvYK
Ax54uk1G9QIxAO0miLVJu8PLNiXXXkiE/gsK3CTRTF/aeo4bMX42Zw40csRU6AC2
6hSW1/IWaas6dg==
-----END CERTIFICATE-----
)PEM";

String hasilDeteksi = "";
uint8_t* frameAntrian = NULL;
size_t ukuranFrameAntrian = 0;
uint32_t nomorAntrian = 0;
bool adaAntrian = false;

String serverUrl = "";
String apiKey = "";
bool simpanKonfigurasi = false;

Preferences prefs;

SemaphoreHandle_t dataMutex = NULL;

httpd_handle_t webServer = NULL;
httpd_handle_t streamServer = NULL;

static const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ESP32-S3 VestCare Detector</title>
<style>
body {
    font-family: Arial;
    text-align: center;
    margin: 20px;
    background: #f5f5f5;
}
h2 {
    color: #222;
}
#stream {
    width: 320px;
    height: 240px;
    border: 2px solid #333;
    background: #111;
}
.control {
    margin: 20px auto;
    width: 320px;
}
.result-box {
    margin: 20px auto;
    width: 80%;
    max-width: 600px;
}
#detectionResult {
    width: 100%;
    padding: 10px;
    box-sizing: border-box;
}
textarea {
    resize: vertical;
}
button {
    padding: 8px 15px;
    margin: 5px;
    cursor: pointer;
}
</style>
</head>
<body>
<h2>ESP32-S3 VestCare Detector</h2>
<img id="stream">
<div class="control">
    <label>LED Flash</label>
    <input type="range" min="0" max="255" value="0" oninput="setFlash(this.value)">
</div>
<div class="result-box">
    <p>Hasil Deteksi</p>
    <textarea id="detectionResult" readonly rows="6"></textarea>
    <br>
    <button onclick="copyResult()">Salin Hasil</button>
    <button onclick="clearResult()">Bersihkan</button>
</div>
<script>
document.getElementById("stream").src =
    "http://" + window.location.hostname + ":81/stream";

function setFlash(val) {
    fetch("/led?val=" + val);
}

function copyResult() {
    const box = document.getElementById("detectionResult");
    if (box.value) {
        navigator.clipboard.writeText(box.value);
    }
}

function clearResult() {
    document.getElementById("detectionResult").value = "";
    fetch("/result?clear=1");
}

setInterval(() => {
    fetch("/result")
    .then(response => response.text())
    .then(data => {
        if (data.length > 0) {
            document.getElementById("detectionResult").value = data;
        }
    });
}, 500);
</script>
</body>
</html>
)rawliteral";

String escapeJson(const String &s) {
    String o;
    o.reserve(s.length() + 8);

    for (size_t i = 0; i < s.length(); i++) {
        char c = s[i];

        switch (c) {
            case '"':  o += "\\\""; break;
            case '\\': o += "\\\\"; break;
            case '\n': o += "\\n";  break;
            case '\r': o += "\\r";  break;
            case '\t': o += "\\t";  break;
            default:
                if ((uint8_t)c < 0x20) {
                    char b[7];
                    snprintf(b, sizeof(b), "\\u%04x", c);
                    o += b;
                } else {
                    o += c;
                }
        }
    }

    return o;
}

String urlBersih() {
    String url = serverUrl;
    url.trim();

    while (url.endsWith("/")) {
        url.remove(url.length() - 1);
    }

    return url;
}

bool urlServerValid() {
    String url = urlBersih();

    const bool https = url.startsWith("https://");
    const bool http = url.startsWith("http://");

    if ((!https && !http) || url.length() <= (https ? 8 : 7)) {
        return false;
    }

    const size_t hostStart = https ? 8 : 7;

    return url.indexOf('/', hostStart) < 0
        && url.indexOf('?', hostStart) < 0
        && url.indexOf('#', hostStart) < 0
        && url.indexOf(' ', hostStart) < 0;
}

void muatKonfigurasi() {
    prefs.begin("vestcare", true);
    serverUrl = prefs.getString("url", "");
    apiKey = prefs.getString("key", VEST_API_KEY);
    prefs.end();
}

void simpanKonfigurasiBaru(const char *url, const char *key) {
    serverUrl = String(url);
    apiKey = String(key);

    prefs.begin("vestcare", false);
    prefs.putString("url", serverUrl);
    prefs.putString("key", apiKey);
    prefs.end();

    Serial.println("[SERVER] Konfigurasi server tersimpan.");
}

void hapusKonfigurasi() {
    prefs.begin("vestcare", false);
    prefs.clear();
    prefs.end();

    serverUrl = "";
    apiKey = "";
}

void tandaiKonfigurasiUntukDisimpan() {
    simpanKonfigurasi = true;
}

void configModeCallback(WiFiManager *wm) {
    Serial.println("\nMasuk mode konfigurasi!");
    Serial.print("Hubungkan HP ke WiFi: ");
    Serial.println(wm->getConfigPortalSSID());
    Serial.print("Buka alamat: ");
    Serial.println(WiFi.softAPIP());
}

static esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, INDEX_HTML, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t led_handler(httpd_req_t *req) {
    char query[32];
    char valStr[8];

    if (httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK) {
        if (httpd_query_key_value(query, "val", valStr, sizeof(valStr)) == ESP_OK) {
            int brightness = constrain(atoi(valStr), 0, 255);
            ledcWrite(FLASH_LED_PIN, brightness);
        }
    }

    return httpd_resp_send(req, "OK", 2);
}

static esp_err_t result_handler(httpd_req_t *req) {
    char query[32];

    if (httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK) {
        if (strstr(query, "clear=1") != NULL) {
            xSemaphoreTake(dataMutex, portMAX_DELAY);
            hasilDeteksi = "";
            xSemaphoreGive(dataMutex);
            return httpd_resp_send(req, "", 0);
        }
    }

    String currentData;

    xSemaphoreTake(dataMutex, portMAX_DELAY);
    currentData = hasilDeteksi;
    xSemaphoreGive(dataMutex);

    httpd_resp_set_type(req, "text/plain");
    return httpd_resp_send(req, currentData.c_str(), currentData.length());
}

static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    char part_buf[64];

    httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    while (true) {
        fb = esp_camera_fb_get();

        if (!fb) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        if (fb->format != PIXFORMAT_JPEG) {
            esp_camera_fb_return(fb);
            res = ESP_FAIL;
            break;
        }

        size_t hlen = snprintf(
            part_buf,
            sizeof(part_buf),
            "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
            (unsigned int)fb->len
        );

        res = httpd_resp_send_chunk(req, part_buf, hlen);

        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
        }

        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, "\r\n", 2);
        }

        esp_camera_fb_return(fb);

        if (res != ESP_OK) {
            break;
        }
    }

    return res;
}

void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;

    httpd_uri_t index_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = index_handler,
        .user_ctx = NULL
    };

    httpd_uri_t led_uri = {
        .uri = "/led",
        .method = HTTP_GET,
        .handler = led_handler,
        .user_ctx = NULL
    };

    httpd_uri_t result_uri = {
        .uri = "/result",
        .method = HTTP_GET,
        .handler = result_handler,
        .user_ctx = NULL
    };

    if (httpd_start(&webServer, &config) == ESP_OK) {
        httpd_register_uri_handler(webServer, &index_uri);
        httpd_register_uri_handler(webServer, &led_uri);
        httpd_register_uri_handler(webServer, &result_uri);
    }

    httpd_config_t stream_config = HTTPD_DEFAULT_CONFIG();
    stream_config.server_port = 81;
    stream_config.ctrl_port += 1;

    httpd_uri_t stream_uri = {
        .uri = "/stream",
        .method = HTTP_GET,
        .handler = stream_handler,
        .user_ctx = NULL
    };

    if (httpd_start(&streamServer, &stream_config) == ESP_OK) {
        httpd_register_uri_handler(streamServer, &stream_uri);
    }
}

int kirimFrameHttp(WiFiClient &client, const String &endpoint,
                   const uint8_t *frame, size_t frameSize) {
    const char *boundary = "VestCareESP32S3Boundary";
    String head = F("--VestCareESP32S3Boundary\r\n"
                    "Content-Disposition: form-data; name=\"gambar\"; filename=\"frame.jpg\"\r\n"
                    "Content-Type: image/jpeg\r\n\r\n");
    String tail = F("\r\n--VestCareESP32S3Boundary\r\n"
                    "Content-Disposition: form-data; name=\"mode_realtime\"\r\n\r\nfalse"
                    "\r\n--VestCareESP32S3Boundary\r\n"
                    "Content-Disposition: form-data; name=\"sesi\"\r\n\r\n");
    tail += DEVICE_ID;
    tail += F("\r\n--VestCareESP32S3Boundary--\r\n");

    const size_t bodySize = head.length() + frameSize + tail.length();
    uint8_t *body = (uint8_t *)heap_caps_malloc(bodySize, MALLOC_CAP_SPIRAM);
    if (!body) {
        Serial.println("[SERVER] Gagal mengalokasikan buffer frame.");
        return -1;
    }

    size_t offset = 0;
    memcpy(body + offset, head.c_str(), head.length());
    offset += head.length();
    memcpy(body + offset, frame, frameSize);
    offset += frameSize;
    memcpy(body + offset, tail.c_str(), tail.length());

    HTTPClient http;
    http.setTimeout(8000);
    if (!http.begin(client, endpoint)) {
        heap_caps_free(body);
        Serial.println("[SERVER] Gagal memulai koneksi HTTP.");
        return -1;
    }

    http.addHeader("Content-Type", "multipart/form-data; boundary=VestCareESP32S3Boundary");
    http.addHeader("ngrok-skip-browser-warning", "1");
    if (apiKey.length() > 0) {
        http.addHeader("X-API-Key", apiKey);
    }

    const int status = http.POST(body, bodySize);
    String response = status >= 200 ? http.getString() : "";
    heap_caps_free(body);

    if (status >= 200 && status < 300) {
        String ringkas = "[SERVER] Deteksi diterima (HTTP ";
        ringkas += status;
        ringkas += ")";
        if (response.length() > 0) {
            ringkas += ": ";
            ringkas += response;
        }
        xSemaphoreTake(dataMutex, portMAX_DELAY);
        hasilDeteksi = ringkas;
        xSemaphoreGive(dataMutex);
        Serial.println(ringkas);
    } else if (status > 0) {
        Serial.printf("[SERVER] Deteksi ditolak (HTTP %d): %s\n", status, response.c_str());
    } else {
        Serial.printf("[SERVER] Koneksi gagal: %s\n", http.errorToString(status).c_str());
    }

    http.end();
    return status;
}

int kirimFrame(const uint8_t *frame, size_t frameSize) {
    const String baseUrl = urlBersih();
    const String endpoint = baseUrl + PATH_API;

    if (baseUrl.startsWith("https://")) {
        if (time(nullptr) < WAKTU_TLS_MINIMUM) {
            Serial.println("[TLS] Menunggu sinkronisasi waktu NTP.");
            return -2;
        }

        WiFiClientSecure client;
        client.setCACert(SERTIFIKAT_ROOT_YE);
        return kirimFrameHttp(client, endpoint, frame, frameSize);
    }

    WiFiClient client;
    return kirimFrameHttp(client, endpoint, frame, frameSize);
}

void kirimServerTask(void *pvParameters) {
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(500));

        if (WiFi.status() != WL_CONNECTED || !urlServerValid()) {
            continue;
        }

        uint8_t *frame = NULL;
        size_t frameSize = 0;
        uint32_t id = 0;
        bool ada = false;

        xSemaphoreTake(dataMutex, portMAX_DELAY);
        if (adaAntrian) {
            frame = frameAntrian;
            frameSize = ukuranFrameAntrian;
            id = nomorAntrian;
            ada = true;
        }
        xSemaphoreGive(dataMutex);

        if (!ada) {
            continue;
        }

        const int status = kirimFrame(frame, frameSize);

        if (status >= 200 && status < 300) {
            xSemaphoreTake(dataMutex, portMAX_DELAY);
            if (nomorAntrian == id) {
                adaAntrian = false;
                if (frameAntrian) {
                    heap_caps_free(frameAntrian);
                    frameAntrian = NULL;
                    ukuranFrameAntrian = 0;
                }
            }
            xSemaphoreGive(dataMutex);
        } else {
            vTaskDelay(pdMS_TO_TICKS(JEDA_ULANG_KIRIM));
        }
    }
}

void cameraDetectTask(void *pvParameters) {
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(JEDA_DETEKSI));

        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb || fb->format != PIXFORMAT_JPEG) {
            if (fb) esp_camera_fb_return(fb);
            continue;
        }

        bool dapatAntrean = false;
        xSemaphoreTake(dataMutex, portMAX_DELAY);
        if (!adaAntrian) {
            uint8_t *salinan = (uint8_t *)heap_caps_malloc(fb->len, MALLOC_CAP_SPIRAM);
            if (salinan) {
                memcpy(salinan, fb->buf, fb->len);
                frameAntrian = salinan;
                ukuranFrameAntrian = fb->len;
                nomorAntrian++;
                adaAntrian = true;
                dapatAntrean = true;
            }
        }
        xSemaphoreGive(dataMutex);

        esp_camera_fb_return(fb);

        if (dapatAntrean) {
            Serial.printf("[CAMERA] Frame %u dikirim untuk deteksi.\n",
                          (unsigned int)nomorAntrian);
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("ESP32-S3 VestCare OBJECT DETECTOR");

    dataMutex = xSemaphoreCreateMutex();

    if (dataMutex == NULL) {
        Serial.println("Data mutex failed");
        return;
    }

    Serial.printf("PSRAM: %s\n", psramFound() ? "Detected" : "Not detected");

    if (!psramFound()) {
        Serial.println("PSRAM is required for this configuration");
        return;
    }

    pinMode(RESET_PIN, INPUT_PULLUP);

    ledcAttach(FLASH_LED_PIN, 5000, 8);
    ledcWrite(FLASH_LED_PIN, 0);

    muatKonfigurasi();

    WiFi.mode(WIFI_STA);

    WiFiManager wm;

    if (digitalRead(RESET_PIN) == LOW) {
        Serial.println("Menghapus pengaturan WiFi dan server...");
        wm.resetSettings();
        hapusKonfigurasi();
        delay(1000);
    }

    WiFiManagerParameter parameterServer(
        "server_url",
        "URL root server VestCare (contoh: https://xxxx.ngrok-free.dev)",
        serverUrl.c_str(),
        127
    );

    WiFiManagerParameter parameterApiKey(
        "api_key",
        "VEST_API_KEY (kosongkan jika autentikasi server nonaktif)",
        apiKey.c_str(),
        64
    );

    wm.addParameter(&parameterServer);
    wm.addParameter(&parameterApiKey);
    wm.setSaveConfigCallback(tandaiKonfigurasiUntukDisimpan);
    wm.setAPCallback(configModeCallback);
    wm.setConfigPortalTimeout(180);

    bool connected = wm.autoConnect("VestCare-ESP32S3", "12345678");

    if (!connected) {
        Serial.println("Gagal terhubung, restart...");
        delay(3000);
        ESP.restart();
    }

    if (simpanKonfigurasi) {
        simpanKonfigurasiBaru(parameterServer.getValue(), parameterApiKey.getValue());
    }

    WiFi.setSleep(false);

    Serial.println("\nWiFi terhubung!");
    Serial.print("SSID : ");
    Serial.println(WiFi.SSID());
    Serial.print("IP   : ");
    Serial.println(WiFi.localIP());

    configTime(7 * 60 * 60, 0, "pool.ntp.org", "time.nist.gov");

    if (urlServerValid()) {
        Serial.printf("[SERVER] Frame dikirim ke %s%s\n", urlBersih().c_str(), PATH_API);
    } else {
        Serial.println("[SERVER] URL belum valid. Atur URL melalui portal VestCare-ESP32S3.");
    }

    camera_config_t config = {};

    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;

    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;

    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;

    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;

    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;

    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;

    Serial.println("Initializing camera...");

    esp_err_t err = esp_camera_init(&config);

    if (err != ESP_OK) {
        Serial.printf("Camera initialization failed: 0x%x\n", err);
        return;
    }

    Serial.println("Camera initialized successfully");

    sensor_t *s = esp_camera_sensor_get();

    if (s != NULL) {
        if (s->id.PID == OV3660_PID) {
            s->set_vflip(s, 1);
        }

        s->set_contrast(s, 1);
        s->set_ae_level(s, -1);
    }

    startCameraServer();

    Serial.println("Camera server started");
    Serial.print("Open browser: http://");
    Serial.println(WiFi.localIP());

    xTaskCreatePinnedToCore(
        cameraDetectTask,
        "CameraDetect",
        32768,
        NULL,
        1,
        NULL,
        1
    );

    xTaskCreatePinnedToCore(
        kirimServerTask,
        "KirimServer",
        16384,
        NULL,
        1,
        NULL,
        0
    );
}

void loop() {
    delay(1000);
}