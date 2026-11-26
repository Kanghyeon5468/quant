import {count, when} from './paper-format';

type Tokens = {input: number; output: number; requests_with_usage: number};
type TokenLimit = {remaining: number; reset_at: string};
type Usage = {
  status: string;
  stale?: boolean;
  checked_at?: string;
  configuration?: {status: string; provider?: string; model?: string};
  daily_requests?: {date_utc: string; reset_at: string; started: number; failed: number; pending: number; limit: number; remaining: number};
  today_tokens?: Tokens;
  recorded_tokens?: Tokens;
  latest_usage?: {at: string; input: number; output: number; model?: string};
  anthropic_rate_limit?: {observed_at: string; limits: Partial<Record<'input' | 'output' | 'tokens', TokenLimit>>};
};

export default function PaperUsage({usage}: {usage: Usage}) {
  const {daily_requests: daily, today_tokens: today, recorded_tokens: total, latest_usage: latest, anthropic_rate_limit: quota} = usage;
  const perMinute: [string, TokenLimit | undefined][] = [
    ['입력', quota?.limits.input], ['출력', quota?.limits.output],
  ];
  if (!quota?.limits.input && !quota?.limits.output) perMinute.push(['제공자 한도', quota?.limits.tokens]);
  return <section className="panel" data-testid="paper-llm-usage">
    <h2 className="panel-title">Claude 토큰과 요청 한도</h2>
    {usage.status !== 'ok' || !daily ? <p className="panel-note">아직 요청 원장의 사용량 기록이 없습니다.</p> : <>
      <p className="panel-note">{usage.configuration?.model || '모델 설정 대기'} · 원장 확인 {when(usage.checked_at)}
        {usage.stale && ' · 최신 사용량 확인 대기'}
      </p>
      <div className="metrics paper-stats">
        <div className="metric"><span>남은 일일 요청</span><strong>{usage.stale ? '—' : `${count(daily.remaining)} / ${count(daily.limit)}건`}</strong>
          <small>{usage.stale ? '마지막 집계 ' + daily.date_utc + ' UTC' : `${count(daily.started)}건 사용 · 초기화 ${when(daily.reset_at)}`}</small>
        </div>
        <div className="metric"><span>일일 입력 토큰 · 캐시 포함</span><strong>{count(today?.input)}</strong><small>{daily.date_utc} UTC 기록</small></div>
        <div className="metric"><span>일일 출력 토큰</span><strong>{count(today?.output)}</strong><small>{daily.date_utc} UTC 기록</small></div>
      </div>
      <div className="paper-usage-detail">
        <p>Claude 누적 기록 · 입력 {count(total?.input)} / 출력 {count(total?.output)} 토큰 ({count(total?.requests_with_usage)}개 응답)</p>
        {latest && <p>최근 응답 · 입력 {count(latest.input)} / 출력 {count(latest.output)} 토큰 · {when(latest.at)}</p>}
        {(daily.failed > 0 || daily.pending > 0) && <p>일일 요청에 실패 {count(daily.failed)}건 · 응답 대기 {count(daily.pending)}건 포함</p>}
        <h3>제공자가 보고한 남은 토큰</h3>
        {quota ? <ul>
          {perMinute.map(([label, limit]) => limit && <li key={label}>{label} 약 {count(limit.remaining)}개 · 한도 회복 {when(limit.reset_at)}</li>)}
        </ul> : <p>Anthropic 응답에 남은 토큰 한도가 기록되면 표시됩니다.</p>}
        {quota && <p className="muted">분당 한도 · 마지막 기록 {when(quota.observed_at)}</p>}
      </div>
    </>}
  </section>;
}
