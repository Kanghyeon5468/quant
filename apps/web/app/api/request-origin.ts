import type {NextRequest} from 'next/server';

export function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get('origin');
  const host = request.headers.get('host');
  if (!origin || !host) return false;
  try {
    const parsed = new URL(origin);
    return parsed.origin === origin && parsed.host === host && parsed.protocol === request.nextUrl.protocol;
  } catch {
    return false;
  }
}
