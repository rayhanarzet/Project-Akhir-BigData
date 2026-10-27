# Panduan Menjalankan Arkadanta: Windows + Ubuntu WSL

## PERINTAH LANGSUNG: JALANKAN HDFS DAN NIFI

Buka terminal **Ubuntu WSL**, lalu jalankan perintah berikut satu per satu:

**Mulai HDFS:**

```bash
bash /home/anam/hadoop/sbin/start-dfs.sh
```

**Periksa proses HDFS:**

```bash
jps
```

Pastikan proses `NameNode` dan `DataNode` muncul.

**Mulai NiFi:**

```bash
bash /opt/nifi/bin/nifi.sh start
```

**Periksa status NiFi:**

```bash
bash /opt/nifi/bin/nifi.sh status
```

Setelah layanan siap, buka melalui browser Windows:

- **HDFS:** http://localhost:9870 (port HTTP standar; periksa bagian 4 jika berbeda).
- **NiFi:** https://localhost:8443/nifi/

Perintah di atas menyalakan layanan. Agar berkas masuk dari NiFi ke HDFS, flow pengiriman juga harus dikonfigurasi; lihat bagian 12.

**Untuk menghentikan layanan**, di Ubuntu WSL:

```bash
bash /opt/nifi/bin/nifi.sh stop
bash /home/anam/hadoop/sbin/stop-dfs.sh
```

---

Panduan ini untuk **satu laptop**: dashboard React berjalan di Windows, sedangkan backend Python, Hadoop HDFS, NiFi, dan PySpark dijalankan di Ubuntu WSL.

## Daftar isi

1. [Kenali terminal dan lokasi proyek](#1-kenali-terminal-dan-lokasi-proyek)
2. [Kondisi integrasi saat ini](#2-kondisi-integrasi-saat-ini)
3. [Persiapan pertama kali](#3-persiapan-pertama-kali)
4. [Menjalankan HDFS di WSL](#4-menjalankan-hdfs-di-wsl)
5. [Menjalankan NiFi di WSL](#5-menjalankan-nifi-di-wsl)
6. [Menjalankan backend di WSL](#6-menjalankan-backend-di-wsl)
7. [Menjalankan dashboard di Windows](#7-menjalankan-dashboard-di-windows)
8. [Mengambil dan memeriksa data nyata](#8-mengambil-dan-memeriksa-data-nyata)
9. [Melihat analisis](#9-melihat-analisis)
10. [Melatih dan memakai model ML](#10-melatih-dan-memakai-model-ml)
11. [Menjalankan PySpark, opsional](#11-menjalankan-pyspark-opsional)
12. [Membuktikan pengiriman NiFi ke HDFS, opsional](#12-membuktikan-pengiriman-nifi-ke-hdfs-opsional)
13. [Menghentikan layanan](#13-menghentikan-layanan)
14. [Mengatasi error](#14-mengatasi-error)
15. [Ringkasan untuk pemakaian berikutnya](#15-ringkasan-untuk-pemakaian-berikutnya)
16. [Urutan demonstrasi](#16-urutan-demonstrasi)

## 1. Kenali terminal dan lokasi proyek

**PowerShell Windows** memiliki prompt seperti:

```text
PS C:\Users\admin>
```

**Ubuntu WSL** memiliki prompt seperti:

```text
anam@DESKTOP-EVVMNA3:~$
```

Jangan ikut menyalin prompt tersebut. Salin hanya perintah di dalam blok kode.

| Komponen | Lokasi pada laptop ini |
|---|---|
| Proyek di Windows | `E:\GIT\Project-Akhir-BigData` |
| Proyek yang sama dari WSL | `/mnt/e/GIT/Project-Akhir-BigData` |
| Environment Python Linux | `/home/anam/venvs/arkadanta` |
| Distro WSL | `Ubuntu-24.04` |
| Script startup HDFS yang ditemukan | `/home/anam/hadoop/sbin/start-dfs.sh` |
| Script NiFi yang ditemukan | `/opt/nifi/bin/nifi.sh` |
| Konfigurasi Hadoop | `/home/anam/hadoop/etc/hadoop/` |
| Konfigurasi NiFi | `/opt/nifi/conf/nifi.properties` |

Path instalasi Hadoop/NiFi ini ditemukan pada WSL laptop Anda. Jika dipindah ke komputer lain, sesuaikan path-nya.

Gunakan **tiga terminal**:

- **Terminal A — Ubuntu WSL:** startup/status HDFS dan NiFi; boleh dipakai lagi untuk pemeriksaan.
- **Terminal B — Ubuntu WSL:** backend; biarkan tetap berjalan.
- **Terminal C — PowerShell Windows:** dashboard React; biarkan tetap berjalan.

Untuk membuka Ubuntu dari PowerShell:

```powershell
wsl -d Ubuntu-24.04
```

## 2. Kondisi integrasi saat ini

| Bagian | Kondisi pada kode proyek |
|---|---|
| Dashboard React Windows → backend WSL | Tersedia melalui API port 8000 |
| Harga live Binance → backend → dashboard React | Tersedia melalui WebSocket dan Server-Sent Events |
| Candle lima menit selesai → penyimpanan penelitian lokal | Tersedia |
| Analisis dan ML GMM/HistGradientBoosting | Tersedia; membutuhkan data yang cukup |
| Pemrosesan fitur dengan Spark | Jalur kode tersedia; Java/PySpark perlu terpasang dan berfungsi |
| Baris baru aplikasi → NiFi outbox berpartisi symbol/year/month | Tersedia otomatis |
| NiFi outbox → HDFS | Perlu flow NiFi bagian 12 dikonfigurasi sekali |
| Training Spark membaca dataset dari HDFS | Tersedia di Tab 4 (sumber Raw atau Clean); bundle dipakai prediksi live |
| Backfill histori Binance hingga 365 hari | Tersedia lewat `POST /api/ingestion/backfill` |
| Retensi otomatis di HDFS | Belum tersedia |

**HDFS/NiFi yang menyala belum membuktikan bahwa data sudah sampai ke HDFS.** Periksa dengan bagian 12.3.

Dashboard/backend dapat dipakai tanpa menyalakan HDFS/NiFi. Untuk demonstrasi seluruh komponen, ikuti urutan HDFS → NiFi → backend → dashboard berikut.

**Jangan gunakan `run-all.ps1`, `run-all.bat`, atau `arkadanta/start.bat` untuk susunan Windows + WSL ini.** Launcher tersebut menjalankan backend Windows. Gunakan satu backend WSL agar tidak terjadi konflik port atau penulisan dataset oleh dua backend.

## 3. Persiapan pertama kali

Lewati bagian yang sudah pernah berhasil dilakukan.

### 3.1 Periksa WSL dari PowerShell

```powershell
wsl --version
wsl -l -v
```

Distro `Ubuntu-24.04` seharusnya memakai `VERSION 2`. Jika ingin melihat versi Windows, jalankan `winver` dari PowerShell.

### 3.2 Siapkan Python di Ubuntu WSL

Di terminal Ubuntu:

```bash
python3 --version
```

Jika dukungan environment Python belum terpasang:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
```

**Jika environment `~/venvs/arkadanta` belum ada**, buat sekali:

```bash
mkdir -p ~/venvs
python3 -m venv ~/venvs/arkadanta
```

Aktifkan dan pasang dependensi backend:

```bash
source ~/venvs/arkadanta/bin/activate
cd /mnt/e/GIT/Project-Akhir-BigData/arkadanta
python -m pip install -r requirements.txt
```

Prompt biasanya diawali `(arkadanta)` setelah aktivasi. Nama berkas aktivasi adalah **`activate`**, bukan `activat`.

Environment Linux ini terpisah dari `.venv` Windows. Jangan memakai `.venv/Scripts/python.exe` untuk backend Linux.

### 3.3 Siapkan frontend di PowerShell Windows

```powershell
node --version
npm --version
```

Jika perintah tidak ditemukan, pasang Node.js LTS di Windows dan buka ulang PowerShell.

Pasang dependensi frontend sekali, atau ketika dependensinya berubah:

```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta\frontend
npm install
```

### 3.4 Periksa Java di WSL

Hadoop, NiFi, dan Spark membutuhkan Java yang sesuai dengan versi masing-masing. Periksa Java **di Ubuntu**, meskipun Windows sudah memiliki Java:

```bash
java -version
```

Bagian berikut memakai instalasi Hadoop/NiFi yang sudah ditemukan; panduan ini tidak mengunduh ulang atau menginisialisasi ulang Hadoop.

## 4. Menjalankan HDFS di WSL

Di **Terminal A — Ubuntu**, jalankan:

```bash
bash /home/anam/hadoop/sbin/start-dfs.sh
```

Perintah `start-hdfs` bukan perintah yang tersedia pada instalasi ini.

Periksa proses Java:

```bash
jps
```

Untuk instalasi satu mesin, proses penting yang diharapkan adalah `NameNode` dan `DataNode`. `SecondaryNameNode` juga dapat muncul.

Periksa akses filesystem HDFS:

```bash
/home/anam/hadoop/bin/hdfs dfs -ls /
```

Jika root HDFS masih kosong, daftar berkas dapat kosong tanpa menjadi error. Periksa laporan DataNode:

```bash
/home/anam/hadoop/bin/hdfs dfsadmin -report
```

Untuk satu laptop, perhatikan apakah ada satu **Live datanode**.

Konfigurasi yang sudah diperiksa memakai `fs.defaultFS = hdfs://localhost:9000` dan replikasi `1`. Alamat `hdfs://...:9000` adalah alamat komunikasi HDFS, bukan halaman web.

Buka antarmuka NameNode dari browser Windows, biasanya:

**http://localhost:9870**

Jika tidak terbuka, periksa alamat HTTP yang digunakan Hadoop:

```bash
/home/anam/hadoop/bin/hdfs getconf -confKey dfs.namenode.http-address
```

Startup harian tidak memerlukan format NameNode. Jangan memakai `hdfs namenode -format` untuk memperbaiki startup instalasi yang sudah menyimpan data.

## 5. Menjalankan NiFi di WSL

Masih di **Terminal A — Ubuntu**:

```bash
bash /opt/nifi/bin/nifi.sh start
```

Periksa status:

```bash
bash /opt/nifi/bin/nifi.sh status
```

NiFi dapat membutuhkan waktu sebelum antarmukanya siap, meskipun proses startup sudah dimulai.

Buka melalui browser Windows:

**https://localhost:8443/nifi/**

Port HTTPS `8443` sudah dikonfirmasi dari konfigurasi instalasi. Gunakan **HTTPS**. Login menggunakan akun yang dibuat saat instalasi NiFi.

Jika memakai sertifikat lokal, browser dapat menampilkan pemberitahuan sertifikat. Pastikan alamat dan port sesuai instalasi lokal sebelum melanjutkan.

Jika gagal menyala, periksa log secara lokal:

```bash
tail -n 50 /opt/nifi/logs/nifi-app.log
```

Jangan langsung menjalankan NiFi sebagai root untuk mengatasi error izin; periksa pemilik direktori dan pesan error instalasinya.

## 6. Menjalankan backend di WSL

Buka **Terminal B — Ubuntu baru**. Pastikan backend lama tidak masih berjalan pada port 8000; hentikan dengan `Ctrl+C` di terminal yang menjalankannya.

```bash
cd /mnt/e/GIT/Project-Akhir-BigData/arkadanta
source ~/venvs/arkadanta/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Biarkan terminal terbuka. Pesan berhasil biasanya mencakup:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
```

Buka dari browser Windows:

**http://localhost:8000/docs**

Jika Swagger/API terbuka, backend WSL sudah dapat dijangkau browser Windows. Anda juga dapat memeriksa dari WSL:

```bash
curl http://localhost:8000/
```

Gunakan satu worker untuk aplikasi lokal ini. Model dan penyimpanan bersama memakai penguncian di dalam satu proses.

## 7. Menjalankan dashboard di Windows

Buka **Terminal C — PowerShell baru**. Jalankan:

```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta\frontend
npm run dev
```

Biarkan terminal terbuka. Buka alamat yang dicetak Vite, biasanya:

**http://localhost:5173**

Jika port 5173 sudah terpakai, Vite dapat memilih port berikutnya. Ikuti alamat pada terminal.

Frontend sudah memiliki proxy `/api` ke `http://127.0.0.1:8000`. Untuk penggunaan lokal ini tidak perlu membuat konfigurasi jaringan antarlaptop.

Perhatikan:

- Status **FastAPI Live (8000)** menunjukkan pemeriksaan baseline backend berhasil.
- Panel harga di atas dashboard menampilkan **LIVE** setelah menerima event Binance yang masih baru.
- Pesan **data penelitian belum tersedia** wajar saat belum ada histori yang diunggah/disinkronkan.
- **LIVE** mengacu pada harga berjalan, bukan bukti bahwa model sudah dilatih atau NiFi/HDFS sudah menerima data.

## 8. Mengambil dan memeriksa data nyata

### 8.1 Ambil candle terbaru

Di dashboard:

1. Buka **Data Ingestion**.
2. Pilih aset, misalnya mulai dari `BTCUSDT`.
3. Pilih jumlah candle yang ingin diambil, sampai batas API/UI yang tersedia (maksimal 1.000 per permintaan).
4. Klik **Manual Sync Now**.
5. Periksa laporan sumber data, jumlah baris, duplikasi, dan status penyimpanan.
6. Ulangi untuk aset lain jika ingin analisis korelasi lintas aset.

Sinkronisasi REST menyimpan candle yang sudah selesai. Kegagalan pengambilan data ditampilkan sebagai error; aplikasi tidak membuat data sintetis pengganti.

### 8.2 Unggah histori untuk penelitian

Jika membutuhkan histori lebih panjang, gunakan unggahan CSV/JSON nyata pada **Data Ingestion**. Periksa sumber dan rentang tanggalnya. Untuk tugas ini, data penelitian harus berada dalam rentang maksimal satu tahun terakhir sampai waktu pengambilan.

Pengambilan 1.000 candle interval 5 menit hanya mencakup sekitar 3,5 hari. Tombol Manual Sync bukan pengunduh histori satu tahun. Pengunduhan bertahap histori panjang belum diimplementasikan.

### 8.3 Periksa berkas penelitian

Di Terminal A — Ubuntu:

```bash
ls -lh /mnt/e/GIT/Project-Akhir-BigData/arkadanta/data/research/drop_zone/
```

Lokasi penyimpanan aktif:

```text
arkadanta/data/research/
├── drop_zone/              # CSV bersih per aset
├── audit_logs.json         # Riwayat ingestion/sinkronisasi
└── models/
    └── gmm_hgb_v1/         # Model GMM/HGB dan metriknya
```

Berkas model baru muncul setelah pelatihan berhasil. Folder data/model lama di luar `research` tidak digunakan otomatis.

### 8.4 Pahami pembaruan live

- Binance mengirim pembaruan candle berjalan sekitar setiap dua detik.
- Harga berjalan ditampilkan, tetapi hanya candle lima menit yang selesai disimpan sebagai histori.
- Setelah penyimpanan berhasil, dashboard mengambil ulang hasil analisis/prediksi.
- Stream aktif selama dashboard React terbuka. Jika dashboard ditutup, stream berhenti setelah pelanggan terakhir terputus.
- Setelah koneksi terputus atau aplikasi lama dimatikan, gunakan Manual Sync untuk mengisi candle terbaru yang terlewat.
- Retensi satu tahun dan penghapusan histori lama otomatis belum tersedia.

## 9. Melihat analisis

1. Buka **Market Analytics**.
2. Pilih aset yang datanya sudah tersedia.
3. Untuk histori yang masih pendek, mulai dengan timeframe **5m**. Timeframe besar mengurangi jumlah candle hasil agregasi.
4. Periksa grafik harga, volume, volatilitas, dan indikator teknikal.
5. Pilih metode anomali, misalnya `adaptive_quantile`, IQR, rolling Z-score, atau GMM.
6. Untuk korelasi lintas aset, sediakan histori aset-aset yang dibutuhkan dan perhatikan kesamaan rentang waktunya.
7. Baca hasil hubungan faktor historis. `T-1` berarti satu periode timeframe sebelumnya; pada timeframe `1h`, artinya satu jam sebelumnya.

Analisis deskriptif dapat digunakan sebelum model prediksi dilatih. Hubungan statistik pada grafik belum membuktikan sebab-akibat.

## 10. Melatih dan memakai model ML

1. Buka **Model Lab & Shield**.
2. Pilih aset dan timeframe dengan histori cukup; mulai dari `BTCUSDT` dan `5m` untuk percobaan awal.
3. Pilih fitur. Untuk awal, gunakan pilihan default.
4. Gunakan tiga komponen GMM, rasio latih default, dan parameter HGB default terlebih dahulu.
5. Untuk awal, gunakan pemrosesan fitur **Pandas**. Pilih Spark setelah bagian 11 berhasil disiapkan.
6. Klik **Train & Evaluate Models** dan tunggu hasil sebenarnya. Jangan menekan berulang kali saat proses masih berjalan.
7. Periksa tanggal/jumlah data latih dan uji, BIC/AIC/silhouette GMM, Accuracy/F1 klasifikasi, serta MAE/RMSE regresi.
8. Periksa prediksi risiko periode berikutnya dan probabilitasnya.

Model yang dipakai:

| Model | Fungsi |
|---|---|
| GaussianMixture (GMM) | Mengelompokkan kondisi pasar; mean komponen diurutkan menjadi SAFE/WARNING/DANGER |
| HistGradientBoostingClassifier | Memprediksi kelas risiko periode berikutnya |
| HistGradientBoostingRegressor | Memprediksi volatilitas periode berikutnya |

Training membutuhkan minimal `30 + horizon` candle hasil agregasi, pembagian latih/uji yang cukup, dan sedikitnya dua kelas risiko pada data latih. Batas minimum ini hanya syarat teknis; penelitian membutuhkan data dan evaluasi yang memadai.

Model disimpan di `data/research/models/gmm_hgb_v1/`. Artefak lama tetap disimpan di lokasinya dan tidak dipakai oleh versi model ini.

**Training dan prediksi berbeda:** training mempelajari histori lalu menyimpan model. Ketika candle baru selesai, model tersimpan digunakan untuk menghasilkan prediksi baru. Model tidak dilatih ulang setiap dua detik. Kode dapat melatih model default saat artefak yang dibutuhkan belum tersedia.

Untuk timeframe `5m` dan horizon 1, prediksi mengarah ke periode lima menit berikutnya. Label risiko merupakan definisi kelompok yang dibentuk dari data; angka akurasi perlu dijelaskan sesuai target tersebut.

## 11. Menjalankan PySpark, opsional

Backend/dashboard dapat dipakai dengan Pandas terlebih dahulu. Jalankan bagian ini jika ingin menunjukkan pemrosesan Spark.

Di terminal Ubuntu baru:

```bash
cd /mnt/e/GIT/Project-Akhir-BigData/arkadanta
source ~/venvs/arkadanta/bin/activate
java -version
python -m pip install -r requirements-spark.txt
```

Pastikan versi Java sesuai versi PySpark yang dipasang. Jika dependensi baru dipasang, restart backend sebelum memilih Spark pada dashboard.

Untuk memanggil job batch secara langsung, setelah tersedia data penelitian:

```bash
cd /mnt/e/GIT/Project-Akhir-BigData/arkadanta
source ~/venvs/arkadanta/bin/activate
python -m spark_jobs.batch_analytics --symbol BTCUSDT --timeframe 5m
```

Job melakukan agregasi/feature engineering Spark, mengumpulkan fitur ke driver dengan batas 500.000 baris, lalu melatih GMM/HGB dan menyimpan model/metrik baru.

Alternatifnya, pilih pemrosesan fitur Spark di **Model Lab & Shield**, lalu klik **Train & Evaluate Models**. Kegagalan training Spark ditampilkan sebagai error.

**Batas implementasi:** training GMM/HGB berlangsung di driver lokal, bukan Spark MLlib terdistribusi. Job saat ini membaca CSV lokal `data/research/drop_zone/`, belum membaca HDFS.

Spark UI biasanya tersedia pada **http://localhost:4040** selama SparkContext masih aktif; port dapat bergeser jika terpakai. Karena job menghentikan Spark setelah selesai, halaman tersebut dapat hilang sesudah job berakhir. Spark tidak perlu dijalankan sebagai daemon terpisah untuk mode `local[*]` ini.

## 12. Flow NiFi → HDFS (otomatis dari aplikasi)

Setiap kali backend menyimpan baris baru (upload, sinkronisasi Binance, atau candle live yang selesai), baris **baru saja** juga ditulis ke antrean NiFi:

```text
arkadanta/data/research/nifi_outbox/symbol=<SYMBOL>/year=<YYYY>/month=<MM>/<SYMBOL>_5m_<waktu>_<id>.csv
```

Berkas ditulis atomik (berkas sementara diawali titik), jadi NiFi tidak mengambil berkas setengah jadi. Dataset aktif di `drop_zone` tidak disentuh NiFi.

### 12.1 Siapkan direktori HDFS

```bash
/home/anam/hadoop/bin/hdfs dfs -mkdir -p /user/arkadanta/data/clean/crypto /arkadanta/raw
```

### 12.2 Buat flow NiFi

```text
GetFile --success--> UpdateAttribute --success--> PutHDFS
                                                    ├── success: auto-terminate
                                                    └── failure: kembali ke PutHDFS (retry)
```

**GetFile**

| Pengaturan | Nilai |
|---|---|
| Input Directory | `/mnt/e/GIT/Project-Akhir-BigData/arkadanta/data/research/nifi_outbox` |
| Recurse Subdirectories | `true` |
| File Filter | `[^.].*\.csv` |
| Keep Source File | `false` (aman: outbox hanya berisi salinan) |

**UpdateAttribute**: menambahkan atribut `hdfs.dir` = `/user/arkadanta/data/clean/crypto/${path}`. Atribut `path` dari GetFile sudah berisi `symbol=.../year=.../month=...`.

**PutHDFS**

| Pengaturan | Nilai |
|---|---|
| Hadoop Configuration Resources | `/home/anam/hadoop/etc/hadoop/core-site.xml,/home/anam/hadoop/etc/hadoop/hdfs-site.xml` |
| Directory | `${hdfs.dir}` |
| Conflict Resolution Strategy | `fail` (nama berkas sudah unik) |

Jika PutHDFS tidak tersedia pada NiFi 2.x, pasang NAR `nifi-hadoop-nar` yang versinya sama dengan NiFi ke `/opt/nifi/lib`, lalu restart NiFi.

### 12.3 Bukti keberhasilan

```bash
/home/anam/hadoop/bin/hdfs dfs -ls -R /user/arkadanta/data/clean/crypto | head
```

Outbox lokal seharusnya kosong setelah NiFi memprosesnya. Di dashboard Tab 4, pilih **Sumber HDFS: Clean**. Spark akan membaca `hdfs://.../user/arkadanta/data/clean/crypto/symbol=<SYMBOL>/`, melatih GMM/HGB, dan menyimpan bundle yang langsung dipakai prediksi live.

Status audit tetap `QUEUED_DROP_ZONE`: aplikasi tidak menerima konfirmasi balik dari NiFi. Bukti pengiriman ada di Data Provenance NiFi dan `hdfs dfs -ls`.

## 13. Menghentikan layanan

1. Hentikan frontend dengan **Ctrl+C** di PowerShell yang menjalankan `npm run dev`.
2. Hentikan backend dengan **Ctrl+C** di terminal Ubuntu yang menjalankan Uvicorn. Tutup juga tab dashboard jika tidak digunakan.
3. Jika job Spark terpisah masih berjalan, tunggu selesai atau hentikan secara teratur dengan **Ctrl+C** di terminal job.
4. Jika memakai flow NiFi, hentikan processor sumber dan periksa antrean sebelum menghentikan layanan.
5. Hentikan NiFi dari Ubuntu:

```bash
bash /opt/nifi/bin/nifi.sh stop
```

6. Hentikan HDFS sesudah pengiriman NiFi berhenti:

```bash
bash /home/anam/hadoop/sbin/stop-dfs.sh
```

Tidak perlu menghapus dataset atau model saat mematikan aplikasi. `wsl --shutdown` menghentikan seluruh distro/proses WSL; gunakan hanya setelah pekerjaan disimpan dan layanan dihentikan.

## 14. Mengatasi error

| Masalah | Langkah pemeriksaan |
|---|---|
| `wsl: command not found` saat berada di Ubuntu | Jalankan perintah `wsl` dari PowerShell Windows. Tidak perlu `sudo apt install wsl`. |
| `start-hdfs: command not found` | Gunakan `bash /home/anam/hadoop/sbin/start-dfs.sh`. |
| `start-nifi: command not found` | Gunakan `bash /opt/nifi/bin/nifi.sh start`. |
| `.../bin/activat: No such file` | Gunakan nama lengkap `source ~/venvs/arkadanta/bin/activate`. |
| `ModuleNotFoundError` di backend | Aktifkan environment Linux lalu jalankan `python -m pip install -r requirements.txt` dari folder `arkadanta`. |
| `npm` tidak ditemukan | Periksa Node.js/npm di Windows dan buka ulang PowerShell. |
| `Address already in use` pada 8000 | Hentikan backend lama dari terminal asal dengan Ctrl+C. Pastikan backend Windows tidak berjalan bersamaan. |
| Dashboard menunjukkan backend terputus | Periksa `http://localhost:8000/docs`, terminal Uvicorn, dan proxy Vite. Jika memakai `VITE_API_URL`, pastikan alamatnya benar lalu restart Vite. |
| Harga menunggu/stream terputus | Periksa koneksi internet dan akses ke Binance WebSocket. Tunggu reconnect; jangan mengganti kegagalan dengan data simulasi. |
| Harga ada tetapi status bukan LIVE | Data terakhir sudah lebih dari 15 detik atau koneksi terputus. Periksa status stream dan waktu sistem. |
| Data penelitian kosong | Jalankan Manual Sync atau unggah histori nyata melalui Data Ingestion. |
| Training menyebut data terlalu sedikit/satu kelas | Tambah histori, pilih timeframe lebih kecil, atau periksa fitur dan pembagian latih/uji. |
| Training Spark gagal | Periksa instalasi PySpark, versi Java/JAVA_HOME, dan log error. Coba mode Pandas untuk memeriksa alur ML dasar. |
| HDFS gagal menghubungi `localhost:22` | Periksa `ssh localhost`. Jika service SSH yang sudah terpasang belum aktif, jalankan `sudo service ssh start`. Konfigurasi SSH lokal Hadoop harus benar. |
| HDFS CLI connection refused | Periksa NameNode/DataNode dengan `jps` dan alamat `fs.defaultFS`; pastikan HDFS berhasil start. |
| `JAVA_HOME` tidak benar | Periksa `java -version` di WSL dan lokasi Java yang sesuai dengan instalasi Hadoop/NiFi/Spark. |
| NiFi belum bisa dibuka | Periksa status dan log; gunakan `https://localhost:8443/nifi/` dan tunggu startup selesai. |
| NiFi berhasil start tetapi HDFS tetap kosong | Periksa flow, antrean, bulletin, direktori tujuan, dan Data Provenance; startup bukan bukti transfer. |

Pemeriksaan tambahan dari Ubuntu:

```bash
ss -ltnp
```

Pemeriksaan API dari PowerShell Windows:

```powershell
Invoke-RestMethod http://localhost:8000/
```

Jika API bisa diakses dari Ubuntu tetapi belum dari Windows, periksa koneksi localhost Windows–WSL dan aturan firewall yang berlaku. Jangan mengubah semua aturan firewall hanya untuk mencoba.

## 15. Ringkasan untuk pemakaian berikutnya

Setelah persiapan pertama kali selesai, biasanya cukup langkah berikut.

**Terminal A — Ubuntu: layanan data, jika diperlukan untuk demonstrasi**

```bash
bash /home/anam/hadoop/sbin/start-dfs.sh
bash /opt/nifi/bin/nifi.sh start
jps
bash /opt/nifi/bin/nifi.sh status
```

**Terminal B — Ubuntu: backend**

```bash
cd /mnt/e/GIT/Project-Akhir-BigData/arkadanta
source ~/venvs/arkadanta/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Terminal C — PowerShell Windows: frontend**

```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta\frontend
npm run dev
```

**Browser Windows**

| Layanan | Alamat |
|---|---|
| Dashboard utama | http://localhost:5173, atau port yang ditampilkan Vite |
| Dokumentasi API | http://localhost:8000/docs |
| NiFi | https://localhost:8443/nifi/ |
| HDFS NameNode | Biasanya http://localhost:9870; periksa konfigurasi jika berbeda |
| Spark UI, ketika job aktif | Biasanya http://localhost:4040 |

## 16. Urutan demonstrasi

Siapkan histori nyata, model, dan halaman layanan sebelum presentasi. Jangan bergantung pada pengunduhan histori panjang saat presentasi berlangsung.

1. **Sumber dan periode data:** tunjukkan aset, sumber Binance, tanggal awal/akhir, serta jumlah baris.
2. **Akuisisi:** lakukan Manual Sync untuk menunjukkan pengambilan candle terbaru dan laporan audit.
3. **Harga live:** tunjukkan panel LIVE dan bedakan harga berjalan dari candle selesai yang disimpan.
4. **NiFi/HDFS, jika bagian 12 sudah berhasil:** kirim satu snapshot, tunjukkan provenance dan berkas tujuan. Jelaskan bahwa pengiriman ini masih manual.
5. **Analisis:** tampilkan tren harga/volume, volatilitas, anomali, dan hubungan faktor historis.
6. **Pelatihan/evaluasi:** tampilkan GMM/HGB, pembagian temporal, serta metrik dari eksperimen nyata. Jika melatih langsung, gunakan konfigurasi/data yang waktu prosesnya sudah dicoba.
7. **Spark, jika sudah diuji:** tampilkan job/log dan engine sebenarnya. Jelaskan bahwa Spark mengolah fitur, sedangkan GMM/HGB dilatih di driver.
8. **Prediksi dan insight:** jelaskan prediksi periode berikutnya beserta keterbatasan, lalu sampaikan temuan aktual dan rekomendasi.

Referensi kode dan arsitektur lebih lanjut tersedia di [README Arkadanta](arkadanta/README.md) dan [kontrak API](arkadanta/CONTRACTS.md).
