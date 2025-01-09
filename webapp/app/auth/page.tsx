'use client';

import { useState } from 'react';
import QRCodeWrapper from './qr-code';

type AuthMode = 'initial' | 'signin' | 'signup' | 'totp';

export default function AuthPage() {
  const [mode, setMode] = useState<AuthMode>('initial');
  const [lastMode, setLastMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [qrUri, setQrUri] = useState('');
  const [tempToken, setTempToken] = useState('');
  const [validationMessage, setValidationMessage] = useState('');

  const validateEmail = (email: string) => {
    const input = document.createElement('input');
    input.type = 'email';
    input.value = email;
    return input.checkValidity();
  };

  const validatePassword = (password: string) => {
    const requirements = [
      { test: password.length >= 8, message: "be at least 8 characters long" },
      { test: /[A-Z]/.test(password), message: "contain at least one uppercase letter" },
      { test: /[a-z]/.test(password), message: "contain at least one lowercase letter" },
      { test: /\d/.test(password), message: "contain at least one number" },
      { test: /[!@#$%^&*(),.?":{}|<>]/.test(password), message: "contain at least one special character" }
    ];

    const failedRequirements = requirements.filter(req => !req.test);
    if (failedRequirements.length > 0) {
      setValidationMessage(
        "Password must:\n" + 
        failedRequirements.map(req => "• " + req.message).join("\n")
      );
      return false;
    }
    setValidationMessage('');
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateEmail(email)) {
      setValidationMessage('Please enter a valid email address');
      return;
    }
    
    if (!validatePassword(password)) {
      return;
    }

    try {
      if (mode === 'signup') {
        const checkResponse = await fetch('/api/auth/check-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email }),
        });

        if (!checkResponse.ok) {
          const data = await checkResponse.json();
          if (checkResponse.status === 409) {
            setValidationMessage('This email is already registered. Please use a different email or sign in.');
            return;
          }
          throw new Error(data.detail || 'Failed to check email');
        }

        const response = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        const data = await response.json();
        if (response.ok) {
          setQrUri(data.totp_uri);
          setTempToken(data.temp_token);
          setLastMode('signup');
          setMode('totp');
        } else {
          setValidationMessage(data.detail || 'Registration failed');
        }
      } else {
        const response = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        const data = await response.json();
        if (response.ok) {
          if (data.temp_token) {
            setTempToken(data.temp_token);
            setLastMode('signin');
            setMode('totp');
          } else {
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            window.location.href = '/';
          }
        } else {
          setValidationMessage(data.detail || 'Login failed');
        }
      }
    } catch (error) {
      setValidationMessage('An error occurred. Please try again.');
    }
  };

  const handleTOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      const response = await fetch('/api/auth/verify-2fa', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${tempToken}`
        },
        body: JSON.stringify({ totp_code: totpCode }),
      });
      
      const data = await response.json();
      if (response.ok) {
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        window.location.href = '/';
      } else {
        setValidationMessage(data.detail || 'Invalid TOTP code');
      }
    } catch (error) {
      setValidationMessage('An error occurred. Please try again.');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#dbdff4' }}>
      <div className="bg-[#f2f0ef] p-8 rounded-lg shadow-lg w-[32rem]">
        {mode === 'initial' ? (
          <div className="space-y-4">
            <button
              onClick={() => {
                setLastMode('signin');
                setMode('signin');
              }}
              className="w-full bg-[#66615e] text-white rounded-lg py-3 px-4 hover:bg-opacity-90 transition-colors"
            >
              Sign In
            </button>
            <button
              onClick={() => {
                setLastMode('signup');
                setMode('signup');
              }}
              className="w-full bg-[#66615e] text-white rounded-lg py-3 px-4 hover:bg-opacity-90 transition-colors"
            >
              Sign Up
            </button>
          </div>
        ) : mode === 'totp' ? (
          <form onSubmit={handleTOTP} className="space-y-6">
            <div className="flex items-center justify-between mb-6">
              <button
                type="button"
                onClick={() => setMode(lastMode)}
                className="text-sm text-gray-600 hover:text-gray-800"
              >
                ← Back
              </button>
              <h2 className="text-center text-lg font-medium">
                {lastMode === 'signin' ? 'Sign In' : 'Sign Up'}
              </h2>
              <div className="w-12"></div>
            </div>

            {lastMode === 'signup' && qrUri && (
              <div className="flex justify-center mb-4">
                <QRCodeWrapper value={qrUri} />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700">Enter 6-digit code</label>
              <input
                type="text"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                className="mt-1 block w-[28rem] h-12 px-3 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                pattern="[0-9]{6}"
                maxLength={6}
                required
              />
            </div>
            <button
              type="submit"
              className="w-full bg-[#66615e] text-white rounded-lg py-2 px-4 hover:bg-opacity-90 transition-colors"
            >
              Verify
            </button>
          </form>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="flex items-center justify-between mb-6">
              <button
                type="button"
                onClick={() => setMode('initial')}
                className="text-sm text-gray-600 hover:text-gray-800"
              >
                ← Back
              </button>
              <h2 className="text-center text-lg font-medium">
                {mode === 'signin' ? 'Sign In' : 'Sign Up'}
              </h2>
              <div className="w-12"></div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 block w-[28rem] h-12 px-3 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-[28rem] h-12 px-3 rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                required
              />
            </div>
            {validationMessage && (
              <div className="text-sm text-red-600 bg-red-100 rounded whitespace-pre-line p-2">
                {validationMessage}
              </div>
            )}
            <button
              type="submit"
              className="w-[28rem] bg-[#66615e] text-white rounded-lg py-2 px-4 hover:bg-opacity-90 transition-colors"
            >
              {mode === 'signin' ? 'Sign In' : 'Sign Up'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
} 