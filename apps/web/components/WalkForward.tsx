'use client';
import dynamic from 'next/dynamic';
import {useEffect,useState} from 'react';
const Chart=dynamic(()=>import('./Chart'),{ssr:false});
const pct=(x:any)=>x==null?'—':(x*100).toFixed(2)+'%';
const names:Record<string,string>={selected_oos:'기간별 선택 전략',fixed_momentum_60:'고정 Momentum60',always_active_slots:'상시 보유·같은 리스크',selected_double_cost:'선택 전략·비용 2배'};
export default function WalkForward(){
 const [report,setReport]=useState<any>(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;fetch('/api/walk-forward',{cache:'no-store'}).then(async r=>{if(!r.ok)throw new Error('기간 분리 검증 조회 실패');return r.json();}).then(r=>{if(active)setReport(r);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[]);
 if(error)return <section className="panel"><p role="alert">{error}</p></section>;
 if(!report)return <section className="panel">기간 분리 검증 결과를 불러오는 중…</section>;
 if(report.status==='unavailable')return <section className="panel"><p>{report.reason}</p></section>;
 const rows=Object.entries(report.results) as [string,any][];const curve=rows[0][1].curve;
 return <section className="panel" data-testid="walk-forward"><div className="panel-title">시간 순서대로 선택하고 이후 구간에서 검증</div><p className="panel-note">{report.metadata.oos_period.join(' → ')} · {report.metadata.oos_sessions}거래일 · 총 $100,000 단일 계좌 · 같은 지정가·리스크·비용. 검증 구간 Sharpe로 후보를 선택하고 다음 구간을 평가했습니다. paper 전략을 자동 변경하지 않습니다.</p><div className="table-wrap"><table><thead><tr><th>시나리오</th><th>수익률</th><th>최대 낙폭</th><th>평균 투자 비중</th></tr></thead><tbody>{rows.map(([name,r])=><tr key={name}><td>{names[name]}</td><td>{pct(r.metrics.total_return)}</td><td>{pct(r.metrics.max_drawdown)}</td><td>{pct(r.metrics.average_gross_weight)}</td></tr>)}</tbody></table></div><Chart option={{tooltip:{trigger:'axis'},legend:{type:'scroll',textStyle:{color:'#9ba8bd'}},grid:{left:70,right:20,top:50,bottom:50},xAxis:{type:'category',data:curve.map((r:any)=>r.session)},yAxis:{type:'value',scale:true},dataZoom:[{type:'inside'}],series:rows.map(([name,r])=>({name:names[name],type:'line',showSymbol:false,data:r.curve.map((p:any)=>p.equity)}))}}/><div className="table-wrap"><table><thead><tr><th>구간</th><th>개발 이력</th><th>선택용 검증 기간</th><th>이후 평가 기간</th><th>선택 전략</th><th>평가 수익률</th></tr></thead><tbody>{report.decisions.map((d:any)=><tr key={d.fold}><td>{d.kind==='reserved_holdout'?'최종 분리 구간':d.fold}</td><td>{d.training.join(' → ')}</td><td>{d.validation.join(' → ')}</td><td>{d.test.join(' → ')}</td><td>{d.selected}</td><td>{pct(d.oos.selected_oos.total_return)}</td></tr>)}</tbody></table></div><p className="panel-note">이번 최종 구간은 선택 과정에서 제외했지만, 이 자료는 앞선 전체 기간 분석에 이미 사용됐습니다. 완전히 처음 보는 외부 검증 자료라고 주장하지 않습니다. 후보는 고정 규칙으로 학습 가중치가 없으며 개발 이력 다음의 검증 구간으로 규칙을 선택했습니다. 과거 시점의 기업 분류를 확인할 수 없어 이 실험은 미분류 40% 한도를 유지합니다.</p><p className="panel-note">선택 전략 − 고정 Momentum60 수익률 차이의 조건부 95% 구간: {report.paired_uncertainty.difference_total_return_95_interval.map(pct).join(' ~ ')}. 표본·선택 편향이 제거됐다는 의미는 아닙니다.</p></section>;
}
