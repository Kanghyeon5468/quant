type Numeric = number | string | null | undefined;

export const usd = (value: Numeric) => value == null ? '—' : Number(value).toLocaleString('en-US', {
  style: 'currency', currency: 'USD',
});
export const pct = (value: Numeric) => value == null ? '—' : `${(100 * Number(value)).toFixed(2)}%`;
export const num = (value: Numeric, digits = 2) => value == null ? '—' : Number(value).toFixed(digits);
export const count = (value: Numeric) => value == null ? '—' : Number(value).toLocaleString('ko-KR');
export const when = (value?: string | null) => value
  ? `${new Date(value.replace(' ', 'T')).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'})} KST` : '—';

export const statuses: Record<string, string> = {
  accepted: '접수', new: '대기', pending_new: '접수 대기', partially_filled: '부분 체결',
  pending_cancel: '취소 대기', pending_replace: '변경 대기', done_for_day: '당일 종료',
  filled: '체결 완료', canceled: '취소', expired: '만료', rejected: '거절', replaced: '교체',
  rejected_locally: '로컬 거절', submitting: '제출 중', unknown: '접수 확인 필요',
};
