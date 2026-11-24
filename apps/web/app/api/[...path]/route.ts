import { NextRequest } from 'next/server';
export const dynamic = 'force-dynamic';
async function proxy(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  if (path.some(p => !/^[A-Za-z0-9_-]+$/.test(p))) return Response.json({detail:'Invalid path'}, {status:400});
  const target = new URL('/api/'+path.join('/'), process.env.API_BASE_URL || 'http://127.0.0.1:8100');
  target.search = request.nextUrl.search;
  const headers: Record<string,string> = {'Content-Type':'application/json'};
  if (process.env.QUANTCORE_API_TOKEN) headers.Authorization = 'Bearer '+process.env.QUANTCORE_API_TOKEN;
  try {
    const response = await fetch(target, {method:request.method, headers, body:request.method==='POST'?await request.text():undefined, cache:'no-store', signal:AbortSignal.timeout(30000)});
    return new Response(await response.text(), {status:response.status, headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  } catch {
    return Response.json({detail:'QuantCore API unavailable. Start the API service on port 8100.'}, {status:503});
  }
}
export const GET = proxy;
export const POST = proxy;
