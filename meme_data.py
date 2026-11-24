"""
Data MEME KOIN Solana untuk bot Asisten Trading (diambil dari server GitHub supaya tidak ditolak
DexScreener/GeckoTerminal seperti dari server Google):
- kandidat koin ramai: DexScreener (boost & profil) + GeckoTerminal (trending, pool ramai, pool baru)
- data pasar tiap koin dari DexScreener (harga, likuiditas, MC, volume, transaksi, perubahan harga)
Disimpan ke data/meme.json lalu diunggah sebagai artifact "meme-data".
Tanpa library tambahan: hanya Python standar.
"""
import json
import os
import time
import urllib.request

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}
ABAIKAN = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}
GT = "https://api.geckoterminal.com/api/v2/networks/solana/"


def ambil(url, coba=3):
    for i in range(coba):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == coba - 1:
                print(f"GAGAL {url}: {e}")
            time.sleep(2 + i * 3)
    return None


def main():
    kand = {}

    def tambah(mint, tanda):
        if not mint or mint in ABAIKAN:
            return
        kand.setdefault(mint, {})[tanda] = 1

    for url, tanda in [
        ("https://api.dexscreener.com/token-boosts/top/v1", "boost"),
        ("https://api.dexscreener.com/token-boosts/latest/v1", "boost"),
        ("https://api.dexscreener.com/token-profiles/latest/v1", "profil"),
    ]:
        for x in ambil(url) or []:
            if isinstance(x, dict) and x.get("chainId") == "solana":
                tambah(x.get("tokenAddress"), tanda)

    for jalur, tanda in [
        ("trending_pools?page=1", "trending"), ("trending_pools?page=2", "trending"), ("trending_pools?page=3", "trending"),
        ("pools?page=1&sort=h24_tx_count_desc", "ramai"), ("pools?page=1&sort=h24_volume_usd_desc", "ramai"),
        ("pools?page=2&sort=h24_tx_count_desc", "ramai"), ("pools?page=2&sort=h24_volume_usd_desc", "ramai"),
        ("new_pools?page=1", "baru"), ("new_pools?page=2", "baru"),
    ]:
        j = ambil(GT + jalur) or {}
        for p in j.get("data") or []:
            bid = (((p.get("relationships") or {}).get("base_token") or {}).get("data") or {}).get("id") or ""
            tambah(bid.replace("solana_", "", 1), tanda)
        time.sleep(2.2)   # GeckoTerminal gratis: ±30 permintaan/menit

    mints = list(kand.keys())[:300]
    pairs = []
    for i in range(0, len(mints), 30):
        arr = ambil("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(mints[i:i + 30])) or []
        for p in arr if isinstance(arr, list) else []:
            pairs.append({k: p.get(k) for k in ("baseToken", "priceUsd", "liquidity", "marketCap", "fdv", "pairCreatedAt",
                                                 "volume", "txns", "priceChange", "dexId", "pairAddress")})
        time.sleep(0.3)

    os.makedirs("data", exist_ok=True)
    with open("data/meme.json", "w") as f:
        json.dump({"waktu": int(time.time()), "kandidat": kand, "pairs": pairs}, f)
    print(f"Kandidat: {len(kand)} | pair DexScreener: {len(pairs)}")


if __name__ == "__main__":
    main()
