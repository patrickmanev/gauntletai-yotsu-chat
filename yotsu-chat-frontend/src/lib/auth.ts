import { jwtDecode } from 'jwt-decode';

export interface TokenPayload {
  user_id: number;
  exp: number;
  temp?: boolean;
}

export function getTokenFromCookies(): string | null {
  const cookies = document.cookie.split(';');
  const tokenCookie = cookies.find(cookie => cookie.trim().startsWith('token='));
  return tokenCookie ? tokenCookie.split('=')[1] : null;
}

export function getRefreshTokenFromCookies(): string | null {
  const cookies = document.cookie.split(';');
  const tokenCookie = cookies.find(cookie => cookie.trim().startsWith('refresh_token='));
  return tokenCookie ? tokenCookie.split('=')[1] : null;
}

export function setTokens(accessToken: string, refreshToken: string) {
  document.cookie = `token=${accessToken}; path=/; SameSite=Strict`;
  document.cookie = `refresh_token=${refreshToken}; path=/; SameSite=Strict`;
}

export function clearTokens() {
  document.cookie = 'token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  document.cookie = 'refresh_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
}

export function isTokenValid(token: string | null): boolean {
  if (!token) return false;
  try {
    const decoded = jwtDecode<TokenPayload>(token);
    const currentTime = Math.floor(Date.now() / 1000);
    return decoded.exp > currentTime && !decoded.temp;
  } catch {
    return false;
  }
}

export function isAuthenticated(): boolean {
  const token = getTokenFromCookies();
  return isTokenValid(token);
} 