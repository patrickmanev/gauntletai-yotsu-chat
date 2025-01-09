'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function ClientPage() {
  const router = useRouter();

  useEffect(() => {
    // Check for authentication
    const accessToken = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');

    if (!accessToken || !refreshToken) {
      router.replace('/auth');
      return;
    }

    // TODO: Verify token validity
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <h1 className="text-2xl font-semibold">Client</h1>
    </div>
  );
} 