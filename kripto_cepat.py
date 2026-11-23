"""
Data kripto CEPAT untuk bot Asisten Trading:
- candle 1 jam (±7 hari) dan candle 15 menit (±30 jam)
- hanya koin Rupiah Indodax yang likuid (volume 24 jam >= Rp1 miliar), tanpa stablecoin
Disimpan ke data/cepat.json lalu diunggah sebagai artifact "kripto-cepat".
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
MIN_VOL_IDR = 1_000_000_000
STABIL = {"usdt", "usdc", "busd", "dai", "tusd", "fdusd", "usdd", "idrt", "bidr", "pyusd", "usde", "eurc", "xsgd"}


def ambil(url, coba=3):
    for i in range(coba):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == coba - 1:
                print(f"GAGAL {url}: {e}")
            time.sleep(1.0 * (i + 1))
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
                if k.endswith("_idr") and k.replace("_idr", "") not in STABIL
                and angka(v.get("last")) > 0 and angka(v.get("vol_idr")) >= MIN_VOL_IDR]
    sekarang = int(time.time())

    def riwayat(arg):
        k, tf, detik = arg
        sym = k.replace("_", "").upper()
        d = ambil(f"https://indodax.com/tradingview/history_v2?symbol={sym}&tf={tf}&from={sekarang - detik}&to={sekarang}")
        if not isinstance(d, list):
            return k, tf, None
        baris = []
        for b in d:
            c = angka(b.get("Close"))
            if c > 0:
                baris.append([int(angka(b.get("Time"))), angka(b.get("Open")), angka(b.get("High")),
                              angka(b.get("Low")), c, angka(b.get("Volume"))])
        time.sleep(0.15)
        return k, tf, baris

    tugas = [(k, "60", 7 * 86400) for k in pasangan] + [(k, "15", 30 * 3600) for k in pasangan]
    with ThreadPoolExecutor(max_workers=8) as ex:
        hasil = list(ex.map(riwayat, tugas))

    keluaran = {
        "updated": sekarang,
        "increments": inc,
        "tickers": {k: {"last": angka(tickers[k].get("last")), "vol_idr": angka(tickers[k].get("vol_idr"))} for k in pasangan},
        "h1": {k: r for k, tf, r in hasil if tf == "60" and r},
        "m15": {k: r for k, tf, r in hasil if tf == "15" and r},
    }
    os.makedirs("data", exist_ok=True)
    with open("data/cepat.json", "w", encoding="utf-8") as f:
        json.dump(keluaran, f, separators=(",", ":"))
    print(f"Koin likuid: {len(pasangan)} | candle 1 jam: {len(keluaran['h1'])} | candle 15 menit: {len(keluaran['m15'])}")


if __name__ == "__main__":
    main()
