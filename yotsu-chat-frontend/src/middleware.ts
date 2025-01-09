import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { jwtDecode } from 'jwt-decode'

interface TokenPayload {
  user_id: number;
  exp: number;
  temp?: boolean;
}

function isTokenValid(token: string | undefined): boolean {
  if (!token) return false;
  try {
    const decoded = jwtDecode<TokenPayload>(token);
    const currentTime = Math.floor(Date.now() / 1000);
    return decoded.exp > currentTime && !decoded.temp;
  } catch {
    return false;
  }
}

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname
  const token = request.cookies.get('token')?.value
  const isPublicPath = path === '/auth'

  // If no valid token and trying to access protected route, redirect to auth
  if (!isTokenValid(token) && !isPublicPath) {
    return NextResponse.redirect(new URL('/auth', request.url))
  }

  // If has valid token and trying to access auth page, redirect to client
  if (isTokenValid(token) && isPublicPath) {
    return NextResponse.redirect(new URL('/client', request.url))
  }

  return NextResponse.next()
}

// Configure which paths the middleware should run on
export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\..*|api).*)',
  ],
} 