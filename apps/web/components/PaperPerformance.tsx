'use client';
import dynamic from 'next/dynamic';
import {useEffect,useState} from 'react';
import PaperHoldings, {type PaperOrder} from './PaperHoldings';
import PaperUsage from './PaperUsage';
import {count, num, pct, statuses, usd, when} from './paper-format';
const Chart=dynamic(()=>import('./Chart'),{ssr:false});
type Row=Record<string,any>;
const decisions:Record<string,string>={hold:'유지',buy:'매수',sell:'매도',existing_pending_or_processed:'접수·평가 완료',buy_limited_budget:'예산 내 매수',deferred_budget:'예산 부족으로 보류',risk_restricted:'리스크 제한',information_data_unavailable:'정보 부족으로 보류'};
const closedOrders = new Set(['filled', 'canceled', 'expired', 'rejected', 'rejected_locally', 'replaced']);
const riskStatuses: Record<string, string> = {ok: '정상', restricted: '제한', halted: '정지'};
function table(rows:Row[],columns:[string,string,((v:any)=>string)?][]){return <div className="table-wrap"><table><thead><tr>{columns.map(([key,title])=><th key={key}>{title}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={r.key||i}>{columns.map(([key,,format])=><td key={key}>{format?format(r[key]):String(r[key]??'—')}</td>)}</tr>)}</tbody></table></div>;}
function option(rows:Row[],series:[string,string][],x='timestamp'){return {tooltip:{trigger:'axis'},legend:{type:'scroll',textStyle:{color:'#9ba8bd'}},grid:{left:85,right:25,top:50,bottom:50},xAxis:{type:'category',data:rows.map(r=>r[x])},yAxis:{type:'value',scale:true},dataZoom:[{type:'inside'}],series:series.map(([key,name])=>({name,type:'line',showSymbol:rows.length<3,data:rows.map(r=>r[key])}))};}
function reason(r:Row){const e=r.evidence||{};if(e.signal_close==null||e.sma_60==null)return '당시 신호 자료 없음';const active=e.signal_close>e.sma_60;const info=e.information?` · 정보 비중 배율 ${Number(e.information.multiplier).toFixed(3)}`:'';return e.strategy==='momentum'?`Momentum ${active?'활성':'비활성'} · 신호가격 ${num(e.signal_close)} / SMA60 ${num(e.sma_60)} · ${r.side==='buy'?'슬롯 목표까지 매수':'보유 수량 감축'}${info}`:`${e.strategy||'전략'} · 슬롯 목표에 따라 ${r.side==='buy'?'매수':'매도'}`;}
export default function PaperPerformance(){
 const [data,setData]=useState<Row|null>(null),[error,setError]=useState(''),[range,setRange]=useState('observations'),[revisionOnly,setRevisionOnly]=useState(true);
 useEffect(()=>{let active=true;async function load(){try{const response=await fetch('/api/paper-performance',{cache:'no-store'});if(!response.ok)throw new Error(`실적 조회 실패 (${response.status})`);const value=await response.json();if(active){setData(value);setError('');}}catch(e){if(active)setError(String(e));}}load();const timer=setInterval(load,30000);return()=>{active=false;clearInterval(timer);};},[]);
 if(!data)return <section className="panel"><p role={error?'alert':'status'}>{error||'paper 계좌 실적을 불러오는 중…'}</p></section>;
 if(data.status==='unavailable')return <><section className="panel"><p className="panel-note" role="status">{data.reason}</p></section>{data.llm_usage&&<PaperUsage usage={data.llm_usage}/>}</>;
 const account=data.account||{},pnl=data.pnl||{},stats=revisionOnly?data.current_revision_execution:data.execution;
 const allOrders: (PaperOrder & Row)[]=data.orders||[];
 const orders=allOrders.filter(r=>!revisionOnly||r.budget_revision===account.budget_revision);
 const openOrders=allOrders.filter(r=>!closedOrders.has(r.status));
 const risk=data.risk||{}, latest=data.latest_decisions;
 const riskLabel=riskStatuses[risk.status]||'확인 대기';
 const rows=data[range]||[],comparison=data.comparison||{};
 return <div data-testid="paper-performance">
 {(error||data.stale||data.status!=='ok')&&<div className="error" role="alert">{error||(data.stale?'실적 갱신 지연 · 마지막 수집 시각을 확인하세요.':'일부 자료 대사·수집 확인이 필요합니다.')} {(pnl.issues||[]).join(' / ')}</div>}
 <section className="panel"><div className="panel-title">PAPER · 실제 모의 계좌 실적</div><p className="panel-note">수집 {when(data.checked_at)} · 관측 시작 {when(data.tracking_started_at)} · 5분 저장 / 화면 30초 갱신</p><div className="metrics" style={{gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))"}}>{[['계좌 평가액',usd(account.equity)],['가용 현금',usd(account.cash)],['체결 기반 실현손익 · 비용 전',usd(pnl.realized_gross)],['체결 기반 미실현손익 · 비용 전',usd(pnl.unrealized_gross)]].map(([label,value])=><div className="metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><p className="panel-note">일간 평가액 변화 {usd(account.daily_equity_change)} ({pct(account.daily_equity_change_pct)}) · 관측 시작 대비 평가액 변화 {usd(account.change_since_tracking)} · 예산 {usd(account.budget_usd)}. 입출금은 매매 수익으로 계산하지 않습니다. 체결 손익은 자체 주문과 사용자가 확인한 수동 청산의 실제 체결을 평균원가로 대사한 금액이며 추정 비용을 차감하지 않습니다.</p></section>
 <PaperHoldings positions={data.positions||[]} orders={allOrders} observedAt={data.broker_observed_at}/>
 <section className="panel" data-testid="paper-order-status">
   <h2 className="panel-title">진행 중 주문과 리스크</h2>
   <p className="panel-note">리스크 {risk.stale ? `갱신 지연 · 마지막 상태 ${riskLabel}` : riskLabel}
     {risk.checked_at && ` · 리스크 확인 ${when(risk.checked_at)}`}
     {' · '}체결 원장 {pnl.ledger_status==='reconciled'?'대사 완료':'확인 필요'}
     {risk.halt_rules?.length>0 && ` · 정지 사유 ${risk.halt_rules.join(', ')}`}
   </p>
   {openOrders.length ? table(openOrders,[['symbol','종목'],['side','방향',v=>v==='buy'?'매수':'매도'],['qty','주문 수량',count],['filled_qty','체결 수량',count],['limit_price','지정가',usd],['status','상태',v=>statuses[v]||v],['submitted_at','제출 시각',when]]) : <p className="panel-note">진행 중인 자체 주문이 없습니다.</p>}
   {latest&&<p className="panel-note">최근 전략 판단 · 미국 거래일 {latest.execution_session} · 기록 {when(latest.captured_at)}</p>}
 </section>
 {data.llm_usage&&<PaperUsage usage={data.llm_usage}/>}
 <section className="panel"><div className="panel-title">계좌 평가액 이력</div><div className="controls"><label>기간<select aria-label="Paper history range" value={range} onChange={e=>setRange(e.target.value)}><option value="observations">수집 시작 이후 · 5분 관측</option><option value="daily_history">브로커 일별 계좌 이력</option></select></label></div>{rows.length?<Chart option={option(rows,[['equity','Paper account NAV / USD']])}/>:<p>해당 기간의 계좌 이력이 없습니다.</p>}<p className="panel-note">{range==='daily_history'?`전략 시작 전 계좌 이력과 진행 중 날짜가 포함될 수 있습니다. 브로커 기준 평가액 ${usd(data.history_base_value)} / ${data.history_base_value_asof||'—'}. 미입금 0원 구간 ${data.unfunded_points_excluded||0}개는 제외했습니다.`:'관측 사이의 값을 보간해 체결이나 수익을 만들어내지 않습니다.'}</p></section>
 <section className="panel"><div className="panel-title">주문·체결 대사</div><div className="controls"><label><input type="checkbox" checked={revisionOnly} onChange={e=>setRevisionOnly(e.target.checked)}/>현재 예산으로 낸 주문만 보기</label></div><div className="metrics" style={{gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))"}}>{[['수량 기준 체결률',pct(stats?.share_fill_rate)],['제출 / 체결 수량',`${stats?.requested_shares??0} / ${stats?.filled_shares??0}`],['체결 건수 / 전체 주문',`${stats?.filled_orders??0} / ${stats?.orders??0}`],['추정 비용 · 별도 표시',stats?.cost_estimate_missing_orders?`${usd(stats?.modeled_cost_estimate)} + 미확인 ${stats.cost_estimate_missing_orders}건`:usd(stats?.modeled_cost_estimate)]].map(([label,value])=><div className="metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>{!stats?.filled_shares&&<p data-testid="paper-no-fills">아직 체결 내역이 없습니다. 접수 주문은 손익 실적으로 계산하지 않습니다.</p>}{table(orders,[['symbol','종목'],['side','방향',v=>v==='buy'?'매수':'매도'],['qty','주문 수량'],['filled_qty','체결 수량'],['status','상태',v=>statuses[v]||v],['limit_price','지정가',usd],['fill_average_price','실제 체결 평균가',usd],['reference_change_bps','주문 기준가 대비 bp',num],['first_fill_delay_seconds','첫 체결까지 초',num],['modeled_cost_estimate','추정 비용',usd]])}<p className="panel-note">체결률 분모에는 취소된 제출 주문도 포함합니다. 주문 기준가 대비 변화는 개장 갭을 포함하므로 순수 체결 슬리피지가 아닙니다. 체결 평균가는 활동 내역과 원장 수량이 일치할 때 표시합니다.</p></section>
 <section className="panel"><div className="panel-title">주문 판단 근거</div>{orders.map((r:Row)=><details key={r.key}><summary>{r.symbol} {r.qty}주 · {reason(r)}</summary><p className="panel-note">{r.evidence_status==='captured_before_submission'?'주문 제출 전 저장한 근거':r.evidence_status==='reconstructed_after_submission'?'기존 주문의 근거를 사후 복원':'당시 근거 없음'} · 기준 시각 {when(r.evidence?.signal_available_at)} · 기록 {when(r.evidence?.captured_at)}</p><p className="panel-note">원본 기준가 {usd(r.reference_close)} · 비용 모형 기준가 {usd(r.modeled_reference_price)} · 실제 체결과 모형의 불리한 차이 {usd(r.actual_vs_model_usd)} (양수는 불리). 기준가는 자동 주문의 전일 종가 또는 명시적 재진입 요청의 완료 분봉 종가이며 실제 호가를 재현하지 않습니다.</p></details>)}{data.latest_decisions&&<><p className="panel-note">최근 세션 판단: {data.latest_decisions.execution_session}</p>{table(data.latest_decisions.decisions||[],[['symbol','종목'],['target_weight_within_slot','슬롯 목표',pct],['desired_qty','목표 수량',v=>Number(v).toFixed(0)],['decision','판단',v=>decisions[v]||v]])}</>}</section>
 {(data.approved_manual_closures||[]).length>0&&<section className="panel"><div className="panel-title">사용자가 확인한 수동 청산</div>{table(data.approved_manual_closures,[["symbol","종목"],["qty","매도 수량"],["filled_average_price","실제 체결 평균가",usd],["filled_at","체결 시각",when]])}<p className="panel-note">보유 수량과 실현손익에 반영합니다. 자동 주문의 체결률과 비용 추정에는 포함하지 않습니다.</p></section>}
 <section className="panel"><div className="panel-title">같은 기간의 백테스트와 비교</div>{comparison.status==='available'?<><Chart option={option(comparison.points,[['paper_index','Paper / base 100'],['backtest_index','Historical replay / base 100']],'session')}/><p className="panel-note">{comparison.basis}</p></>:<p>{comparison.reason||'같은 날짜의 자료가 아직 없습니다.'}</p>}</section>
 </div>;
}
