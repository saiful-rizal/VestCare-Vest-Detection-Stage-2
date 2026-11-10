#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <WiFiManager.h>
#include <SoftwareSerial.h>
#include <TinyGPSPlus.h>
#include <EEPROM.h>
#include <time.h>

#define TRIG_PIN D6
#define ECHO_PIN D7
#define PIN_TERIMA_DARI_GPS D2
#define PIN_KIRIM_KE_GPS D1
#define RESET_PIN D5
#define LED_PIN LED_BUILTIN

const float SUHU_UDARA = 27.0;
const float OFFSET_METER = 0.0;
const int JUMLAH_SAMPEL = 5;
const unsigned long JEDA_BACA = 60;
const unsigned long JEDA_TELEMETRI = 5000;
const bool TAMPILKAN_MENTAH = false;
const uint32_t CONFIG_MAGIC = 0x56435431;
const size_t EEPROM_SIZE = 256;
const time_t WAKTU_TLS_MINIMUM = 1780000000;
const char DEFAULT_SERVER_URL[] = "https://italics-blast-vibes.ngrok-free.dev";

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

BearSSL::X509List tlsTrustAnchors(SERTIFIKAT_ROOT_YE);

struct KonfigurasiVestCare {
  uint32_t magic;
  char serverUrl[128];
  char apiKey[65];
};

ESP8266WebServer server(80);
SoftwareSerial gpsSerial(PIN_TERIMA_DARI_GPS, PIN_KIRIM_KE_GPS);
TinyGPSPlus gps;
KonfigurasiVestCare konfigurasi;

float kecepatanSuara = 0;
float sampel[JUMLAH_SAMPEL];
int indeksSampel = 0;
int sampelTerisi = 0;
int gagalBerturut = 0;
float jarakTerakhir = -1;
unsigned long waktuBaca = 0;
unsigned long waktuLaporan = 0;
unsigned long waktuTelemetri = 0;
bool simpanKonfigurasi = false;

const char halaman[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor Wemos</title>
<style>
body{font-family:sans-serif;background:#f2f4f8;margin:0;padding:12px}
.kartu{background:#fff;border-radius:16px;padding:20px;max-width:360px;margin:14px auto;box-shadow:0 2px 10px rgba(0,0,0,.15)}
h2{text-align:center;margin:0 0 12px}
.nilai{font-size:68px;font-weight:bold;color:#1565c0;text-align:center}
.satuan{font-size:24px;color:#555}
.bar{height:12px;background:#e3e8ef;border-radius:6px;margin-top:14px;overflow:hidden}
.isi{height:100%;width:0;background:#1565c0;transition:width .15s}
.status{text-align:center;margin-top:12px;font-size:14px;font-weight:bold}
.ok{color:#2e7d32}.cari{color:#ef6c00}.err{color:#c62828}
.baris{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #eee}
.baris span:first-child{color:#666}
.baris span:last-child{font-weight:bold;color:#1565c0}
a.peta{display:block;text-align:center;margin-top:16px;padding:12px;background:#1565c0;color:#fff;border-radius:10px;text-decoration:none}
a.mati{background:#b0bec5;pointer-events:none}
</style>
</head>
<body>
<div class="kartu">
<h2>Sensor Jarak</h2>
<div class="nilai"><span id="jarak">--</span> <span class="satuan">m</span></div>
<div class="bar"><div class="isi" id="isi"></div></div>
<div class="status cari" id="sj">Menunggu data...</div>
</div>
<div class="kartu">
<h2>GPS NEO-6M</h2>
<div class="status cari" id="sg">Menunggu data...</div>
<div class="baris"><span>Latitude</span><span id="lat">--</span></div>
<div class="baris"><span>Longitude</span><span id="lng">--</span></div>
<div class="baris"><span>Ketinggian</span><span id="alt">--</span></div>
<div class="baris"><span>Kecepatan</span><span id="spd">--</span></div>
<div class="baris"><span>Satelit</span><span id="sat">--</span></div>
<div class="baris"><span>HDOP</span><span id="hdop">--</span></div>
<div class="baris"><span>Waktu (WIB)</span><span id="waktu">--</span></div>
<div class="baris"><span>Karakter diterima</span><span id="kar">--</span></div>
<a class="peta mati" id="peta" href="#" target="_blank">Buka di Google Maps</a>
</div>
<script>
function set(id,v){document.getElementById(id).innerText=v}
function kelas(id,c,t){var e=document.getElementById(id);e.className='status '+c;e.innerText=t}
function ambil(){
  fetch('/data',{cache:'no-store'})
  .then(r=>r.json())
  .then(d=>{
    if(d.valid){
      set('jarak',d.jarak.toFixed(2));
      document.getElementById('isi').style.width=Math.min(d.jarak/4*100,100)+'%';
      kelas('sj','ok','Realtime');
    } else {
      set('jarak','--');
      document.getElementById('isi').style.width='0';
      kelas('sj','cari','Di luar jangkauan (0,02 - 4 m)');
    }
    set('sat',d.sat);
    set('kar',d.kar);
    var p=document.getElementById('peta');
    if(!d.fix){
      set('lat','--');
      set('lng','--');
      set('alt','--');
      set('spd','--');
      set('hdop','--');
      set('waktu','--');
      p.className='peta mati';
      p.href='#';
    }
    if(!d.terbaca){
      kelas('sg','err','GPS tidak terdeteksi, cek kabel TX');
    } else if(!d.fix){
      kelas('sg','cari','GPS terbaca, mencari satelit...');
    } else {
      kelas('sg','ok','Lokasi terkunci');
      set('lat',d.lat.toFixed(6));
      set('lng',d.lng.toFixed(6));
      set('alt',d.alt.toFixed(1)+' m');
      set('spd',d.spd.toFixed(1)+' km/jam');
      set('hdop',d.hdop.toFixed(1));
      set('waktu',d.waktu);
      p.className='peta';
      p.href='https://www.google.com/maps?q='+d.lat+','+d.lng;
    }
  })
  .catch(()=>{
    kelas('sj','err','Koneksi terputus');
    kelas('sg','err','Koneksi terputus');
  })
  .finally(()=>setTimeout(ambil,300));
}
ambil();
</script>
</body>
</html>
)rawliteral";

void configModeCallback(WiFiManager *wm) {
  Serial.println("\nMasuk mode konfigurasi!");
  Serial.print("Hubungkan HP ke WiFi: ");
  Serial.println(wm->getConfigPortalSSID());
  Serial.print("Buka alamat: ");
  Serial.println(WiFi.softAPIP());
  digitalWrite(LED_PIN, LOW);
}

void bacaGPS() {
  while (gpsSerial.available() > 0) {
    char c = gpsSerial.read();
    if (TAMPILKAN_MENTAH) {
      Serial.write(c);
    }
    gps.encode(c);
  }
}

float bacaSekali() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(4);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long durasi = pulseIn(ECHO_PIN, HIGH, 25000);
  if (durasi == 0) {
    return -1;
  }
  float jarak = (durasi * 0.000001f * kecepatanSuara) / 2.0f + OFFSET_METER;
  if (jarak < 0.02f || jarak > 4.0f) {
    return -1;
  }
  return jarak;
}

float hitungMedian() {
  float tmp[JUMLAH_SAMPEL];
  for (int i = 0; i < sampelTerisi; i++) {
    tmp[i] = sampel[i];
  }
  for (int i = 1; i < sampelTerisi; i++) {
    float kunci = tmp[i];
    int j = i - 1;
    while (j >= 0 && tmp[j] > kunci) {
      tmp[j + 1] = tmp[j];
      j--;
    }
    tmp[j + 1] = kunci;
  }
  return tmp[sampelTerisi / 2];
}

void perbaruiJarak() {
  if (millis() - waktuBaca < JEDA_BACA) {
    return;
  }
  waktuBaca = millis();

  float j = bacaSekali();
  if (j < 0) {
    gagalBerturut++;
    if (gagalBerturut >= 5) {
      jarakTerakhir = -1;
      sampelTerisi = 0;
      indeksSampel = 0;
    }
    return;
  }
  gagalBerturut = 0;

  sampel[indeksSampel] = j;
  indeksSampel = (indeksSampel + 1) % JUMLAH_SAMPEL;
  if (sampelTerisi < JUMLAH_SAMPEL) {
    sampelTerisi++;
  }
  jarakTerakhir = hitungMedian();
}

void laporanSerial() {
  if (millis() - waktuLaporan < 3000) {
    return;
  }
  waktuLaporan = millis();
  Serial.print("[JARAK] ");
  if (jarakTerakhir > 0) {
    Serial.print(jarakTerakhir, 2);
    Serial.print(" m");
  } else {
    Serial.print("di luar jangkauan");
  }
  Serial.print(" | [GPS] karakter: ");
  Serial.print(gps.charsProcessed());
  Serial.print(" | satelit: ");
  Serial.print(gps.satellites.isValid() ? gps.satellites.value() : 0);
  Serial.print(" | lokasi: ");
  Serial.println(gps.location.isValid() ? "terkunci" : "belum");
}

void handleRoot() {
  server.send_P(200, "text/html", halaman);
}

void handleData() {
  bool terbaca = gps.charsProcessed() > 10;
  bool fix = gps.location.isValid() && gps.location.age() < 3000;

  String json = "{";
  if (jarakTerakhir > 0) {
    json += "\"valid\":true,\"jarak\":" + String(jarakTerakhir, 3);
  } else {
    json += "\"valid\":false,\"jarak\":0";
  }
  json += ",\"terbaca\":" + String(terbaca ? "true" : "false");
  json += ",\"fix\":" + String(fix ? "true" : "false");
  json += ",\"kar\":" + String(gps.charsProcessed());
  json += ",\"sat\":" + String(gps.satellites.isValid() ? gps.satellites.value() : 0);

  if (fix) {
    char waktu[12] = "--:--:--";
    if (gps.time.isValid()) {
      snprintf(waktu, sizeof(waktu), "%02d:%02d:%02d", (gps.time.hour() + 7) % 24, gps.time.minute(), gps.time.second());
    }
    json += ",\"lat\":" + String(gps.location.lat(), 6);
    json += ",\"lng\":" + String(gps.location.lng(), 6);
    json += ",\"alt\":" + String(gps.altitude.isValid() ? gps.altitude.meters() : 0.0, 1);
    json += ",\"spd\":" + String(gps.speed.isValid() ? gps.speed.kmph() : 0.0, 1);
    json += ",\"hdop\":" + String(gps.hdop.isValid() ? gps.hdop.hdop() : 0.0, 1);
    json += ",\"waktu\":\"" + String(waktu) + "\"";
  }

  json += "}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

void tandaiKonfigurasiUntukDisimpan() {
  simpanKonfigurasi = true;
}

void muatKonfigurasi() {
  EEPROM.begin(EEPROM_SIZE);
  EEPROM.get(0, konfigurasi);
  if (konfigurasi.magic != CONFIG_MAGIC) {
    memset(&konfigurasi, 0, sizeof(konfigurasi));
    konfigurasi.magic = CONFIG_MAGIC;
  } else {
    konfigurasi.serverUrl[sizeof(konfigurasi.serverUrl) - 1] = '\0';
    konfigurasi.apiKey[sizeof(konfigurasi.apiKey) - 1] = '\0';
  }

  if (konfigurasi.serverUrl[0] == '\0') {
    snprintf(konfigurasi.serverUrl, sizeof(konfigurasi.serverUrl), "%s", DEFAULT_SERVER_URL);
  }
}

bool urlServerValid() {
  String url = String(konfigurasi.serverUrl);
  url.trim();
  while (url.endsWith("/")) {
    url.remove(url.length() - 1);
  }
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

void simpanKonfigurasiBaru(const char *serverUrl, const char *apiKey) {
  snprintf(konfigurasi.serverUrl, sizeof(konfigurasi.serverUrl), "%s", serverUrl);
  snprintf(konfigurasi.apiKey, sizeof(konfigurasi.apiKey), "%s", apiKey);
  konfigurasi.magic = CONFIG_MAGIC;
  EEPROM.put(0, konfigurasi);
  if (!EEPROM.commit()) {
    Serial.println("[SERVER] Gagal menyimpan konfigurasi ke EEPROM.");
    return;
  }
  Serial.println("[SERVER] Konfigurasi server tersimpan.");
}

void tambahAngkaJson(String &json, bool valid, double nilai, uint8_t desimal) {
  if (valid) {
    json += String(nilai, desimal);
  } else {
    json += F("null");
  }
}

int kirimHttpTelemetri(WiFiClient &client, const String &endpoint, const String &payload) {
  HTTPClient http;
  http.setTimeout(8000);
  if (!http.begin(client, endpoint)) {
    Serial.println("[SERVER] Gagal memulai koneksi HTTP.");
    return -1;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("ngrok-skip-browser-warning", "1");
  if (konfigurasi.apiKey[0] != '\0') {
    http.addHeader("X-API-Key", konfigurasi.apiKey);
  }

  const int status = http.POST(payload);
  if (status >= 200 && status < 300) {
    Serial.printf("[SERVER] Telemetri terkirim (HTTP %d).\n", status);
  } else if (status > 0) {
    Serial.printf("[SERVER] Telemetri ditolak (HTTP %d).\n", status);
  } else {
    Serial.printf("[SERVER] Koneksi gagal: %s\n", http.errorToString(status).c_str());
  }
  http.end();
  return status;
}

void kirimTelemetri() {
  if (millis() - waktuTelemetri < JEDA_TELEMETRI) {
    return;
  }
  waktuTelemetri = millis();

  if (WiFi.status() != WL_CONNECTED || !urlServerValid()) {
    return;
  }

  String baseUrl = String(konfigurasi.serverUrl);
  baseUrl.trim();
  while (baseUrl.endsWith("/")) {
    baseUrl.remove(baseUrl.length() - 1);
  }

  const bool jarakValid = jarakTerakhir > 0;
  const bool fix = gps.location.isValid() && gps.location.age() < 3000;
  const bool terbaca = gps.charsProcessed() > 10;
  char waktu[12] = "--:--:--";
  if (gps.time.isValid()) {
    snprintf(
      waktu,
      sizeof(waktu),
      "%02d:%02d:%02d",
      (gps.time.hour() + 7) % 24,
      gps.time.minute(),
      gps.time.second()
    );
  }

  String payload;
  payload.reserve(256);
  payload += F("{\"jarak\":");
  tambahAngkaJson(payload, jarakValid, jarakTerakhir, 3);
  payload += F(",\"valid_jarak\":");
  payload += jarakValid ? "true" : "false";
  payload += F(",\"lat\":");
  tambahAngkaJson(payload, fix, gps.location.lat(), 6);
  payload += F(",\"lng\":");
  tambahAngkaJson(payload, fix, gps.location.lng(), 6);
  payload += F(",\"alt\":");
  tambahAngkaJson(payload, gps.altitude.isValid(), gps.altitude.meters(), 1);
  payload += F(",\"spd\":");
  tambahAngkaJson(payload, gps.speed.isValid(), gps.speed.kmph(), 1);
  payload += F(",\"sat\":");
  payload += String(gps.satellites.isValid() ? gps.satellites.value() : 0);
  payload += F(",\"hdop\":");
  tambahAngkaJson(payload, gps.hdop.isValid(), gps.hdop.hdop(), 1);
  payload += F(",\"fix\":");
  payload += fix ? "true" : "false";
  payload += F(",\"terbaca\":");
  payload += terbaca ? "true" : "false";
  payload += F(",\"waktu\":\"");
  payload += waktu;
  payload += F("\"}");

  const String endpoint = baseUrl + F("/api/telemetri");
  if (baseUrl.startsWith("https://")) {
    if (time(nullptr) < WAKTU_TLS_MINIMUM) {
      Serial.println("[TLS] Menunggu sinkronisasi waktu NTP.");
      return;
    }

    BearSSL::WiFiClientSecure client;
    client.setTrustAnchors(&tlsTrustAnchors);
    kirimHttpTelemetri(client, endpoint, payload);
    return;
  }

  WiFiClient client;
  kirimHttpTelemetri(client, endpoint, payload);
}

void setup() {
  Serial.begin(115200);
  gpsSerial.begin(9600);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RESET_PIN, INPUT_PULLUP);

  kecepatanSuara = 331.3f + 0.606f * SUHU_UDARA;

  muatKonfigurasi();
  WiFiManager wm;
  if (digitalRead(RESET_PIN) == LOW) {
    Serial.println("Menghapus pengaturan WiFi dan server...");
    wm.resetSettings();
    memset(&konfigurasi, 0, sizeof(konfigurasi));
    konfigurasi.magic = CONFIG_MAGIC;
    snprintf(konfigurasi.serverUrl, sizeof(konfigurasi.serverUrl), "%s", DEFAULT_SERVER_URL);
    EEPROM.put(0, konfigurasi);
    if (!EEPROM.commit()) {
      Serial.println("[SERVER] Gagal menghapus konfigurasi EEPROM.");
    }
    delay(1000);
  }

  WiFiManagerParameter parameterServer(
    "server_url",
    "URL server VestCare (sudah terisi otomatis)",
    konfigurasi.serverUrl,
    sizeof(konfigurasi.serverUrl)
  );
  WiFiManagerParameter parameterApiKey(
    "api_key",
    "VEST_API_KEY (kosongkan jika autentikasi server nonaktif)",
    konfigurasi.apiKey,
    sizeof(konfigurasi.apiKey)
  );
  wm.addParameter(&parameterServer);
  wm.addParameter(&parameterApiKey);
  wm.setSaveConfigCallback(tandaiKonfigurasiUntukDisimpan);

  wm.setAPCallback(configModeCallback);
  wm.setConfigPortalTimeout(180);

  bool connected = wm.autoConnect("Wemos_Setup", "12345678");

  if (!connected) {
    Serial.println("Gagal terhubung, restart...");
    delay(3000);
    ESP.restart();
  }

  if (simpanKonfigurasi) {
    simpanKonfigurasiBaru(parameterServer.getValue(), parameterApiKey.getValue());
  }

  digitalWrite(LED_PIN, HIGH);
  Serial.println("\nWiFi terhubung!");
  Serial.print("SSID : ");
  Serial.println(WiFi.SSID());
  Serial.print("IP   : ");
  Serial.println(WiFi.localIP());

  if (String(konfigurasi.serverUrl).startsWith("https://")) {
    configTime(7 * 60 * 60, 0, "pool.ntp.org", "time.nist.gov");
    Serial.println("[TLS] Sinkronisasi waktu NTP diaktifkan.");
  }

  if (urlServerValid()) {
    Serial.printf("[SERVER] Telemetri menuju %s/api/telemetri\n", konfigurasi.serverUrl);
  } else {
    Serial.println("[SERVER] URL belum valid. Atur URL server melalui portal Wemos.");
  }

  server.on("/", handleRoot);
  server.on("/data", handleData);
  server.begin();
  Serial.println("Web server berjalan.");
}

void loop() {
  bacaGPS();
  perbaruiJarak();
  bacaGPS();
  laporanSerial();
  kirimTelemetri();
  server.handleClient();
}