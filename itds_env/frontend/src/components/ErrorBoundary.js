import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // You can integrate remote logging here
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '40px 20px',
          textAlign: 'center',
          background: 'rgba(255, 255, 255, 0.7)',
          backdropFilter: 'blur(12px)',
          borderRadius: '16px',
          border: '1px solid rgba(226, 232, 240, 0.8)',
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.05)',
          margin: '40px auto',
          maxWidth: '500px'
        }}>
          <div style={{
            fontSize: '48px',
            marginBottom: '16px'
          }}>
            ✨
          </div>
          <h2 style={{
            margin: '0 0 12px 0',
            color: '#1e293b',
            fontSize: '24px',
            fontWeight: '700'
          }}>
            Unexpected Hiccup
          </h2>
          <p style={{
            color: '#64748b',
            fontSize: '15px',
            lineHeight: '1.6',
            margin: '0 0 24px 0'
          }}>
            The application encountered a temporary issue. Don't worry, your data is safe!
          </p>
          
          <div style={{
            background: '#f8fafc',
            padding: '12px',
            borderRadius: '8px',
            fontSize: '12px',
            fontFamily: 'monospace',
            color: '#ef4444',
            textAlign: 'left',
            overflowX: 'auto',
            marginBottom: '24px',
            border: '1px solid #fee2e2'
          }}>
            {String(this.state.error)}
          </div>

          <button 
            onClick={() => window.location.reload()} 
            style={{
              background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
              color: 'white',
              padding: '12px 28px',
              borderRadius: '10px',
              border: 'none',
              fontWeight: '600',
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(37, 99, 235, 0.25)',
              transition: 'transform 0.2s ease'
            }}
            onMouseOver={(e) => e.target.style.transform = 'scale(1.02)'}
            onMouseOut={(e) => e.target.style.transform = 'scale(1)'}
          >
            Refresh Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
