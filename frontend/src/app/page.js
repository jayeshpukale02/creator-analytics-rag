'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

const BACKEND = 'http://localhost:8000';

// Generate a stable session ID once per browser tab
function makeThreadId() {
  return 'thread_' + Math.random().toString(36).slice(2) + Date.now();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatNum(n) {
  if (n == null || n === 0) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return n.toString();
}

function formatEngagement(rate) {
  if (rate == null) return 'N/A';
  return rate + '%';
}

function extractYouTubeId(url) {
  const m = url?.match(/(?:v=|\/)([0-9A-Za-z_-]{11})/);
  return m ? m[1] : null;
}

function parseCitations(text) {
  const re = /\[Source:\s*Video\s*([AB])[^\]]*\]/gi;
  const seen = new Set();
  let m;
  while ((m = re.exec(text)) !== null) seen.add(m[1].toUpperCase());
  return [...seen];
}

function now() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function VideoCard({ label, data, url }) {
  const ytId = label === 'A' ? extractYouTubeId(url) : null;

  if (!data) {
    return (
      <div className="video-card-empty">
        <span className="icon">{label === 'A' ? '▶' : '📱'}</span>
        <span className={`label`}>Video {label}</span>
        <span style={{ fontSize: 12 }}>
          {label === 'A' ? 'YouTube' : 'Instagram'} · paste a URL above and click Analyze
        </span>
      </div>
    );
  }

  return (
    <div className={`video-card ${label.toLowerCase()}`}>
      <div className="video-embed">
        {ytId ? (
          <iframe
            src={`https://www.youtube.com/embed/${ytId}`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            title={`Video ${label}`}
          />
        ) : (
          <div className="video-embed-placeholder">
            <span className="icon">📱</span>
            <span>Instagram Reel</span>
            <span style={{ fontSize: 11, opacity: 0.6 }}>@{data.creator}</span>
          </div>
        )}
      </div>

      <div className="video-card-body">
        <div className="video-card-header">
          <span className={`video-badge ${label.toLowerCase()}`}>
            Video {label}
          </span>
          <span className="video-platform-tag">{data.platform?.toUpperCase()}</span>
        </div>

        <div className="video-creator" title={data.creator}>
          @{data.creator}
        </div>

        <div className="video-metrics">
          <div className="metric-chip">
            <span className="metric-label">Views</span>
            <span className="metric-value">{formatNum(data.views)}</span>
          </div>
          <div className="metric-chip">
            <span className="metric-label">Likes</span>
            <span className="metric-value">{formatNum(data.likes)}</span>
          </div>
          <div className="metric-chip">
            <span className="metric-label">Comments</span>
            <span className="metric-value">{formatNum(data.comments)}</span>
          </div>
          <div className="metric-chip engagement">
            <span className="metric-label">Engagement</span>
            <span className="metric-value">{formatEngagement(data.engagement_rate)}</span>
          </div>
          <div className="metric-chip">
            <span className="metric-label">Followers</span>
            <span className="metric-value">{formatNum(data.follower_count)}</span>
          </div>
          <div className="metric-chip">
            <span className="metric-label">Duration</span>
            <span className="metric-value">{data.duration_secs}s</span>
          </div>
        </div>

        {data.hashtags?.length > 0 && (
          <div className="video-hashtags">
            {data.hashtags.slice(0, 5).map((tag, i) => (
              <span key={i} className="hashtag">{tag}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <div className="typing-dot" />
      <div className="typing-dot" />
      <div className="typing-dot" />
    </div>
  );
}

const SUGGESTED = [
  'Why did Video A get more engagement than Video B?',
  "What's the engagement rate of each video?",
  'Compare the hooks in the first 5 seconds.',
  "Who's the creator of Video B and what's their follower count?",
  'Suggest improvements for B based on what worked in A.',
];

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function HomePage() {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [instagramUrl, setInstagramUrl] = useState('');
  const [ingesting, setIngesting] = useState(false);
  const [ingestStatus, setIngestStatus] = useState(null); // { type, msg }
  const [videoData, setVideoData] = useState({ A: null, B: null });

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  // Stable session ID — persists for the lifetime of this browser tab
  const threadId = useRef(makeThreadId());

  // Auto-scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  // ── Ingest handler ──────────────────────────────────────────────────────────
  const handleIngest = useCallback(async () => {
    if (!youtubeUrl.trim() || !instagramUrl.trim()) {
      setIngestStatus({ type: 'error', msg: 'Both URLs are required.' });
      return;
    }
    setIngesting(true);
    setIngestStatus({ type: 'loading', msg: 'Scraping videos, embedding transcripts…' });
    setVideoData({ A: null, B: null });

    try {
      const res = await fetch(`${BACKEND}/api/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ youtube_url: youtubeUrl, instagram_url: instagramUrl }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Ingest failed');
      }

      const data = await res.json();
      const a = data.videos?.video_A;
      const b = data.videos?.video_B;

      setVideoData({ A: a, B: b });
      setIngestStatus({
        type: 'success',
        msg: `✓ Ingested ${data.total_chunks} chunks · RAG chatbot ready`,
      });

      // Seed a system message in chat
      setMessages([{
        role: 'system',
        content: `Videos ingested. Video A: @${a?.creator} (${a?.platform}) · Video B: @${b?.creator} (${b?.platform}). Ask me anything!`,
        time: now(),
      }]);
    } catch (e) {
      setIngestStatus({ type: 'error', msg: e.message });
    } finally {
      setIngesting(false);
    }
  }, [youtubeUrl, instagramUrl]);

  // ── Chat / streaming handler ────────────────────────────────────────────────
  const handleSend = useCallback(async (text) => {
    const question = (text || input).trim();
    if (!question || streaming) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: question, time: now() }]);
    setStreaming(true);

    // Placeholder for streaming assistant reply
    const assistantIdx = Date.now();
    setMessages(prev => [...prev, { role: 'assistant', content: '', time: now(), id: assistantIdx, streaming: true }]);

    try {
      const res = await fetch(`${BACKEND}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, thread_id: threadId.current }),
      });

      if (!res.ok) throw new Error('Stream request failed');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let full = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        full += chunk;

        setMessages(prev => prev.map(m =>
          m.id === assistantIdx ? { ...m, content: full } : m
        ));
      }

      // Finalize — mark streaming done
      setMessages(prev => prev.map(m =>
        m.id === assistantIdx ? { ...m, content: full, streaming: false } : m
      ));
    } catch (e) {
      setMessages(prev => prev.map(m =>
        m.id === assistantIdx
          ? { ...m, content: `Error: ${e.message}`, streaming: false }
          : m
      ));
    } finally {
      setStreaming(false);
    }
  }, [input, streaming]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const chatReady = videoData.A !== null;

  return (
    <div className="app-shell">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-logo">
          <div className="header-logo-icon">⚡</div>
          <h1>Creator Analytics RAG</h1>
        </div>
        <span className="header-sub">LangGraph · Qdrant · Gemini</span>
      </header>

      <div className="main-layout">
        {/* ── Left panel ── */}
        <div className="left-panel">

          {/* URL input + ingest */}
          <div className="ingest-form">
            <div className="ingest-form-title">Analyze Two Videos</div>
            <div className="url-inputs">
              <div className="input-group">
                <label className="input-label">
                  <span className="label-badge a">A</span>
                  YouTube URL
                </label>
                <input
                  id="youtube-url-input"
                  className="url-input"
                  type="url"
                  placeholder="https://youtube.com/watch?v=..."
                  value={youtubeUrl}
                  onChange={e => setYoutubeUrl(e.target.value)}
                  disabled={ingesting}
                />
              </div>
              <div className="input-group">
                <label className="input-label">
                  <span className="label-badge b">B</span>
                  Instagram Reel URL
                </label>
                <input
                  id="instagram-url-input"
                  className="url-input b"
                  type="url"
                  placeholder="https://instagram.com/reel/..."
                  value={instagramUrl}
                  onChange={e => setInstagramUrl(e.target.value)}
                  disabled={ingesting}
                />
              </div>
            </div>

            <button
              id="analyze-btn"
              className="ingest-btn"
              onClick={handleIngest}
              disabled={ingesting || !youtubeUrl || !instagramUrl}
            >
              {ingesting ? (
                <><span className="spinner" /> Analyzing…</>
              ) : (
                <> Analyze Videos</>
              )}
            </button>

            {ingestStatus && (
              <div className={`status-bar ${ingestStatus.type}`}>
                {ingestStatus.type === 'loading' && <span className="spinner" />}
                {ingestStatus.msg}
              </div>
            )}
          </div>

          {/* Video cards */}
          <div className="video-cards">
            <VideoCard label="A" data={videoData.A} url={youtubeUrl} />
            <VideoCard label="B" data={videoData.B} url={instagramUrl} />
          </div>
        </div>

        {/* ── Chat panel ── */}
        <div className="chat-panel">
          <div className="chat-header">
            <span className="chat-header-icon">🤖</span>
            <h2>RAG Chat</h2>
            <div className={`chat-status-dot ${chatReady ? 'ready' : ''}`} title={chatReady ? 'Ready' : 'Ingest videos first'} />
          </div>

          <div className="chat-messages">
            {messages.length === 0 ? (
              <div className="chat-welcome">
                <span className="icon">💬</span>
                <p>Ingest two videos above, then ask anything about them — engagement, transcripts, hooks, creator info.</p>
                <div className="suggested-questions">
                  {SUGGESTED.map((q, i) => (
                    <button
                      key={i}
                      className="suggested-btn"
                      onClick={() => handleSend(q)}
                      disabled={!chatReady || streaming}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, i) => {
                if (msg.role === 'system') {
                  return (
                    <div key={i} style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono, monospace', padding: '4px 0' }}>
                      {msg.content}
                    </div>
                  );
                }

                const citations = msg.role === 'assistant' ? parseCitations(msg.content) : [];

                return (
                  <div key={i} className={`message ${msg.role}`}>
                    <div className="message-bubble">
                      {msg.content || (msg.streaming ? '' : '…')}
                    </div>
                    {msg.streaming && !msg.content && <TypingIndicator />}
                    {citations.length > 0 && (
                      <div className="citations">
                        {citations.map(c => (
                          <span key={c} className={`citation-tag ${c.toLowerCase()}`}>
                            Video {c}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="message-meta">{msg.time}</div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-area">
            <textarea
              ref={inputRef}
              id="chat-input"
              className="chat-input"
              placeholder={chatReady ? 'Ask about the videos…' : 'Ingest videos first…'}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!chatReady || streaming}
              rows={1}
            />
            <button
              id="send-btn"
              className="send-btn"
              onClick={() => handleSend()}
              disabled={!chatReady || streaming || !input.trim()}
              title="Send"
            >
              ➤
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
