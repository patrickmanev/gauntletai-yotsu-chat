'use client';

import { useEffect, useState } from 'react';

export default function QRCodeWrapper({ value }: { value: string }) {
  const [QRComponent, setQRComponent] = useState<any>(null);

  useEffect(() => {
    import('qrcode.react').then(mod => {
      setQRComponent(() => mod.QRCodeSVG);
    });
  }, []);

  if (!QRComponent) return null;

  return (
    <QRComponent 
      value={value} 
      size={200} 
      bgColor="#f2f0ef" 
      fgColor="#66615e" 
    />
  );
} 