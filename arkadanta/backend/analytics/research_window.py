"""Satu batas waktu penelitian UTC untuk pandas dan Spark; arsip tetap dipertahankan."""
import pandas as pd

MAX_HISTORY_DAYS = 365


def research_bounds(start_date=None, end_date=None, now=None):
    clock = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock.tz_convert("UTC")
    earliest = clock - pd.Timedelta(days=MAX_HISTORY_DAYS)
    start = pd.to_datetime(start_date, utc=True) if start_date else earliest
    end = pd.to_datetime(end_date, utc=True) if end_date else clock
    if end_date and len(str(end_date)) == 10:
        end = min(end + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1), clock)
    # Pemilihan hari pada batas bawah berarti sisa hari itu yang masih masuk 365 hari.
    if start_date and len(str(start_date)) == 10 and start.date() == earliest.date():
        start = earliest
    if pd.isna(start) or pd.isna(end) or start < earliest or end > clock or start >= end:
        raise ValueError("Rentang penelitian harus berada dalam 365 hari terakhir dan tanggal awal sebelum akhir.")
    return start, end


def filter_research_window(frame, start_date=None, end_date=None, now=None):
    start, end = research_bounds(start_date, end_date, now)
    stamp = pd.to_datetime(frame["timestamp"], utc=True)
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock.tz_convert("UTC")
    mask = stamp.between(start, end) & (stamp + pd.Timedelta(minutes=5) <= clock)
    return frame.loc[mask].assign(timestamp=stamp[mask]).copy()
