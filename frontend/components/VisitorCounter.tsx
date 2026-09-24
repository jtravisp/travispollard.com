'use client';

import { useEffect, useState } from 'react';

export default function VisitorCounter() {
    const [count, setCount] = useState<number | null>(null);

    useEffect(() => {
        fetch('https://29mh2e7a07.execute-api.us-east-1.amazonaws.com/prod/count')
          .then((res) => res.json())
          .then((data) => setCount(data.count))
          .catch((err) => console.error('Visitor counter error:', err));
      }, []);
    
      return (
        <div className="pb-6 text-center text-xs text-base-content/40">
          {count !== null ? `${count} visitors to travispollard.com` : ''}
        </div>
      );
    }
    