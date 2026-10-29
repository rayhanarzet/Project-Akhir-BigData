"""Satu SparkContext per proses backend: job yang memanggil spark.stop() tidak boleh tumpang tindih."""
from contextlib import contextmanager
import os
from pathlib import Path
import threading

_spark_lock = threading.Lock()


class SparkBusyError(ValueError):
    """Job Spark lain sedang berjalan di proses ini."""


def check_java_home() -> None:
    # PySpark menggantung selamanya (bukan error) bila JAVA_HOME menunjuk folder tanpa bin/java.
    home = os.environ.get("JAVA_HOME")
    if home and not any((Path(home) / "bin" / name).exists() for name in ("java", "java.exe")):
        raise ValueError(f"JAVA_HOME={home} tidak berisi bin/java. Perbaiki JAVA_HOME lalu restart backend.")


@contextmanager
def exclusive_spark():
    check_java_home()
    # Tolak, jangan antre: job Tab 4 bisa berjalan beberapa menit.
    if not _spark_lock.acquire(blocking=False):
        raise SparkBusyError("Spark sedang dipakai job lain (mis. Historical HDFS Batch). Coba lagi setelah selesai.")
    try:
        yield
    finally:
        _spark_lock.release()
