#!/usr/bin/env python3
"""
Bot Prakiraan Cuaca Harian — Asia -> Indonesia -> Jatim -> GRESIK & LAMONGAN (fokus utama)
Real-time tiap hari, korelasi lintas negara, detail titik kecamatan,
deteksi peringatan BMKG, banjir kiriman Kali Lamong, dan sintesis akhir.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import quote

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT", "")

# ---- stasiun korelasi lintas negara: (lapis, peran) -------------------------
ASIA_STATIONS = {
    "Bangkok":       ("Asia", "trough Indochina / monsun barat"),
    "Singapura":     ("Asia", "ITCZ / konveksi ekuator"),
    "Kota Kinabalu": ("Asia", "Borneo — sumber uap air timur"),
    "Manila":        ("Asia", "Pasifik barat — seed siklon"),
    "Darwin":        ("Selatan", "monsun selatan"),
    "Perth":         ("Selatan", "front Australia — uap dari selatan"),
    "Medan":         ("Indonesia", "SIT / gelombang tropis barat"),
    "Jakarta":       ("Indonesia", "barat Jawa"),
    "Surabaya":      ("Jatim", "patokan Jatim"),
    "Kediri":        ("Jatim", "hulu jauh Kali Lamong"),
    "Mojokerto":     ("Jatim", "hulu Kali Lamong"),
}

# ---- titik detail Gresik & Lamongan (fokus utama) ---------------------------
FOKUS_POINTS = [
    # (nama, kabupaten, catatan risiko)
    ("Menganti", "Gresik", "riwayat banjir Kali Lamong (Bringkang, Pranti, Beton)"),
    ("Benjeng", "Gresik", "riwayat banjir luapan Kali Lamong, 10 desa pernah terdampak"),
    ("Driyorejo", "Gresik", "riwayat banjir TMA Kali Surabaya"),
    ("Balongpanggang", "Gresik", "riwayat banjir kiriman hulu, sawah terendam"),
    ("Lamongan Kota", "Lamongan", "pusat kabupaten, dekat muara Kali Lamong"),
    ("Babat", "Lamongan", "hulu, kiriman dari Mojokerto"),
    ("Sugio", "Lamongan", "pernah masuk peringatan dini BMKG"),
    ("Deket", "Lamongan", "koridor Gresik-Lamongan"),
]

RAIN_CODES = {"176","263","266","293","296","299","302","305","308","311","314",
              "350","353","356","359","362","365","368","371","374","377","384","386","389"}
HEAVY_CODES = {"299","302","305","308","311","314","356","359","365","384","386","389"}

def _f(x, default=0.0):
    """float() yang tidak pernah crash untuk string kosong/None."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def fetch(loc: str) -> dict | None:
    """Data live wttr.in: kondisi sekarang + prakiraan 3 hari."""
    try:
        r = subprocess.run(
            ["curl", "--fail", "--silent", "--max-time", "25",
             f"https://wttr.in/{quote(loc)},Indonesia?format=j1"],
            capture_output=True, text=True, timeout=30)
        j = json.loads(r.stdout)
        cc = (j.get("current_condition") or [{}])[0]
        days = []
        for d in j.get("weather", [])[:3]:
            hourly = d.get("hourly") or []
            rain = sum(_f(h.get("precipMM")) for h in hourly)
            if hourly:
                mx = max(hourly, key=lambda h: _f(h.get("precipMM")))
                mid = hourly[min(6, len(hourly) - 1)]
            else:
                mx = {"time": "0", "precipMM": 0}
                mid = {"weatherCode": "113", "weatherDesc": [{"value": "N/A"}]}
            wd = (mid.get("weatherDesc") or [{"value": "N/A"}])[0]
            days.append({
                "date": d.get("date", "?"), "max": d.get("maxtempC", "?"), "min": d.get("mintempC", "?"),
                "rain_mm": round(rain, 1),
                "code": mid.get("weatherCode", "113"),
                "desc": wd.get("value", "N/A").strip(),
                "peak_hour": str(mx.get("time", "0")).zfill(4)[:2] + ":00",
                "peak_mm": _f(mx.get("precipMM")),
            })
        ccd = (cc.get("weatherDesc") or [{"value": "N/A"}])[0]
        return {
            "now": ccd.get("value", "N/A").strip(),
            "temp": cc.get("temp_C", "?"), "feels": cc.get("FeelsLikeC", "?"),
            "hum": cc.get("humidity", "?"), "wind": cc.get("windspeedKmph", "?"),
            "days": days,
        }
    except Exception as e:
        print(f"[warn] fetch {loc}: {e}", file=sys.stderr)
        return None


def is_rain(d) -> bool:
    return d["code"] in RAIN_CODES or d["rain_mm"] > 0.5

def is_heavy(d) -> bool:
    return d["code"] in HEAVY_CODES or d["rain_mm"] >= 10

# ------------------------------------------------ korelasi lintas negara
def correlate(data: dict) -> tuple[list[str], int]:
    """Skor korelasi 0-100 -> risiko hujan di Gresik/Lamongan dalam 48 jam."""
    notes, score = [], 0
    def rainy(k):
        v = data.get(k)
        return bool(v and v["days"] and is_rain(v["days"][0]))
    def heavy(k):
        v = data.get(k)
        return bool(v and v["days"] and is_heavy(v["days"][0]))

    # ITCZ ekuator
    eq = [k for k in ("Singapura", "Kota Kinabalu") if rainy(k)]
    if eq:
        score += 20
        notes.append(f"🌧️ ITCZ ekuator aktif ({', '.join(eq)}) — zona konveksi bergerak ke barat; uap timur bisa mencapai Jatim via Selat Madura.")
    else:
        notes.append("☀️ ITCZ ekuator lemah — sumber uap dari timur minim.")

    # Pasifik / seed siklon
    if rainy("Manila"):
        score += 15
        notes.append("🌀 Konveksi Pasifik barat aktif (Manila) — awasi pembentukan sistem tropis; pengaruh ke Jawa biasanya 3–7 hari lagi.")
    # Indochina
    if rainy("Bangkok"):
        score += 10
        notes.append("⛈️ Trough Indochina aktif (Bangkok) — monsun barat membawa lembap melintasi Sumatera.")
    # Selatan
    if rainy("Darwin") or rainy("Perth"):
        score += 15
        notes.append("🌊 Aktivitas selatan (Darwin/Perth) — front dari Australia bisa memicu hujan pesisir utara Jatim saat berbelok.")
    # Barat Indonesia
    if rainy("Medan") or rainy("Jakarta"):
        score += 10
        notes.append("🌫️ Pola barat aktif (Medan/Jakarta hujan) — gelombang tropis bergerak timur, pertimbangkan pengaruh ke Jawa dalam 1–2 hari.")

    # Jatim & hulu Kali Lamong
    hulu = [k for k in ("Mojokerto", "Kediri") if rainy(k)]
    hulu_heavy = [k for k in ("Mojokerto", "Kediri") if heavy(k)]
    if hulu_heavy:
        score += 25
        notes.append(f"🚨 HULU LAMONG HUJAN LEBAT ({', '.join(hulu_heavy)}) — risiko tinggi banjir kiriman ke Menganti/Benjeng/Driyorejo & Babat dalam 24–48 jam!")
    elif hulu:
        score += 15
        notes.append(f"⚠️ Hulu Kali Lamong hujan ({', '.join(hulu)}) — pantau TMA Kali Lamong, dampingan air sampai hilir dalam ~24 jam.")
    else:
        notes.append("✅ Hulu Kali Lamong kering — aman dari banjir kiriman untuk saat ini.")

    # kondisi aktual fokus area (bobot terbesar — data langsung di lokasi)
    fokus = [k for k in ("Gresik", "Lamongan") if rainy(k)]
    fokus_heavy = [k for k in ("Gresik", "Lamongan") if heavy(k)]
    if fokus_heavy:
        score += 25
        notes.append(f"🚨 FOKUS AREA hujan lebat ({', '.join(fokus_heavy)}) — prioritas utama, bukan sekadar korelasi regional.")
    elif fokus:
        score += 15
        notes.append(f"🌧️ Fokus area sedang hujan ({', '.join(fokus)}).")
    else:
        notes.append("☀️ Fokus area (Gresik & Lamongan) kering saat ini — skor regional tinggi tidak langsung berarti hujan di sini.")

    # Surabaya sebagai penanda lokal
    if rainy("Surabaya"):
        score += 5
        notes.append("🌥️ Surabaya hujan — penanda lokal pesisir Jatim lembap.")

    score = min(score, 100)
    # kalibrasi: tanpa hujan lebat nyata di fokus area, maksimal WASPADA
    if not fokus_heavy:
        score = min(score, 60)
    notes.append(f"📊 **Skor korelasi regional: {score}/100** — "
                 + ("risiko hujan tinggi di Gresik–Lamongan 48 jam ke depan" if score >= 50
                    else "risiko hujan sedang" if score >= 25
                    else "risiko hujan rendah, cuaca dominan kering/panas"))
    return notes, score

# ------------------------------------------------ deteksi peringatan BMKG (dalam)
def fetch_bmkg_alert() -> list[str]:
    """Deteksi peringatan dini BMKG multi-sumber (best effort, real-time)."""
    alerts = []
    # 1. RSS peringatan nasional
    try:
        r = subprocess.run(["curl","--fail","-sL","--max-time","20",
                            "https://www.bmkg.go.id/rss/provinsi20.xml"],
                           capture_output=True, text=True, timeout=25)
        body = r.stdout or ""
        if "peringatan" in body.lower():
            for m in re.finditer(r"<title>(.*?)</title>", body, re.S):
                t = m.group(1).strip()
                if any(w in t.lower() for w in ("jawa timur", "jatim", "surabaya", "gresik", "lamongan")):
                    alerts.append(f"🟠 BMKG RSS: {t}")
    except Exception:
        pass
    # 2. Halaman peringatan dini BMKG (HTML)
    try:
        r = subprocess.run(["curl","--fail","-sL","--max-time","20",
                            "https://www.bmkg.go.id/cuaca/peringatan-cuaca.bmkg"],
                           capture_output=True, text=True, timeout=25)
        body = re.sub(r"<[^>]+>", " ", r.stdout or "")
        if re.search(r"(jawa\s*timur|jatim)", body, re.I) and re.search(r"(peringatan|siaga|waspada)", body, re.I):
            m = re.search(r".{0,200}(jawa\s*timur|jatim).{0,300}", body, re.I)
            if m:
                alerts.append("🟠 BMKG halaman peringatan: ... " + " ".join(m.group(0).split())[:280])
    except Exception:
        pass
    # 3. Gempa terakhir (konteks regional)
    try:
        r = subprocess.run(["curl","--fail","-sL","--max-time","20",
                            "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"],
                           capture_output=True, text=True, timeout=25)
        j = json.loads(r.stdout)
        q = j["Infogempa"]["gempa"]
        if isinstance(q, list):
            q = q[0]
        alerts.append(f"🌍 Gempa terakhir: M{q['Magnitudo']} {q['Wilayah']} ({q['Jam']}, kedalaman {q['Kedalaman']})")
    except Exception:
        pass
    return alerts

# ------------------------------------------------------------------ telegram
def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("[warn] TELEGRAM_TOKEN/CHAT belum diset — output hanya stdout")
        return False
    import urllib.request, urllib.parse
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    text = text.replace("**", "*")  # mode Markdown klasik Telegram tidak mendukung **
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT, "text": text[:4000],
        "parse_mode": "Markdown", "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=payload), timeout=20) as resp:
            ok = json.loads(resp.read()).get("ok", False)
            print("[ok] terkirim ke Telegram" if ok else "[err] Telegram menolak")
            return ok
    except Exception as e:
        print(f"[err] Telegram: {e}", file=sys.stderr)
        return False

# ------------------------------------------------------------------- laporan
def build_report(data, notes, score, alerts):
    today_id = datetime.now().strftime("%d %b %Y")
    lines = [f"🌦️ *PRAKIRAAN CUACA REAL-TIME — FOKUS GRESIK & LAMONGAN*",
             f"📅 {today_id} • 🔗 korelasi {len(data)} titik live", ""]

    # Lapis Asia (ringkas)
    lines.append("🌏 *LAPIS ASIA (korelasi lintas negara)*")
    for k, (lvl, why) in ASIA_STATIONS.items():
        v = data.get(k)
        if v and v["days"]:
            ic = "🌧️" if is_rain(v["days"][0]) else "☀️"
            lines.append(f"  {ic} {k}: {v['days'][0]['desc']}, {v['days'][0]['min']}–{v['days'][0]['max']}°C — _{why}_")
    lines.append("")
    lines.append("🔗 *SINTESIS KORELASI →*")
    for n in notes:
        lines.append(f"  {n}")
    lines.append("")

    # FOKUS: titik kecamatan real-time
    lines.append("🎯 *FOKUS REAL-TIME — TITIK GRESIK & LAMONGAN*")
    for name, kab, risk in FOKUS_POINTS:
        v = data.get(name)
        if not v:
            lines.append(f"  • {name} ({kab}): data gagal")
            continue
        d = v["days"][0]
        ic = "🌧️" if is_rain(d) else ("🌦️" if d["rain_mm"] > 0 else "☀️")
        lines.append(f"  {ic} *{name}* ({kab}): {v['now']}, {v['temp']}°C (terasa {v['feels']}°), "
                     f"lembap {v['hum']}%, angin {v['wind']} km/j | 3 hari: {d['min']}–{d['max']}°C, "
                     f"hujan {d['rain_mm']}mm (puncak {d['peak_mm']}mm @{d['peak_hour']})")
        lines.append(f"      ↳ risiko lokal: {risk}")
    lines.append("")

    # tabel 3 hari gabungan
    lines.append("📅 *PRAKIRAAN 3 HARI GRESIK & LAMONGAN*")
    lines.append("| Tanggal | Gresik | Lamongan | Interpretasi korelasi |")
    lines.append("|---|---|---|---|")
    for i in range(3):
        g = data.get("Gresik", {}).get("days", [None]*3)[i] if data.get("Gresik") else None
        l = data.get("Lamongan", {}).get("days", [None]*3)[i] if data.get("Lamongan") else None
        gs = f"{g['desc']} {g['min']}–{g['max']}°C {g['rain_mm']}mm" if g else "—"
        ls = f"{l['desc']} {l['min']}–{l['max']}°C {l['rain_mm']}mm" if l else "—"
        interp = ("🌧️ hujan lebat — siaga" if (g and is_heavy(g)) or (l and is_heavy(l))
                  else "⛅ potensi hujan lokal" if (g and is_rain(g)) or (l and is_rain(l))
                  else "☀️ kering — aman")
        dt = g["date"] if g else (datetime.now()+timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(f"| {dt} | {gs} | {ls} | {interp} |")
    lines.append("")

    # peringatan BMKG & bencana
    lines.append("🛰️ *PERINGATAN & BENCANA (BMKG live)*")
    if alerts:
        for a in alerts:
            lines.append(f"  {a}")
    else:
        lines.append("  ✅ Tidak ada peringatan dini aktif terdeteksi untuk Jatim/Gresik/Lamongan.")

    # kesimpulan akhir
    lines.append("")
    verdict = "🟢 AMAN" if score < 25 else "🔴 SIAGA" if score >= 70 else "🟡 WASPADA"
    lines.append(f"🏁 *KESIMPULAN FOKUS: {verdict}* — skor korelasi {score}/100.")
    lines.append("_Sumber: wttr.in live + BMKG. Kiriman otomatis GitHub Actions 2×/hari._")
    return "\n".join(lines)

def main():
    print(f"[run] {datetime.now().isoformat()}")
    targets = list(ASIA_STATIONS.keys()) + ["Gresik", "Lamongan"] + [p[0] for p in FOKUS_POINTS]
    targets = list(dict.fromkeys(targets))  # dedupe
    data = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for loc, v in zip(targets, ex.map(fetch, targets)):
            if v:
                data[loc] = v
                print(f"  {loc}: OK")
            else:
                print(f"  {loc}: FAIL")
    if "Gresik" not in data or "Lamongan" not in data:
        print("[err] data fokus Gresik/Lamongan gagal — bot tetap kirim yang ada")
    notes, score = correlate(data)
    alerts = fetch_bmkg_alert()
    report = build_report(data, notes, score, alerts)
    print(report)
    send_telegram(report)

if __name__ == "__main__":
    main()
