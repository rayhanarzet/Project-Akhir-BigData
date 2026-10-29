# Penggabungan event CSV v3 di NiFi

Konfigurasi ini mengurangi berkas kecil saat aplikasi berjalan terus. Harga live dan analisis CSV tetap diperbarui setiap candle selesai; batch HDFS dapat tertunda sampai satu jam. Konfigurasi processor dilakukan di antarmuka NiFi, bukan otomatis oleh backend.

Gunakan alur berikut untuk event v3:

```text
GetFile → UpdateAttribute (hdfs.dir) → MergeRecord → UpdateAttribute (filename) → PutHDFS
```

1. Arahkan **GetFile** ke `/mnt/e/GIT/Project-Akhir-BigData/arkadanta/data/research/nifi_outbox/v3`, Recurse Subdirectories `true`, Keep Source File `false`, File Filter `[^.].*\.csv`.
2. **UpdateAttribute** sebelum MergeRecord: `hdfs.dir = /user/arkadanta/data/clean/crypto/v3/${path}`. Karena input GetFile sudah dimulai dari `v3`, `${path}` dimulai dari `symbol=...`; jangan menambahkan `v3` dua kali.
3. Buat controller service **CSVReader**. Gunakan **Schema Access Strategy = Use Schema Text**, isi Schema Text dengan isi [candle-v3.avsc](candle-v3.avsc), dan **Treat First Line as Header = true**. Gunakan pemisah koma dan quote karakter `"`.
4. Buat **CSVRecordSetWriter**, gunakan **Inherit Record Schema** dan **Include Header Line = true**. Enable kedua controller service.
5. **MergeRecord**: Record Reader = CSVReader tadi; Record Writer = CSVRecordSetWriter tadi; Merge Strategy = `Bin-Packing Algorithm`; Correlation Attribute Name = `hdfs.dir`; Minimum Number of Records = `288`; Maximum Number of Records = `100000`; Max Bin Age = `1 hour`. Pertahankan atribut yang sama antar anggota bin (Attribute Strategy `Keep Only Common Attributes` jika tersedia). Kelompok tidak boleh mencampur aset/tahun/bulan.
6. **UpdateAttribute** setelah MergeRecord: `filename = ${uuid}.csv`. Nama unik ini wajib: memakai nama berkas pertama dapat membuat isi batch lain terlewat ketika PutHDFS mengabaikan konflik.
7. **PutHDFS**: Directory = `${hdfs.dir}`, Conflict Resolution Strategy = `ignore`. Konfigurasi Hadoop sama dengan START.md. Hubungkan failure kembali ke PutHDFS, tanpa melewati UpdateAttribute filename. Success boleh terminate.

Periksa bahwa `hdfs.dir` tetap ada sesudah MergeRecord melalui atribut flowfile/Data Provenance. Processor failure yang berasal dari CSVReader/MergeRecord harus diarahkan ke antrean pemeriksaan; jangan auto-terminate failure. Sebelum mengganti flow, hentikan processor input, tunggu antrean lama selesai, lalu ubah konfigurasi.

Untuk demo cepat, gunakan sementara Max Bin Age = `1 min` dan jalankan backfill. Setelah melihat batch berhasil di HDFS, gunakan kembali `1 hour` untuk operasi rutin. Jumlah file yang muncul bukan jumlah candle; satu file dapat memuat banyak candle.

Jangan menggabungkan CSV dengan penggabungan teks biasa: header berulang dan tipe versi candle dapat rusak. `ingestion_version` wajib bertipe Avro **long**, sehingga bilangan versi tidak dibulatkan menjadi float. Spark memilih versi terbesar per simbol/timestamp dan menolak isi yang bertentangan pada versi sama.

Data v1/v2 tidak dipindahkan/dihapus. Backfill dari dashboard menerbitkan ulang histori lokal yang belum berversi ke skema v3. Periksa lokasi hasil dengan:

```bash
/home/anam/hadoop/bin/hdfs dfs -ls -R /user/arkadanta/data/clean/crypto/v3
```
