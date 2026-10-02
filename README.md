# LMS Wakaf Salman — Backend

Backend Flask untuk authentication, profil/foto profil, dan pengelolaan akun LMS Wakaf Salman. Folder ini disiapkan sebagai root repository backend terpisah. Frontend React/Vite tetap berada pada repository frontend.

## Isi repository

```text
backend/                   # Setelah clone, ini adalah root repository
├── .gitignore
├── .env.example
├── README.md
├── requirements.txt
├── schema.sql
├── app.py
├── config.py
├── extensions.py
├── models/
│   ├── __init__.py
│   ├── user.py
│   └── user_profile.py
├── routes/
│   ├── __init__.py
│   ├── auth.py
│   ├── users.py
│   ├── user_validation.py
│   └── profile_photos.py
└── tests/
    └── test_users_api.py
```

`.env`, virtual environment, cache Python, serta `instance/profile_photos/` tidak dibagikan. Foto baru disimpan di folder instance saat aplikasi menerima upload.

## Status implementasi

- Tersedia: register/login JWT, role `admin`/`user`, status `aktif`/`nonaktif`, baca/edit profil, upload foto, serta list/tambah/edit/status akun oleh admin.
- `schema.sql` memuat 13 tabel existing; model SQLAlchemy yang tersedia adalah `User` dan `UserProfile`. Keberadaan tabel bukan berarti API fiturnya sudah dibuat.
- Course, materi, enrollment/progress, test, discussion, activity, dan laporan belum memiliki implementasi backend.
- No. HP dibaca melalui `GET /api/auth/me` sebagai `user_profile.no_hp`. Kirim field teks `no_hp` (maksimal 30 karakter) melalui `PATCH /api/auth/me`, baik JSON maupun multipart. String kosong menghapus nomor; field yang tidak dikirim mempertahankan nomor. Baris profil dibuat saat nomor pertama disimpan, untuk User maupun Admin.
- `users.divisi` tetap ada sebagai kolom legacy, walaupun frontend tidak menggunakannya.
- Flask-Migrate sudah diinisialisasi, tetapi belum ada baseline/revisi migration. Jangan menjalankan `db.create_all()`, autogenerate migration, atau upgrade untuk setup clone ini.

## Lingkungan asal

- Windows / PowerShell.
- Python 3.13, sesuai virtual environment pengembangan yang diperiksa.
- MariaDB **10.4.32** pada port 3306, diakses menggunakan driver PyMySQL.
- Frontend pada `http://localhost:5173`; backend pada port 5000.

Schema diekspor dari MariaDB tersebut pada 2 Oktober 2026. Kompatibilitas import ke versi MySQL/MariaDB lain belum diuji. Gunakan database development terpisah; jangan import schema ke database berisi data yang ingin dipertahankan.

## Setup setelah clone

### 1. Clone dan install dependency

Ganti URL repository di bawah dengan URL sebenarnya:

```powershell
git clone https://github.com/USERNAME/lms-wakaf-salman-backend.git
cd lms-wakaf-salman-backend
py -3.13 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Aktivasi environment tidak wajib karena perintah memakai executable Python di `venv` secara langsung. Gunakan requirements yang disertakan; jangan mengambil folder `venv` dari komputer rekan.

### 2. Buat database development kosong

Jalankan MariaDB dan gunakan SQL client untuk membuat database baru di mesin masing-masing:

```sql
CREATE DATABASE lmswakafsalman_dev
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Pilih database **lmswakafsalman_dev** di SQL client, lalu jalankan isi `schema.sql` satu kali. Bila memakai CLI SQL client, pilih database tersebut lalu gunakan `SOURCE` dengan path absolut file schema.

Schema berisi `CREATE TABLE` saja, tanpa akun contoh, `INSERT`, `DROP`, `TRUNCATE`, atau kredensial. Urutannya sudah mengikuti dependency FK. Jika tabel sudah ada, hentikan proses dan periksa database yang dipilih; jangan menghapus tabel untuk memaksa import berhasil.

File ini adalah snapshot struktur existing, bukan migration dan bukan script pembaruan database lama.

### 3. Isi .env lokal

Isi `DB_USER` dan `DB_PASSWORD` sesuai akun database lokal yang dapat mengakses database baru. Pastikan `DB_NAME=lmswakafsalman_dev` serta host/port sesuai server masing-masing.

Buat JWT key lokal:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Salin hasilnya ke `JWT_SECRET_KEY` dalam `.env`. Jangan memakai key atau password dari komputer pengembang lain.

Konfigurasi existing membentuk URL database langsung dari variabel environment. Jika username/password mengandung karakter khusus URL seperti `@`, `/`, `:` atau `%`, gunakan nilai yang di-URL-encode untuk komponen tersebut; jangan mengubah password database hanya untuk menyalin contoh.

### 4. Jalankan backend

Dari root repository backend:

```powershell
.\venv\Scripts\python.exe app.py
```

Biarkan terminal tetap berjalan. Membuka frontend saja tidak mengaktifkan backend.

Pemeriksaan lokal:

- `http://localhost:5000/` → pesan backend berjalan.
- `http://localhost:5000/db-test` → koneksi database berhasil.

Jalankan frontend dari repository frontend dengan `npm run dev`. Gunakan `http://localhost:5173`, sesuai origin CORS existing. Jika Vite pindah ke port lain, kosongkan port 5173 atau koordinasikan perubahan konfigurasi; jangan menganggap backend menerima semua origin.

### 5. Buat akun uji sendiri

Registrasi melalui frontend atau `POST /api/auth/register` dengan body JSON:

```json
{
  "nama": "Developer Lokal",
  "email": "developer@example.test",
  "password": "GANTI_DENGAN_PASSWORD_LOKAL"
}
```

Registrasi publik selalu menghasilkan role `user`, status `aktif`, dan password hash. Tidak ada password atau admin bawaan dalam repository.

Untuk menguji admin pertama pada **database development milik sendiri**, setelah registrasi berhasil, jalankan perintah berikut di database yang sama. Sesuaikan email dengan akun uji yang benar:

```sql
UPDATE users
SET role = 'admin'
WHERE email = 'developer@example.test';
```

Login setelah perubahan role. Jangan mengisi kolom password menggunakan password plaintext. Setelah admin pertama tersedia, akun berikutnya dapat dibuat melalui Kelola User/API admin.

## API existing

| Method | URL | Akses |
|---|---|---|
| POST | `/api/auth/register` | Publik |
| POST | `/api/auth/login` | Publik |
| GET | `/api/auth/me` | Bearer token, akun aktif |
| PATCH | `/api/auth/me` | Bearer token, profil sendiri |
| GET | `/api/auth/admin-test` | Admin aktif |
| GET | `/api/auth/profile-photos/<filename>` | Publik, file foto |
| GET | `/api/users` | Admin aktif |
| POST | `/api/users` | Admin aktif |
| PATCH | `/api/users/<user_id>` | Admin aktif |

Login mengembalikan `{token, user, message}`. `GET /api/auth/me` mengembalikan object user langsung. Request terautentikasi memakai `Authorization: Bearer <token>`.

Edit profil mendukung JSON atau multipart dengan nama field upload `foto`. Foto maksimal 2 MB, JPG/PNG/WebP. File disimpan backend dan alamatnya disimpan pada `users.foto_profil`.

`/`, `/db-test`, dan `/user-test` adalah endpoint development. `/user-test` menampilkan satu identitas akun tanpa autentikasi; jangan mengekspos deployment development ini ke publik.

## Menjalankan tes

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tes existing menggunakan session database simulasi dan foto sementara. Tes ini tidak membuktikan integrasi transaksi/FK pada database MySQL/MariaDB nyata. Setup clone dan import schema perlu diuji pada database development kosong tersendiri.

## Mengunggah repository pertama kali — pemilik proyek

Bagian ini hanya dijalankan pemilik proyek setelah repository kosong dibuat di GitHub. Rekan yang melakukan clone tidak perlu menjalankan `git init`.

Jalankan dari folder backend, bukan folder `venv` atau repository frontend:

```powershell
git init
git branch -M main
git add .gitignore .env.example README.md schema.sql requirements.txt app.py config.py extensions.py models routes tests
git status
git diff --cached --name-only
git diff --cached
```

Periksa bahwa daftar tersebut tidak berisi `.env`, `venv/`, `__pycache__/`, upload foto, atau dump data pengguna. `.gitignore` tidak menghapus file rahasia yang sudah terlanjur dilacak; pemeriksaan staged files tetap diperlukan.

Setelah hasil review benar, ganti URL berikut dengan repository sebenarnya:

```powershell
git commit -m "Initial backend authentication and user management"
git remote add origin https://github.com/USERNAME/lms-wakaf-salman-backend.git
git push -u origin main
```

## Batas kerja tim

- Developer 1: identitas/profil, activity/reporting, dan integrasi file bersama.
- Developer 2: kategori/course/materi, enrollment, dan progress.
- Developer 3: test/penilaian/jawaban serta discussion.
- Satu owner mengintegrasikan perubahan `app.py`, `models/__init__.py`, `extensions.py`, `config.py`, dan dependency.
- Buat feature branch dari `main`; review melalui PR. Jangan bekerja langsung pada `main` bersama-sama.
- Jangan commit `.env`, akun nyata, foto pengguna, atau virtual environment.
- Perubahan schema berikutnya harus disepakati tim; jangan menjalankan migration otomatis terhadap database existing tanpa baseline yang telah diperiksa.
