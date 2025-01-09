'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import QRCodeWrapper from './qr-code';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type AuthMode = 'initial' | 'signin' | 'signup' | 'totp';

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>('initial');
  const [lastMode, setLastMode] = useState<'signin' | 'signup'>('signin');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [qrUri, setQrUri] = useState('');
  const [tempToken, setTempToken] = useState('');
  const [validationMessage, setValidationMessage] = useState('');

  const validateDisplayName = (name: string) => {
    const requirements = [
      { test: name.length <= 25, message: "not exceed 25 characters" },
      { test: /^[a-zA-Z']+(?:\s[a-zA-Z']+)*$/.test(name), message: "contain only English letters, apostrophes, and single spaces between names" }
    ];

    const failedRequirements = requirements.filter(req => !req.test);
    if (failedRequirements.length > 0) {
      setValidationMessage(
        "Display name must:\n" + 
        failedRequirements.map(req => "• " + req.message).join("\n")
      );
      return false;
    }
    setValidationMessage('');
    return true;
  };

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
    
    if (mode === 'signup' && !validateDisplayName(displayName)) {
      return;
    }
    
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
          body: JSON.stringify({ email, password, display_name: displayName }),
        });
        
        if (!response.ok) {
          const data = await response.json();
          setValidationMessage(data.detail || 'Registration failed');
          return;
        }
        
        const data = await response.json();
        setQrUri(data.totp_uri);
        setTempToken(data.temp_token);
        setLastMode('signup');
        setMode('totp');
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
            router.push('/client');
          }
        } else {
          setValidationMessage(data.detail || 'Login failed');
        }
      }
    } catch (error) {
      if (error instanceof Error) {
        setValidationMessage(error.message);
      } else {
        setValidationMessage('An error occurred. Please try again.');
      }
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
      
      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        router.push('/client');
      } else {
        setValidationMessage("TOTP code is invalid. Please try again.");
      }
    } catch (error) {
      setValidationMessage("TOTP code is invalid. Please try again.");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#dbdff4]">
      <div className="bg-[#f2f0ef] p-8 rounded-lg shadow-lg w-[32rem]">
        {mode === 'initial' ? (
          <div className="space-y-4">
            <Button
              onClick={() => {
                setLastMode('signin');
                setMode('signin');
              }}
              className="w-full bg-[#66615e] text-white hover:bg-opacity-90"
            >
              Sign In
            </Button>
            <Button
              onClick={() => {
                setLastMode('signup');
                setMode('signup');
              }}
              className="w-full bg-[#66615e] text-white hover:bg-opacity-90"
            >
              Sign Up
            </Button>
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
            
            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-700">Enter 6-digit code</div>
              <InputOTP
                value={totpCode}
                onChange={setTotpCode}
                maxLength={6}
                render={({ slots }) => (
                  <InputOTPGroup>
                    {slots.map((slot, idx) => (
                      <InputOTPSlot key={idx} {...slot} index={idx} />
                    ))}
                  </InputOTPGroup>
                )}
              />
            </div>

            {validationMessage && (
              <div className="text-sm text-red-600 bg-red-100 rounded whitespace-pre-line p-2">
                {validationMessage}
              </div>
            )}
            
            <Button
              type="submit"
              className="w-full bg-[#66615e] text-white hover:bg-opacity-90"
            >
              Verify
            </Button>
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

            {mode === 'signup' && (
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-700">Display Name</div>
                <Input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  required
                />
              </div>
            )}

            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-700">Email</div>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-700">Password</div>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {validationMessage && (
              <div className="text-sm text-red-600 bg-red-100 rounded whitespace-pre-line p-2">
                {validationMessage}
              </div>
            )}

            <Button
              type="submit"
              className="w-full bg-[#66615e] text-white hover:bg-opacity-90"
            >
              {mode === 'signin' ? 'Sign In' : 'Sign Up'}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
} 