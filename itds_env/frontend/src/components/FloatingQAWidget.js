import React, { useState, useEffect, useRef } from 'react';
import { Send, MessageCircle, X, AlertCircle, Loader, Sparkles, Bot, User, Copy, ThumbsUp, ThumbsDown, RotateCcw } from 'lucide-react';
import { aiAPI } from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import './FloatingQAWidget.css';

const FloatingQAWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      type: 'bot',
      text: 'Hi! Ask me anything about the ITDS Board Minutes app.',
      timestamp: new Date(),
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState(null);
  const messagesEndRef = useRef(null);
  const widgetPanelRef = useRef(null);
  const streamingTimerRef = useRef(null);
  const quickPrompts = [
    'Show me recent meetings',
    'What were the main themes this month?',
    'Summarize the latest anomalies',
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const handleOutsideClick = (event) => {
      if (widgetPanelRef.current && !widgetPanelRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  useEffect(() => () => {
    if (streamingTimerRef.current) {
      clearInterval(streamingTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!streamingMessageId) return undefined;

    if (streamingTimerRef.current) {
      clearInterval(streamingTimerRef.current);
    }

    streamingTimerRef.current = setInterval(() => {
      let completed = false;

      setMessages((prev) => prev.map((msg) => {
        if (msg.id !== streamingMessageId) {
          return msg;
        }

        const fullText = msg.fullText || msg.text || '';
        const currentLength = (msg.text || '').length;
        const nextLength = Math.min(fullText.length, currentLength + 3);
        completed = nextLength >= fullText.length;

        return {
          ...msg,
          text: fullText.slice(0, nextLength),
          streaming: !completed,
        };
      }));

      if (completed) {
        clearInterval(streamingTimerRef.current);
        streamingTimerRef.current = null;
        setStreamingMessageId(null);
      }
    }, 18);

    return () => {
      if (streamingTimerRef.current) {
        clearInterval(streamingTimerRef.current);
        streamingTimerRef.current = null;
      }
    };
  }, [streamingMessageId]);

  const updateMessage = (messageId, updater) => {
    setMessages((prev) => prev.map((msg) => (msg.id === messageId ? updater(msg) : msg)));
  };

  const submitQuestion = async (rawQuestion) => {
    const nextQuestion = String(rawQuestion || '').trim();

    if (!nextQuestion) {
      notifyError('Please enter a question');
      return;
    }

    const userMessage = {
      id: `user-${Date.now()}`,
      type: 'user',
      text: nextQuestion,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    try {
      const history = messages
        .filter((m) => m.type !== 'loading' && m.type !== 'error' && m.id !== 'welcome')
        .map((m) => ({
          role: m.type === 'user' ? 'user' : 'assistant',
          content: m.fullText || m.text,
        }));

      const response = await aiAPI.answerQuestion(nextQuestion, history);
      const result = response.data || response;
      const fullText = String(result.answer || 'No answer found');
      const botMessageId = `bot-${Date.now()}`;

      setMessages((prev) => [...prev, {
        id: botMessageId,
        type: 'bot',
        text: '',
        fullText,
        prompt: nextQuestion,
        feedback: null,
        timestamp: new Date(),
      }]);
      setStreamingMessageId(botMessageId);
    } catch (error) {
      const errorMessage = {
        id: `error-${Date.now()}`,
        type: 'error',
        text: error.response?.data?.error || 'Error answering question',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      notifyError('Failed to get answer');
    } finally {
      setLoading(false);
    }
  };

  const handleAsk = async (e) => {
    e.preventDefault();
    await submitQuestion(question);
  };

  const handleCopy = async (msg) => {
    const text = msg.fullText || msg.text || '';
    if (!text) return;

    try {
      await navigator.clipboard.writeText(text);
      notifySuccess('Copied answer');
    } catch (error) {
      notifyError('Could not copy the answer');
    }
  };

  const handleFeedback = (messageId, feedback) => {
    updateMessage(messageId, (msg) => ({
      ...msg,
      feedback: msg.feedback === feedback ? null : feedback,
    }));
  };

  const handleRetry = (msg) => {
    if (!msg.prompt) return;
    submitQuestion(msg.prompt);
  };

  const renderMessage = (msg) => {
    if (msg.type === 'loading') {
      return (
        <div key={msg.id} className="qa-widget-message qa-widget-message-loading">
          <div className="qa-widget-avatar qa-widget-avatar-bot">
            <Bot size={14} />
          </div>
          <div className="qa-widget-message-content">
            <p className="qa-widget-message-text qa-widget-typing-text">
              Thinking<span className="qa-widget-typing-dots"><span>.</span><span>.</span><span>.</span></span>
            </p>
          </div>
        </div>
      );
    }

    if (msg.type === 'error') {
      return (
        <div key={msg.id} className="qa-widget-message qa-widget-message-error">
          <div className="qa-widget-avatar qa-widget-avatar-error">
            <AlertCircle size={14} />
          </div>
          <div className="qa-widget-message-content">
            <p className="qa-widget-message-text">{msg.text}</p>
            <span className="qa-widget-message-time">
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        </div>
      );
    }

    if (msg.type === 'user') {
      return (
        <div key={msg.id} className="qa-widget-message qa-widget-message-user">
          <div className="qa-widget-avatar qa-widget-avatar-user">
            <User size={14} />
          </div>
          <div className="qa-widget-message-content">
            <p className="qa-widget-message-text">{msg.text}</p>
            <span className="qa-widget-message-time">
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        </div>
      );
    }

    if (msg.type === 'bot') {
      return (
        <div key={msg.id} className="qa-widget-message qa-widget-message-bot" data-streaming={msg.streaming ? 'true' : 'false'}>
          <div className="qa-widget-avatar qa-widget-avatar-bot">
            <Bot size={14} />
          </div>
          <div className="qa-widget-message-content">
            <p className="qa-widget-message-text">{msg.text}</p>
            <span className="qa-widget-message-time">
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            <div className="qa-widget-message-actions" aria-label="Message actions">
              <button type="button" className={`qa-widget-action-btn ${msg.feedback === 'up' ? 'is-active' : ''}`} onClick={() => handleFeedback(msg.id, 'up')} aria-label="Mark answer as helpful" title="Helpful">
                <ThumbsUp size={14} />
              </button>
              <button type="button" className={`qa-widget-action-btn ${msg.feedback === 'down' ? 'is-active' : ''}`} onClick={() => handleFeedback(msg.id, 'down')} aria-label="Mark answer as not helpful" title="Not helpful">
                <ThumbsDown size={14} />
              </button>
              <button type="button" className="qa-widget-action-btn" onClick={() => handleCopy(msg)} aria-label="Copy answer" title="Copy">
                <Copy size={14} />
              </button>
              <button type="button" className="qa-widget-action-btn" onClick={() => handleRetry(msg)} aria-label="Retry this question" title="Retry">
                <RotateCcw size={14} />
              </button>
            </div>
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`qa-widget-fab ${isOpen ? 'qa-widget-fab-active' : ''}`}
        title="Ask me about the app"
        aria-label="Open app help chat"
      >
        {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div className="qa-widget-backdrop" onClick={() => setIsOpen(false)}>
          <div className="qa-widget-container" ref={widgetPanelRef} onClick={(e) => e.stopPropagation()}>
          {/* Header */}
          <div className="qa-widget-header">
            <div className="qa-widget-header-content">
              <div className="qa-widget-title-row">
                <Sparkles size={14} />
                <h3 className="qa-widget-title">App Assistant</h3>
              </div>
              <p className="qa-widget-subtitle">Ask about the app, reports, charts, or settings</p>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="qa-widget-close"
              aria-label="Close"
            >
              <X size={20} />
            </button>
          </div>

          {/* Messages */}
          <div className="qa-widget-messages">
            {messages.map((msg) => renderMessage(msg))}
            {loading && (
              <div className="qa-widget-message qa-widget-message-loading">
                <Loader className="qa-widget-icon qa-widget-spinner" size={16} />
                <div className="qa-widget-message-content">
                  <p className="qa-widget-message-text qa-widget-typing-text">
                    Thinking<span className="qa-widget-typing-dots"><span>.</span><span>.</span><span>.</span></span>
                  </p>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="qa-widget-suggestions" aria-label="Quick prompts">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="qa-widget-suggestion"
                onClick={() => submitQuestion(prompt)}
                disabled={loading}
              >
                {prompt}
              </button>
            ))}
          </div>

          {/* Input Form */}
          <form onSubmit={handleAsk} className="qa-widget-form">
            <div className="qa-widget-input-group">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about the app..."
                className="qa-widget-input"
                disabled={loading}
              />
              <button
                type="submit"
                className="qa-widget-button"
                disabled={loading || !question.trim()}
                aria-label="Send message"
              >
                <Send size={18} />
              </button>
            </div>
          </form>
          </div>
        </div>
      )}
    </>
  );
};

export default FloatingQAWidget;
