'use client';

import dynamic from 'next/dynamic';
import {useEffect, useState, type FormEvent, type ReactNode} from 'react';
import CryptoFeed from './CryptoFeed';
import {count, num, pct, usd} from './paper-format';
import styles from './ResearchLab.module.css';

const Chart = dynamic(() => import('./Chart'), {ssr: false});
type Data = Record<string, any>;
type Tool = keyof typeof tools;
const tools = {
  macro: '거시경제 · 환율', crypto: '암호화폐 시세', imports: '가져온 시장 데이터', valuation: '재무 · 가치평가', technical: '다중 시간봉',
  factors: '팩터 검증', statistics: '시계열 통계', ml: 'ML 실험', basket: '전략 리플레이',
  options: '옵션 분석', brief: '기업 비교 리서치',
};
const study = [
  ['cross_sectional_momentum', '횡단면 모멘텀'], ['pairs_rotation', '페어 롱온리 로테이션'],
  ['volatility_targeting', '변동성 목표 배분'], ['etf_allocation', 'SPY 슬롯 배분'],
];
const valuationModels = {
  fcff: 'FCFF / 역DCF', wacc: 'WACC', fcfe: 'FCFE', dividend: '배당 할인',
  residual: '잔여이익', segments: '사업부 합산',
};
const waccFields = [
  ['risk_free','무위험금리',.04], ['beta','베타',1], ['equity_risk_premium','주식 위험 프리미엄',.05],
  ['pretax_cost_of_debt','세전 부채 비용',.06], ['tax_rate','세율',.21],
  ['equity_value','자기자본 시장가치 (USD)',100], ['debt_value','부채 시장가치 (USD)',0],
] as const;

function Panel({title, children}: {title: string; children: ReactNode}) {
  return <section className="panel"><h2 className="panel-title">{title}</h2><div className={styles.body}>{children}</div></section>;
}

function Link({href, children}: {href?: string; children: ReactNode}) {
  return href && /^https:\/\//.test(href) ? <a className={styles.link} href={href} target="_blank" rel="noreferrer">{children}</a> : null;
}

function useRequest(path: string) {
  const [result, setResult] = useState<{path: string; data?: Data; error?: string}>();
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch('/api/' + path, {signal: controller.signal, cache: 'no-store'});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '입력과 자료를 확인하세요.');
        if (!controller.signal.aborted) setResult({path,data});
      } catch (error) {
        if (!controller.signal.aborted) setResult({path,error: String(error instanceof Error ? error.message : error)});
      }
    }
    void load();
    return () => controller.abort();
  }, [path]);
  return result?.path === path ? result : undefined;
}

function WithData({path, children}: {path: string; children: (data: Data) => ReactNode}) {
  const result = useRequest(path);
  if (!result) return <p role="status">조회 중…</p>;
  if (result.error) return <p className="error" role="alert">{result.error}</p>;
  if (!result.data || ['unavailable','missing'].includes(result.data.status)) return <p role="status">{result.data?.reason || '자료가 없습니다.'}</p>;
  return <>{children(result.data)}</>;
}

function Grid({headers, rows}: {headers:string[]; rows: ReactNode[][]}) {
  return <div className="table-wrap"><table><thead><tr>{headers.map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead>
    <tbody>{rows.map((row,i) => <tr key={i}>{row.map((cell,j) => <td key={j}>{cell ?? '—'}</td>)}</tr>)}</tbody></table></div>;
}

function Series({rows, date = 'period', keys}: {rows: Data[]; date?: string; keys: [string,string][]}) {
  return rows.length ? <Chart option={{
    tooltip:{trigger:'axis'}, legend:{top:0,textStyle:{color:'#aebed4'}}, grid:{left:76,right:20,top:45,bottom:40},
    xAxis:{type:'category',data:rows.map(r => r[date]?.slice(0,10))},
    yAxis:{type:'value',scale:true},dataZoom:[{type:'inside'}],
    series:keys.map(([key,name]) => ({name,type:'line',showSymbol:false,data:rows.map(r => r[key] == null ? null : Number(r[key]))})),
  }}/> : <p>표시할 관측치가 없습니다.</p>;
}

function NumberField({name, label, value, required}: {name:string; label:string; value?:number | string; required?:boolean}) {
  return <label>{label}<input type="number" step="any" required={required ?? (value !== undefined)} name={name} defaultValue={value}/></label>;
}

function formValues(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return Object.fromEntries([...new FormData(event.currentTarget)].filter(([,value]) => value !== '')
    .map(([key,value]) => [key, key === 'kind' ? value : Number(value)]));
}

function useCalculate() {
  const [data,setData] = useState<Data>();
  const [message,setMessage] = useState('');
  const [pending,setPending] = useState(false);
  async function calculate(path:string, payload?:unknown) {
    setPending(true);setData(undefined);setMessage('');
    try {
      const response = await fetch('/api/'+path, payload ? {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload),
      } : undefined);
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '입력값을 확인하세요.');
      setData(body);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '계산 실패');
    } finally {
      setPending(false);
    }
  }
  return {data,message,pending,calculate};
}

function FX() {
  const state = useCalculate();
  return <>
    <form className={styles.form} onSubmit={event => void state.calculate('research/fx?amount='+encodeURIComponent(String(formValues(event).amount)))}>
      <NumberField name="amount" label="금액 (USD)" value={100}/>
      <button type="submit" className="primary" disabled={state.pending}>KRW 환산</button>
    </form>
    {state.message && <p role="alert">{state.message}</p>}
    {state.data && <p>{usd(state.data.usd)} = ₩{count(state.data.krw)} · {state.data.period} 기준 {count(state.data.rate)} KRW/USD · <Link href={state.data.url}>FRED 원문</Link></p>}
  </>;
}

function Macro() {
  const [series,setSeries] = useState('DEXKOUS');
  return <Panel title="미국 거시 지표 · 환율">
    <WithData path="research/macro">{data => {
      const entries = Object.values(data.series) as Data[];
      const selected = data.series[series] || entries[0];
      return <>
        {entries.length > 0 && <label className={styles.inline}>지표<select value={selected.id} onChange={e => setSeries(e.target.value)}>
          {entries.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}
        </select></label>}
        {selected && <><p>{selected.observations.at(-1)?.period} · {selected.observations.at(-1)?.value} {selected.unit} · <Link href={selected.url}>FRED 원문</Link></p>
          <Series rows={selected.observations} keys={[['value',selected.label]]}/></>}
        {data.curve?.length > 0 && <p>미 국채 10년물 − 2년물 · {data.curve.at(-1).spread_pp} %p ({data.curve.at(-1).period})</p>}
        <p className="muted">최신 수정 시계열 · 수집 {data.checked_at} UTC</p>
        {Object.keys(data.failures || {}).length > 0 && <p className="muted">수집 확인 필요 · {Object.keys(data.failures).join(', ')}</p>}
        <h3>공식 발표 일정</h3>
        {(Object.values(data.calendar) as Data[]).filter(source => source.events?.length).map(source => <div key={source.url}>
          <Link href={source.url}>{source.source}</Link>
          <Grid headers={['날짜 / 시간','일정']} rows={source.events
            .filter((entry: Data) => (entry.scheduled_at || entry.scheduled_date) >= new Date().toISOString().slice(0,10))
            .slice(0,8).map((entry: Data) => [entry.scheduled_at || entry.scheduled_date, entry.title])}/>
        </div>)}
      </>;
    }}</WithData>
    <FX/>
  </Panel>;
}

function Crypto() {
  const [symbol,setSymbol] = useState('BTC-USD');
  return <Panel title="Coinbase 암호화폐 관측">
    <WithData path="research/crypto">{data => {
      const entries = Object.values(data.products) as Data[];
      const product = data.products[symbol] || entries[0];
      if (!product) return <p>공개 시세를 가져오지 못했습니다.</p>;
      const micro = product.microstructure;
      return <>
        <label className={styles.inline}>마켓<select value={product.symbol} onChange={e => setSymbol(e.target.value)}>
          {entries.map(p => <option key={p.symbol}>{p.symbol}</option>)}
        </select></label>
        <p>{product.source} · 수집 {product.collected_at} · <Link href={product.source_url}>시세 원문</Link></p>
        <Series rows={product.bars} date="timestamp" keys={[['close','일봉 종가 (USD)']]}/>
        <CryptoFeed key={product.symbol} symbol={product.symbol}/>
        {micro && <>
          <p className="muted">호가 관측 {micro.book.available_at} · {micro.basis}</p>
          <Grid headers={['매수 호가 (USD)','수량','매도 호가 (USD)','수량']} rows={micro.book.bids.map((bid:Data,i:number) =>
            [bid.price,bid.size,micro.book.asks[i]?.price,micro.book.asks[i]?.size])}/>
          <details><summary>최근 거래 틱</summary>
            <Grid headers={['거래 시각 (UTC)','방향','가격 (USD)','수량']} rows={micro.trades.rows.map((row:Data) => [row.timestamp,row.side,row.price,row.size])}/>
          </details>
        </>}
        {!!Object.keys(data.failures || {}).length && <p className="muted">조회 확인 필요 · {Object.keys(data.failures).join(', ')}</p>}
      </>;
    }}</WithData>
  </Panel>;
}

function ImportedChart({symbol}: {symbol:string}) {
  return <WithData path={'research/imported-markets/'+encodeURIComponent(symbol)}>{data => <>
    <p>{data.metadata.source} · {data.metadata.exchange_timezone} · {data.metadata.currency} · {data.collected_at}</p>
    <Series rows={data.bars} date="timestamp" keys={[['close','종가 ('+data.metadata.currency+')']]}/>
  </>}</WithData>;
}

function ImportedMarkets() {
  const [active,setActive] = useState('');
  return <Panel title="로컬 시장 데이터">
    <WithData path="research/imported-markets">{data => {
      const symbol = data.symbols.includes(active) ? active : data.symbols[0];
      return symbol ? <>
        <label className={styles.inline}>가져온 종목<select value={symbol} onChange={event => setActive(event.target.value)}>
          {data.symbols.map((name:string) => <option key={name}>{name}</option>)}
        </select></label>
        <ImportedChart symbol={symbol}/>
      </> : <p>가져온 데이터 파일이 없습니다. 공급자에게 사용 권한을 받은 OHLCV를 로컬 가져오기로 추가할 수 있습니다.</p>;
    }}</WithData>
  </Panel>;
}

function ValueCalculator({profile}: {profile?: Data}) {
  const [method,setMethod] = useState<keyof typeof valuationModels>('fcff');
  const state = useCalculate();
  function submit(event: FormEvent<HTMLFormElement>) {
    const fields = formValues(event);
    let payload: unknown = {[method]: fields};
    if (method === 'fcff') {
      const {reverse_dcf_price,bull_growth,bear_growth,...inputs} = fields;
      payload = {dcf_assumptions: inputs, reverse_dcf_price,bull_growth,bear_growth};
    } else if (method === 'segments') {
      payload = {segments: [{name:'사업부 1',enterprise_value:fields.first},{name:'사업부 2',enterprise_value:fields.second}],
                 segment_net_debt:fields.segment_net_debt};
    }
    void state.calculate('research/valuation',payload);
  }
  return <>
    <label className={styles.inline}>평가 모델<select value={method} onChange={event => setMethod(event.target.value as keyof typeof valuationModels)}>
      {Object.entries(valuationModels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    <p className="muted">표시된 SEC 입력과 직접 선택한 전망을 확인하세요. 비율 입력은 0.10 = 10%입니다.</p>
    <form key={method} className={styles.form} onSubmit={submit}>
      {method === 'fcff' && <>
        <NumberField name="revenue" label="기준 매출 (USD)" required value={profile?.revenue ?? undefined}/>
        <NumberField name="shares" label="발행주식 수" required value={profile?.shares ?? undefined}/>
        <NumberField name="operating_margin" label="영업이익률 가정" required value={profile?.operating_margin ?? undefined}/>
        <NumberField name="tax_rate" label="세율 가정" required value={profile?.tax_rate ?? undefined}/>
        <NumberField name="net_debt" label="순부채 (USD)" required value={profile?.net_debt ?? undefined}/>
        <NumberField name="growth" label="성장률 가정" value={0.08}/>
        <NumberField name="wacc" label="WACC 가정" value={0.09}/>
        <NumberField name="terminal_growth" label="영구 성장률 가정" value={0.025}/>
        <NumberField name="depreciation_ratio" label="감가상각 / 매출 가정" value={0.03}/>
        <NumberField name="capex_ratio" label="CAPEX / 매출 가정" value={0.06}/>
        <NumberField name="working_capital_ratio" label="운전자본 / 매출 가정" value={0.12}/>
        <NumberField name="reverse_dcf_price" label="역DCF 기준 주가 (USD)" required={false} value={profile?.price}/>
        <NumberField name="bull_growth" label="낙관 성장률 (선택)"/>
        <NumberField name="bear_growth" label="비관 성장률 (선택)"/>
      </>}
      {method === 'wacc' && waccFields.map(([name,label,value]) => <NumberField key={name} name={name} label={label} value={value}/>)}
      {(method === 'fcfe' || method === 'dividend' || method === 'residual') && <>
        {method === 'residual' ? <><NumberField name="book_value" label="장부가치 (USD)" value={100}/><NumberField name="net_income" label="순이익 (USD)" value={12}/></>
          : <NumberField name="cash_flow" label={method === 'dividend' ? '직전 주당 배당금 (USD)' : '직전 FCFE (USD)'} value={1}/>}
        <NumberField name="discount" label="할인율" value={0.1}/><NumberField name="growth" label="영구 성장률" value={0.03}/>
      </>}
      {method === 'segments' && <>
        <NumberField name="first" label="사업부 1 기업가치 (USD)" value={100}/>
        <NumberField name="second" label="사업부 2 기업가치 (USD)" value={100}/>
        <NumberField name="segment_net_debt" label="연결 순부채 (USD)" value={0}/>
      </>}
      <button type="submit" className="primary" disabled={state.pending}>가치 계산</button>
    </form>
    {state.message && <p role="alert">{state.message}</p>}
    {state.data && <Grid headers={['모델','결과','값']} rows={Object.entries(state.data.models as Data).flatMap(([name,values]) =>
      Object.entries(values).filter(([,value]) => typeof value === 'number' || typeof value === 'string').map(([key,value]) => [name,key,typeof value === 'number' ? num(value,4) : String(value)]))}/>}
    {state.data?.models.fcff && <p>FCFF 불확실성 범위 · {usd(state.data.models.fcff.monte_carlo.p05)}–{usd(state.data.models.fcff.monte_carlo.p95)} (P05–P95)</p>}
  </>;
}

function Valuation({symbol}: {symbol:string}) {
  const profile = useRequest('research/valuation/'+symbol);
  return <Panel title={symbol+' · 재무와 가치평가'}>
    {profile?.data?.multiples && <><p>SEC TTM {profile.data.period_end || '—'} · <Link href={profile.data.source_url}>공시 출처</Link></p>
      <Grid headers={['배수 · 수익률','값']} rows={Object.entries(profile.data.multiples).map(([name,value]) =>
        [name, name.endsWith('yield') ? pct(value as number) : num(value as number,3)])}/></>}
    <WithData path={'research/fundamentals/'+symbol+'/scores'}>{data =>
      <Grid headers={['고급 지표','값','단위','계산 기준']} rows={data.metrics.map((r:Data) => [r.name,num(r.value),r.unit,r.formula])}/>}
    </WithData>
    <ValueCalculator key={symbol+'-'+(profile?.data?.period_end || '')} profile={profile?.data}/>
  </Panel>;
}

function Options() {
  const state = useCalculate();
  const [mode,setMode] = useState('price');
  function submit(event: FormEvent<HTMLFormElement>) {
    const values = formValues(event);
    if (mode === 'iv') {
      const params = new URLSearchParams(Object.entries(values).map(([key,value]) => [key,String(value)]));
      void state.calculate('research/options/implied-volatility?'+params);
    } else {
      void state.calculate('options',values);
    }
  }
  return <Panel title="유럽형 옵션 계산기">
    <p>사용자 입력으로 Black–Scholes 가격, Greeks 또는 내재변동성을 계산합니다.</p>
    <label className={styles.inline}>계산<select value={mode} onChange={event => setMode(event.target.value)}>
      <option value="price">가격과 Greeks</option><option value="iv">내재변동성</option>
    </select></label>
    <form key={mode} className={styles.form} onSubmit={submit}>
      <label>옵션<select name="kind"><option value="call">콜</option><option value="put">풋</option></select></label>
      <NumberField name="spot" label="기초자산 가격" value={100}/><NumberField name="strike" label="행사가" value={100}/>
      <NumberField name="years" label="잔존 기간 (년)" value={1}/><NumberField name="rate" label="무위험금리" value={0.04}/>
      {mode === 'iv' ? <NumberField name="price" label="관측 옵션 가격" value={10}/> : <NumberField name="volatility" label="연변동성" value={0.2}/>}
      <button className="primary" type="submit" disabled={state.pending}>옵션 계산</button>
    </form>
    {state.message && <p role="alert">{state.message}</p>}
    {state.data && <Grid headers={['지표','값']} rows={Object.entries(state.data).map(([name,value]) => [name,typeof value === 'number' ? num(value,5) : String(value)])}/>}
  </Panel>;
}

function AssetPeer({symbol, symbols}: {symbol:string; symbols:string[]}) {
  const [peer,setPeer] = useState(symbols.find(value => value !== symbol) || '');
  return <Panel title={symbol+' · 시계열 통계'}>
    <label className={styles.inline}>비교 종목<select value={peer} onChange={e => setPeer(e.target.value)}>
      <option value="">단일 종목</option>{symbols.filter(value => value !== symbol).map(value => <option key={value}>{value}</option>)}
    </select></label>
    <WithData path={'research/timeseries/'+symbol+(peer?'?peer='+peer:'')}>{data => <>
      <p className="muted">{data.source} · {data.observations}개 관측 · {data.basis}</p>
      <Grid headers={['검정','통계량','p값','상태']} rows={Object.entries(data.tests as Data).map(([key,row]) =>
        [key,num(row.statistic,4),num(row.p_value,4),row.reason || row.status])}/>
      <Grid headers={['모델','다음 일 수익률','다음 일 변동성','AIC','상태']} rows={Object.entries(data.models as Data).map(([key,row]) =>
        [key,pct(row.next_return),pct(row.next_daily_volatility),num(row.aic),row.reason || row.status])}/>
      {data.granger_predictability && <Grid headers={['대상','선행 비교','p값','보정 p값']} rows={data.granger_predictability.map((row:Data) => [row.target,row.lagged,num(row.p_value,4),num(row.bh_adjusted_p_value,4)])}/>}
    </>}</WithData>
  </Panel>;
}

function Technical({symbol}: {symbol:string}) {
  const [timeframe,setTimeframe] = useState('daily');
  return <Panel title={symbol+' · 다중 시간봉과 시장 폭'}>
    <label className={styles.inline}>시간봉<select value={timeframe} onChange={e => setTimeframe(e.target.value)}>
      <option value="daily">일봉</option><option value="weekly">주봉</option><option value="monthly">월봉</option>
    </select></label>
    <WithData path={'research/technical/'+symbol+'?timeframe='+timeframe}>{data => <>
      <p className="muted">{data.source} · {data.as_of} · {data.basis}</p>
      <Series rows={data.values} date="timestamp" keys={[['close','종가 (USD)'],['sma_20','SMA 20']]}/>
      {data.values.some((row:Data) => row.iex_session_vwap_raw != null) && <>
        <p className="muted">{data.vwap_basis}</p>
        <Series rows={data.values} date="timestamp" keys={[['iex_session_vwap_raw','IEX 정규장 VWAP (USD)']]}/>
      </>}
      <Series rows={data.breadth} date="timestamp" keys={[['advancing','상승 종목 수'],['declining','하락 종목 수'],['above_sma_50','SMA50 상회']]}/>
    </>}</WithData>
  </Panel>;
}

function Basket() {
  const [method,setMethod] = useState(study[0][0]);
  return <Panel title="전략 비교 · IEX 분봉">
    <label className={styles.inline}>전략<select value={method} onChange={event => setMethod(event.target.value)}>
      {study.map(([key,label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    <WithData path={'research/basket/'+method+'?days=63'}>{data => <>
      <p>{data.evaluation_sessions}거래일 · 순수익률 {pct(data.metrics.total_return)} · 최대낙폭 {pct(data.metrics.max_drawdown)}</p>
      <p className="muted">{data.source} · {data.as_of} · {data.basis}</p>
      <Series rows={data.curve} date="session" keys={[['equity','시뮬레이션 평가액 (USD)']]}/>
    </>}</WithData>
  </Panel>;
}

function Brief({symbols}: {symbols:string[]}) {
  const [first,setFirst] = useState(symbols[0]);
  const [second,setSecond] = useState(symbols[1]);
  return <Panel title="기업 비교 리서치">
    <div className={styles.form}>
      <label>종목 1<select value={first} onChange={e => setFirst(e.target.value)}>{symbols.filter(value => value !== second).map(s => <option key={s}>{s}</option>)}</select></label>
      <label>종목 2<select value={second} onChange={e => setSecond(e.target.value)}>{symbols.filter(value => value !== first).map(s => <option key={s}>{s}</option>)}</select></label>
    </div>
    <WithData path={'research/brief?symbols='+first+','+second}>{data => <>
      <p className="muted">{data.basis}</p>
      {data.rows.map((row:Data) => <article key={row.symbol} className={styles.card}>
        <h3>{row.symbol}</h3>
        <p>{row.period_end || '기간 미확인'} · 매출 성장 {pct(row.revenue_growth)} · 영업이익률 {pct(row.operating_margin)} · <Link href={row.financial_url}>SEC 근거</Link></p>
        {row.period_end && <><p>검증 가설 · {row.hypothesis}</p><p>반대 가설 · {row.counter_hypothesis}</p></>}
        {row.claims.length > 0 && <details><summary>저장된 Claude 근거 {row.claims.length}개</summary>
          {row.claims.map((claim:Data,index:number) => <blockquote key={index}>{claim.summary}<br/>“{claim.quote}” · <Link href={claim.url}>원문</Link></blockquote>)}
        </details>}
      </article>)}
    </>}</WithData>
  </Panel>;
}

function FactorValidation() {
  const [neutral,setNeutral] = useState('size');
  return <Panel title="횡단면 팩터 검증">
    <WithData path="research/factor-validation">{data => <>
      <p className="muted">{data.source} · {data.universe_size}종목 · {data.basis}</p>
      <Grid headers={['보유 기간','표본','평균 Rank IC','ICIR']} rows={data.horizons.map((row:Data) =>
        [row.holding_sessions+'세션',row.samples,num(row.mean_rank_ic,4),num(row.icir,4)])}/>
      {data.horizons.map((row:Data) => <details key={row.holding_sessions}><summary>{row.holding_sessions}세션 관측</summary>
        <Grid headers={['신호일','Rank IC','그룹별 수익률','상위 그룹 교체율']} rows={row.events.map((event:Data) =>
          [event.timestamp.slice(0,10),num(event.rank_ic,3),event.quantile_returns.map(pct).join(' / '),pct(event.top_group_turnover)])}/>
      </details>)}
    </>}</WithData>
    <label className={styles.inline}>현재 점수 중립화<select value={neutral} onChange={event => setNeutral(event.target.value)}>
      <option value="size">시가총액</option><option value="sic">SEC SIC 위험 그룹</option><option value="size_and_sic">시가총액 + SEC SIC</option>
    </select></label>
    <WithData path={'research/factor-neutralization?by='+neutral}>{data => <>
      <p className="muted">{data.basis} · 기준 {data.as_of}</p>
      <Grid headers={['종목','분류','원 점수','중립화 점수','제거한 노출']} rows={data.rows.map((row:Data) =>
        [row.symbol,row.classification,num(row.score,4),num(row.neutral_score,4),num(row.removed_exposure,4)])}/>
    </>}</WithData>
  </Panel>;
}

function ML({symbol}: {symbol:string}) {
  return <Panel title={symbol+' · 시계열 ML 실험'}>
    <WithData path={'research/ml/'+symbol}>{data => <>
      <p className="muted">{data.source} · 실험 {data.experiment.slice(0,12)} · {data.manifest.version}</p>
      <Grid headers={['모델','구간','표본','MSE','방향 정확도']} rows={data.models.map((row:Data) =>
        [row.model,row.fold,row.samples,num(row.mse,8),pct(row.direction_accuracy)])}/>
      <details><summary>구간별 특성 변화와 Ridge 기여도</summary>
        <Grid headers={['구간','학습 라벨 종료','평가 시작','특성 변화 (학습 표준편차 단위)']} rows={data.folds.map((row:Data,index:number) =>
          [index+1,row.train_last_target,row.test_start,Object.entries(row.feature_shift_train_std).map(([key,v]) => key+' '+num(v as number,3)).join(' · ')])}/>
        <Grid headers={['구간','선형 SHAP 평균 절댓값']} rows={data.models.filter((row:Data) => row.mean_abs_linear_shap).map((row:Data) =>
          [row.fold,Object.entries(row.mean_abs_linear_shap).map(([key,v]) => key+' '+num(v as number,5)).join(' · ')])}/>
      </details>
    </>}</WithData>
  </Panel>;
}

export default function ResearchLab({symbol,symbols}: {symbol:string; symbols:string[]}) {
  const [active,setActive] = useState<Tool>('macro');
  const [pinned,setPinned] = useState<Tool[]>([]);
  const [expanded,setExpanded] = useState<Tool[]>([]);
  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem('quantcore-research-widgets') || '[]');
      if (Array.isArray(saved)) setPinned(saved.filter(key => Object.hasOwn(tools,key)));
    } catch {}
  },[]);
  function toggle() {
    const next = pinned.includes(active) ? pinned.filter(item => item !== active) : [...pinned,active];
    setPinned(next);
    try { localStorage.setItem('quantcore-research-widgets',JSON.stringify(next)); } catch {}
  }
  const panels: Record<Tool, ReactNode> = {
    macro:<Macro/>,crypto:<Crypto/>,imports:<ImportedMarkets/>,valuation:<Valuation key={symbol} symbol={symbol}/>,technical:<Technical symbol={symbol}/>,
    factors:<FactorValidation/>,statistics:<AssetPeer key={symbol} symbol={symbol} symbols={symbols}/>,
    ml:<ML symbol={symbol}/>,basket:<Basket/>,options:<Options/>,brief:<Brief symbols={symbols}/>,
  };
  return <div data-testid="research-lab">
    <div className={styles.form}>
      <label>연구 도구<select aria-label="연구 도구" value={active} onChange={event => setActive(event.target.value as Tool)}>
        {Object.entries(tools).map(([key,title]) => <option key={key} value={key}>{title}</option>)}
      </select></label>
      <button type="button" className="primary" onClick={toggle}>{pinned.includes(active) ? '고정 해제' : '도구 고정'}</button>
      {pinned.filter(item => item !== active).map(item => <button type="button" key={item} className="primary" onClick={() => setActive(item)}>{tools[item]}</button>)}
    </div>
    {panels[active]}
    {pinned.filter(item => item !== active).map(item =>
      <details key={item} className={styles.widget} onToggle={event => {
        const open = event.currentTarget.open;
        setExpanded(items => open ? [...new Set([...items,item])] : items.filter(name => name !== item));
      }}><summary>{tools[item]}</summary>{expanded.includes(item) && panels[item]}</details>)}
  </div>;
}
