# Menjalankan Arkadanta (Windows + Ubuntu WSL)

## Setelah pembaruan integritas data v3 (sekali)

1. Hentikan backend lama dengan `Ctrl+C`, lalu jalankan kembali sesuai bagian A.3. Refresh dashboard.
2. Di NiFi, hentikan sementara **PutHDFS**, ubah **Conflict Resolution Strategy** menjadi **ignore**, lalu Start kembali. Nama berkas event bersifat unik dan tetap saat retry; ignore membuat replay event yang sama aman.
3. **GetFile Input Directory** tetap `.../data/research/nifi_outbox`, dan **Recurse Subdirectories = true**. **UpdateAttribute hdfs.dir** tetap `/user/arkadanta/data/clean/crypto/${path}`. Event baru memiliki awalan direktori `v3/`, sehingga tujuannya otomatis `/user/arkadanta/data/clean/crypto/v3/symbol=.../`.
4. Jalankan **Data Ingestion → Backfill Histori**, maksimal 365 hari. Ini juga menerbitkan ulang candle lokal lama yang belum berversi ke antrean v3. Dataset/arsip sebelumnya tetap disimpan.
5. Tunggu data masuk HDFS, lalu jalankan **Historical HDFS Batch → Clean**, atau latih melalui **Model Lab** untuk jalur CSV. Model baru berada di `data/research/models/gmm_hgb_v3/`; model lama perlu dilatih ulang.
6. Periksa rentang histori, jam candle sumber, jam periode target, serta panel **Status integrasi** pada dashboard. Status port NiFi dan direktori HDFS bukan konfirmasi bahwa setiap candle sudah terkirim.

Jika startup gagal saat memulihkan jurnal, perbaiki izin/ruang disk pada `data/research/drop_zone` dan `nifi_outbox`, lalu restart. Jangan menghapus `.pending`: berkas di sana adalah perubahan data yang menunggu pemulihan.

Audit lengkap tersimpan di `data/research/audit_logs.jsonl`; `audit_logs.json` hanya snapshot kompatibilitas 50 catatan terbaru. Training/analisis memakai 365 hari terakhir, sementara arsip yang lebih tua tetap ada. Upload dengan NaN/Inf, OHLCV kosong, timestamp di luar grid 5m, atau candle belum selesai ditolak dan dihitung dalam laporan kualitas.

Untuk mencegah penumpukan berkas kecil selama penggunaan rutin, terapkan [penggabungan berkas NiFi](arkadanta/nifi/README.md). Jalur langsung GetFile → PutHDFS tetap tersedia untuk demo singkat; penggabungan memberi jeda HDFS sampai satu jam dan tidak menunda harga live dashboard.

Dashboard React jalan di **Windows**. Backend Python, HDFS, NiFi, dan PySpark jalan di **Ubuntu WSL**.

> **Tentang "database":** Arkadanta tidak memakai server database (tidak ada MySQL/Postgres yang perlu dinyalakan).
> Datanya disimpan sebagai berkas: CSV di `arkadanta/data/research/` dan salinan besarnya di **HDFS**. Jadi yang perlu dinyalakan hanya HDFS, NiFi, backend, dan dashboard.

## Peta singkat

| # | Layanan | Dijalankan di | Alamat | Wajib? |
|---|---|---|---|---|
| 1 | HDFS (penyimpanan besar) | Ubuntu | http://localhost:9870 | Untuk Tab 4 / demo Big Data |
| 2 | NiFi (pengirim data ke HDFS) | Ubuntu | https://localhost:8443/nifi/ | Untuk Tab 4 / demo Big Data |
| 3 | Backend FastAPI | Ubuntu | http://localhost:8000/docs | **Ya** |
| 4 | Dashboard React | PowerShell | http://localhost:5173 | **Ya** |

Dashboard dan model biasa (Tab 1–3) jalan **tanpa** HDFS/NiFi. Nyalakan 1–2 hanya kalau ingin memakai Tab 4 atau mendemokan alur Big Data.

Lokasi proyek: Windows `E:\GIT\Project-Akhir-BigData`, dari WSL `/mnt/e/GIT/Project-Akhir-BigData`.

---

## A. Setiap kali ingin menjalankan (urutan)

Buka Ubuntu dari PowerShell dengan `wsl -d Ubuntu-24.04`. Biarkan tiap terminal terbuka selama dipakai.

### 1. HDFS (terminal Ubuntu 1)

```bash
/home/anam/hadoop/bin/hdfs --daemon start namenode
/home/anam/hadoop/bin/hdfs --daemon start datanode
/home/anam/hadoop/bin/hdfs --daemon start secondarynamenode
jps
```

`jps` harus menampilkan `NameNode`, `DataNode`, dan `SecondaryNameNode`. Cara ini tidak butuh SSH. Jangan pakai `start-dfs.sh`, karena skrip itu gagal bila SSH belum aktif (`port 22: Connection refused`).

### 2. NiFi (terminal Ubuntu 1, lanjutan)

```bash
bash /opt/nifi/bin/nifi.sh start
```

Tunggu 1–2 menit, lalu cek:

```bash
bash /opt/nifi/bin/nifi.sh status      # harus: Status: UP
```

Buka https://localhost:8443/nifi/, pilih **Advanced → Continue** pada peringatan sertifikat, lalu login. Pastikan 3 processor (GetFile, UpdateAttribute, PutHDFS) berstatus ▶. Pesan `JAVA_HOME not set` boleh diabaikan.

### 3. Backend (terminal Ubuntu 2)

```bash
cd /mnt/e/GIT/Project-Akhir-BigData/arkadanta
source ~/venvs/arkadanta/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Berhasil bila muncul `Application startup complete`. Jalankan **satu** backend saja. Jangan memakai `run-all.bat`, `run-all.ps1`, atau `start.bat` untuk susunan Windows + WSL ini.

### 4. Dashboard (PowerShell Windows)

```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta\frontend
npm run dev
```

Buka http://localhost:5173. Panel harga di atas harus berubah menjadi **LIVE**.

---

## B. Pertama kali saja (persiapan)

Lewati yang sudah pernah dikerjakan.

**Python + PySpark di Ubuntu**

```bash
mkdir -p ~/venvs && python3 -m venv ~/venvs/arkadanta
source ~/venvs/arkadanta/bin/activate
cd /mnt/e/GIT/Project-Akhir-BigData/arkadanta
python -m pip install -r requirements.txt -r requirements-spark.txt
java -version        # Java 21
```

**Frontend di Windows**

```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta\frontend
npm install
```

**NiFi: akses dari browser Windows.** Di `/opt/nifi/conf/nifi.properties` set:

```text
nifi.web.https.host=0.0.0.0
nifi.web.proxy.host=localhost:8443,127.0.0.1:8443
```

**NiFi: login.** Lupa username/password? Reset (NiFi harus mati):

```bash
bash /opt/nifi/bin/nifi.sh stop
bash /opt/nifi/bin/nifi.sh set-single-user-credentials admin 'PasswordMinimal12Karakter'
bash /opt/nifi/bin/nifi.sh start
```

**NiFi: pasang PutHDFS** (sekali):

```bash
cd /opt/nifi/extensions
for a in nifi-hadoop-libraries-nar nifi-hadoop-nar; do
  wget -q "https://repo1.maven.org/maven2/org/apache/nifi/$a/2.12.0/$a-2.12.0.nar"
done
/home/anam/hadoop/bin/hdfs dfs -mkdir -p /user/arkadanta/data/clean/crypto /arkadanta/raw
```

Refresh browser NiFi (`Ctrl+F5`) agar PutHDFS muncul di daftar processor.

### Flow NiFi (dibuat sekali)

Setiap baris baru yang disimpan backend otomatis ditulis ke
`arkadanta/data/research/nifi_outbox/v3/symbol=…/year=…/month=…/`. NiFi tinggal memindahkannya ke HDFS:

```text
GetFile ──success──▶ UpdateAttribute ──success──▶ PutHDFS
                                                    ├─ success: terminate
                                                    └─ failure: kembali ke PutHDFS
```

| Processor | Property | Isi (tanpa spasi di depan/belakang) |
|---|---|---|
| **GetFile** | Input Directory | `/mnt/e/GIT/Project-Akhir-BigData/arkadanta/data/research/nifi_outbox` |
| | File Filter | `[^.].*\.csv` |
| | Recurse Subdirectories | `true` |
| | Keep Source File | `false` |
| **UpdateAttribute** | tambah property baru (tombol **+**) `hdfs.dir` | `/user/arkadanta/data/clean/crypto/${path}` |
| **PutHDFS** | Hadoop Configuration Resources | `/home/anam/hadoop/etc/hadoop/core-site.xml,/home/anam/hadoop/etc/hadoop/hdfs-site.xml` |
| | Directory | `${hdfs.dir}` |
| | Conflict Resolution Strategy | `ignore` |

Lalu klik kanan area kosong kanvas → **Start**. Bukti berhasil:

```bash
/home/anam/hadoop/bin/hdfs dfs -ls -R /user/arkadanta/data/clean/crypto | grep csv | head
```

Folder `nifi_outbox` seharusnya kosong setelah NiFi memprosesnya.

---

## C. Mengisi data dan melatih model (urutan di dashboard)

Model **tidak** dilatih otomatis. Prediksi akan menjawab `409 Conflict` sampai model dilatih.

1. **Tab Data Ingestion → Backfill Histori.** Pilih aset, isi **Backfill (hari)** = `365`, klik tombol. Sekitar 1–2 menit per aset. (**Manual Sync Now** hanya mengambil candle terbaru; cukup untuk uji cepat.)
2. **Tab Model Lab & Shield → Train & Evaluate Models.** Pilih aset + timeframe (mis. `BTCUSDT` `1h`). Perlu minimal 31 candle hasil agregasi. Model tersimpan per pasangan aset + timeframe, jadi latih ulang bila mengganti salah satunya.
3. **Tab Market Analytics:** lihat harga, anomali, korelasi lintas aset. Boleh dibuka sebelum model dilatih.
4. **Tab Historical HDFS Batch** (butuh HDFS + NiFi menyala): pilih **Sumber HDFS = Clean**, lalu **Baca HDFS & latih model**. Spark membaca data dari HDFS, lalu model yang dihasilkan langsung dipakai prediksi live.

Tabel kebutuhan data:

| Timeframe | Data minimal |
|---|---|
| `5m` | ±3 jam |
| `15m` | ±8 jam |
| `1h` | ±1,5 hari |
| `4h` | ±6 hari |
| `1d` | ±1 bulan |

Untuk Tab 4, tunggu NiFi selesai memindahkan data setelah backfill (cek jumlah CSV di HDFS bertambah).

**Lokasi data:**

```text
arkadanta/data/research/
├── drop_zone/        CSV bersih per aset (dipakai Tab 1–3)
├── nifi_outbox/      antrean untuk NiFi → HDFS
├── models/gmm_hgb_v3/  model hasil training
├── audit_logs.jsonl  riwayat ingestion lengkap
└── audit_logs.json   snapshot 50 catatan terbaru
```

---

## D. Mematikan

Urutan terbalik: `Ctrl+C` di dashboard dan backend, lalu

```bash
bash /opt/nifi/bin/nifi.sh stop
/home/anam/hadoop/bin/hdfs --daemon stop secondarynamenode
/home/anam/hadoop/bin/hdfs --daemon stop datanode
/home/anam/hadoop/bin/hdfs --daemon stop namenode
```

Setiap WSL di-restart (mis. setelah laptop mati), bagian **A** perlu diulang dari awal.

---

## E. Masalah umum

| Gejala | Penyebab dan perbaikan |
|---|---|
| `start-dfs.sh`: `ssh ... port 22: Connection refused` | Pakai perintah `hdfs --daemon start …` di bagian A.1. |
| Harga "MENUNGGU STREAM / timed out during opening handshake" | ISP memblokir `*.binance.com`. Kode sudah memakai mirror `data-stream.binance.vision`. Restart backend. |
| `409 Conflict` pada `/api/ml/predict` atau `/api/models/metrics` | Model untuk aset + timeframe itu belum dilatih. Lakukan C.2. |
| `Data penelitian … belum tersedia` | Belum ada data. Lakukan C.1. |
| `Candle … lengkap terakhir selesai …; data setelahnya hilang` | Backend/laptop sempat mati. Biasanya terisi otomatis saat panel harga tersambung (LIVE); kalau tidak, klik **Manual Sync** atau **Backfill Histori**. |
| Training: data terlalu sedikit | Lihat tabel kebutuhan data di C. Backfill atau pilih timeframe lebih kecil. |
| Tab 4: `No module named 'pyspark'` | Backend jalan di venv WSL: `python -m pip install -r requirements-spark.txt` di venv itu, lalu restart backend. |
| Tab 4: `Hanya N baris valid …` | Data di HDFS belum cukup atau NiFi belum memindahkan semuanya. Cek C.4, lalu pilih sumber **Clean**. |
| Tab 4: Sumber **Raw** gagal | Isi `/arkadanta/raw/symbol=BTCUSDT/` dengan data BTC, atau gunakan sumber **Clean**. Raw wajib terpisah per simbol. |
| NiFi: `Key Password length less than required [12]` | `nifi.sensitive.props.key` di `nifi.properties` kurang dari 12 karakter. Ganti ke string ≥ 12 karakter (NiFi belum pernah punya flow). |
| NiFi: browser `ERR_CONNECTION_CLOSED`/tidak bisa dibuka dari Windows | Set `nifi.web.https.host=0.0.0.0` (bagian B). NiFi yang di-start dari sesi `wsl.exe` non-interaktif ikut mati; start dari terminal Ubuntu Anda. |
| NiFi berjalan tetapi HDFS kosong | Periksa spasi di awal property PutHDFS, property `hdfs.dir` di UpdateAttribute, dan bulletin merah di PutHDFS. |
| `Address already in use` port 8000 | Ada backend lama. `Ctrl+C` di terminal asalnya. |
| Spark gagal start di Windows | `JAVA_HOME` salah. Periksa `java -version` dan folder tujuan `JAVA_HOME`. |
| `ModuleNotFoundError` di backend | Aktifkan venv Linux, lalu `python -m pip install -r requirements.txt`. |

---

## F. Urutan demo (singkat)

1. Tunjukkan HDFS (:9870) dan NiFi (flow ▶) menyala.
2. **Backfill/Manual Sync**, lalu tunjukkan CSV muncul di HDFS (`hdfs dfs -ls -R …`) dan Data Provenance di NiFi.
3. **Market Analytics:** harga, volatilitas, anomali, korelasi.
4. **Model Lab:** latih GMM + HistGradientBoosting, tunjukkan metrik dan prediksi T+1.
5. **Tab 4:** Spark membaca data dari HDFS dan menghasilkan model.
6. Jelaskan batas: HistGradientBoosting dilatih di driver lokal (bukan Spark MLlib); keluaran hanya untuk analitik akademik.

Detail kode: [arkadanta/README.md](arkadanta/README.md) dan [arkadanta/CONTRACTS.md](arkadanta/CONTRACTS.md).
