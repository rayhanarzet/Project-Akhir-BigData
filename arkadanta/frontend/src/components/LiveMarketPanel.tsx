import React, { useEffect, useState } from 'react';
import { LiveQuote, subscribeMarket } from '../services/api';

interface Props {
  symbol: string;
  onCandleClosed: () => void;
}

export const LiveMarketPanel: React.FC<Props> = ({ symbol, onCandleClosed }) => {
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [connected, setConnected] = useState(false);
  const [message, setMessage] = useState('Menghubungkan stream pasar...');
  const [storageError, setStorageError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const close = subscribeMarket((event) => {
      if (event.type === 'status') {
        setConnected(event.connected);
        setMessage(event.message);
      } else if (event.type === 'quote') {
        setQuotes((previous) => ({ ...previous, [event.symbol]: event }));
        if (!event.snapshot) setConnected(true);
      } else if (event.type === 'storage_error') {
        setStorageError(event.message);
      } else if (event.type === 'candle_closed') {
        setStorageError(null);
        onCandleClosed();
      }
    }, (error) => {
      setConnected(false);
      setMessage(error);
    });
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { close(); clearInterval(timer); };
  }, [onCandleClosed]);

  const quote = quotes[symbol];
  // Freshness uses Binance event time, including when an old cached snapshot arrives.
  const age = quote ? Math.max(0, Math.floor((now - quote.event_time) / 1000)) : null;
  const live = connected && age !== null && age < 15;

  return (
    <section className="bd-card mb-5" aria-label="Harga pasar real-time">
      <div className="bd-card-body">
        <div className="flex flex-wrap justify-between gap-4 items-center">
          <div>
            <p className="text-xs text-[#9a9a9a]">Binance WebSocket · {symbol} · candle 5m</p>
            <p className="text-2xl font-mono mt-2">
              {quote ? `$${quote.close.toLocaleString(undefined, { maximumFractionDigits: 6 })}` : 'Menunggu harga nyata...'}
            </p>
          </div>
          <div className="text-sm" role="status" aria-live="polite">
            <span className={live ? 'text-[#00f2c3]' : 'text-amber-300'}>
              {live ? '● LIVE' : quote ? '● DATA TERAKHIR — BELUM LIVE' : '● MENUNGGU STREAM'}
            </span>
            <p className="text-xs text-[#9a9a9a] mt-1">
              {quote ? `Pembaruan ${age} detik lalu · ${quote.closed ? 'candle selesai' : 'candle berjalan'}` : message}
            </p>
          </div>
        </div>
        {quote && (
          <p className="text-xs text-[#9a9a9a] mt-3">
            Open {quote.open.toLocaleString()} · High {quote.high.toLocaleString()} · Low {quote.low.toLocaleString()} · Volume {quote.volume.toLocaleString()}
          </p>
        )}
        {!connected && quote && <p role="alert" className="text-amber-300 text-xs mt-3">{message}</p>}
        {connected && quote && !live && <p role="alert" className="text-amber-300 text-xs mt-3">Belum ada pembaruan harga baru. Data terakhir tidak dianggap live.</p>}
        {storageError && <p role="alert" className="text-red-300 text-xs mt-3">{storageError}</p>}
        <p className="text-xs text-[#9a9a9a] mt-3">
          Harga diperbarui saat event Binance masuk (sekitar 2 detik). Analisis dan prediksi diperbarui setelah candle 5 menit tersimpan.
        </p>
      </div>
    </section>
  );
};
