import {count, num, pct, usd, when} from './paper-format';

type Holding = {
  symbol: string;
  qty: string;
  avg_entry_price: string;
  current_price: string;
  market_value: string;
  unrealized_pl: string;
  unrealized_plpc: string;
};
type Source = {url?: string; source_url?: string; available_at?: string; manager?: string; kind?: string; model?: string};
type Component = 'financials' | 'institutions' | 'news' | 'earnings';
type Evidence = {
  strategy?: string;
  signal_close?: number;
  sma_60?: number;
  signal_available_at?: string;
  target_weight_within_slot?: string;
  execution_reference_type?: string;
  execution_reference_bar_end?: string;
  information?: {
    multiplier?: number;
    cutoff?: string;
    scores?: Partial<Record<Component, number | null>>;
    sources?: Partial<Record<Component, Source | Source[]>>;
    details?: {news_method?: string};
  } | null;
};
export type PaperOrder = {
  key: string;
  symbol: string;
  side: string;
  qty: number;
  status: string;
  limit_price: number;
  submitted_at?: string;
  filled_qty: number;
  last_fill_at?: string;
  fill_average_price?: number;
  evidence_status?: string;
  evidence?: Evidence;
};

const components: [Component, string][] = [
  ['financials', 'SEC 재무'], ['institutions', 'SEC 13F'], ['news', '뉴스'], ['earnings', 'Claude 등 LLM 실적 분석'],
];
const sourceKinds: Record<string, string> = {
  transcript: '어닝콜 녹취록', earnings_release: '공식 실적 발표문', cfo_commentary: 'CFO 설명자료',
};
const newsMethods: Record<string, string> = {
  'literal risk-topic count; not LLM sentiment': '기사의 위험 키워드 집계',
  'validated LLM sentiment 70% + actual risk-topic evidence 30%': '검증된 LLM 뉴스 해석 70% + 위험 키워드 집계 30%',
};

function sourceUrl(source: Source) {
  const href = source.url || source.source_url;
  return href && /^https?:\/\//i.test(href) ? href : undefined;
}

function latestBuys(orders: PaperOrder[]) {
  const buys = new Map<string, PaperOrder>();
  for (const order of orders) {
    if (order.side !== 'buy' || order.filled_qty <= 0 || !order.last_fill_at) continue;
    const previousAt = buys.get(order.symbol)?.last_fill_at;
    if (!previousAt || Date.parse(order.last_fill_at) > Date.parse(previousAt)) buys.set(order.symbol, order);
  }
  return buys;
}

function BuyReason({order}: {order: PaperOrder}) {
  const evidence = order.evidence;
  const info = evidence?.information;
  const momentum = evidence?.strategy === 'momentum' && evidence.signal_close != null && evidence.sma_60 != null;
  const active = momentum && Number(evidence.signal_close) > Number(evidence.sma_60);
  const newsMethod = info?.details?.news_method;
  return <div className="paper-buy-reason">
    <p className="paper-buy-heading">최근 매수 체결 {count(order.filled_qty)}주 · 평균 {usd(order.fill_average_price)}</p>
    <p className="muted">체결 {when(order.last_fill_at)}{order.evidence_status === 'reconstructed_after_submission' && ' · 주문 근거 사후 복원'}</p>
    {momentum ? <p>
      {active ? 'Momentum 매수 신호' : 'Momentum 신호 비활성'} · 완료 일봉 종가 <strong>{usd(evidence.signal_close)}</strong>
      {' '}{active ? '>' : '≤'} <strong>{usd(evidence.sma_60)}</strong> (60일 이동평균)
    </p> : <p>{evidence?.strategy ? `기록된 전략 ${evidence.strategy}` : '이 매수의 당시 신호 자료가 없습니다.'}</p>}
    {evidence?.target_weight_within_slot != null && <p>
      종목 슬롯 목표 <strong>{pct(evidence.target_weight_within_slot)}</strong>
      {info?.multiplier != null && ` · 정보 조정 배율 ${num(info.multiplier, 3)}×`}
    </p>}
    {evidence?.signal_available_at && <details className="paper-evidence">
      <summary>매수 근거와 원문</summary>
      <p className="muted">일봉 신호 사용 가능 {when(evidence.signal_available_at)}
        {info?.cutoff && <><br/>정보 반영 기준 {when(info.cutoff)}</>}
        {evidence.execution_reference_type === 'completed_regular_minute' && <><br/>재진입 지정가 기준 · IEX 완료 분봉 {when(evidence.execution_reference_bar_end)}</>}
      </p>
      {info && <ul>{components.map(([key, label]) => {
        const score = info.scores?.[key];
        const source = info.sources?.[key];
        const sources = Array.isArray(source) ? source : source ? [source] : [];
        return <li key={key}>
          <strong>{label}</strong> · {score == null ? '반영할 자료 없음' : `배분 점수 ${num(score, 3)}`}
          {key === 'news' && newsMethod && newsMethods[newsMethod] && <div className="muted">{newsMethods[newsMethod]}</div>}
          {score != null && sources.map((item, index) => {
            const href = sourceUrl(item);
            const title = item.manager || (item.kind && sourceKinds[item.kind]) || `원문${sources.length > 1 ? ` ${index + 1}` : ''}`;
            return href && <div key={index} className="paper-source">
              <a href={href} target="_blank" rel="noreferrer">{title}</a>
              {item.model && ` · ${item.model}`}
              {item.available_at && ` · 사용 가능 ${when(item.available_at)}`}
            </div>;
          })}
        </li>;
      })}</ul>}
    </details>}
  </div>;
}

export default function PaperHoldings({positions, orders, observedAt}: {
  positions: Holding[]; orders: PaperOrder[]; observedAt?: string;
}) {
  const buys = latestBuys(orders);
  return <section className="panel" data-testid="paper-holdings">
    <h2 className="panel-title">보유 종목과 매수 근거</h2>
    <p className="panel-note">Alpaca 모의 계좌 평가 {when(observedAt)} · 보유 종목별 자체 주문의 최근 매수 체결</p>
    {positions.length ? <div className="paper-holding-grid">
      {positions.map(position => {
        const buy = buys.get(position.symbol);
        return <article className="paper-holding" key={position.symbol} aria-label={position.symbol}>
          <div className="paper-holding-heading"><h3>{position.symbol}</h3><span>{count(position.qty)}주 보유</span></div>
          <dl className="paper-holding-values">
            <div><dt>평가액</dt><dd>{usd(position.market_value)}</dd></div>
            <div><dt>미실현손익</dt><dd className={Number(position.unrealized_pl) < 0 ? 'paper-loss' : Number(position.unrealized_pl) > 0 ? 'paper-gain' : ''}>{usd(position.unrealized_pl)} ({pct(position.unrealized_plpc)})</dd></div>
            <div><dt>보유 평균 원가</dt><dd>{usd(position.avg_entry_price)}</dd></div>
            <div><dt>최근 평가 가격</dt><dd>{usd(position.current_price)}</dd></div>
          </dl>
          {buy ? <BuyReason order={buy}/> : <p className="panel-note">이 종목에 연결할 수 있는 매수 체결 기록이 없습니다.</p>}
        </article>;
      })}
    </div> : <p className="panel-note">현재 보유 종목이 없습니다.</p>}
  </section>;
}
