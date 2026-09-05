import React from 'react';

const LoadingSkeleton = ({ width = '100%', height = 16, style = {} }) => {
  const base = {
    background: 'linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 37%, #f3f4f6 63%)',
    backgroundSize: '400% 100%',
    animation: 'shine 1.2s ease-in-out infinite',
    borderRadius: 4,
    display: 'block',
    width,
    height,
    ...style,
  };
  return (
    <div style={base} aria-busy="true" aria-label="Loading" />
  );
};

export default LoadingSkeleton;
