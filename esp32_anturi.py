# esp32_anturi.py
# Ajetaan ESP32:lla (MicroPython). Lukee DHT22-anturin, näyttää lukemat
# ESP32:n omalla OLED-näytöllä (SSD1306, I2C) ja lähettää tiedot
# Raspberry Pi:llä pyörivälle palvelimelle live-seurantaa varten.
#
# Kytkentä:
#   DHT22 VCC   -> 3V3        OLED VCC -> 3V3
#   DHT22 GND   -> GND        OLED GND -> GND
#   DHT22 DATA  -> GPIO4      OLED SDA -> GPIO21
#                              OLED SCL -> GPIO22
#
# OLED-ajuri "ssd1306" ei ole oletuksena mukana MicroPythonissa.
# Asenna se ESP32:lle kerran esim. Thonnyllä tai mpremotella:
#   mpremote mip install ssd1306
# (tai lataa micropython-lib:stä ssd1306.py ja kopioi se ESP32:lle)
#
# Muista asentaa/kopioida tämä tiedosto ESP32:lle nimellä main.py,
# jotta se käynnistyy automaattisesti virran kytkeytyessä.

import network
import time
import ujson
import urequests
import dht
from machine import Pin, I2C

try:
    import ssd1306
    NAYTTO_KAYTOSSA = True
except ImportError:
    NAYTTO_KAYTOSSA = False
    print("Huom: ssd1306-ajuria ei löytynyt, jatketaan ilman näyttöä")

# ---- ASETUKSET: muokkaa nämä omiin tietoihisi ----
WIFI_SSID = "WIFI_NIMI"
WIFI_SALASANA = "WIFI_SALASANA"
PALVELIN_URL = "http://192.168.1.50:5000/api/data"  # Raspberry Pi:n IP-osoite
ANTURI_PIN = 4
I2C_SDA_PIN = 21
I2C_SCL_PIN = 22
LAHETYSVALI_S = 5  # kuinka usein mitataan, näytetään ja lähetetään (sekuntia)
# ---------------------------------------------------

anturi = dht.DHT22(Pin(ANTURI_PIN))

naytto = None
if NAYTTO_KAYTOSSA:
    try:
        i2c = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=400000)
        naytto = ssd1306.SSD1306_I2C(128, 64, i2c)
    except Exception as e:
        print("OLED-näyttöä ei saatu käyttöön:", e)
        naytto = None


def paivita_nayttoa(lampotila, kosteus, wifi_ok, lahetys_ok):
    if naytto is None:
        return
    naytto.fill(0)
    naytto.text("Saaasema", 0, 0)
    naytto.text("Lampo: {:.1f} C".format(lampotila), 0, 20)
    naytto.text("Kosteus: {:.1f} %".format(kosteus), 0, 34)
    tila = "WiFi:{} Lahetys:{}".format(
        "OK" if wifi_ok else "EI", "OK" if lahetys_ok else "EI"
    )
    naytto.text(tila, 0, 52)
    naytto.show()


def yhdista_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Yhdistetään verkkoon:", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_SALASANA)
        aikaraja = time.ticks_add(time.ticks_ms(), 15000)
        while not wlan.isconnected():
            if time.ticks_diff(aikaraja, time.ticks_ms()) < 0:
                raise RuntimeError("WiFi-yhteys epäonnistui")
            time.sleep(0.5)
    print("Yhdistetty, IP:", wlan.ifconfig()[0])
    return wlan


def lue_anturi():
    anturi.measure()
    return anturi.temperature(), anturi.humidity()


def laheta_data(lampotila, kosteus):
    kuorma = ujson.dumps({
        "temperature": lampotila,
        "humidity": kosteus,
        "device_time": time.time()
    })
    try:
        vastaus = urequests.post(
            PALVELIN_URL,
            data=kuorma,
            headers={"Content-Type": "application/json"}
        )
        print("Lähetetty:", kuorma, "-> status", vastaus.status_code)
        onnistui = vastaus.status_code == 200
        vastaus.close()
        return onnistui
    except Exception as e:
        print("Lähetysvirhe:", e)
        return False


def main():
    wlan = yhdista_wifi()
    while True:
        lahetys_ok = False
        try:
            if not wlan.isconnected():
                wlan = yhdista_wifi()
            lampotila, kosteus = lue_anturi()
            print("Lämpötila: {} C, Kosteus: {} %".format(lampotila, kosteus))
            lahetys_ok = laheta_data(lampotila, kosteus)
            paivita_nayttoa(lampotila, kosteus, wlan.isconnected(), lahetys_ok)
        except Exception as e:
            print("Mittausvirhe:", e)
        time.sleep(LAHETYSVALI_S)


main()
