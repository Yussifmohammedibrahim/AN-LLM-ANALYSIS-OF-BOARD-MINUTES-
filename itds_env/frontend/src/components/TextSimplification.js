import React, { useState } from 'react';
import { Send, Copy, Check, AlertCircle, Loader } from 'lucide-react';
import { notifyError, notifySuccess } from '../utils/notify';
import './TextSimplification.css';

const TextSimplification = () => {
  const [originalText, setOriginalText] = useState('');
  const [simplifiedText, setSimplifiedText] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [maxLength, setMaxLength] = useState(150);
  const [history, setHistory] = useState([]);

  const API_BASE_URL = process.env.REACT_APP_API_URL || `http://${window.location.hostname}:5001`;

  const handleSimplify = async (e) => {
    e.preventDefault();

    if (!originalText.trim()) {
      notifyError('Please enter text to simplify');
      return;
    }

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/ai/simplify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          text: originalText,
          max_length: maxLength,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to simplify text');
      }

      const result = await response.json();
      setSimplifiedText(result.simplified_text);

      // Add to history
      setHistory((prev) => [
        {
          id: Date.now(),
          original: originalText,
          simplified: result.simplified_text,
          timestamp: new Date(),
        },
        ...prev.slice(0, 9), // Keep last 10
      ]);

      notifySuccess('Text simplified successfully!');
    } catch (error) {
      notifyError(error.message || 'Failed to simplify text');
      setSimplifiedText('');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (simplifiedText) {
      navigator.clipboard.writeText(simplifiedText);
      setCopied(true);
      notifySuccess('Copied to clipboard!');
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="text-simplification-container">
      {/* Header */}
      <div className="text-simplification-header">
        <h2>Text Simplification</h2>
        <p>Convert complex meeting minutes into accessible, easy-to-read text</p>
      </div>

      {/* Main Content */}
      <div className="text-simplification-content">
        {/* Input Section */}
        <div className="text-simplification-section">
          <label className="text-simplification-label">
            Enter Text to Simplify
            <span className="text-simplification-hint">
              ({originalText.length} characters)
            </span>
          </label>
          <textarea
            value={originalText}
            onChange={(e) => setOriginalText(e.target.value)}
            placeholder="Enter complex text from meeting minutes..."
            className="text-simplification-textarea"
            disabled={loading}
            rows={6}
          />
        </div>

        {/* Options */}
        <div className="text-simplification-options">
          <div className="text-simplification-slider">
            <label>
              Max Output Length: <span>{maxLength}</span> characters
            </label>
            <input
              type="range"
              min="50"
              max="512"
              step="10"
              value={maxLength}
              onChange={(e) => setMaxLength(parseInt(e.target.value))}
              disabled={loading}
              className="text-simplification-range"
            />
          </div>
        </div>

        {/* Action Button */}
        <button
          onClick={handleSimplify}
          disabled={loading || !originalText.trim()}
          className="text-simplification-button"
        >
          {loading ? (
            <>
              <Loader size={18} className="text-simplification-spinner" />
              Simplifying...
            </>
          ) : (
            <>
              <Send size={18} />
              Simplify Text
            </>
          )}
        </button>

        {/* Output Section */}
        {simplifiedText && (
          <div className="text-simplification-section text-simplification-output">
            <div className="text-simplification-output-header">
              <label className="text-simplification-label">Simplified Text</label>
              <button
                onClick={handleCopy}
                className="text-simplification-copy-button"
                title="Copy to clipboard"
              >
                {copied ? (
                  <>
                    <Check size={16} />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy size={16} />
                    Copy
                  </>
                )}
              </button>
            </div>
            <div className="text-simplification-result">
              {simplifiedText}
            </div>
            <div className="text-simplification-stats">
              <span>
                Reduced from {originalText.length} to {simplifiedText.length} characters
              </span>
              <span className="text-simplification-reduction">
                {Math.round(((originalText.length - simplifiedText.length) / originalText.length) * 100)}% reduction
              </span>
            </div>
          </div>
        )}
      </div>

      {/* History Section */}
      {history.length > 0 && (
        <div className="text-simplification-history">
          <h3>Recent Simplifications</h3>
          <div className="text-simplification-history-list">
            {history.map((item) => (
              <div
                key={item.id}
                className="text-simplification-history-item"
                onClick={() => {
                  setOriginalText(item.original);
                  setSimplifiedText(item.simplified);
                }}
              >
                <div className="text-simplification-history-preview">
                  <p className="text-simplification-history-original">
                    {item.original.substring(0, 60)}...
                  </p>
                  <p className="text-simplification-history-simplified">
                    {item.simplified.substring(0, 60)}...
                  </p>
                </div>
                <span className="text-simplification-history-time">
                  {item.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Info Box */}
      <div className="text-simplification-info">
        <AlertCircle size={18} />
        <div>
          <h4>How Text Simplification Works</h4>
          <p>
            This tool uses advanced NLP models to convert complex professional language into
            clear, accessible text. It's useful for:
          </p>
          <ul>
            <li>Making meeting minutes accessible to all stakeholders</li>
            <li>Creating summaries for non-specialist audiences</li>
            <li>Improving communication clarity</li>
            <li>Accessibility compliance</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default TextSimplification;
