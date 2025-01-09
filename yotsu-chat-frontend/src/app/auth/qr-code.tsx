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
    <div className="p-4 bg-white rounded-lg shadow-md">
      <QRComponent 
        value={value} 
        size={200} 
        bgColor="#FFFFFF"
        fgColor="#000000"
        level="H"
        includeMargin={true}
      />
    </div>
  );
} 