'use client';

import { QRCodeSVG } from 'qrcode.react';

export default function QRCodeWrapper({ value }: { value: string }) {
  return (
    <div className="p-4 bg-white rounded-lg shadow-md">
      <QRCodeSVG 
        value={value} 
        size={200} 
        bgColor="#FFFFFF"
        fgColor="#000000"
        level="H"
      />
    </div>
  );
} 