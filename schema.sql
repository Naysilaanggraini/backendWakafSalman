-- LMS Wakaf Salman: schema only, no user data or credentials.
-- Snapshot of the existing local schema; not a migration.
-- Import once into a NEW, EMPTY development database selected by your SQL client.
-- No DROP, TRUNCATE, INSERT, or database creation is included.

CREATE TABLE `kategori` (
  `id_kategori` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `nama_kategori` varchar(100) NOT NULL,
  `thumbnail` varchar(255) DEFAULT NULL,
  `status` enum('aktif','nonaktif') NOT NULL DEFAULT 'aktif',
  `tanggal_dibuat` timestamp NOT NULL DEFAULT current_timestamp(),
  `tanggal_diperbarui` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_kategori`),
  UNIQUE KEY `uq_kategori_nama` (`nama_kategori`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `users` (
  `id_user` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `nama` varchar(150) NOT NULL,
  `email` varchar(150) NOT NULL,
  `password` varchar(255) NOT NULL,
  `divisi` varchar(100) DEFAULT NULL,
  `jabatan` varchar(100) DEFAULT NULL,
  `role` enum('admin','user') NOT NULL DEFAULT 'user',
  `status` enum('aktif','nonaktif') NOT NULL DEFAULT 'aktif',
  `foto_profil` varchar(500) DEFAULT NULL,
  `tanggal_dibuat` timestamp NOT NULL DEFAULT current_timestamp(),
  `terakhir_login` datetime DEFAULT NULL,
  PRIMARY KEY (`id_user`),
  UNIQUE KEY `uq_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `course` (
  `id_course` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `judul_course` varchar(150) NOT NULL,
  `deskripsi` text DEFAULT NULL,
  `id_kategori` int(10) unsigned NOT NULL,
  `key_point` text DEFAULT NULL,
  `credit` varchar(150) DEFAULT NULL,
  `thumbnail` varchar(500) DEFAULT NULL,
  `passing_grade` tinyint(3) unsigned NOT NULL DEFAULT 70,
  `maksimal_attempt` smallint(5) unsigned NOT NULL DEFAULT 3,
  `masa_tunggu_test_hari` smallint(5) unsigned NOT NULL DEFAULT 7,
  `status` enum('aktif','nonaktif') NOT NULL DEFAULT 'aktif',
  `tanggal_dibuat` timestamp NOT NULL DEFAULT current_timestamp(),
  `tanggal_diperbarui` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_course`),
  KEY `idx_course_kategori` (`id_kategori`),
  CONSTRAINT `fk_course_kategori` FOREIGN KEY (`id_kategori`) REFERENCES `kategori` (`id_kategori`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `user_profile` (
  `id_profile` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `id_user` int(10) unsigned NOT NULL,
  `no_hp` varchar(30) DEFAULT NULL,
  `tanggal_diperbarui` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_profile`),
  UNIQUE KEY `uq_user_profile` (`id_user`),
  CONSTRAINT `fk_user_profile_user` FOREIGN KEY (`id_user`) REFERENCES `users` (`id_user`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `discussion` (
  `id_discussion` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `id_user` int(10) unsigned NOT NULL,
  `id_course` int(10) unsigned NOT NULL,
  `id_materi` int(10) unsigned DEFAULT NULL,
  `id_parent` int(10) unsigned DEFAULT NULL,
  `isi_komentar` text NOT NULL,
  `status` enum('tampil','disembunyikan') NOT NULL DEFAULT 'tampil',
  `waktu` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_discussion`),
  KEY `idx_discussion_user` (`id_user`),
  KEY `idx_discussion_course` (`id_course`),
  KEY `idx_discussion_materi` (`id_materi`),
  KEY `idx_discussion_parent` (`id_parent`),
  CONSTRAINT `fk_discussion_course` FOREIGN KEY (`id_course`) REFERENCES `course` (`id_course`) ON UPDATE CASCADE,
  CONSTRAINT `fk_discussion_parent` FOREIGN KEY (`id_parent`) REFERENCES `discussion` (`id_discussion`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_discussion_user` FOREIGN KEY (`id_user`) REFERENCES `users` (`id_user`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `materi` (
  `id_materi` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `id_course` int(10) unsigned NOT NULL,
  `judul_materi` varchar(150) NOT NULL,
  `jenis_file` enum('pdf','youtube','drive') NOT NULL,
  `tautan_file` varchar(500) NOT NULL,
  `durasi` int(10) unsigned DEFAULT NULL,
  `urutan` smallint(5) unsigned NOT NULL DEFAULT 1,
  `status` enum('aktif','nonaktif') NOT NULL DEFAULT 'aktif',
  `tanggal_dibuat` timestamp NOT NULL DEFAULT current_timestamp(),
  `tanggal_diperbarui` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_materi`),
  UNIQUE KEY `uq_materi_urutan` (`id_course`,`urutan`),
  KEY `idx_materi_course` (`id_course`),
  CONSTRAINT `fk_materi_course` FOREIGN KEY (`id_course`) REFERENCES `course` (`id_course`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `penilaian` (
  `id_penilaian` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `id_user` int(10) unsigned NOT NULL,
  `id_course` int(10) unsigned NOT NULL,
  `nilai` decimal(5,2) NOT NULL DEFAULT 0.00,
  `test_attempt` smallint(5) unsigned NOT NULL DEFAULT 1,
  `status` enum('lulus','tidak_lulus') NOT NULL,
  `waktu_mulai` datetime NOT NULL,
  `waktu_selesai` datetime DEFAULT NULL,
  `durasi` int(10) unsigned DEFAULT NULL,
  PRIMARY KEY (`id_penilaian`),
  UNIQUE KEY `uq_penilaian_attempt` (`id_user`,`id_course`,`test_attempt`),
  KEY `idx_penilaian_user` (`id_user`),
  KEY `idx_penilaian_course` (`id_course`),
  CONSTRAINT `fk_penilaian_course` FOREIGN KEY (`id_course`) REFERENCES `course` (`id_course`) ON UPDATE CASCADE,
  CONSTRAINT `fk_penilaian_user` FOREIGN KEY (`id_user`) REFERENCES `users` (`id_user`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `soal` (
  `id_soal` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `id_course` int(10) unsigned NOT NULL,
  `pertanyaan` text NOT NULL,
  `urutan` smallint(5) unsigned NOT NULL DEFAULT 1,
  `status` enum('aktif','nonaktif') NOT NULL DEFAULT 'aktif',
  `tanggal_dibuat` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_soal`),
  UNIQUE KEY `uq_soal_urutan` (`id_course`,`urutan`),
  KEY `idx_soal_course` (`id_course`),
  CONSTRAINT `fk_soal_course` FOREIGN KEY (`id_course`) REFERENCES `course` (`id_course`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `user_course` (
  `id_user_course` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `id_user` int(10) unsigned NOT NULL,
  `id_course` int(10) unsigned NOT NULL,
  `tanggal_mulai` datetime NOT NULL DEFAULT current_timestamp(),
  `tanggal_selesai` datetime DEFAULT NULL,
  `status` enum('belum_mulai','berlangsung','selesai') NOT NULL DEFAULT 'belum_mulai',
  `status_test` enum('aktif','nonaktif','lulus') NOT NULL DEFAULT 'aktif',
  `test_dapat_diakses_lagi` datetime DEFAULT NULL,
  PRIMARY KEY (`id_user_course`),
  UNIQUE KEY `uq_user_course` (`id_user`,`id_course`),
  KEY `idx_user_course_user` (`id_user`),
  KEY `idx_user_course_course` (`id_course`),
  KEY `idx_user_course_status` (`status`),
  KEY `idx_user_course_status_test` (`status_test`),
  KEY `idx_user_course_test_access` (`test_dapat_diakses_lagi`),
  CONSTRAINT `fk_user_course_course` FOREIGN KEY (`id_course`) REFERENCES `course` (`id_course`) ON UPDATE CASCADE,
  CONSTRAINT `fk_user_course_user` FOREIGN KEY (`id_user`) REFERENCES `users` (`id_user`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `activity` (
  `id_activity` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `id_user` int(10) unsigned NOT NULL,
  `id_course` int(10) unsigned DEFAULT NULL,
  `id_materi` int(10) unsigned DEFAULT NULL,
  `id_penilaian` int(10) unsigned DEFAULT NULL,
  `jenis_aktivitas` enum('login','buka_course','buka_materi','selesai_materi','selesai_course','mulai_test','selesai_test') NOT NULL,
  `durasi` int(10) unsigned DEFAULT NULL,
  `waktu_dimulai` datetime NOT NULL DEFAULT current_timestamp(),
  `waktu_selesai` datetime DEFAULT NULL,
  PRIMARY KEY (`id_activity`),
  KEY `idx_activity_user` (`id_user`),
  KEY `idx_activity_course` (`id_course`),
  KEY `idx_activity_materi` (`id_materi`),
  KEY `idx_activity_penilaian` (`id_penilaian`),
  KEY `idx_activity_waktu` (`waktu_dimulai`),
  KEY `idx_activity_jenis` (`jenis_aktivitas`),
  CONSTRAINT `fk_activity_course` FOREIGN KEY (`id_course`) REFERENCES `course` (`id_course`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_activity_materi` FOREIGN KEY (`id_materi`) REFERENCES `materi` (`id_materi`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_activity_penilaian` FOREIGN KEY (`id_penilaian`) REFERENCES `penilaian` (`id_penilaian`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_activity_user` FOREIGN KEY (`id_user`) REFERENCES `users` (`id_user`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `pilihan_soal` (
  `id_pilihan` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `id_soal` int(10) unsigned NOT NULL,
  `teks_pilihan` varchar(255) NOT NULL,
  `urutan` smallint(5) unsigned NOT NULL DEFAULT 1,
  `is_benar` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id_pilihan`),
  UNIQUE KEY `uq_pilihan_urutan` (`id_soal`,`urutan`),
  KEY `idx_pilihan_soal` (`id_soal`),
  CONSTRAINT `fk_pilihan_soal` FOREIGN KEY (`id_soal`) REFERENCES `soal` (`id_soal`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `user_materi` (
  `id_user_materi` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `id_user` int(10) unsigned NOT NULL,
  `id_materi` int(10) unsigned NOT NULL,
  `status` enum('belum_mulai','berlangsung','selesai') NOT NULL DEFAULT 'belum_mulai',
  `waktu_mulai` datetime DEFAULT NULL,
  `waktu_selesai` datetime DEFAULT NULL,
  `durasi` int(10) unsigned DEFAULT NULL,
  PRIMARY KEY (`id_user_materi`),
  UNIQUE KEY `uq_user_materi` (`id_user`,`id_materi`),
  KEY `idx_user_materi_user` (`id_user`),
  KEY `idx_user_materi_materi` (`id_materi`),
  KEY `idx_user_materi_status` (`status`),
  CONSTRAINT `fk_user_materi_materi` FOREIGN KEY (`id_materi`) REFERENCES `materi` (`id_materi`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_user_materi_user` FOREIGN KEY (`id_user`) REFERENCES `users` (`id_user`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `jawaban` (
  `id_jawaban` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `id_penilaian` int(10) unsigned NOT NULL,
  `id_user` int(10) unsigned NOT NULL,
  `id_soal` int(10) unsigned NOT NULL,
  `id_pilihan` int(10) unsigned NOT NULL,
  `benar` tinyint(1) NOT NULL DEFAULT 0,
  `waktu_jawab` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_jawaban`),
  UNIQUE KEY `uq_jawaban_soal` (`id_penilaian`,`id_soal`),
  KEY `fk_jawaban_pilihan` (`id_pilihan`),
  KEY `idx_jawaban_user` (`id_user`),
  KEY `idx_jawaban_soal` (`id_soal`),
  CONSTRAINT `fk_jawaban_penilaian` FOREIGN KEY (`id_penilaian`) REFERENCES `penilaian` (`id_penilaian`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_jawaban_pilihan` FOREIGN KEY (`id_pilihan`) REFERENCES `pilihan_soal` (`id_pilihan`) ON UPDATE CASCADE,
  CONSTRAINT `fk_jawaban_soal` FOREIGN KEY (`id_soal`) REFERENCES `soal` (`id_soal`) ON UPDATE CASCADE,
  CONSTRAINT `fk_jawaban_user` FOREIGN KEY (`id_user`) REFERENCES `users` (`id_user`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
