# Deployment production Lentera

Docker hanya menjalankan API Gunicorn. MariaDB/MySQL disediakan di luar Docker,
baik terpasang di host yang sama maupun server database terpisah. Nginx di host
menangani HTTPS. Foto memakai named volume; API dipublikasikan ke
**127.0.0.1:8000**. Compose tidak membuat, menjalankan, atau menyimpan database.

## 1. Konfigurasi

Clone release yang akan dipakai. Jalankan semua command dari root repository.
Pastikan DNS `api.example.com` menuju server, firewall membuka 80/443, dan
sertifikat TLS domain sudah tersedia. Ganti domain contoh di konfigurasi.

```sh
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Gunakan hasil generator untuk `JWT_SECRET_KEY`. Isi `DB_PASSWORD` dengan
password akun pada server database Anda. `.env.example` adalah template yang
sama untuk development dan production; nilai awalnya untuk development lokal.
Edit `.env` untuk server production:

- `APP_ENV=production`: mengaktifkan validasi secret/HTTPS dan menonaktifkan debug
  serta route diagnostik. Compose membaca nilai ini dari `.env`, sama seperti API lokal.
- `DB_HOST`: hostname/IP server database eksternal. Jika database terpasang di
  host Docker, gunakan `host.docker.internal`; mapping `host-gateway` sudah
  disertakan untuk Linux. **Jangan gunakan `localhost`/`127.0.0.1`** untuk DB
  host karena alamat tersebut mengarah ke container API sendiri.
- `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: sesuaikan database yang sudah
  disediakan. Gunakan akun aplikasi, bukan `root`.
- `CORS_ORIGINS=https://domain-frontend-anda` (pisahkan beberapa origin dengan
  koma, tanpa path/trailing slash). Wildcard/HTTP ditolak pada mode production.
- `APP_IMAGE=lentera-backend:<commit-atau-release>`: simpan image release lama
  untuk rollback. Tag jangan dipakai ulang untuk release berbeda.
- `PROXY_HOPS=1` hanya untuk konfigurasi Nginx satu proxy di bawah. Tanpa proxy,
  gunakan `0`; jangan membuka port Gunicorn ke publik.
- `WEB_CONCURRENCY=2`, `GUNICORN_THREADS=4` sebagai nilai awal; sesuaikan kapasitas
  CPU/RAM dan batas koneksi database melalui pengujian beban.

Nilai password database menggunakan karakter asli, **bukan URL-encoded**.
SQLAlchemy melakukan encoding. Pada development, `DB_PASSWORD=` boleh kosong
jika akun database memang tidak memiliki password. Production tetap menolak
password kosong melalui validasi aplikasi. Jika nilai `.env` mengandung `$`,
spasi, atau `#`, gunakan single quote agar parser Compose membacanya literal.
Jangan commit/upload file ini. Jangan menyalin output `docker compose config`
tanpa `--quiet` karena dapat memuat secret.

Sediakan database dan akun melalui DBA/SQL client sebelum migrasi. Untuk database
baru, buat database kosong ber-charset `utf8mb4`. Akun migrasi harus memiliki
izin DDL pada database tujuan; akun runtime dapat dibatasi ke izin yang diperlukan
aplikasi. Jika berbeda akun, jalankan command migrasi dengan kredensial migrasi.
Database harus menerima koneksi dari jaringan container: sesuaikan bind address,
firewall, dan grant akun ke sumber koneksi yang tepat. Database yang hanya listen
pada loopback host Linux tidak dapat diakses melalui `host-gateway`; gunakan
interface privat yang dapat dijangkau Docker. Jangan membuka akses DB ke internet.
Untuk DB remote, gunakan jaringan privat/tunnel TLS sesuai infrastruktur.

```sh
docker compose --env-file .env config --quiet
make build
```

Gunakan helper `make` atau command Docker langsung pada bagian berikut. Pada
PowerShell tanpa Make, command `docker compose` yang sama tetap dapat dipakai.

## 2. Migrasi: pilih sesuai kondisi database

Riwayat Alembic tersimpan di `alembic_version`:

| Revisi | Isi |
|---|---|
| `0001_baseline` | Snapshot immutable 13 tabel dari `schema.sql` |
| `0002_assessment` | Perubahan additive dari `001_test_discussion.sql` |

Migrasi memakai advisory lock per database sehingga dua proses migrasi tidak
berjalan bersamaan. **DDL MariaDB tidak transactional**: jika gagal di tengah,
jangan menganggap rollback otomatis mengembalikan struktur sebelumnya.

### A. Database baru, kosong

Jangan import `schema.sql` secara manual. Jalankan:

```sh
make migrate
make migration-status
```

Command langsung yang setara:

```sh
docker compose --env-file .env run --rm --no-deps api flask --app app db upgrade
docker compose --env-file .env run --rm --no-deps api flask --app app db current
```

`db upgrade` membuat baseline dan menerapkan revisi assessment. Menjalankan
ulang pada database yang sudah `head` tidak mengubah schema lagi.

### B. Database lama yang baru memakai `schema.sql`

Hentikan writer/API, buat dan uji backup terlebih dahulu (bagian backup).
Bandingkan struktur **seluruh 13 tabel** dengan `schema.sql`: kolom, tipe,
nullability, default, PK, unique/index, FK, dan aturan ON UPDATE/DELETE.
Gunakan `SHOW CREATE TABLE` atau dump schema dari SQL client. Pastikan belum ada
kolom tambahan assessment pada `penilaian`/`discussion`.

Setelah struktur terbukti cocok:

```sh
docker compose --env-file .env stop api
docker compose --env-file .env run --rm --no-deps api flask --app app db stamp 0001_baseline
make migrate
make migration-status
```

`stamp` **hanya mencatat versi; tidak memverifikasi atau mengubah schema**.
Jangan stamp database kosong, schema berbeda, atau migrasi yang baru diterapkan
sebagian. Upgrade tanpa stamp akan menolak database berisi tabel.

### C. Database lama sudah menjalankan `001_test_discussion.sql`

Setelah backup dan pemeriksaan baseline, periksa juga seluruh perubahan SQL
tersebut: tiga kolom baru di masing-masing tabel, default `status_attempt`
`in_progress`, backfill record lama sebagai `completed`, context materi,
index `idx_discussion_context`, dan constraint `ck_discussion_context`.
Jika semuanya sudah sesuai:

```sh
docker compose --env-file .env run --rm --no-deps api flask --app app db stamp 0002_assessment
make migration-status
```

Jangan menjalankan SQL assessment atau revision kedua kembali. Jika hanya
sebagian perubahan ada, pulihkan backup pra-migrasi pada database terpisah dan
ulang migrasi di sana; investigasi DDL yang gagal sebelum mengganti database
aplikasi. Jangan menutupi kegagalan dengan `stamp head`.

Snapshot SQL dalam revision tidak boleh diedit setelah dipakai. Untuk perubahan
berikutnya, buat revision baru dengan `flask --app app db revision -m "..."`,
tulis operasi secara eksplisit, review SQL, dan uji terhadap salinan database.
Jangan menggunakan `db.create_all()` atau mengandalkan autogenerate: beberapa
mapping ORM sengaja tidak memuat seluruh constraint/kolom legacy.

## 3. Jalankan API dan buat admin

```sh
make up
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
docker compose --env-file .env run --rm --no-deps api flask --app app create-admin
```

Command admin meminta nama/email/password interaktif; password minimal 12
karakter disimpan sebagai hash. Email existing ditolak, bukan dinaikkan role
secara diam-diam. Jangan memasukkan password melalui argumen shell.

`/health/live` memeriksa proses; `/health/ready` memeriksa koneksi database dan
revisi terbaru. Kegagalan readiness menghasilkan 503 tanpa detail koneksi.
`/db-test` dan `/user-test` selalu dinonaktifkan di production, begitu juga debug.
Healthcheck Docker tidak otomatis memperbaiki container yang masih berjalan
namun unhealthy; gunakan monitoring dan alert untuk status ini.

## 4. HTTPS melalui Nginx host

`deploy/nginx.conf` berisi template proxy HTTPS, batas request 3 MB, dan rate
limit login/register. API tetap memvalidasi foto maksimal 2 MB. Sesuaikan
`server_name`, lokasi sertifikat, dan port upstream bila `API_PORT` diubah.

Sertifikat harus dibuat melalui penyedia ACME/operasional Anda terlebih dahulu;
repository tidak membuat akun ACME atau sertifikat. Setelah tersedia:

```sh
sudo cp deploy/nginx.conf /etc/nginx/conf.d/lentera.conf
sudo nginx -t
sudo systemctl reload nginx
curl --fail https://api.example.com/health/ready
```

Periksa login dari frontend pada origin yang diizinkan, upload foto, dan akses
foto setelah container direstart. Nginx harus menimpa `X-Forwarded-*` dari client,
seperti template. Hindari memasang proxy/CDN tambahan tanpa meninjau kembali
jumlah trusted hops dan kebijakan alamat IP/rate limit.

## 5. Update release

Ada jendela maintenance singkat. Backup diambil sesudah API berhenti agar foto
dan database konsisten. Hentikan juga writer di luar Compose bila ada.

```sh
# Checkout release baru, lalu ubah APP_IMAGE ke tag release baru.
make build
# Jangan hapus image release sebelumnya.
docker compose --env-file .env stop api
DB_BACKUP_CONFIG=/etc/lentera-backup.cnf DB_BACKUP_NAME=lentera make backup
make migrate
make up
make migration-status
curl --fail http://127.0.0.1:8000/health/ready
```

`make deploy` merangkum build → stop API → migrate database eksternal → start API.
Gunakan sesudah backup terverifikasi; command berhenti jika migrasi gagal dan
API tetap berhenti. Migrasi tidak dijalankan otomatis oleh setiap worker.

## 6. Backup, restore, rollback

Backup database menggunakan client **di host**, bukan container database.
Pasang `mariadb-dump` (atau `mysqldump` dengan `DB_DUMP_BIN=mysqldump`) yang
kompatibel dengan server. Siapkan `/etc/lentera-backup.cnf`, dapat dibaca user
operator saja (`chmod 600`), dengan format client berikut:

```ini
[client]
host=alamat-database-dari-host
port=3306
user=akun_backup
password=password_akun_backup
```

Alamat ini dilihat dari host: gunakan `127.0.0.1` jika DB terpasang pada host yang
sama, atau hostname/IP DB remote. Akun backup harus mempunyai izin membaca data
serta metadata/trigger yang di-dump. Untuk layanan managed, snapshot/backup
penyedia juga dapat digunakan; foto tetap perlu dicadangkan terpisah.

```sh
# Untuk snapshot konsisten: stop api dan writer lainnya sebelum command ini.
DB_BACKUP_CONFIG=/etc/lentera-backup.cnf DB_BACKUP_NAME=lentera make backup
```

Backup disimpan pada `backups/database-<UTC>.sql` dan
`backups/profile-photos-<UTC>.tar.gz`, dengan permission privat. `.partial`
menandakan backup belum berhasil. Backup mencakup `alembic_version`; simpan tag
image dan konfigurasi release yang cocok dalam penyimpanan secret terpisah.
Jadwalkan backup, salin terenkripsi ke lokasi lain, atur retensi, dan uji restore.
Jangan menganggap volume Docker sebagai backup.

Restore terlebih dahulu ke **database eksternal baru yang kosong**. Provision
melalui DBA, lalu isi `/etc/lentera-restore.cnf` dengan koneksi tujuan restore
(format client seperti di atas). Siapkan `.env.restore` untuk API yang mengarah
ke database tersebut, port API berbeda, dan image release yang cocok. Gunakan
project Compose baru agar volume foto terpisah.

```sh
mariadb --defaults-extra-file=/etc/lentera-restore.cnf lentera_restore \
  < backups/database-YYYYMMDDTHHMMSSZ.sql
docker compose -p lentera-restore --env-file .env.restore run --rm --no-deps -T api \
  tar -xzf - -C /app/instance/profile_photos < backups/profile-photos-YYYYMMDDTHHMMSSZ.tar.gz
docker compose -p lentera-restore --env-file .env.restore up -d --wait api
```

Untuk MySQL, gunakan client `mysql` yang sesuai menggantikan `mariadb`.

Verifikasi data, login, foto, dan readiness sebelum mengalihkan traffic.
Restore database baru dan foto yang sesuai bersamaan. Jika hanya rollback image,
pastikan image lama kompatibel dengan schema sekarang. `db downgrade` sengaja
menolak penghapusan kolom/tabel; rollback schema menggunakan backup dan release
yang cocok. Jangan menjalankan `docker compose down -v` pada production karena
akan menghapus volume foto. Database eksternal tidak dikelola Compose;
`make down` mempertahankan volume foto.

## 7. Menjalankan tanpa Docker

Gunakan Python 3.13+, MariaDB, dan environment production yang sama. Untuk DB
external, atur host/port/user sesuai server dan provisioning database melalui DBA.
Contoh shell Linux, setelah environment diisi melalui service manager:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-production.txt
.venv/bin/flask --app app db upgrade  # hanya untuk database kosong / sudah dikelola Alembic
.venv/bin/gunicorn --config gunicorn.conf.py --bind 127.0.0.1:8000 'app:create_app()'
```

Adopsi database lama tetap mengikuti bagian 2 sebelum upgrade. Jalankan Gunicorn
melalui service manager agar restart setelah reboot. Contoh `deploy/lentera.service`
menggunakan `/opt/lentera`, user sistem `lentera`, dan environment file
`/etc/lentera.env` (format systemd, bukan shell yang di-source). Isi
`PROFILE_PHOTO_DIR=/var/lib/lentera/profile_photos`, `DB_HOST` sesungguhnya,
`APP_ENV=production`, dan konfigurasi lain. Untuk database jarak jauh, sediakan
jaringan privat/tunnel TLS sesuai infrastruktur.

```sh
# Provision user service terlebih dahulu; repository dan .venv berada di /opt/lentera.
sudo useradd --system --home /opt/lentera --shell /usr/sbin/nologin lentera
# /etc/lentera.env harus sudah diisi dan hanya dapat dibaca root (chmod 600).
sudo cp deploy/lentera.service /etc/systemd/system/lentera.service
sudo systemctl daemon-reload
sudo systemctl enable --now lentera
sudo journalctl -u lentera -f
```

Jangan menjalankan `python app.py` atau `flask run` sebagai server production.

## 8. Pemeriksaan dan referensi

```sh
make test PYTHON=.venv/bin/python
make logs
docker compose --env-file .env ps
```

Tes MariaDB destruktif hanya untuk database disposable dengan nama berakhiran
`_test`, bukan database aplikasi. Provision database eksternal disposable, gunakan project Compose terpisah dan
`RUN_MARIADB_INTEGRATION=1`; lihat `tests/integration/test_migrations.py`.

- [Flask: production deployment](https://flask.palletsprojects.com/en/stable/deploying/)
- [Flask-Migrate: upgrade dan stamp](https://flask-migrate.readthedocs.io/en/latest/)
- [Docker Compose: startup dan healthcheck](https://docs.docker.com/compose/how-tos/startup-order/)
