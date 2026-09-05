import React, { useState, useRef, useEffect } from 'react';
import { Send, MessageCircle, AlertCircle, CheckCircle2, Loader } from 'lucide-react';
import { aiAPI } from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import './QuestionAnswering.css';

const QuestionAnswering = () => {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      type: 'bot',
      text: 'Ask me anything about the ITDS Board Minutes app. I\'ll answer from app help, reports, settings, and meeting data when relevant.',
      timestamp: new Date(),
    },
  ]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleAsk = async (e) => {
    e.preventDefault();

    if (!question.trim()) {
      notifyError('Please enter a question');
      return;
    }

    // Minimum length validation removed to allow short conversational queries

    // Add user question to messages
    const userMessage = {
      id: `user-${Date.now()}`,
      type: 'user',
      text: question,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    try {
      const history = messages
        .filter(m => m.type !== 'loading' && m.type !== 'error' && m.id !== 'welcome')
        .map(m => ({ 
          role: m.type === 'user' ? 'user' : 'assistant', 
          content: m.text 
        }));

      const response = await aiAPI.answerQuestion(question, history);
      
      const botMessage = {
        id: `bot-${Date.now()}`,
        type: 'bot',
        text: response.data.answer || 'Could not find an answer to that question.',
        confidence: response.data.confidence,
        context: response.data.context_preview,
        timestamp: new Date(),
      };
      
      setMessages((prev) => [...prev, botMessage]);
      
      if (response.data.confidence < 0.5) {
        notifyError('Answer confidence is low. Please verify the result.');
      } else {
        notifySuccess('Answer retrieved successfully');
      }
    } catch (error) {
      const errorMessage = {
        id: `error-${Date.now()}`,
        type: 'error',
        text: error.response?.data?.error || 'Failed to get an answer. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      notifyError(error.response?.data?.error || 'Failed to answer question');
    } finally {
      setLoading(false);
    }
  };

  const renderMessage = (msg) => {
    if (msg.type === 'user') {
      return (
        <div key={msg.id} className="qa-message qa-message-user">
          <div className="qa-message-content">
            <p className="qa-message-text">{msg.text}</p>
            <span className="qa-message-time">{msg.timestamp.toLocaleTimeString()}</span>
          </div>
        </div>
      );
    }

    if (msg.type === 'error') {
      return (
        <div key={msg.id} className="qa-message qa-message-error">
          <AlertCircle size={16} className="qa-icon" />
          <div className="qa-message-content">
            <p className="qa-message-text">{msg.text}</p>
            <span className="qa-message-time">{msg.timestamp.toLocaleTimeString()}</span>
          </div>
        </div>
      );
    }

    return (
      <div key={msg.id} className="qa-message qa-message-bot">
        <MessageCircle size={16} className="qa-icon" />
        <div className="qa-message-content">
          <p className="qa-message-text">{msg.text}</p>
          {msg.confidence !== undefined && (
            <div className="qa-confidence">
              {msg.confidence > 0.7 ? (
                <>
                  <CheckCircle2 size={14} className="qa-confidence-high" />
                  <span>High confidence ({Math.round(msg.confidence * 100)}%)</span>
                </>
              ) : msg.confidence > 0.4 ? (
                <>
                  <AlertCircle size={14} className="qa-confidence-medium" />
                  <span>Medium confidence ({Math.round(msg.confidence * 100)}%)</span>
                </>
              ) : (
                <>
                  <AlertCircle size={14} className="qa-confidence-low" />
                  <span>Low confidence ({Math.round(msg.confidence * 100)}%)</span>
                </>
              )}
            </div>
          )}
          {msg.context && (
            <details className="qa-context">
              <summary>Show context</summary>
              <p className="qa-context-text">{msg.context}</p>
            </details>
          )}
          <span className="qa-message-time">{msg.timestamp.toLocaleTimeString()}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="qa-container">
      <div className="qa-header">
        <div className="qa-header-content">
          <h3 className="qa-title">Ask About the App</h3>
          <p className="qa-subtitle">Ask natural language questions about the app, reports, settings, or meeting data</p>
        </div>
      </div>

      <div className="qa-messages">
        {messages.map((msg) => renderMessage(msg))}
        {loading && (
          <div className="qa-message qa-message-loading">
            <Loader size={16} className="qa-icon qa-spinner" />
            <div className="qa-message-content">
              <p className="qa-message-text">Analyzing your question...</p>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleAsk} className="qa-form">
        <div className="qa-input-group">
          <input
            type="text"
            className="qa-input"
            placeholder="Ask about the app..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
            aria-label="Question input"
          />
          <button
            type="submit"
            className="qa-button"
            disabled={loading || !question.trim()}
            aria-label="Send question"
            title={loading ? 'Processing...' : 'Send question'}
          >
            {loading ? <Loader size={18} className="qa-spinner" /> : <Send size={18} />}
          </button>
        </div>
      </form>
    </div>
  );
};

export default QuestionAnswering;
