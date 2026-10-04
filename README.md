# 🌦️ Weather Bot — Asia → Gresik & Lamongan

Bot real-time harian: mengambil data cuaca live dari 13 kota lintas Asia,
**mengorelasikan pola regional** (ITCZ, trough Indochina, konveksi Pasifik,
front Australia, hulu Kali Lamong), lalu mengirim ringkasan ke Telegram.

## Alur data
1. **Lapis 1 — Asia:** Bangkok, Singapura, Kota Kinabalu, Manila (Pasifik/cyclone seed), Darwin, Perth (front selatan).
2. **Lapis 2 — Indonesia:** Medan, Jakarta, Surabaya, Kediri, Mojokerto (**hulu Kali Lamong**).
3. **Fokus:** Gresik & Lamongan — prakiraan 3 hari + status banjir kiriman.

Logika korelasi ada di fungsi `correlate()` di `weather_bot.py` — silakan sesuaikan ambang hujan/daftar kota.

## Setup di GitHub
1. Push repo ini (folder `.github/` ikut ter-push).
2. Settings → Secrets and variables → Actions → tambah:
   - `TELEGRAM_TOKEN` — token dari @BotFather
   - `TELEGRAM_CHAT` — chat_id kamu (bisa dari @userinfobot)
3. Selesai. Actions jalan otomatis **05:00 & 17:00 WIB** tiap hari (cron `0 22 * * *` dan `0 10 * * *` UTC), plus bisa manual lewat tab **Actions → Run workflow**.

## Jalankan lokal
```bash
TELEGRAM_TOKEN=xxx TELEGRAM_CHAT=yyy python3 weather_bot.py
```
Tanpa env var, laporan hanya dicetak ke terminal.

## Catatan
- Data: wttr.in (jaringan observasi global) + deteksi peringatan BMKG (best-effort).
- Jika wttr.in gagal, bot lanjut dengan kota lain; kalau Gresik/Lamongan gagal, ia menandai error agar GitHub Actions terlihat.

## Website dashboard
File `index.html` adalah dashboard web live — data diambil langsung dari wttr.in di browser, tanpa server.
Aktifkan di Settings → Pages → Deploy from branch → branch `main` → folder `/(root)`.
