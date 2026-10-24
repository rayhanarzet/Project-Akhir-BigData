"""Dashboard Interaktif Arkadanta (Streamlit + Plotly) sesuai Bab 7 Proposal."""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from plotly.subplots import make_subplots

from backend.api.analytics_routes import get_cross_asset_correlation, run_dynamic_analytics
from backend.api.ingestion_routes import get_historical_baseline, sync_live_binance
from backend.config import AVAILABLE_FEATURES, DEFAULT_FEATURES, DEFAULT_SYMBOLS, SUPPORTED_TIMEFRAMES
from backend.ingestion.dynamic_pipeline import run_dynamic_ingestion_pipeline
from backend.ml.model_predictor import get_latest_metrics, predict_next_period
from backend.ml.model_trainer import train_dynamic_models
from backend.schemas import DynamicConfig, LiveSyncRequest, PredictRequest

st.set_page_config(
    page_title="Arkadanta | Crypto Risk Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------------------
# Tema visual
# ------------------------------------------------------------------------------
RISK = {"SAFE": "#10b981", "WARNING": "#f59e0b", "DANGER": "#ef4444"}
PALETTE = ["#22d3ee", "#a78bfa", "#f472b6", "#facc15", "#34d399", "#fb923c"]
ASSET_COLOR = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(DEFAULT_SYMBOLS)}
UP, DOWN = "#10b981", "#ef4444"
GRID = "rgba(148,163,184,0.12)"

pio.templates["arka"] = go.layout.Template(pio.templates["plotly_dark"])
pio.templates["arka"].layout.update(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,23,42,0.35)",
    font=dict(family="Inter, Segoe UI, sans-serif", color="#cbd5e1", size=12),
    colorway=PALETTE,
    margin=dict(l=10, r=10, t=48, b=10),
    hoverlabel=dict(bgcolor="#0f172a", bordercolor="#334155"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    title=dict(font=dict(size=14, color="#e2e8f0")),
)
pio.templates.default = "arka"

st.markdown(
    """
<style>
.stApp {background: radial-gradient(circle at 8% 0%, #1e1b4b 0%, #0b1120 42%, #020617 100%);}
section[data-testid="stSidebar"] {background: rgba(2,6,23,.85); border-right: 1px solid rgba(148,163,184,.15);}
.hero {padding: 22px 28px; border-radius: 18px; margin-bottom: 14px;
  background: linear-gradient(120deg, rgba(34,211,238,.16), rgba(167,139,250,.16) 50%, rgba(244,114,182,.14));
  border: 1px solid rgba(148,163,184,.22);}
.hero h1 {margin: 0; font-size: 2.1rem; font-weight: 800;
  background: linear-gradient(90deg, #22d3ee, #a78bfa, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
.hero p {margin: 4px 0 0; color: #94a3b8;}
.chip {display: inline-block; padding: 3px 11px; margin: 10px 6px 0 0; border-radius: 999px; font-size: .74rem;
  background: rgba(15,23,42,.65); border: 1px solid rgba(148,163,184,.25); color: #e2e8f0;}
.kpi {padding: 13px 16px; border-radius: 14px; background: rgba(15,23,42,.62); height: 100%;
  border: 1px solid rgba(148,163,184,.16); border-left: 4px solid var(--c);}
.kpi .l {font-size: .7rem; text-transform: uppercase; letter-spacing: .07em; color: #94a3b8;}
.kpi .v {font-size: 1.4rem; font-weight: 700; color: #f8fafc; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.kpi .d {font-size: .78rem; color: var(--c);}
.sec {margin: 26px 0 10px; padding-left: 12px; border-left: 4px solid #a78bfa; font-size: 1.15rem; font-weight: 700; color: #e2e8f0;}
.sec small {display: block; font-weight: 400; color: #94a3b8; font-size: .8rem;}
.badge {padding: 18px; border-radius: 16px; text-align: center; font-weight: 800; font-size: 1.8rem; color: #fff; letter-spacing: .1em;
  box-shadow: 0 0 28px var(--c); background: var(--c);}
.flow {display: flex; flex-wrap: wrap; align-items: center; gap: 6px;}
.flow .step {padding: 8px 14px; border-radius: 10px; background: rgba(34,211,238,.12); border: 1px solid rgba(34,211,238,.35); color: #e2e8f0; font-size: .82rem;}
.flow .arr {color: #a78bfa; font-weight: 700;}
div[data-testid="stPlotlyChart"] {background: rgba(15,23,42,.45); border: 1px solid rgba(148,163,184,.14); border-radius: 14px; padding: 4px;}
.stTabs [data-baseweb="tab-list"] {gap: 6px;}
.stTabs [data-baseweb="tab"] {background: rgba(15,23,42,.6); border-radius: 10px 10px 0 0; padding: 8px 16px;}
</style>
""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------------------
# Helper UI
# ------------------------------------------------------------------------------
def kpi(col, label, value, delta="", color="#22d3ee"):
    col.markdown(
        f'<div class="kpi" style="--c:{color}"><div class="l">{label}</div>'
        f'<div class="v">{value}</div><div class="d">{delta}</div></div>',
        unsafe_allow_html=True,
    )


def section(title, sub=""):
    st.markdown(f'<div class="sec">{title}<small>{sub}</small></div>', unsafe_allow_html=True)


def show(fig, height=380, title=None):
    fig.update_layout(height=height)
    if title:
        fig.update_layout(title=title)
    st.plotly_chart(fig, width="stretch")


def gauge(value, title, max_value=100.0, suffix="", good_high=False):
    steps = [RISK["SAFE"], RISK["WARNING"], RISK["DANGER"]]
    if good_high:
        steps = steps[::-1]
    return go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"suffix": suffix, "font": {"size": 34}},
            title={"text": title, "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, max_value]},
                "bar": {"color": "#e2e8f0", "thickness": 0.25},
                "bgcolor": "rgba(0,0,0,0)",
                "steps": [
                    {"range": [0, max_value * 0.4], "color": steps[0]},
                    {"range": [max_value * 0.4, max_value * 0.7], "color": steps[1]},
                    {"range": [max_value * 0.7, max_value], "color": steps[2]},
                ],
            },
        )
    )


def pct(a, b):
    return (a / b - 1.0) * 100.0 if b else 0.0


def color_of(label):
    return RISK.get(str(label).upper(), "#a78bfa")


# ------------------------------------------------------------------------------
# Data loader (cache; dibersihkan setelah ingest / sync / train)
# ------------------------------------------------------------------------------
@st.cache_data(ttl=120, show_spinner=False)
def load_series(symbol, tf, method="adaptive_quantile", q=0.95, z=2.5, ma=20, rsi=14, roll=20):
    res = run_dynamic_analytics(
        DynamicConfig(
            symbol=symbol,
            timeframe=tf,
            ma_period=ma,
            rsi_period=rsi,
            rolling_window=roll,
            anomaly_method=method,
            anomaly_quantile=q,
            anomaly_z_threshold=z,
            anomaly_iqr_multiplier=z,
        )
    )
    df = pd.DataFrame(res["series"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df, res


@st.cache_data(ttl=120, show_spinner=False)
def load_corr(tf, base, target, window, max_lag=6):
    return get_cross_asset_correlation(
        timeframe=tf, base_symbol=base, target_symbol=target, rolling_window=window, max_lag=max_lag
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_prediction(symbol, tf):
    return predict_next_period(PredictRequest(symbol=symbol, timeframe=tf, target_horizon=1))


def refresh():
    st.cache_data.clear()
    st.rerun()


# ------------------------------------------------------------------------------
# Sidebar: konfigurasi global
# ------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🛡️ Arkadanta")
    st.caption("Dynamic Big Data Intelligence Pipeline")
    sym = st.selectbox("Aset utama", DEFAULT_SYMBOLS)
    tf = st.selectbox("Timeframe agregasi", SUPPORTED_TIMEFRAMES, index=2)
    st.markdown("**Deteksi anomali**")
    method = st.selectbox("Metode", ["adaptive_quantile", "rolling_zscore", "iqr", "gmm"])
    q = st.slider("Kuantil adaptif", 0.85, 0.99, 0.95, 0.01)
    z = st.slider("Z-score / IQR multiplier", 1.0, 5.0, 2.5, 0.1)
    with st.expander("Indikator teknikal"):
        ma = st.number_input("Periode SMA / EMA / Bollinger", 5, 100, 20)
        rsi = st.number_input("Periode RSI", 5, 50, 14)
        roll = st.number_input("Rolling window volatilitas", 5, 100, 20)
    if st.button("♻️ Refresh data", width="stretch"):
        refresh()
    st.divider()
    st.caption("Keluaran hanya untuk analitik akademik, bukan rekomendasi investasi.")

# ------------------------------------------------------------------------------
# Muat data bersama
# ------------------------------------------------------------------------------
st.caption("Mode penelitian: data dan model lama tidak dipakai otomatis. Tidak ada pengganti data sintetis.")
with st.expander("Ambil atau unggah data penelitian", expanded=True):
    if st.button("Sinkronisasi data nyata Binance (semua aset)"):
        try:
            sync_live_binance(LiveSyncRequest(symbols=DEFAULT_SYMBOLS, limit=1000))
            st.cache_data.clear()
            st.rerun()
        except Exception as exc:
            st.error(f"Sinkronisasi gagal: {getattr(exc, 'detail', str(exc))}")
    research_file = st.file_uploader("Unggah CSV/JSON dari sumber nyata", type=["csv", "json"])
    if research_file is not None and st.button("Proses data penelitian"):
        try:
            run_dynamic_ingestion_pipeline(research_file.name, research_file.getvalue(), default_symbol=sym)
            st.cache_data.clear()
            st.rerun()
        except Exception as exc:
            st.error(f"Unggah gagal: {getattr(exc, 'detail', str(exc))}")

try:
    baseline = get_historical_baseline()
    audit = pd.DataFrame(baseline.get("audit_logs", []))
    df_assets = pd.DataFrame(baseline["assets"])
    df, res = load_series(sym, tf, method, q, z, int(ma), int(rsi), int(roll))
    assets = {s: load_series(s, tf)[0] for s in DEFAULT_SYMBOLS}
    asset_res = {s: load_series(s, tf)[1] for s in DEFAULT_SYMBOLS}
    corr_all = load_corr(tf, DEFAULT_SYMBOLS[0], DEFAULT_SYMBOLS[1 % len(DEFAULT_SYMBOLS)], 30)
    metrics = get_latest_metrics()
except Exception as exc:
    st.error(f"Analisis belum tersedia: {getattr(exc, 'detail', str(exc))}")
    st.info("Ambil atau unggah data nyata untuk aset yang dibutuhkan melalui panel di atas.")
    st.stop()

st.markdown(
    f"""
<div class="hero">
  <h1>Arkadanta</h1>
  <p>Dynamic Big Data Intelligence Pipeline untuk Analisis, Deteksi Anomali, dan Prediksi Risiko Volatilitas Pasar Kripto</p>
  <span class="chip">⚡ Lambda Architecture</span><span class="chip">🗄️ NiFi → HDFS</span>
  <span class="chip">🔥 PySpark</span><span class="chip">📡 Binance 5m</span>
  <span class="chip">🧠 Gaussian Mixture + HistGradientBoosting T+1</span>
  <span class="chip">📌 {sym} · {tf} · {method}</span>
</div>
""",
    unsafe_allow_html=True,
)

tabs = st.tabs(
    [
        "🏠 Command Center",
        "📥 Ingestion & Quality",
        "📊 BI Explorer",
        "🌐 Cross-Asset",
        "🧠 Model Lab",
        "🛡️ Live Shield",
    ]
)

# ==============================================================================
# TAB 0: COMMAND CENTER
# ==============================================================================
with tabs[0]:
    section("Ringkasan Pasar", f"Seluruh aset · timeframe {tf}")
    cols = st.columns(len(DEFAULT_SYMBOLS))
    for col, s in zip(cols, DEFAULT_SYMBOLS):
        d = assets[s]
        chg = pct(d["close"].iloc[-1], d["close"].iloc[0])
        kpi(
            col,
            s,
            f"${d['close'].iloc[-1]:,.4f}",
            f"{'▲' if chg >= 0 else '▼'} {chg:+.2f}% · anomali {int(d['is_anomaly'].sum())}",
            UP if chg >= 0 else DOWN,
        )

    c1, c2 = st.columns([1, 2])
    with c1:
        show(
            gauge(float(corr_all.get("market_wide_risk_score", 0.0)), f"Market-Wide Risk · {corr_all.get('market_wide_regime', '-')}"),
            330,
        )
    with c2:
        fig = go.Figure()
        for s, d in assets.items():
            fig.add_trace(
                go.Scatter(x=d["timestamp"], y=d["close"] / d["close"].iloc[0] * 100, name=s, line=dict(color=ASSET_COLOR[s], width=2))
            )
        fig.add_hline(y=100, line_dash="dot", line_color="#64748b")
        show(fig, 330, "Performa Relatif (basis 100)")

    c1, c2 = st.columns([3, 2])
    with c1:
        if not audit.empty:
            fmt = audit.groupby("format_detected")[["rows_before"]].sum()
            fmts = list(fmt.index)
            nodes = [f"Sumber {f}" for f in fmts] + [
                "Dynamic Pipeline Controller",
                "Ditolak / Duplikat",
                "NiFi → HDFS (Batch)",
                "PySpark Aggregation",
                "Feature Engineering",
                "Gaussian Mixture Risk Labeler",
                "HistGradientBoosting T+1",
                "FastAPI Serving",
                "Dashboard",
            ]
            i = {n: k for k, n in enumerate(nodes)}
            rej = int(audit["duplicates_removed"].sum() + audit["rejected_rows"].sum())
            ok = int(audit["rows_after"].sum())
            links = [(f"Sumber {f}", "Dynamic Pipeline Controller", int(fmt.loc[f, "rows_before"])) for f in fmts] + [
                ("Dynamic Pipeline Controller", "Ditolak / Duplikat", rej),
                ("Dynamic Pipeline Controller", "NiFi → HDFS (Batch)", ok),
                ("NiFi → HDFS (Batch)", "PySpark Aggregation", ok),
                ("PySpark Aggregation", "Feature Engineering", ok),
                ("Feature Engineering", "Gaussian Mixture Risk Labeler", ok // 2),
                ("Feature Engineering", "HistGradientBoosting T+1", ok - ok // 2),
                ("Gaussian Mixture Risk Labeler", "FastAPI Serving", ok // 2),
                ("HistGradientBoosting T+1", "FastAPI Serving", ok - ok // 2),
                ("FastAPI Serving", "Dashboard", ok),
            ]
            node_colors = [PALETTE[k % len(PALETTE)] for k in range(len(nodes))]
            node_colors[i["Ditolak / Duplikat"]] = DOWN
            fig = go.Figure(
                go.Sankey(
                    node=dict(label=nodes, color=node_colors, pad=14, thickness=16, line=dict(width=0)),
                    link=dict(
                        source=[i[a] for a, _, _ in links],
                        target=[i[b] for _, b, _ in links],
                        value=[max(v, 1) for _, _, v in links],
                        color="rgba(167,139,250,0.25)",
                    ),
                )
            )
            # Pembagian aliran diagram ini ilustrasi, bukan jumlah sampel pelatihan model.
            show(fig, 400, "Alur Data Lambda Architecture (jumlah baris dari audit log)")
        else:
            st.info("Belum ada audit log ingestion.")
    with c2:
        dist = metrics.get("gmm_metrics", {}).get("regime_distribution", {})
        if dist:
            fig = go.Figure(
                go.Pie(
                    labels=list(dist),
                    values=list(dist.values()),
                    hole=0.6,
                    marker=dict(colors=[color_of(k) for k in dist]),
                )
            )
            fig.update_layout(annotations=[dict(text=f"{sum(dist.values())}<br>candle", showarrow=False, font_size=16)])
            show(fig, 400, f"Distribusi Rezim Risiko ({metrics.get('symbol')} · {metrics.get('timeframe')})")

    c1, c2, c3 = st.columns(3)
    long = pd.concat([d.assign(asset=s) for s, d in assets.items()])
    with c1:
        fig = px.box(long, x="asset", y="max_volatility", color="asset", color_discrete_map=ASSET_COLOR, points=False)
        show(fig.update_layout(showlegend=False), 340, "Sebaran Volatilitas Maksimum")
    with c2:
        pm = pd.DataFrame(corr_all["pearson_matrix"])
        show(px.imshow(pm, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1), 340, "Korelasi Pearson Log Return")
    with c3:
        rates = pd.DataFrame(
            [{"asset": s, "rate": r["anomaly_summary"]["anomaly_rate_pct"]} for s, r in asset_res.items()]
        )
        fig = px.bar(rates, x="asset", y="rate", color="asset", color_discrete_map=ASSET_COLOR, text_auto=".2f")
        show(fig.update_layout(showlegend=False, yaxis_title="%"), 340, "Tingkat Anomali per Aset (%)")

# ==============================================================================
# TAB 1: INGESTION & QUALITY
# ==============================================================================
with tabs[1]:
    section("Status Pipeline", f"HDFS: {baseline['hdfs_cluster_path']}")
    k = st.columns(6)
    kpi(k[0], "Status", baseline["pipeline_status"], "Batch & Speed aktif", UP)
    kpi(k[1], "Aset terdaftar", len(df_assets), "partisi symbol=", "#22d3ee")
    if not audit.empty:
        kpi(k[2], "Run ingestion", len(audit), "audit log", "#a78bfa")
        kpi(k[3], "Baris masuk", f"{int(audit['rows_before'].sum()):,}", "rows_before", "#facc15")
        kpi(k[4], "Baris valid", f"{int(audit['rows_after'].sum()):,}", f"ditolak {int(audit['rejected_rows'].sum())}", UP)
        kpi(k[5], "Rata-rata kualitas", f"{audit['quality_score_pct'].mean():.2f}%", f"duplikat {int(audit['duplicates_removed'].sum())}", "#f472b6")

        run = st.selectbox("Pilih run audit", audit["run_id"], format_func=lambda r: f"{r} · {audit.set_index('run_id').loc[r, 'source_name']}")
        a = audit.set_index("run_id").loc[run]

        steps = "".join(
            f'<span class="step">{s.strip()}</span><span class="arr">➜</span>' for s in str(a["selected_pipeline"]).split("->")
        )
        st.markdown(
            f'<div class="flow"><span class="step">📄 {a["source_name"]} ({a["format_detected"]})</span><span class="arr">➜</span>'
            f'{steps}<span class="step">🗄️ {a["nifi_hdfs_status"]}</span></div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            show(gauge(float(a["quality_score_pct"]), "Skor Kualitas Data", 100, "%", good_high=True), 320)
        with c2:
            dup, rej = int(a["duplicates_removed"]), int(a["rejected_rows"])
            fig = go.Figure(
                go.Funnel(
                    y=["Baris mentah", "Setelah deduplikasi", "Setelah validasi", "Masuk HDFS"],
                    x=[int(a["rows_before"]), int(a["rows_before"]) - dup, int(a["rows_before"]) - dup - rej, int(a["rows_after"])],
                    textinfo="value+percent initial",
                    marker=dict(color=["#64748b", "#22d3ee", "#a78bfa", UP]),
                )
            )
            show(fig, 320, "Funnel Preprocessing")
        with c3:
            er = dict(a["error_reasons"] or {})
            er.update({"duplikat": dup, "imputasi OHLC": int(a["imputed_ohlc_rows"]), "imputasi volume": int(a["imputed_volume_rows"])})
            er_df = pd.DataFrame({"alasan": list(er), "jumlah": list(er.values())}).sort_values("jumlah")
            fig = px.bar(er_df, x="jumlah", y="alasan", orientation="h", color="jumlah", color_continuous_scale="Sunsetdark", text_auto=True)
            show(fig.update_layout(coloraxis_showscale=False), 320, "Masalah Kualitas & Perbaikan")

        c1, c2 = st.columns(2)
        with c1:
            per_run = audit[["run_id", "duplicates_removed", "rejected_rows", "imputed_ohlc_rows", "imputed_volume_rows"]].melt(
                "run_id", var_name="jenis", value_name="baris"
            )
            show(px.bar(per_run, x="run_id", y="baris", color="jenis", barmode="stack"), 340, "Koreksi Data per Run")
        with c2:
            fig = px.scatter(
                audit,
                x="rows_before",
                y="quality_score_pct",
                size="rows_after",
                color="format_detected",
                hover_name="source_name",
                size_max=40,
            )
            show(fig, 340, "Volume Input vs Skor Kualitas")

        mp = a["column_mapping"] or {}
        if mp:
            st.caption("Mapping kolom terdeteksi: " + " · ".join(f"`{s}` → `{t}`" for s, t in mp.items()))

    c1, c2 = st.columns(2)
    with c1:
        cov = df_assets.assign(
            start=pd.to_datetime(df_assets["start_timestamp"], utc=True),
            end=pd.to_datetime(df_assets["end_timestamp"], utc=True),
        )
        fig = px.timeline(cov, x_start="start", x_end="end", y="symbol", color="symbol", color_discrete_map=ASSET_COLOR, hover_data=["rows_5m", "status"])
        show(fig.update_layout(showlegend=False), 300, "Cakupan Data Historis per Aset")
    with c2:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=df_assets["symbol"], y=df_assets["rows_5m"], name="Baris 5m", marker_color=[ASSET_COLOR.get(s) for s in df_assets["symbol"]]), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_assets["symbol"], y=df_assets["avg_volume_5m"], name="Rata-rata volume 5m", mode="lines+markers", line=dict(color="#facc15")), secondary_y=True)
        show(fig, 300, "Ukuran Dataset & Volume per Aset")

    st.dataframe(df_assets, width="stretch", hide_index=True)

    section("Ingest Data Baru", "Upload CSV/JSON atau sinkronisasi Binance API")
    c_up, c_sync = st.columns([3, 2])
    with c_up:
        uploaded = st.file_uploader("Unggah file OHLCV (.csv / .json)", type=["csv", "json"])
        cs, cm = st.columns(2)
        default_sym = cs.selectbox("Simbol default (bila kolom simbol tidak ada)", DEFAULT_SYMBOLS)
        custom_map_str = cm.text_input("Mapping kolom kustom (JSON opsional)", placeholder='{"open_time": "timestamp", "vol": "volume"}')
        if st.button("🚀 Validasi & Ingest", width="stretch"):
            if uploaded is None:
                st.warning("Pilih file CSV atau JSON terlebih dahulu.")
            else:
                try:
                    custom_map = json.loads(custom_map_str) if custom_map_str.strip() else None
                    _, rep = run_dynamic_ingestion_pipeline(
                        filename=uploaded.name, content=uploaded.getvalue(), custom_mapping=custom_map, default_symbol=default_sym
                    )
                    st.success(f"`{rep.source_name}` diproses. Kualitas **{rep.quality_score_pct}%** ({rep.rows_after}/{rep.rows_before} baris valid).")
                    st.json(rep.model_dump())
                    st.cache_data.clear()
                except Exception as err:
                    st.error(f"Pipeline menolak data: {err}")
    with c_sync:
        sync_symbols = st.multiselect("Aset untuk `/api/v3/klines`", DEFAULT_SYMBOLS, default=DEFAULT_SYMBOLS)
        sync_limit = st.slider("Jumlah candle 5m terbaru", 100, 1000, 300, 50)
        if st.button("🔄 Sinkronkan Binance", width="stretch"):
            with st.spinner("Mengambil klines Binance..."):
                try:
                    r = sync_live_binance(LiveSyncRequest(symbols=sync_symbols, interval="5m", limit=sync_limit))
                    st.success(f"Sinkronisasi selesai untuk {r['synced_assets']} aset.")
                    refresh()
                except Exception as err:
                    st.error(f"Sinkronisasi gagal: {err}")

    if not audit.empty:
        section("Audit Log Preprocessing")
        st.dataframe(
            audit[["run_id", "timestamp", "source_name", "format_detected", "rows_before", "rows_after", "duplicates_removed", "rejected_rows", "quality_score_pct", "nifi_hdfs_status"]],
            width="stretch",
            hide_index=True,
        )

# ==============================================================================
# TAB 2: BI EXPLORER
# ==============================================================================
with tabs[2]:
    anom = res["anomaly_summary"]
    last, first = df["close"].iloc[-1], df["close"].iloc[0]
    k = st.columns(6)
    kpi(k[0], "Candle", f"{res['total_candles']:,}", f"{sym} · {tf}", "#22d3ee")
    kpi(k[1], "Close terakhir", f"${last:,.4f}", f"{pct(last, first):+.2f}% periode", UP if last >= first else DOWN)
    kpi(k[2], "High / Low", f"${df['high'].max():,.2f}", f"low ${df['low'].min():,.2f}", "#a78bfa")
    kpi(k[3], "Anomali", anom["total_anomalies"], f"{anom['anomaly_rate_pct']}% observasi", DOWN)
    kpi(k[4], "Ambang adaptif", str(anom["threshold_info"].get("per_symbol_threshold", {}).get(sym, "-")), method, "#facc15")
    kpi(k[5], "RSI terakhir", f"{df['rsi_14'].iloc[-1]:.1f}", "overbought >70 · oversold <30", "#f472b6")

    section("Grafik Teknikal Multi-Panel", "Candlestick, Bollinger, SMA/EMA, volume, RSI, volatilitas, skor anomali")
    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.42, 0.13, 0.15, 0.15, 0.15],
        subplot_titles=("Harga & Bollinger Bands", "Volume", f"RSI ({rsi})", "Max vs Rolling Volatility", "Skor Anomali"),
    )
    ts = df["timestamp"]
    fig.add_trace(go.Scatter(x=ts, y=df["bb_upper"], name="BB upper", line=dict(color="rgba(167,139,250,.6)", width=1)), 1, 1)
    fig.add_trace(go.Scatter(x=ts, y=df["bb_lower"], name="BB lower", line=dict(color="rgba(167,139,250,.6)", width=1), fill="tonexty", fillcolor="rgba(167,139,250,.08)"), 1, 1)
    fig.add_trace(go.Candlestick(x=ts, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="OHLC", increasing_line_color=UP, decreasing_line_color=DOWN), 1, 1)
    fig.add_trace(go.Scatter(x=ts, y=df["sma_20"], name=f"SMA {ma}", line=dict(color="#22d3ee", width=1.4)), 1, 1)
    fig.add_trace(go.Scatter(x=ts, y=df["ema_20"], name=f"EMA {ma}", line=dict(color="#facc15", width=1.4, dash="dot")), 1, 1)
    pts = df[df["is_anomaly"]]
    fig.add_trace(go.Scatter(x=pts["timestamp"], y=pts["high"] * 1.004, mode="markers", name="Anomali", marker=dict(color=DOWN, size=10, symbol="diamond", line=dict(color="white", width=1)), text=pts["anomaly_reason"]), 1, 1)
    fig.add_trace(go.Bar(x=ts, y=df["volume"], name="Volume", marker_color=np.where(df["close"] >= df["open"], UP, DOWN), showlegend=False), 2, 1)
    fig.add_trace(go.Scatter(x=ts, y=df["rsi_14"], name="RSI", line=dict(color="#f472b6", width=1.5)), 3, 1)
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(148,163,184,.08)", line_width=0, row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color=DOWN, row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color=UP, row=3, col=1)
    fig.add_trace(go.Scatter(x=ts, y=df["max_volatility"], name="Max volatility", line=dict(color=DOWN, width=1.4)), 4, 1)
    fig.add_trace(go.Scatter(x=ts, y=df["rolling_volatility"], name="Rolling volatility", line=dict(color="#22d3ee", width=1.4), fill="tozeroy", fillcolor="rgba(34,211,238,.08)"), 4, 1)
    fig.add_trace(go.Bar(x=ts, y=df["anomaly_score"], name="Skor anomali", marker_color=np.where(df["is_anomaly"], DOWN, "#475569"), showlegend=False), 5, 1)
    fig.update_layout(xaxis_rangeslider_visible=False)
    show(fig, 980)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.histogram(df, x="log_return", nbins=60, marginal="box", color_discrete_sequence=["#22d3ee"])
        fig.add_vline(x=0, line_dash="dot", line_color="#94a3b8")
        show(fig, 360, "Distribusi Log Return")
    with c2:
        d5 = load_series(sym, "5m")[0]
        d5 = d5.assign(jam=d5["timestamp"].dt.hour, hari=d5["timestamp"].dt.day_name())
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        heat = d5.pivot_table(index="hari", columns="jam", values="max_volatility", aggfunc="mean").reindex([d for d in days if d in set(d5["hari"])])
        show(px.imshow(heat, aspect="auto", color_continuous_scale="Inferno", labels=dict(color="vol")), 360, "Musiman Volatilitas (hari × jam UTC, data 5m)")

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for col_, name, colr in [("lower_wick_ratio", "Lower wick", "#22d3ee"), ("body_ratio", "Body", "#a78bfa"), ("upper_wick_ratio", "Upper wick", "#f472b6")]:
            fig.add_trace(go.Scatter(x=ts, y=df[col_], name=name, stackgroup="one", line=dict(width=0.5, color=colr)))
        show(fig, 340, "Struktur Candle (komposisi wick/body)")
    with c2:
        bsp = df["buy_sell_pressure_ratio"]
        fig = go.Figure(go.Bar(x=ts, y=bsp - bsp.median(), marker_color=np.where(bsp >= bsp.median(), UP, DOWN), name="Tekanan beli/jual"))
        show(fig, 340, "Tekanan Taker Buy/Sell (deviasi dari median)")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1:
        fig = px.scatter(
            df, x="volume_zscore", y="max_volatility", color=df["is_anomaly"].map({True: "Anomali", False: "Normal"}),
            size=df["spike_ratio"].clip(lower=0.1), color_discrete_map={"Anomali": DOWN, "Normal": "#3b82f6"},
            hover_data=["timestamp", "close", "rsi_14"],
        )
        show(fig.update_layout(legend_title=None), 360, "Volatilitas vs Volume Z-Score")
    with c2:
        reasons = pts["anomaly_reason"].value_counts()
        if not reasons.empty:
            show(go.Figure(go.Pie(labels=reasons.index, values=reasons.values, hole=0.55)).update_layout(showlegend=False), 360, "Penyebab Anomali")
        else:
            st.info("Tidak ada anomali.")
    with c3:
        fig = go.Figure(go.Scatter(x=ts, y=df["spike_ratio"], line=dict(color="#facc15"), fill="tozeroy", fillcolor="rgba(250,204,21,.08)", name="Spike ratio"))
        fig.add_hline(y=df["spike_ratio"].quantile(q), line_dash="dash", line_color=DOWN, annotation_text=f"P{int(q * 100)}")
        show(fig, 360, "Spike Ratio Timeline")

    c1, c2 = st.columns(2)
    with c1:
        feats = [f for f in AVAILABLE_FEATURES if f in df.columns]
        show(px.imshow(df[feats].corr(), color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto"), 480, "Korelasi Antar-Fitur")
    with c2:
        radar_feats = ["max_volatility", "spike_ratio", "rsi_14", "volume_zscore", "bb_width", "hl_range", "buy_sell_pressure_ratio"]
        normed = df[radar_feats].rank(pct=True)
        fig = go.Figure()
        for lbl, row, colr in [("Rata-rata", normed.mean(), "#22d3ee"), ("Candle terakhir", normed.iloc[-1], "#f472b6"), ("Rata-rata anomali", normed[df["is_anomaly"]].mean(), DOWN)]:
            if row.notna().any():
                fig.add_trace(go.Scatterpolar(r=row.values, theta=radar_feats, name=lbl, fill="toself", line=dict(color=colr), opacity=0.7))
        fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 1], gridcolor=GRID), angularaxis=dict(gridcolor=GRID)))
        show(fig, 480, "Profil Fitur (persentil)")

    if res.get("historical_factor_attribution"):
        section("Atribusi Faktor Historis (Periode Lampau T-k → Volatilitas Hari Ini T)")
        attr_df = pd.DataFrame(res["historical_factor_attribution"])
        st.dataframe(
            attr_df[["feature", "dominant_lag", "correlation_to_today", "abs_impact_score", "bi_insight"]],
            width="stretch",
            hide_index=True,
        )

    section("Log Kejadian Anomali")
    log = pd.DataFrame(res["anomalies_log"])
    if not log.empty:
        st.dataframe(log[["timestamp", "coin_symbol", "close", "max_volatility", "spike_ratio", "anomaly_score", "anomaly_reason"]], width="stretch", hide_index=True)
    else:
        st.info("Tidak ada anomali pada ambang saat ini.")

# ==============================================================================
# TAB 3: CROSS-ASSET
# ==============================================================================
with tabs[3]:
    c = st.columns(3)
    base = c[0].selectbox("Aset acuan", DEFAULT_SYMBOLS, index=0)
    target = c[1].selectbox("Aset pembanding", DEFAULT_SYMBOLS, index=1 % len(DEFAULT_SYMBOLS))
    win = c[2].slider("Window rolling correlation", 10, 100, 30)
    corr = load_corr(tf, base, target, win)
    lag = pd.DataFrame(corr["lag_correlation"])
    rc = pd.DataFrame(corr["rolling_correlation"])
    best = lag.loc[lag["correlation"].abs().idxmax()] if not lag.empty else None
    pmat = pd.DataFrame(corr["pearson_matrix"])

    k = st.columns(4)
    kpi(k[0], "Market-wide risk", f"{corr.get('market_wide_risk_score', 0)} / 100", corr.get("market_wide_regime", "-"), color_of(corr.get("market_wide_regime")))
    kpi(k[1], f"Pearson {base}/{target}", f"{pmat.loc[base, target]:.3f}", "log return", "#22d3ee")
    kpi(k[2], "Rolling corr terakhir", f"{rc['rolling_corr'].iloc[-1]:.3f}" if not rc.empty else "-", f"window {win}", "#a78bfa")
    kpi(k[3], "Lag terkuat", f"{int(best['lag'])}" if best is not None else "-", best["interpretation"] if best is not None else "", "#facc15")

    c1, c2 = st.columns(2)
    with c1:
        show(px.imshow(pmat, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1), 380, "Matriks Korelasi Pearson")
    with c2:
        fig = go.Figure(go.Scatter(x=pd.to_datetime(rc["timestamp"]), y=rc["rolling_corr"], line=dict(color="#a78bfa"), fill="tozeroy", fillcolor="rgba(167,139,250,.12)"))
        fig.add_hline(y=0, line_dash="dot", line_color="#64748b")
        show(fig, 380, f"Rolling Correlation {base} vs {target}")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(lag, x="lag", y="correlation", color="correlation", color_continuous_scale="RdBu_r", range_color=[-1, 1], hover_data=["interpretation"])
        show(fig, 360, "Lag Correlation (negatif = pembanding mendahului)")
    with c2:
        j = assets[base][["timestamp", "log_return"]].merge(assets[target][["timestamp", "log_return"]], on="timestamp", suffixes=("_b", "_t")).dropna()
        fig = px.scatter(j, x="log_return_b", y="log_return_t", opacity=0.6, color_discrete_sequence=["#22d3ee"], labels={"log_return_b": base, "log_return_t": target})
        if len(j) > 2:
            m_, c_ = np.polyfit(j["log_return_b"], j["log_return_t"], 1)
            xs = np.linspace(j["log_return_b"].min(), j["log_return_b"].max(), 2)
            fig.add_trace(go.Scatter(x=xs, y=m_ * xs + c_, mode="lines", name=f"β = {m_:.2f}", line=dict(color="#f472b6", width=2)))
        show(fig, 360, "Scatter Return & Beta")

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for s, d in assets.items():
            fig.add_trace(go.Scatter(x=d["timestamp"], y=d["rolling_volatility"], name=s, line=dict(color=ASSET_COLOR[s])))
        show(fig, 360, "Rolling Volatility Lintas Aset")
    with c2:
        ret = pd.concat([d.set_index("timestamp")["log_return"].rename(s) for s, d in assets.items()], axis=1).fillna(0).cumsum()
        fig = go.Figure()
        for s in ret.columns:
            fig.add_trace(go.Scatter(x=ret.index, y=ret[s], name=s, line=dict(color=ASSET_COLOR[s], width=2)))
        show(fig.update_layout(yaxis_title="Σ log return"), 360, "Kumulatif Log Return")

# ==============================================================================
# TAB 4: MODEL LAB
# ==============================================================================
with tabs[4]:
    section("Konfigurasi Pelatihan", "Gaussian Mixture risk labeler + HistGradientBoosting T+1 dengan temporal split")
    m = st.columns(4)
    ml_symbol = m[0].selectbox("Aset target", DEFAULT_SYMBOLS, key="ml_sym")
    ml_tf = m[1].selectbox("Timeframe model", SUPPORTED_TIMEFRAMES, index=2, key="ml_tf")
    ml_k = m[2].slider("Jumlah komponen GMM", 3, 5, 3)
    ml_ratio = m[3].slider("Rasio data latih", 0.60, 0.90, 0.80, 0.05)
    m = st.columns([2, 1, 1])
    ml_features = m[0].multiselect("Fitur dinamis", AVAILABLE_FEATURES, default=DEFAULT_FEATURES)
    ml_trees = m[1].number_input("max_iter HGB", 50, 500, 200, 50)
    ml_depth = m[2].number_input("max_depth", 3, 25, 10, 1)
    ml_learning_rate = st.number_input("Learning rate HGB", 0.01, 1.0, 0.1, 0.01)

    if st.button("⚡ Latih Model", type="primary"):
        with st.spinner("Melatih Gaussian Mixture & HistGradientBoosting..."):
            metrics = train_dynamic_models(
                DynamicConfig(
                    symbol=ml_symbol, timeframe=ml_tf, features=ml_features or DEFAULT_FEATURES, gmm_components=int(ml_k),
                    train_ratio=float(ml_ratio), gb_max_iter=int(ml_trees), gb_max_depth=int(ml_depth),
                    gb_learning_rate=float(ml_learning_rate), target_horizon=1,
                )
            )
            st.cache_data.clear()
            st.success("Pelatihan dan evaluasi temporal selesai.")

    km, cls, reg, split = metrics["gmm_metrics"], metrics["classification_metrics"], metrics["regression_metrics"], metrics["temporal_split"]
    st.caption(f"Model aktif: **{metrics.get('symbol')} · {metrics.get('timeframe')}** · dilatih {metrics.get('trained_at', '-')} · fitur: {', '.join(metrics.get('features', []))}")
    k = st.columns(6)
    kpi(k[0], "Silhouette", km["silhouette_score"], "Gaussian Mixture", "#22d3ee")
    kpi(k[1], "Accuracy T+1", f"{cls['accuracy'] * 100:.2f}%", "HGB classifier", UP)
    kpi(k[2], "Macro F1", cls["f1_macro"], "HGB classifier", "#a78bfa")
    kpi(k[3], "Macro precision", cls["precision_macro"], f"recall {cls['recall_macro']}", "#f472b6")
    kpi(k[4], "MAE volatilitas", reg["mae"], "HGB regressor", "#facc15")
    kpi(k[5], "RMSE volatilitas", reg["rmse"], "HGB regressor", DOWN)

    sp = pd.DataFrame(
        [
            {"set": f"Latih ({split['train_samples']})", "start": split["train_start"], "end": split["train_end"]},
            {"set": f"Uji ({split['test_samples']})", "start": split["test_start"], "end": split["test_end"]},
        ]
    )
    sp["start"], sp["end"] = pd.to_datetime(sp["start"], utc=True), pd.to_datetime(sp["end"], utc=True)
    fig = px.timeline(sp, x_start="start", x_end="end", y="set", color="set", color_discrete_sequence=["#22d3ee", "#f472b6"])
    show(fig.update_layout(showlegend=False), 200, "Temporal Split (tanpa kebocoran data masa depan)")

    cent = pd.DataFrame(km["centroids"])
    zc = [c_ for c_ in cent.columns if c_.startswith("z_")]
    c1, c2, c3 = st.columns(3)
    with c1:
        fig = go.Figure()
        for _, r in cent.iterrows():
            fig.add_trace(
                go.Scatterpolar(
                    r=r[zc].values.astype(float), theta=[c_[2:] for c_ in zc], fill="toself", opacity=0.6,
                    name=f"{r['assigned_risk_label']} (c{int(r['cluster_id'])})", line=dict(color=color_of(r["assigned_risk_label"])),
                )
            )
        fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(gridcolor=GRID), angularaxis=dict(gridcolor=GRID)))
        show(fig, 400, "Profil Centroid (z-score)")
    with c2:
        fig = px.bar(
            cent.sort_values("risk_rank"), x="assigned_risk_label", y="composite_risk_score", color="assigned_risk_label",
            color_discrete_map=RISK, text_auto=".3f", hover_data=["cluster_id", "train_sample_count"],
        )
        show(fig.update_layout(showlegend=False, xaxis_title=None), 400, "Skor Risiko Gabungan per Cluster")
    with c3:
        dist = km.get("regime_distribution", {})
        fig = go.Figure(go.Pie(labels=list(dist), values=list(dist.values()), hole=0.55, marker=dict(colors=[color_of(x) for x in dist])))
        show(fig, 400, "Distribusi Rezim")

    c1, c2, c3 = st.columns(3)
    with c1:
        show(
            px.imshow(cls["confusion_matrix"], x=cls["labels"], y=cls["labels"], text_auto=True, color_continuous_scale="Purples", labels=dict(x="Prediksi", y="Aktual")),
            380, "Confusion Matrix T+1",
        )
    with c2:
        pc = pd.DataFrame(cls["per_class"]).T.reset_index().rename(columns={"index": "kelas"})
        pcl = pc.melt("kelas", value_vars=["precision", "recall", "f1_score"], var_name="metrik", value_name="nilai")
        show(px.bar(pcl, x="kelas", y="nilai", color="metrik", barmode="group", range_y=[0, 1]), 380, "Metrik per Kelas")
    with c3:
        fi = pd.DataFrame(metrics["feature_importances"]).sort_values("importance")
        fig = px.bar(fi, x="importance", y="feature", orientation="h", color="importance", color_continuous_scale="Tealgrn", text_auto=".3f")
        show(fig.update_layout(coloraxis_showscale=False), 380, "Permutation Importance: Holdout Macro F1")

    tp = pd.DataFrame(metrics.get("test_predictions_preview", []))
    if not tp.empty:
        tp["timestamp"] = pd.to_datetime(tp["timestamp"], utc=True)
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=tp["timestamp"], y=tp["actual_vol_t1"], name="Aktual", line=dict(color="#22d3ee", width=2)))
            fig.add_trace(go.Scatter(x=tp["timestamp"], y=tp["predicted_vol_t1"], name="Prediksi", line=dict(color="#f472b6", width=2, dash="dot")))
            show(fig, 360, "Volatilitas T+1: Aktual vs Prediksi (data uji)")
        with c2:
            order = {"SAFE": 0, "WARNING": 1, "DANGER": 2}
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=tp["timestamp"], y=tp["actual_risk_t1"].map(order), mode="lines+markers", name="Aktual", line=dict(color="#22d3ee", shape="hv")))
            fig.add_trace(go.Scatter(x=tp["timestamp"], y=tp["predicted_risk_t1"].map(order), mode="markers", name="Prediksi", marker=dict(size=10, symbol="x", color=[color_of(x) for x in tp["predicted_risk_t1"]])))
            fig.update_yaxes(tickvals=list(order.values()), ticktext=list(order))
            show(fig, 360, "Rezim Risiko T+1: Aktual vs Prediksi")
        c1, c2 = st.columns(2)
        with c1:
            err = (tp["predicted_vol_t1"] - tp["actual_vol_t1"]).rename("residual")
            show(px.histogram(err, nbins=30, color_discrete_sequence=["#a78bfa"]).update_layout(showlegend=False, xaxis_title="prediksi − aktual"), 320, "Distribusi Residual Regresi")
        with c2:
            fig = px.scatter(tp, x="actual_vol_t1", y="predicted_vol_t1", color="actual_risk_t1", color_discrete_map=RISK)
            lim = [0, float(max(tp["actual_vol_t1"].max(), tp["predicted_vol_t1"].max()))]
            fig.add_trace(go.Scatter(x=lim, y=lim, mode="lines", name="ideal", line=dict(color="#64748b", dash="dot")))
            show(fig, 320, "Kalibrasi Prediksi Volatilitas")

    with st.expander("Tabel centroid lengkap"):
        st.dataframe(cent, width="stretch", hide_index=True)

# ==============================================================================
# TAB 5: LIVE SHIELD
# ==============================================================================
with tabs[5]:
    live_sym, live_tf = metrics.get("symbol", sym), metrics.get("timeframe", tf)
    p = load_prediction(live_sym, live_tf)
    regime = p["predicted_regime_t_plus_1"]
    probs = p["probabilities_t_plus_1"]

    section("Prediksi Periode Berikutnya (T+1)", f"Model aktif {live_sym} · {live_tf}")
    c0, *k = st.columns([1.3, 1, 1, 1, 1])
    c0.markdown(f'<div class="badge" style="--c:{color_of(regime)}">{regime}</div>', unsafe_allow_html=True)
    kpi(k[0], "Harga sekarang", f"${p['current_price']:,.4f}", f"rezim T: {p['current_regime_t']}", color_of(p["current_regime_t"]))
    kpi(k[1], "Estimasi volatilitas", f"{p['predicted_volatility_pct']:.3f}%", f"±${p['estimated_volatility_nominal']:,.4f}", "#facc15")
    kpi(k[2], "Resistance T+1", f"${p['resistance_level']:,.4f}", "harga + volatilitas", UP)
    kpi(k[3], "Stop loss T+1", f"${p['stop_loss_level']:,.4f}", "harga − volatilitas", DOWN)

    c1, c2, c3 = st.columns(3)
    with c1:
        show(gauge(probs.get("DANGER", 0.0) * 100, "Probabilitas DANGER", 100, "%"), 300)
    with c2:
        show(gauge(p["predicted_volatility_pct"], "Volatilitas T+1", max(5.0, p["predicted_volatility_pct"] * 1.5), "%"), 300)
    with c3:
        fig = go.Figure(go.Pie(labels=list(probs), values=list(probs.values()), hole=0.6, marker=dict(colors=[color_of(x) for x in probs])))
        show(fig, 300, "Probabilitas Rezim T+1")

    dl = load_series(live_sym, live_tf)[0].tail(80)
    step = dl["timestamp"].diff().median()
    t_last = dl["timestamp"].iloc[-1]
    fig = go.Figure(go.Candlestick(x=dl["timestamp"], open=dl["open"], high=dl["high"], low=dl["low"], close=dl["close"], name=live_sym, increasing_line_color=UP, decreasing_line_color=DOWN))
    fig.add_shape(type="rect", x0=t_last, x1=t_last + step * 3, y0=p["stop_loss_level"], y1=p["resistance_level"], fillcolor=color_of(regime), opacity=0.18, line_width=0)
    fig.add_hline(y=p["resistance_level"], line_dash="dash", line_color=UP, annotation_text=f"Resistance ${p['resistance_level']:,.2f}")
    fig.add_hline(y=p["stop_loss_level"], line_dash="dash", line_color=DOWN, annotation_text=f"Stop loss ${p['stop_loss_level']:,.2f}")
    fig.add_trace(go.Scatter(x=[t_last, t_last + step * 3], y=[p["current_price"]] * 2, mode="lines", name="Proyeksi T+1", line=dict(color="#facc15", dash="dot")))
    fig.update_layout(xaxis_rangeslider_visible=False)
    show(fig, 480, "Live Candle Monitor + Zona Proyeksi T+1")

    section("Risk Radar Lintas Aset", "Model aktif diterapkan ke setiap aset")
    rows = []
    for s in DEFAULT_SYMBOLS:
        try:
            ps = load_prediction(s, live_tf)
            rows.append({"asset": s, "regime": ps["predicted_regime_t_plus_1"], "vol_pct": ps["predicted_volatility_pct"], **{k_: v * 100 for k_, v in ps["probabilities_t_plus_1"].items()}})
        except Exception as err:
            st.warning(f"{s}: {err}")
    if rows:
        rr = pd.DataFrame(rows)
        c1, c2 = st.columns(2)
        with c1:
            pl = rr.melt("asset", value_vars=[x for x in ["SAFE", "WARNING", "DANGER"] if x in rr], var_name="kelas", value_name="prob")
            show(px.bar(pl, x="prob", y="asset", color="kelas", orientation="h", color_discrete_map=RISK, text_auto=".0f").update_layout(xaxis_title="%"), 320, "Probabilitas Rezim per Aset (%)")
        with c2:
            fig = px.bar(rr, x="asset", y="vol_pct", color="regime", color_discrete_map=RISK, text_auto=".3f")
            show(fig.update_layout(yaxis_title="%"), 320, "Estimasi Volatilitas T+1 per Aset")
    st.caption(f"ℹ️ {p['disclaimer']}")
