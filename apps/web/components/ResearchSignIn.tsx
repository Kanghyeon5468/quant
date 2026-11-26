'use client';

import {useEffect, useState, type FormEvent} from 'react';

export default function ResearchSignIn() {
  const [error,setError] = useState('');
  const [pending,setPending] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      const key = new FormData(event.currentTarget).get('key');
      const response = await fetch('/api/sign-in', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key})});
      if (!response.ok) throw new Error((await response.json()).detail);
      window.location.reload();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '로그인 실패');
    } finally {
      setPending(false);
    }
  }
  return <section className="panel">
    <h2 className="panel-title">연구 계정 로그인</h2>
    <form className="controls" onSubmit={submit}>
      <label>액세스 키<input type="password" autoComplete="current-password" name="key" required className="access-key"/></label>
      <button className="primary" type="submit" disabled={pending}>로그인</button>
    </form>
    {error && <p className="panel-note" role="alert">{error}</p>}
  </section>;
}


export function ResearchAccount() {
  const [role,setRole] = useState<string>();
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/session-role',{signal:controller.signal, cache:'no-store'}).then(async response => {
      if (response.ok) setRole((await response.json()).role);
    }).catch(() => {});
    return () => controller.abort();
  },[]);
  return role ? <button className="language" type="button" onClick={async () => {
    const response=await fetch('/api/sign-in',{method:'DELETE'});
    if(response.ok)window.location.reload();
  }}>로그아웃</button> : null;
}
