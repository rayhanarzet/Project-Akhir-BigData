import shutil
import subprocess
from pathlib import Path

try:
    from src.parser import parse_file
    from src.validator import validate_data
    from src.profiler import profile_data
    from src.cleaner import clean_data
    from src.pipeline_router import select_pipeline
except ImportError:
    from parser import parse_file
    from validator import validate_data
    from profiler import profile_data
    from cleaner import clean_data
    from pipeline_router import select_pipeline

BASE_DIR = Path(__file__).resolve().parent.parent


def save_processed_data(df, original_path):
    output_dir = BASE_DIR / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{Path(original_path).stem}_processed.csv"

    df.to_csv(output_path, index=False)

    print(f"Output tersimpan: {output_path}")

    return output_path


def upload_to_hdfs(local_path):
    hdfs_dir = "/arkadanta/processed"
    hdfs_path = f"{hdfs_dir}/{Path(local_path).name}"

    if not shutil.which("hdfs"):
        print(f"[Fallback Lokal] CLI 'hdfs' tidak ditemukan, melewati unggah ke {hdfs_path}")
        return hdfs_path

    try:
        subprocess.run(
            ["hdfs", "dfs", "-mkdir", "-p", hdfs_dir],
            check=True,
            timeout=10,
        )
        subprocess.run(
            ["hdfs", "dfs", "-put", "-f", str(local_path), hdfs_dir],
            check=True,
            timeout=15,
        )
        print(f"Data berhasil diunggah ke HDFS: {hdfs_dir}")
    except Exception as exc:
        print(f"[Fallback Lokal] Gagal mengunggah ke HDFS ({exc}), menggunakan file lokal: {local_path}")

    return hdfs_path


def run_pipeline(file_path):
    path = Path(file_path)

    print(f"File diterima: {path.name}")

    if not path.exists():
        raise FileNotFoundError(
            f"File tidak ditemukan: {path}"
        )

    extension = path.suffix.lower()

    if extension not in [".csv", ".json"]:
        raise ValueError(
            f"Format tidak didukung: {extension}"
        )

    print(f"Format terdeteksi: {extension.upper()}")

    # Membaca file sesuai formatnya
    df = parse_file(path)
    print("Parsing berhasil!")
    profile = profile_data(df)

    # Menentukan pipeline berdasarkan karakteristik data
    pipeline_type = select_pipeline(profile)
    print(f"Pipeline terpilih: {pipeline_type}")

    if pipeline_type == "CLEANING":
        df = clean_data(df)

    # Memvalidasi kualitas data
    is_valid, messages = validate_data(df)

    for message in messages:
        print(message)

    if not is_valid:
        raise ValueError(
            "Data ditolak karena tidak memenuhi validasi."
        )

    print(f"Jumlah baris: {len(df)}")
    print(f"Jumlah kolom: {len(df.columns)}")

    output_path = save_processed_data(df, path)
    hdfs_path = upload_to_hdfs(output_path)

    if shutil.which("spark-submit"):
        try:
            subprocess.run(
                [
                    "spark-submit",
                    str(BASE_DIR / "src" / "spark_jobs" / "process_data.py"),
                    f"hdfs://localhost:9000{hdfs_path}",
                ],
                check=True,
                timeout=30,
            )
        except Exception as exc:
            print(f"[Fallback Lokal] Eksekusi spark-submit dilewati ({exc}).")
    else:
        print("[Fallback Lokal] CLI 'spark-submit' tidak ditemukan, hasil lokal siap digunakan.")

    print("Status pipeline: BERHASIL")

    return df
