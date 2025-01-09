'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const accessToken = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');

    if (!accessToken || !refreshToken) {
      router.replace('/auth');
      return;
    }

    // Verify the access token is still valid
    fetch('/api/auth/verify', {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    })
    .then(response => {
      if (!response.ok) {
        // If token is invalid, try refresh
        return fetch('/api/auth/refresh', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ refresh_token: refreshToken })
        });
      }
      return response;
    })
    .then(response => {
      if (!response.ok) {
        // If refresh fails, redirect to login
        throw new Error('Authentication failed');
      }
      return response.json();
    })
    .then(data => {
      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
      }
      // Stay on the main page if authentication is successful
      router.replace('/yotsu-interface');
    })
    .catch(() => {
      // Clear tokens and redirect to login on any error
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      router.replace('/auth');
    });
  }, [router]);

  // Show a loading state while checking authentication
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#dbdff4' }}>
      <div className="animate-pulse text-gray-600">
        Loading...
      </div>
    </div>
  );
}

