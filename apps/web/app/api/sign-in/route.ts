import {NextRequest, NextResponse} from 'next/server';
import {sameOrigin} from '../request-origin';

export async function POST(request: NextRequest) {
  if (process.env.QUANTCORE_WEB_SIGN_IN !== 'true') {
    return NextResponse.json({detail:'이 대시보드에 개별 로그인이 설정되지 않았습니다.'}, {status:404});
  }
  if (!sameOrigin(request)) {
    return NextResponse.json({detail:'Invalid origin'}, {status:403});
  }
  try {
    const {key} = await request.json();
    if (typeof key !== 'string' || !/^[A-Za-z0-9_-]{24,256}$/.test(key)) {
      return NextResponse.json({detail:'액세스 키를 확인하세요.'}, {status:401});
    }
    const endpoint = new URL('/api/session-role', process.env.API_BASE_URL || 'http://127.0.0.1:8100');
    const checked = await fetch(endpoint, {headers:{Authorization:'Bearer '+key}, cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!checked.ok) return NextResponse.json({detail:'액세스 키를 확인하세요.'}, {status:checked.status});
    const {role} = await checked.json();
    const response = NextResponse.json({role}, {headers:{'Cache-Control':'no-store'}});
    response.cookies.set('quantcore-session', key, {
      httpOnly:true, sameSite:'strict', secure:request.nextUrl.protocol === 'https:', path:'/api', maxAge:8*60*60,
    });
    return response;
  } catch {
    return NextResponse.json({detail:'로그인 서버 응답을 확인하세요.'}, {status:503});
  }
}

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) {
    return NextResponse.json({detail:'Invalid origin'}, {status:403});
  }
  const response = NextResponse.json({status:'ok'});
  response.cookies.set('quantcore-session', '', {httpOnly:true, sameSite:'strict', path:'/api', maxAge:0});
  return response;
}
