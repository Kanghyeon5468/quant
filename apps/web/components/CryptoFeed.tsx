'use client';

import {useEffect, useState} from 'react';
import {when} from './paper-format';
import styles from './ResearchLab.module.css';

type Level = [string, string];
type Trade = {trade_id:number; time:string; price:string; size:string; side:string};
type Book = {bids:Level[]; asks:Level[]; at:string; trades:Trade[]; exchangeAt?:string};
const feedUrl = 'wss://ws-feed.exchange.coinbase.com';

function level(row: unknown): row is Level {
  return Array.isArray(row) && row.length === 2 && row.every(value =>
    typeof value === 'string' && /^\d+(\.\d+)?$/.test(value) && Number.isFinite(Number(value)))
    && Number(row[0]) > 0;
}

export default function CryptoFeed({symbol}: {symbol:string}) {
  const [enabled,setEnabled] = useState(false);
  const [status,setStatus] = useState('정지');
  const [book,setBook] = useState<Book>();
  useEffect(() => {
    if (!enabled) return;
    let socket:WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let watchdog: ReturnType<typeof setInterval>;
    let render: ReturnType<typeof setInterval>;
    let active = true;
    let delay = 1000;
    function connect() {
      setStatus('연결 중');
      const bids = new Map<number,Level>();
      const asks = new Map<number,Level>();
      const trades:Trade[] = [];
      let snapshot = false;
      let touched = false;
      let received = Date.now();
      let exchangeAt: string | undefined;
      socket = new WebSocket(feedUrl);
      socket.onopen = () => socket.send(JSON.stringify({type:'subscribe', product_ids:[symbol],
        channels:['level2_batch','matches','heartbeat']}));
      socket.onmessage = event => {
        if (!active || typeof event.data !== 'string') return;
        if (event.data.length > 16_000_000) {
          socket.close();
          return;
        }
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'error') {
            socket.close();
            return;
          }
          if (data.product_id !== symbol) return;
          if (data.type === 'snapshot' && Array.isArray(data.bids) && Array.isArray(data.asks)) {
            for (const [target,rows] of [[bids,data.bids],[asks,data.asks]] as const) {
              target.clear();
              for (const row of rows) {
                if (!level(row)) throw new Error('invalid depth');
                if (Number(row[1]) > 0) target.set(Number(row[0]),row);
              }
            }
            snapshot = true;
            delay = 1000;
            setStatus('연결됨');
            touched = true;
          } else if (snapshot && data.type === 'l2update' && Array.isArray(data.changes)) {
            for (const [side,price,size] of data.changes) {
              const row = [price,size];
              if (!level(row) || !['buy','sell'].includes(side)) throw new Error('invalid depth update');
              const target = side === 'buy' ? bids : asks;
              if (Number(size) === 0) target.delete(Number(price));
              else target.set(Number(price),row);
            }
            if (typeof data.time === 'string') exchangeAt = data.time;
            touched = true;
          } else if (data.type === 'match' && level([data.price,data.size]) && typeof data.time === 'string') {
            trades.unshift(data as Trade);
            if (trades.length > 20) trades.pop();
            touched = true;
          }
          received = Date.now();
        } catch {
          socket.close();
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        clearInterval(watchdog);
        clearInterval(render);
        if (!active) return;
        setBook(undefined);
        setStatus('재연결 대기');
        retry = setTimeout(connect,delay);
        delay = Math.min(delay*2,30000);
      };
      watchdog = setInterval(() => {
        if (Date.now() - received > 10000) socket.close();
      },2000);
      render = setInterval(() => {
        if (!snapshot || !touched) return;
        touched = false;
        setBook({
          bids:[...bids.entries()].sort(([a],[b]) => b-a).slice(0,10).map(([,row]) => row),
          asks:[...asks.entries()].sort(([a],[b]) => a-b).slice(0,10).map(([,row]) => row),
          trades:[...trades], at:new Date(received).toISOString(), exchangeAt,
        });
      },250);
    }
    connect();
    return () => {
      active = false;
      clearTimeout(retry);
      clearInterval(watchdog);
      clearInterval(render);
      if (socket.readyState <= WebSocket.OPEN) socket.close();
    };
  },[enabled,symbol]);
  return <section className={styles.card}>
    <h3>Coinbase 실시간 호가와 체결 · {symbol}</h3>
    <p className="muted">공개 Exchange WebSocket · {enabled ? status : '정지'}</p>
    <div className={styles.form}><button className="primary" type="button" onClick={() => {
      setEnabled(value => !value);
      setBook(undefined);
    }}>{enabled ? '실시간 중지' : '실시간 연결'}</button></div>
    {enabled && book && <>
      <p className="muted">최근 수신 {when(book.at)}{book.exchangeAt && ' · 최근 호가 변경 '+when(book.exchangeAt)}</p>
      <div className="table-wrap"><table><thead><tr>
        <th scope="col">실시간 매수 (USD)</th><th scope="col">수량</th><th scope="col">실시간 매도 (USD)</th><th scope="col">수량</th>
      </tr></thead><tbody>{book.bids.map(([price,size],index) => <tr key={price}>
        <td>{price}</td><td>{size}</td><td>{book.asks[index]?.[0] ?? '—'}</td><td>{book.asks[index]?.[1] ?? '—'}</td>
      </tr>)}</tbody></table></div>
      {book.trades.length > 0 && <details open><summary>실시간 관측 체결</summary>
        <div className="table-wrap"><table><thead><tr><th scope="col">시각</th><th scope="col">가격 (USD)</th><th scope="col">수량</th></tr></thead>
          <tbody>{book.trades.map(trade => <tr key={trade.trade_id}>
            <td>{when(trade.time)}</td><td>{trade.price}</td><td>{trade.size}</td>
          </tr>)}</tbody></table></div>
      </details>}
    </>}
  </section>;
}
