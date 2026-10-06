# LMS Wakaf Salman — Backend

Backend Flask untuk authentication, profil/foto profil, pengelolaan akun, serta Test & Discussion LMS Wakaf Salman. Folder ini disiapkan sebagai root repository backend terpisah. Frontend React/Vite tetap berada pada repository frontend.

## Production, Docker, dan migrasi

Panduan lengkap: [docs/PRODUCTION.md](docs/PRODUCTION.md).
Tersedia Dockerfile non-root, Compose khusus API Gunicorn dengan volume foto persisten dan database eksternal,
Makefile, migrasi Alembic, template Nginx HTTPS, backup/restore, dan service systemd.

Untuk **database baru** setelah mengisi secret dan domain di `.env`:

```sh
cp .env.example .env
# Isi APP_ENV=production, koneksi DB eksternal, secret, dan origin HTTPS terlebih dahulu:
make build
make migrate
make up
```

Untuk database existing, ikuti prosedur adopsi/stamp di panduan sebelum migrasi.
Jangan mengimpor ulang schema atau menjalankan SQL assessment yang sudah diterapkan.

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
- Tersedia: kategori/course/materi, enrollment/progress, Test & Discussion, activity login, dan dashboard statistik Identity. Leaderboard masih menunggu kontrak data/ranking.
- Model course/materi/enrollment/progress dipakai bersama oleh Learning dan Assessment; `models/learning.py` menyediakan alias kompatibilitas serta model assessment/discussion.
- Audit dan kontrak Identity: [IDENTITY_INTEGRATION.md](IDENTITY_INTEGRATION.md).
- No. HP dibaca melalui `GET /api/auth/me` sebagai `user_profile.no_hp`. Kirim field teks `no_hp` (maksimal 30 karakter) melalui `PATCH /api/auth/me`, baik JSON maupun multipart. String kosong menghapus nomor; field yang tidak dikirim mempertahankan nomor. Baris profil dibuat saat nomor pertama disimpan, untuk User maupun Admin.
- `users.divisi` tetap ada sebagai kolom legacy, walaupun frontend tidak menggunakannya.
- Flask-Migrate memiliki baseline `0001_baseline` dan revisi `0002_assessment`. Database kosong memakai `flask --app app db upgrade`; database existing memerlukan prosedur adopsi di panduan production. Jangan menjalankan `db.create_all()` atau autogenerate terhadap database aplikasi.

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

Database harus kosong. Setelah mengisi `.env` pada langkah berikutnya, jalankan
migrasi melalui Flask. `schema.sql` disimpan sebagai referensi struktur legacy;
tidak perlu diimpor untuk setup baru.

### 3. Isi .env lokal

Isi `DB_USER` dan `DB_PASSWORD` sesuai akun database lokal yang dapat mengakses database baru. Pastikan `DB_NAME=lmswakafsalman_dev` serta host/port sesuai server masing-masing.

Buat JWT key lokal:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Salin hasilnya ke `JWT_SECRET_KEY` dalam `.env`. Jangan memakai key atau password dari komputer pengembang lain.

Masukkan username/password dengan karakter aslinya, termasuk `@`, `/`, `:`, dan
`%`; SQLAlchemy melakukan encoding URL secara otomatis.

Terapkan migrasi ke database development kosong yang baru dibuat:

```powershell
.\venv\Scripts\python.exe -m flask --app app db upgrade
```

### 4. Jalankan backend

Dari root repository backend:

```powershell
.\venv\Scripts\python.exe app.py
```

Biarkan terminal tetap berjalan. Membuka frontend saja tidak mengaktifkan backend.

Pemeriksaan lokal:

- `http://localhost:5000/` → pesan backend berjalan.
- `http://localhost:5000/health/ready` → database terhubung dan migrasi terbaru.

Jalankan frontend dari repository frontend dengan `npm run dev`. Gunakan `http://localhost:5173`, sesuai `CORS_ORIGINS` di `.env`. Jika port frontend berubah, sesuaikan origin tersebut.

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

## Dokumentasi API (OpenAPI)

Kontrak API tersedia di [openapi.yaml](openapi.yaml) (OpenAPI 3.1): 35 path dan
49 operasi, termasuk autentikasi JWT, request/response, upload foto, akses admin,
enrollment/progress, ujian, diskusi, reporting, dan healthcheck.

Import file ini ke Postman atau buka dengan Swagger Editor yang mendukung OpenAPI
3.1. Pilih server lokal/Docker atau sesuaikan hostname production. Login melalui
`POST /api/auth/login`, lalu gunakan token sebagai Bearer authentication.
Endpoint bertag `Development` hanya aktif jika konfigurasi mengizinkannya;
leaderboard didokumentasikan sebagai `501` sesuai implementasi saat ini.
File spesifikasi tidak otomatis menyediakan endpoint `/docs` atau Swagger UI.

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
| GET | `/api/activity` | Admin aktif; pagination dan filter |
| GET | `/api/dashboard` | Admin aktif; statistik Identity |
| GET | `/api/leaderboard` | Akun aktif; sementara 501 pending_dependencies |

Login mengembalikan `{token, user, message}`. `GET /api/auth/me` mengembalikan object user langsung. Request terautentikasi memakai `Authorization: Bearer <token>`.

Login sukses mencatat activity `login` dalam transaksi yang sama dengan terakhir_login.
Kegagalan transaksi mengembalikan 503 tanpa token. Event edit/register/admin belum
didukung enum activity existing, sehingga tidak dicatat sebagai event lain.
Admin POST/PATCH `/api/users` juga menerima field opsional `no_hp` dengan aturan
yang sama seperti profil sendiri; respons tetap memakai `user_profile.no_hp`.

Edit profil mendukung JSON atau multipart dengan nama field upload `foto`. Foto maksimal 2 MB, JPG/PNG/WebP. File disimpan backend dan alamatnya disimpan pada `users.foto_profil`.

`/health/live` dan `/health/ready` tersedia untuk monitoring. `/db-test` dan `/user-test` hanya tersedia jika `ENABLE_DEV_ROUTES=true` pada development; keduanya selalu dinonaktifkan di production.

## Menjalankan tes

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tes existing menggunakan session database simulasi dan foto sementara. Tes Identity/reporting tambahan menggunakan SQLite in-memory dengan transaksi ORM nyata. Tes ini tidak membuktikan locking/enum/FK pada database MySQL/MariaDB nyata. Setup clone dan import schema perlu diuji pada database development kosong tersendiri.

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


## Developer 3: Test & Discussion

### Analisis dan batas integrasi existing

Source of truth: `schema.sql`, `models/user.py`, `routes/auth.py`, `src/api/axiosInstance.js`, `src/store/{courseStore,userLearningStore,authStore}.js`, `src/data/userLearningData.js`, `src/pages/user/{CourseDetail,FinalTest}.jsx`, `src/components/user/{CourseDiscussion,CourseMaterial,CourseMaterialNavigation,CourseInformation}.jsx`, dan routing frontend existing. Backend menggunakan Flask + SQLAlchemy + Flask-Migrate + MySQL/MariaDB/PyMySQL. Authentication tetap JWT HS256 delapan jam dari login existing; response error tetap `{"message":"..."}`.

Sebelum perubahan, API frontend hanya memanggil auth/profil/users: base URL `http://localhost:5000/api`, token dari `localStorage.token`, header `Authorization: Bearer ...`. Tidak ada fetch/axios untuk course, soal, attempt, result, atau discussion. Course/materi/test admin berada di Zustand/localStorage; user learning di sessionStorage. FinalTest menghitung score dari answer key lokal; discussion materi memiliki reply/edit/delete lokal. Route test tetap `/user/my-course/:courseId/final-test`, `/questions`, `/result`. Materi dipilih melalui `progress.selectedMaterial`, bukan route material baru.

Database existing tidak mempunyai tabel `test`: `soal.id_course` adalah final test course. Karena itu **test_id = course_id** dalam kontrak ini, bukan FK/table baru. Backend memakai tabel `penilaian` sebagai attempt dan `jawaban` sebagai jawaban. Tidak ditambahkan API history; frontend membutuhkan jumlah attempt, attempt aktif, dan result terbaru dalam GET test.

### File dan model

File backend baru:

- `models/learning.py`: model assessment/discussion serta alias ke model lengkap `Course`, `Materi`, `UserCourse`, dan `UserMateri` dari Learning.
- `routes/learning_access.py`: validasi payload/context, akses enrollment, dan error konsisten.
- `routes/tests.py`: soal, attempt, jawaban, submit, score, result.
- `routes/discussions.py`: satu sistem discussion untuk tiga context, reply, edit/delete milik author.
- `migrations_sql/001_test_discussion.sql`: migration additive MySQL/MariaDB.
- `tests/test_learning_api.py`: integration test Flask + SQLAlchemy dengan fixture DB terisolasi.

File backend diubah: `app.py` (register dua blueprint), `models/__init__.py` (import model), `.gitignore` (mengizinkan satu migration SQL tanpa membuka akses dump SQL lainnya), `README.md` (dokumentasi). Auth, API admin/users, dan business logic admin tidak diubah.

Relasi:

- `course` ? `materi`, `soal` ? `pilihan_soal`.
- `users` + `course` ? `user_course` (enrollment/access).
- `users` + `materi` ? `user_materi` (status completion).
- `users` + `course` ? `penilaian` ? `jawaban` ? `soal`/`pilihan_soal`.
- `users` + `course` + optional `materi` ? `discussion`; `discussion.id_parent` menunjuk parent pada context yang sama.

Tidak ada tabel baru. `penilaian` ditambah `status_attempt`, private `question_snapshot`, dan snapshot `passing_grade`. `discussion` ditambah `context_type`, `tanggal_diperbarui`, `deleted_at`, index context, dan CHECK context/material. Kolom/status legacy tetap digunakan. Parent FK existing dipertahankan. FK material discussion divalidasi API; migration tidak menambah FK baru yang dapat menggagalkan data legacy.

### Authentication dan akses

Semua endpoint berikut menggunakan `token_required` existing. Actor diambil dari JWT ? `User.id_user`, bukan payload. Course wajib aktif dan memiliki `user_course` untuk actor. Materi wajib aktif dan milik course tersebut. Test discussion hanya memerlukan test tersedia dan akses course, **tanpa** syarat completion materi/attempt/hasil test. Memulai attempt membutuhkan seluruh materi aktif berstatus `selesai` pada `user_materi`, mengikuti flow frontend existing. Tidak ada auto-enrollment dari Test/Discussion.

`course.passing_grade` (default schema 70), `maksimal_attempt` (default 3), `masa_tunggu_test_hari` (default 7), serta `user_course.status_test`/`test_dapat_diakses_lagi` digunakan. Attempt aktif dapat dilanjutkan tanpa menambah attempt. Setelah lulus, `user_course.status_test=lulus`, `status=selesai`, dan `tanggal_selesai` disimpan. Setelah gagal, cooldown mengikuti konfigurasi course. Discussion tetap tersedia selama cooldown atau sebelum test dimulai.

### Kontrak Test

Semua URL di bawah sudah termasuk prefix `/api`. GET tidak membuat attempt.

| Method | Endpoint | Payload | Response sukses |
|---|---|---|---|
| GET | `/api/courses/:course_id/test` | tidak ada | metadata, questions, active_attempt, latest_result (200) |
| GET | `/api/courses/:course_id/questions/:question_id` | tidak ada | `{question: Question}` (200) |
| POST | `/api/courses/:course_id/test-attempts` | `{}` | `{attempt: Attempt, questions: Question[]}` (201 baru / 200 resume) |
| GET | `/api/test-attempts/:attempt_id` | tidak ada | `{attempt: Attempt}` (200) |
| POST | `/api/test-attempts/:attempt_id/answers` | `{answers: [{question_id, selected_option_id}]}` | `{attempt: Attempt}` (200) |
| POST | `/api/test-attempts/:attempt_id/submit` | `{}` untuk jawaban tersimpan, atau `{answers: [...]}` untuk submit-all | Result (200) |
| GET | `/api/test-attempts/:attempt_id/result` | tidak ada | Result (200) |

Question:

```json
{"question_id":1,"number":1,"pertanyaan":"Isi soal dari DB","options":[{"option_id":3,"text":"Isi pilihan dari DB"}]}
```

Contoh tersebut hanya menunjukkan shape; tidak ada soal/pilihan yang di-hardcode pada runtime. Question/detail/attempt tidak pernah mengirim `is_benar`, `is_correct`, `correct_answer`, atau private snapshot.

Attempt:

```json
{"attempt_id":123,"course_id":1,"test_id":1,"attempt_number":1,"status":"in_progress","started_at":"2026-10-05T07:00:00Z","completed_at":null,"answers":[{"question_id":1,"selected_option_id":3}]}
```

GET test:

```text
{
  course_id, test_id, passing_score, max_attempts, attempts_used,
  materials_completed, test_access_status, retry_at,
  questions: Question[], active_attempt: Attempt | null,
  latest_result: Result | null
}
```

Submit/result:

```json
{"attempt_id":123,"course_id":1,"test_id":1,"total_questions":10,"answered_questions":10,"correct_answers":8,"wrong_answers":2,"score":80.0,"passing_score":70,"passed":true,"completed_at":"2026-10-05T07:10:00Z"}
```

Scoring di backend: `correct / total * 100`; pertanyaan tidak dijawab dihitung salah, sehingga `wrong_answers = total_questions - correct_answers`. Score disimpan dua desimal; kelulusan membandingkan rasio sebelum pembulatan dengan passing grade. Soal, pilihan, kunci, dan threshold difreeze di DB saat start; perubahan konten tidak mengubah attempt berjalan. Jawaban upsert per attempt/soal, validasi seluruh bulk dilakukan sebelum mutasi. Submit dan grading berlangsung dalam satu transaksi. Enrollment lalu attempt dikunci dengan `SELECT ... FOR UPDATE`; unique constraint existing menjaga nomor attempt dan jawaban. Submit kedua ditolak 409, termasuk update jawaban setelah selesai.

Records penilaian lama dipertahankan sebagai completed. Karena legacy tidak menyimpan snapshot, result lama mengembalikan total/correct/wrong/answered/passing_score `null` jika tidak dapat dibuktikan; nilai dan status lulus existing tetap dipertahankan. Migration tidak menebak hasil historis.

### Kontrak Discussion

| Context | GET list / POST create | PATCH edit / DELETE komentar sendiri |
|---|---|---|
| Course | `/api/discussions/course/:course_id` | `/api/discussions/course/:course_id/:discussion_id` |
| Materi | `/api/discussions/material/:material_id` | `/api/discussions/material/:material_id/:discussion_id` |
| Test | `/api/discussions/test/:course_id` | `/api/discussions/test/:course_id/:discussion_id` |

Payload POST: `{"content":"Isi discussion","parent_id":null}`; `parent_id` optional untuk reply. PATCH: `{"content":"Isi yang diperbarui"}`. DELETE: `{}`. GET: tanpa body.

GET response `{"discussions":[Discussion]}` (200). POST response `{"discussion":Discussion}` (201). PATCH/DELETE response sama (200).

```json
{"discussion_id":1,"user_id":10,"user":{"id_user":10,"nama":"Nama dari User"},"context_type":"material","context_id":5,"parent_id":null,"content":"Isi discussion","created_at":"2026-10-05T07:00:00Z","updated_at":null,"deleted":false}
```

Satu tabel memakai `context_type`; `id_course` selalu disimpan, `id_materi` hanya untuk material. Context course/test dipisahkan walau sama-sama memakai course ID. Parent harus berada pada context dan course/material yang sama. Thread dikirim flat dengan `parent_id`, lalu frontend merender recursive replies. Soft delete mempertahankan parent sebagai placeholder kosong agar reply tidak hilang. Komentar `disembunyikan` dan seluruh subtree-nya tidak dikirim. Tidak ada API moderation/admin baru.

### Validasi dan error

- 401: token hilang, invalid, expired melalui auth existing.
- 403: akun nonaktif, tidak enrolled, course/materi nonaktif, attempt/comment bukan milik actor, belum menyelesaikan materi, batas attempt/lulus/cooldown.
- 404: course/materi/test/soal/attempt/parent discussion tidak ditemukan.
- 400: body bukan object JSON, field ekstra, ID bukan integer positif, jawaban duplicate, soal bukan bagian test, option bukan bagian soal, content bukan string/kosong/lebih dari 2000 karakter, context invalid.
- 409: attempt sudah selesai/result belum tersedia, konfigurasi soal/threshold tidak valid, konflik unique constraint.

Field `user_id`, `id_user`, `score`, `passed`, `correct_answers`, `wrong_answers`, dan answer key ditolak pada payload karena allowlist. Semua error fitur ini berbentuk `{"message":"..."}` dan transaksi di-rollback.

### Integrasi frontend dan dependency yang belum tersedia

Frontend baru: `src/api/learningApi.js` memakai axiosInstance/token existing; `src/hooks/useCourseTest.js` mengambil metadata, resume, autosave pilihan, submit-all, dan result backend. FinalTest menggunakan hook tersebut; score lokal/mock questions dihapus dari flow user. User learning store tetap mengurus pemilihan/completion materi lokal, sementara status test/result diisi dari API. Navigasi test tetap memakai route existing dan menunggu load sebelum redirect, sehingga refresh tidak membuat attempt baru.

`CourseDiscussion` sekarang reusable melalui `{contextType, contextId, title}`. CourseDetail memasangnya untuk course dan materi terpilih; FinalTest memasangnya pada detail/questions/result dan tidak lagi redirect hanya karena materi belum selesai. Existing markup/styles, reply, edit, delete dipertahankan. Komentar seed lokal tidak digunakan lagi. Admin, auth, catalog store dan API unrelated tidak diubah.

**Catatan integrasi:** API daftar course/materi dan enrollment/completion materi kini tersedia dari branch Learning. Integrasi frontend masih perlu disesuaikan. CourseDetail/MyCourse/catalog admin tetap menggunakan data lokal. Tombol Mark as complete masih menyimpan sessionStorage, belum menulis `user_materi`; course yang dibuka secara lokal belum otomatis menjadi `user_course`. Akibatnya ID demo/localStorage tidak selalu cocok dengan ID DB; backend akan menolak 403/404 secara benar dan test belum dapat dimulai hanya dengan completion lokal. Developer Course/Material/Enrollment perlu menghubungkan catalog dan progress ke DB. Tidak ditambahkan endpoint atau enrollment palsu untuk menutupi gap tersebut. Leaderboard existing juga masih data prototype dan tidak menjadi sumber score Test.

### Migration dan menjalankan

Gunakan migrasi Alembic sesuai [panduan migrasi](docs/PRODUCTION.md#2-migrasi-pilih-sesuai-kondisi-database).
SQL `migrations_sql/001_test_discussion.sql` tetap disimpan sebagai referensi
legacy; perubahan yang sama kini diterapkan oleh revisi `0002_assessment`.
Jangan menjalankan keduanya. Untuk database yang sudah menerima SQL manual,
verifikasi schema lalu adopsi revisi sesuai panduan.

```powershell
cd backend
.\venv\Scripts\python.exe app.py
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tidak ada seed production atau data hardcode runtime. Soal/pilihan, enrollment, dan completion harus tersedia di DB dari pekerjaan pemilik fitur terkait.

### Hasil verifikasi

- Integration test Test & Discussion menggunakan Flask test client + SQLAlchemy nyata + DB SQLite terisolasi, FK enforcement aktif; bukan mocked scoring/session. SQLite hanya dependency test standar, database aplikasi tetap MySQL/MariaDB.
- Skenario: soal/pilihan tanpa kunci, detail soal, start, answer/upsert, refresh/resume tanpa duplicate, submit-all/saved answers, score 80 lulus, 60 gagal, tepat 70 lulus, kosong/partial dihitung salah, result persisted, snapshot, cooldown, attempt limit, login JWT/expired/invalid/nonaktif, akses antar-user, manipulasi score, rollback bulk invalid, discussion course/material/test sebelum attempt, author/timestamp, reply context, edit/delete ownership, hidden threads, payload validation.
- 30 test lulus: 16 integration test learning dan 14 regression test users/auth existing.
- Frontend `npm run build` berhasil dan ESLint pada file yang disentuh bersih.
- Factory backend/import dan server HTTP nyata diuji untuk home serta penolakan unauthenticated pada Test/Discussion.
- MySQL lokal menolak koneksi dengan error 1045 (Access denied). Migration/live MySQL dan concurrency row locks belum diverifikasi terhadap engine tersebut. Tidak ada perubahan kredensial/database atau migration yang dijalankan pada DB lokal. E2E browser dengan catalog/enrollment/progress DB belum dapat dinyatakan selesai karena dependency di atas.
