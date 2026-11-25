'use client';
import {useEffect,useState} from 'react';
type D=Record<string,any>;
export default function InformationResearch({symbol}:{symbol:string}){
  const [data,setData]=useState<D|null>(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;const load=()=>fetch('/api/information?symbol='+encodeURIComponent(symbol),{cache:'no-store'}).then(async r=>{const x=await r.json();if(!r.ok)throw new Error(x.detail||'정보 조회 실패');if(active){setData(x);setError('');}}).catch(e=>{if(active)setError(e.message);});setData(null);load();const timer=setInterval(load,60000);return()=>{active=false;clearInterval(timer);};},[symbol]);
  return <>
    {error&&<div role="alert" className="error">{error}</div>}
    {data?.status==='degraded'&&<div role="alert" className="error">일부 수집이 실패했습니다. 아래 자료의 실제 수집 시각을 확인하세요.</div>}
    {data?.news?.stale&&<div role="status" className="error">뉴스 수집본이 2시간 이상 갱신되지 않았습니다.</div>}
    <section className="panel"><div className="panel-title">실제 뉴스 · {symbol}</div>
      <p className="panel-note">Alpaca News · 키워드·수치 추출 · LLM 감성 분석은 데이터 없음. 생성 기사와 요약을 사용하지 않습니다.</p>
      {!data?<p>수집 상태 조회 중…</p>:<><p className="panel-note">조회 시각 {data.as_of} · 수집 {data.news?.snapshot?.collected_at||'없음'} · 일치 기사 {data.news?.matching_articles||0}건 {data.news?.snapshot?.truncated?'· 수집 한도 도달':''}</p>
      <div className="table-wrap"><table><thead><tr><th>발행 / 사용 가능 UTC</th><th>원문 제목</th><th>출처</th><th>감지 키워드</th><th>원문 수치</th></tr></thead><tbody>{(data.news?.articles||[]).slice(0,30).map((a:D)=><tr key={a.id}><td>{a.created_at}<br/>{a.available_at}</td><td><a href={a.url} target="_blank" rel="noreferrer">{a.headline}</a><small> · {a.quality}</small></td><td>{a.source||'없음'}</td><td>{a.topics.join(', ')||'—'}</td><td>{a.numeric_mentions.join(', ')||'—'}</td></tr>)}</tbody></table></div>{!data.news?.articles?.length&&<p>조회 시각에 사용 가능한 실제 기사가 없습니다.</p>}</>}
    </section>
    <section className="panel"><div className="panel-title">SEC 13F · 기관 보고 보유량 · {symbol}</div>
      <p className="panel-note">분기 말 신고 보유량이며 현재 계좌나 전체 운용자산이 아닙니다. 매매 날짜·체결 가격은 알 수 없습니다. 단위 USD / 신고 주식 수.</p>
      {(data?.institutions?.managers||[]).map((m:D)=><div key={m.manager}><h3>{m.manager} · {m.status==='stale'?'오래된 보고서':m.status}</h3><p className="panel-note">{m.prior_report_date||'이전 자료 없음'} → {m.report_date} · 보고기준일 경과 {m.report_age_days}일 · <a href={m.source_url} target="_blank" rel="noreferrer">SEC 원문</a> · 사용 가능 {m.available_at}</p><div className="table-wrap"><table><thead><tr><th>종목 / CUSIP</th><th>구분</th><th>현재 신고량</th><th>이전량 (분할 보정)</th><th>수량 변화</th><th>신고 가치 USD</th></tr></thead><tbody>{m.holdings.map((h:D,i:number)=><tr key={i}><td>{h.ticker||h.cusip}</td><td>{h.share_type} {h.put_call||''} {h.class}</td><td>{Number(h.shares).toLocaleString()}</td><td>{h.split_adjusted_prior_shares==null?'—':Number(h.split_adjusted_prior_shares).toLocaleString()}</td><td>{h.change} {h.change_fraction==null?'':(100*h.change_fraction).toFixed(2)+'%'}</td><td>{Number(h.reported_value_usd).toLocaleString()}</td></tr>)}</tbody></table></div>{!m.holdings.length&&<p>매핑된 해당 종목의 신고 보유량 없음</p>}</div>)}
      {!data?.institutions?.managers?.length&&<p>조회 시각에 사용 가능한 13F 자료가 없습니다.</p>}
    </section>
    <section className="panel"><div className="panel-title">연결·모델 반영 상태</div><p>{data?.earnings_calls?.reason||'어닝콜 데이터 없음'}</p><p>{data?.llm?.reason||'LLM 분석 데이터 없음'}</p><p className="panel-note">{data?.model_integration?.reason} 자동 수집: 재무·13F 24시간, 뉴스 15분. 수집 실패 시 기존 관측 시각을 유지합니다.</p></section>
  </>;
}
