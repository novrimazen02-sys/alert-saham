"""
Ambil harga + riwayat candle harian SEMUA koin Rupiah di Indodax,
lalu simpan ke data/indodax.json (diunggah sebagai artifact oleh workflow).
Dipakai oleh bot Asisten Trading (Google Apps Script) karena Indodax
memblokir server Google, tetapi tidak memblokir server GitHub.
Tanpa library tambahan: hanya Python standar.
"""
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}
HARI_RIWAYAT = 160


def ambil(url, coba=4):
    for i in range(coba):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == coba - 1:
                print(f"GAGAL {url}: {e}")
            time.sleep(1.5 * (i + 1))
    return None


def angka(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def main():
    t = ambil("https://indodax.com/api/ticker_all")
    if not t or "tickers" not in t:
        raise SystemExit("Tidak bisa mengambil ticker_all dari Indodax.")
    tickers = t["tickers"]
    inc = (ambil("https://indodax.com/api/price_increments") or {}).get("increments", {})

    pasangan = [k for k, v in tickers.items()
                if k.endswith("_idr") and angka(v.get("last")) > 0 and angka(v.get("vol_idr")) > 0]
    sekarang = int(time.time())
    dari = sekarang - HARI_RIWAYAT * 86400

    def riwayat(k):
        sym = k.replace("_", "").upper()
        d = ambil(f"https://indodax.com/tradingview/history_v2?symbol={sym}&tf=1D&from={dari}&to={sekarang}")
        if not isinstance(d, list):
            return k, None
        baris = []
        for b in d:
            c = angka(b.get("Close"))
            if c <= 0:
                continue
            baris.append([int(angka(b.get("Time"))), angka(b.get("Open")), angka(b.get("High")),
                          angka(b.get("Low")), c, angka(b.get("Volume"))])
        time.sleep(0.2)
        return k, baris

    with ThreadPoolExecutor(max_workers=6) as ex:
        hasil = list(ex.map(riwayat, pasangan))

    keluaran = {
        "updated": sekarang,
        "increments": inc,
        "tickers": {k: {"last": angka(tickers[k].get("last")), "vol_idr": angka(tickers[k].get("vol_idr"))} for k in pasangan},
        "candles": {k: r for k, r in hasil if r},
    }
    os.makedirs("data", exist_ok=True)
    with open("data/indodax.json", "w", encoding="utf-8") as f:
        json.dump(keluaran, f, separators=(",", ":"))
    print(f"Pasangan aktif: {len(pasangan)} | riwayat terbaca: {len(keluaran['candles'])}")


if __name__ == "__main__":
    main()
