# palvelin.py
# Ajetaan Raspberry Pi 4:llä tavallisella Pythonilla (ei MicroPython).
# Ottaa vastaan ESP32:n lähettämän JSON-datan, tallettaa sen levylle
# ja tarjoaa sen edelleen index.html-sivulle.
#
# Asennus Raspberry Pi:llä:
#   pip install flask
#   python3 palvelin.py
#
# Sivu näkyy selaimessa osoitteessa http://<pin_ip>:5000/

import json
import os
import queue
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response

app = Flask(__name__)

TIEDOSTOKANSIO = os.path.dirname(os.path.abspath(__file__))
VIIMEISIN_TIEDOSTO = os.path.join(TIEDOSTOKANSIO, "viimeisin.json")
HISTORIA_TIEDOSTO = os.path.join(TIEDOSTOKANSIO, "historia.json")
HISTORIA_MAX_PITUUS = 200

# Live-seurantaa varten: jokainen avoin selainyhteys saa oman jonon,
# johon uusi data työnnetään heti kun sitä saapuu.
TILAAJAT = []
TILAAJA_LUKKO = threading.Lock()


def laheta_kaikille_tilaajille(data):
    with TILAAJA_LUKKO:
        for jono in TILAAJAT:
            jono.put(data)


def lataa_json(polku, oletus):
    if os.path.exists(polku):
        with open(polku, "r") as f:
            return json.load(f)
    return oletus


def tallenna_json(polku, data):
    with open(polku, "w") as f:
        json.dump(data, f)


@app.route("/api/data", methods=["POST"])
def vastaanota_data():
    kuorma = request.get_json(force=True)
    if kuorma is None or "temperature" not in kuorma or "humidity" not in kuorma:
        return jsonify({"virhe": "odotettiin kenttiä temperature ja humidity"}), 400

    kuorma["received_at"] = datetime.now().isoformat(timespec="seconds")
    tallenna_json(VIIMEISIN_TIEDOSTO, kuorma)

    historia = lataa_json(HISTORIA_TIEDOSTO, [])
    historia.append(kuorma)
    historia = historia[-HISTORIA_MAX_PITUUS:]
    tallenna_json(HISTORIA_TIEDOSTO, historia)

    laheta_kaikille_tilaajille(kuorma)

    return jsonify({"tila": "ok"})


@app.route("/api/data", methods=["GET"])
def hae_viimeisin():
    return jsonify(lataa_json(VIIMEISIN_TIEDOSTO, {}))


@app.route("/api/history", methods=["GET"])
def hae_historia():
    return jsonify(lataa_json(HISTORIA_TIEDOSTO, []))


@app.route("/api/stream")
def tapahtumavirta():
    oma_jono = queue.Queue()
    with TILAAJA_LUKKO:
        TILAAJAT.append(oma_jono)

    def virta():
        try:
            while True:
                data = oma_jono.get()  # jää odottamaan seuraavaa mittausta
                yield "data: " + json.dumps(data) + "\n\n"
        finally:
            with TILAAJA_LUKKO:
                if oma_jono in TILAAJAT:
                    TILAAJAT.remove(oma_jono)

    return Response(virta(), mimetype="text/event-stream")


@app.route("/")
def index():
    return send_from_directory(TIEDOSTOKANSIO, "index.html")


if __name__ == "__main__":
    # host="0.0.0.0" tekee palvelimesta näkyvän muille laitteille verkossa
    # threaded=True on välttämätön, jotta /api/stream ei tuki muita pyyntöjä
    app.run(host="0.0.0.0", port=5000, threaded=True)
