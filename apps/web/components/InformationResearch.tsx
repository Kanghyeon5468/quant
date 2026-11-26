'use client';

import {useEffect, useState, type ReactNode} from 'react';
import styles from './InformationResearch.module.css';
import {count, num, pct} from './paper-format';

type NewsArticle = {
  id: string;
  headline: string;
  url: string;
  source: string | null;
  created_at: string;
  updated_at: string;
  available_at: string;
  topics: string[];
  numeric_mentions: string[];
};
type News = {
  status: string;
  articles: NewsArticle[];
  matching_articles: number;
  snapshot: {collected_at: string; truncated?: boolean} | null;
  stale: boolean;
};
type Filing = {
  manager: string;
  status: string;
  prior_report_date: string | null;
  report_date: string;
  source_url: string;
  holdings: {
    ticker: string | null;
    cusip: string;
    class: string;
    share_type: string;
    put_call: string | null;
    shares: string;
    split_adjusted_prior_shares: string | null;
    change: string;
    change_fraction: number | null;
  }[];
};
type Earnings = {
  reason: string;
  documents: {document_key: string; fiscal_year: number; quarter: string; kind: string; available_at: string; source_url: string}[];
  failures: {symbol?: string; kind?: string; reason: string}[];
  comparisons: {
    symbol: string; prior_quarter: string; current_quarter: string;
    topics: {topic: string; prior: {mentions: number}; current: {mentions: number}; mention_change: number}[];
  }[];
};
type Analysis = {
  analysis_key: string;
  kind: string;
  model: string;
  sentiment: number | null;
  article_id: string | null;
  article_updated_at: string | null;
  fiscal_year: number | null;
  quarter: string | null;
  chunk: number;
  total_chunks: number;
  available_at: string;
  source_url: string;
  claims: {summary: string; speaker: string | null; quote: string; source_url?: string}[];
};
type ModelReport = {
  status: string;
  configuration: {status?: string; provider?: string; model?: string};
  analyses: Analysis[];
};
type Information = {
  status: string;
  reason?: string;
  news?: News;
  earnings_calls?: Earnings;
  llm?: ModelReport;
  institutions?: {managers: Filing[]};
  model_integration?: {status: string; reason: string};
};
const decisionComponents = {financials: '실제 재무', institutions: '기관 보유량 변화', news: '뉴스', earnings: '실적 자료 LLM'};
type Decision = {
  status?: string;
  reason?: string;
  target_weight_within_slot?: number;
  effective_target_weight_within_slot?: number;
  decision_policy_version?: string;
  information_analysis?: {
    scores?: Partial<Record<keyof typeof decisionComponents, number | null>>;
    multiplier?: number;
    cutoff?: string;
    details?: {news_method?: string};
  } | null;
};

const articlePageSize = 8;
const docKinds: Record<string, string> = {
  news: '뉴스', transcript: '녹취록', earnings_release: '실적 발표문', cfo_commentary: 'CFO 설명자료',
};
const quarters: Record<string, string> = {'First Quarter': '1분기', 'Second Quarter': '2분기', 'Third Quarter': '3분기', 'Fourth Quarter': '4분기'};
const newsMethods: Record<string, string> = {
  'literal risk-topic count; not LLM sentiment': '기사의 위험 키워드 집계',
  'validated LLM sentiment 70% + actual risk-topic evidence 30%': '검증된 LLM 뉴스 해석 70% + 위험 키워드 집계 30%',
};
const newsTopics: Record<string, string> = {earnings: '실적', guidance: '가이던스', risk: '위험', capital: '자본 배분'};
const shareChanges: Record<string, string> = {
  new: '신규 신고', exited: '신고량 0', increased: '증가', decreased: '감소', unchanged: '유지', unavailable: '이전 자료 없음',
};
const timestamp = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

function Time({value}: {value?: string}) {
  if (!value) return <>—</>;
  const date = new Date(value.replace(' ', 'T'));
  return Number.isNaN(date.getTime()) ? <>—</> : <time dateTime={date.toISOString()} title={value}>{timestamp.format(date)} KST</time>;
}

function SourceLink({url, children}: {url?: string | null; children: ReactNode}) {
  return url && /^https?:\/\//i.test(url)
    ? <a className={styles.source} href={url} target="_blank" rel="noreferrer">{children}</a> : <>{children}</>;
}

function Panel({title, testId, children}: {title: string; testId?: string; children: ReactNode}) {
  return <section className="panel" data-testid={testId}>
    <h2 className={`panel-title ${styles.title}`}>{title}</h2>
    <div className={styles.body}>{children}</div>
  </section>;
}

function useReport<T>(path: string) {
  const [result, setResult] = useState<{path: string; data: T | null; error: string}>();
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const response = await fetch(path, {cache: 'no-store', signal: controller.signal});
        if (!response.ok) throw new Error(`조회 실패 (${response.status})`);
        const data: T = await response.json();
        if (!controller.signal.aborted) setResult({path, data, error: ''});
      } catch (error) {
        if (!controller.signal.aborted) {
          const message = error instanceof Error ? error.message : '조회 실패';
          setResult(previous => ({path, data: previous?.path === path ? previous.data : null, error: message}));
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 60000);
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [path]);
  return result?.path === path ? result : undefined;
}

function DecisionPanel({symbol, decision, integration}: {
  symbol: string; decision?: {data: Decision | null; error: string}; integration?: Information['model_integration'];
}) {
  const signal = decision?.data;
  const overlay = signal?.information_analysis;
  const newsMethod = overlay?.details?.news_method;
  return <Panel title={`주문 판단 근거 · ${symbol}`} testId="decision-preview">
    {decision?.error && <p role="status" className={styles.warning}>주문 신호 {decision.error}{signal && ' · 마지막 수집 결과 표시 중'}</p>}
    {!signal ? !decision?.error && <p role="status" className={styles.note}>주문 신호를 불러오는 중…</p>
      : signal.status === 'unavailable' ? <p className={styles.note}>{signal.reason || '사용 가능한 주문 신호가 없습니다.'}</p>
      : <>
        <p className={styles.lead}>
          기본 목표 <strong>{pct(signal.target_weight_within_slot)}</strong> → 정보 반영 목표 <strong>{pct(signal.effective_target_weight_within_slot)}</strong>
        </p>
        <p className={styles.note}>종목 슬롯 내 목표 비중입니다. 실제 수량은 보유량·현금·리스크를 확인해 정합니다.</p>
        <table className={styles.table}>
          <thead><tr><th scope="col">정보</th><th scope="col">사용 점수</th><th scope="col">반영 상태</th></tr></thead>
          <tbody>{(Object.keys(decisionComponents) as (keyof typeof decisionComponents)[]).map(key => {
            const score = overlay?.scores?.[key];
            return <tr key={key}><th scope="row">{decisionComponents[key]}</th><td>{num(score, 3)}</td>
              <td>{score == null ? '미확보 · 계산 제외' : '관측 자료 반영'}</td></tr>;
          })}</tbody>
        </table>
        <p className={styles.note}>
          비중 조정 배율 {num(overlay?.multiplier, 3)} · 기준 <Time value={overlay?.cutoff}/>
          {' · '}정책 {signal.decision_policy_version || '기본 전략'}
          {newsMethod && newsMethods[newsMethod] && ` · ${newsMethods[newsMethod]}`}
        </p>
      </>}
    {integration && <p className={styles.note}>{integration.status === 'active' ? '모의투자 정책 적용 중' : '정책 미리 보기'} · {integration.reason}</p>}
  </Panel>;
}

function NewsPanel({symbol, news}: {symbol: string; news?: News}) {
  const [limit, setLimit] = useState(articlePageSize);
  const articles = news?.articles ?? [];
  return <Panel title={`실제 뉴스 · ${symbol}`} testId="research-news">
    {news?.snapshot && <p className={styles.note}>Alpaca News · 수집 <Time value={news.snapshot.collected_at}/>
      {' · '}일치 {count(news.matching_articles)}건{news.stale && ' · 갱신 지연'}{news.snapshot.truncated && ' · 수집 한도 도달'}</p>}
    {articles.length ? <>
      <ul className={styles.newsList}>{articles.slice(0, limit).map(article => <li key={article.id}>
        <h3><SourceLink url={article.url}>{article.headline}</SourceLink></h3>
        <div className={styles.metadata}>
          {article.source && <span>{article.source}</span>}
          <span>발행 <Time value={article.created_at}/></span><span>사용 가능 <Time value={article.available_at}/></span>
        </div>
        {!!article.topics.length && <p className={styles.note}>감지 주제 · {article.topics.map(topic => newsTopics[topic] || topic).join(', ')}</p>}
        {!!article.numeric_mentions.length && <p className={styles.note}>원문 수치 · {article.numeric_mentions.join(', ')}</p>}
      </li>)}</ul>
      {articles.length > limit && <button className="primary" type="button" onClick={() => setLimit(limit + articlePageSize)}>
        기사 더 보기 ({articles.length - limit}건)
      </button>}
    </> : <p className={styles.note}>{news?.status === 'available' ? '조회 시각에 사용 가능한 기사가 없습니다.' : '수집된 뉴스 자료가 없습니다.'}</p>}
  </Panel>;
}

function EarningsPanel({symbol, earnings}: {symbol: string; earnings?: Earnings}) {
  return <Panel title={`공식 실적·어닝콜 자료 · ${symbol}`}>
    <p className={styles.note}>{earnings?.reason || '공식 실적 문서 수집본이 없습니다.'}</p>
    {!!earnings?.documents.length && <table className={styles.table}>
      <thead><tr><th scope="col">회계연도 / 분기</th><th scope="col">자료 유형</th><th scope="col">사용 가능</th><th scope="col">원문</th></tr></thead>
      <tbody>{earnings.documents.map(doc => <tr key={doc.document_key}>
        <th scope="row">{doc.fiscal_year} / {quarters[doc.quarter] || doc.quarter}</th><td>{docKinds[doc.kind] || '재무자료'}</td>
        <td><Time value={doc.available_at}/></td><td><SourceLink url={doc.source_url}>공식 원문</SourceLink></td>
      </tr>)}</tbody>
    </table>}
    {earnings?.failures.filter(failure => !failure.symbol || failure.symbol === symbol).map((failure, index) =>
      <p key={index} className={styles.note}>수집 보류 · {failure.kind || failure.symbol} · {failure.reason}</p>)}
    {earnings?.comparisons.map(comparison => <div className={styles.comparison} key={comparison.symbol}>
      <h3>실적 발표문 언급 횟수</h3>
      <p className={styles.note}>{comparison.prior_quarter} → {comparison.current_quarter} · 원문 문자열 빈도 집계</p>
      <table className={styles.table}>
        <thead><tr><th scope="col">주제</th><th scope="col">이전 언급</th><th scope="col">현재 언급</th><th scope="col">변화</th></tr></thead>
        <tbody>{comparison.topics.map(topic => <tr key={topic.topic}><th scope="row">{topic.topic}</th>
          <td>{topic.prior.mentions}</td><td>{topic.current.mentions}</td><td>{topic.mention_change}</td></tr>)}</tbody>
      </table>
    </div>)}
  </Panel>;
}

function AnalysisPanel({model, articles}: {model?: ModelReport; articles: NewsArticle[]}) {
  const headlines = new Map(articles.map(article => [`${article.id}:${article.updated_at}`, article.headline]));
  const analyses = [...(model?.analyses ?? [])].sort((a, b) => Date.parse(b.available_at) - Date.parse(a.available_at));
  return <Panel title="LLM 근거 분석" testId="research-analysis">
    {model?.configuration.model && <p className={styles.note}>{model.configuration.provider} · {model.configuration.model}</p>}
    {analyses.length ? <div className={styles.cards}>{analyses.map((analysis, index) => {
      const kind = docKinds[analysis.kind] || analysis.kind;
      const headline = headlines.get(`${analysis.article_id}:${analysis.article_updated_at}`);
      const quarter = analysis.quarter && (quarters[analysis.quarter] || analysis.quarter);
      const title = headline || (quarter ? `${analysis.fiscal_year} ${quarter} ${kind}` : `${kind} 분석`);
      return <details key={analysis.analysis_key} open={index === 0} className={styles.analysisCard}>
        <summary><span className={styles.analysisSummary}>
          <strong>{title}</strong><span className={styles.metadata}>
            <span>{analysis.model}</span><span>감성 해석 {num(analysis.sentiment, 3)}</span>
            {analysis.total_chunks > 1 && <span>분석 조각 {analysis.chunk + 1}/{analysis.total_chunks}</span>}
          </span>
        </span></summary>
        <div className={styles.analysisDetails}>
          <p className={styles.note}>사용 가능 <Time value={analysis.available_at}/> · <SourceLink url={analysis.source_url}>분석 원문</SourceLink></p>
          {analysis.claims.length ? <ul className={styles.claims}>{analysis.claims.map((claim, claimIndex) => <li key={claimIndex}>
            <p>{claim.summary}</p>
            <figure><blockquote>“{claim.quote}”</blockquote>
              <figcaption>{claim.speaker || '발언자 미확인'} · <SourceLink url={claim.source_url || analysis.source_url}>인용 원문</SourceLink></figcaption>
            </figure>
          </li>)}</ul> : <p className={styles.note}>원문으로 확인된 요약 항목이 없습니다.</p>}
        </div>
      </details>;
    })}</div> : <p className={styles.note}>{model?.status === 'pending' ? '이 종목의 모델 분석을 기다리는 중입니다.' : '표시할 모델 분석 기록이 없습니다.'}</p>}
    <p className={styles.note}>원문 인용 검증을 통과한 모델 해석입니다. 실적 분석은 현재 분기 문서 전체를 검증한 뒤 주문 비중에 반영합니다.</p>
  </Panel>;
}

function InstitutionsPanel({symbol, filings}: {symbol: string; filings: Filing[]}) {
  return <Panel title={`SEC 13F · 기관 보고 보유량 · ${symbol}`} testId="research-institutions">
    <p className={styles.note}>분기 말 신고 보유량이며 공시까지 시차가 있습니다.</p>
    {filings.length ? <div className={styles.filings}>{filings.map(filing => <article key={filing.manager} className={styles.filing} aria-label={filing.manager}>
      <div className={styles.filingHeader}>
        <h3>{filing.manager}</h3>
        <span className={filing.status === 'stale' ? styles.staleBadge : styles.badge}>
          {filing.status === 'stale' ? '오래된 보고서' : filing.status === 'ok' ? '확인된 보고서' : '확인 필요'}
        </span>
      </div>
      <div className={styles.metadata}>
        <span>{filing.prior_report_date ? `${filing.prior_report_date} → ${filing.report_date}` : `기준 분기 ${filing.report_date}`}</span>
        <SourceLink url={filing.source_url}>SEC 원문</SourceLink>
      </div>
      {filing.holdings.length ? <div className={styles.filingRows}>{filing.holdings.map(holding => <dl
        className={styles.filingMetrics} key={`${holding.cusip}-${holding.class}-${holding.share_type}-${holding.put_call}`}>
        <div><dt>종목 / CUSIP</dt><dd>{holding.ticker || holding.cusip}</dd>
          {holding.ticker && <dd className={styles.note}>{holding.cusip}{holding.put_call && ` · ${holding.put_call}`}</dd>}</div>
        <div><dt>신고량</dt><dd>{count(holding.shares)}{holding.share_type === 'SH' ? '주' : ` ${holding.share_type}`}</dd></div>
        <div><dt>이전량 · 분할 보정</dt><dd>{count(holding.split_adjusted_prior_shares)}</dd></div>
        <div><dt>변화</dt><dd>{shareChanges[holding.change] || '확인 필요'}
          {holding.change_fraction != null && ` (${pct(holding.change_fraction)})`}</dd></div>
      </dl>)}</div> : <p className={styles.emptyFiling}>{symbol}에 해당하는 신고 항목이 없습니다.</p>}
    </article>)}</div> : <p className={styles.note}>조회 시각에 사용 가능한 기관 보고서가 없습니다.</p>}
  </Panel>;
}

export default function InformationResearch({symbol}: {symbol: string}) {
  const asset = encodeURIComponent(symbol);
  const information = useReport<Information>(`/api/information?symbol=${asset}`);
  const decision = useReport<Decision>(`/api/assets/${asset}/signal`);
  const data = information?.data;

  return <div data-testid="information-research">
    {information?.error && <div role="alert" className="error">뉴스·공시 {information.error}{data && ' · 마지막 수집 결과 표시 중'}</div>}
    {data?.status === 'degraded' && <div role="status" className="error">일부 자료의 수집 또는 분석을 확인해야 합니다. 각 자료의 수집 시각과 원문을 확인할 수 있습니다.</div>}
    <DecisionPanel symbol={symbol} decision={decision} integration={data?.model_integration}/>
    {data ? <>
      <NewsPanel symbol={symbol} news={data.news}/>
      <EarningsPanel symbol={symbol} earnings={data.earnings_calls}/>
      <AnalysisPanel model={data.llm} articles={data.news?.articles ?? []}/>
      <InstitutionsPanel symbol={symbol} filings={data.institutions?.managers ?? []}/>
    </> : !information?.error && <p className="loading" role="status">{symbol} 뉴스와 공시를 불러오는 중…</p>}
  </div>;
}
