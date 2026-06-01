/* global React, CandleChart, Sparkline */
const { useState, useEffect, useRef } = React;

// ---------------- Brand mark ----------------
function Logo({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" style={{ flex: 'none' }}>
      <rect x="16" y="2" width="19.8" height="19.8" rx="4" transform="rotate(45 16 2)"
        fill="var(--accent)" opacity="0.18" />
      <rect x="16" y="7.2" width="12.4" height="12.4" rx="3" transform="rotate(45 16 7.2)"
        fill="none" stroke="var(--accent-bright)" strokeWidth="2" />
      <circle cx="16" cy="16" r="2.6" fill="var(--accent-bright)" />
    </svg>
  );
}

// ---------------- Live clock / market status ----------------
function MarketStatus() {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, color: 'var(--text-dim)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <span style={{ width: 7, height: 7, borderRadius: 99, background: 'var(--down)',
          boxShadow: '0 0 0 4px var(--down-soft)', animation: 'pulse 2s infinite' }} />
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>休市</span>
      </div>
      <span style={{ fontSize: 13, opacity: 0.3 }}>·</span>
      <span className="mono" style={{ fontSize: 13.5, letterSpacing: '0.02em' }}>{hh}:{mm}<span style={{ opacity: 0.5 }}>:{ss}</span></span>
    </div>
  );
}

// ---------------- Top navigation ----------------
function Nav({ route, setRoute }) {
  const tabs = [
    { id: 'dashboard', label: '供应链看板' },
    { id: 'analysis', label: 'AI 分析' },
    { id: 'config', label: '模型配置' },
  ];
  return (
    <header style={{ height: 'var(--nav-h)', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 22px', borderBottom: '1px solid var(--border)', position: 'relative', zIndex: 20,
      background: 'color-mix(in oklab, var(--bg) 70%, transparent)', backdropFilter: 'blur(14px)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 240 }}>
        <Logo size={24} />
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: 17, letterSpacing: '-0.01em' }}>
            Daimsen<span style={{ color: 'var(--accent-bright)' }}>Gogo</span>
          </span>
          <span style={{ fontSize: 10.5, color: 'var(--text-faint)', letterSpacing: '0.32em', marginTop: 1 }}>供应链股票大屏</span>
        </div>
      </div>

      <MarketStatus />

      <nav style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', padding: 4, borderRadius: 'var(--r-pill)',
        border: '1px solid var(--border)', minWidth: 240, justifyContent: 'flex-end' }}>
        {tabs.map((t) => {
          const on = route === t.id;
          return (
            <button key={t.id} onClick={() => setRoute(t.id)}
              style={{ border: 'none', cursor: 'pointer', fontFamily: 'var(--font-cjk)', fontWeight: 600,
                fontSize: 13.5, padding: '8px 16px', borderRadius: 'var(--r-pill)', transition: 'all 0.2s var(--ease)',
                color: on ? '#fff' : 'var(--text-dim)',
                background: on ? 'var(--accent)' : 'transparent',
                boxShadow: on ? '0 6px 18px -8px var(--accent)' : 'none' }}>
              {t.label}
            </button>
          );
        })}
      </nav>
    </header>
  );
}

// ---------------- Sidebar (theme list) ----------------
function Sidebar({ themes, active, setActive }) {
  return (
    <aside style={{ width: 'var(--sidebar-w)', flex: 'none', borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', height: '100%', background: 'color-mix(in oklab, var(--surface) 40%, transparent)' }}>
      <div style={{ padding: '18px 18px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.18em', color: 'var(--text-faint)', textTransform: 'uppercase' }}>主题列表</span>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', background: 'var(--surface-2)',
          padding: '2px 8px', borderRadius: 99 }}>{themes.length}</span>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {themes.map((t, i) => {
          const on = active === i;
          return (
            <button key={i} onClick={() => setActive(i)} className="card"
              style={{ textAlign: 'left', cursor: 'pointer', padding: '13px 14px', background: on ? 'var(--accent-soft)' : 'var(--surface)',
                borderColor: on ? 'var(--accent-line)' : 'var(--border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 6, height: 6, borderRadius: 99, background: on ? 'var(--accent-bright)' : 'var(--text-faint)' }} />
                <span style={{ fontWeight: 600, fontSize: 13.5, color: on ? 'var(--text)' : 'var(--text-dim)' }}>{t.name}</span>
              </div>
              <span style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.5,
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{t.desc}</span>
              <div style={{ display: 'flex', gap: 12, marginTop: 2 }}>
                <span className="mono" style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{t.count} 支</span>
                <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>· {t.updated}</span>
              </div>
            </button>
          );
        })}
      </div>
      <div style={{ padding: 14 }}>
        <button style={{ width: '100%', cursor: 'pointer', border: 'none', borderRadius: 'var(--r-sm)', padding: '12px',
          fontFamily: 'var(--font-cjk)', fontWeight: 600, fontSize: 13.5, color: '#fff',
          background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
          boxShadow: '0 10px 26px -12px var(--accent)', transition: 'transform 0.15s var(--ease)' }}
          onMouseDown={(e) => e.currentTarget.style.transform = 'scale(0.98)'}
          onMouseUp={(e) => e.currentTarget.style.transform = 'none'}
          onMouseLeave={(e) => e.currentTarget.style.transform = 'none'}>
          + 新建分析
        </button>
      </div>
    </aside>
  );
}

// ---------------- Stock card ----------------
function StockCard({ s, onOpen, delay }) {
  const up = s.chg >= 0;
  const closes = s.candles.map((c) => c.c);
  return (
    <button onClick={() => onOpen(s)} className="card fade-in"
      style={{ animationDelay: `${delay}ms`, cursor: 'pointer', textAlign: 'left', background: 'var(--surface)',
        padding: 0, display: 'flex', flexDirection: 'column', width: '100%' }}>
      <div style={{ padding: '14px 16px 8px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <span className="card-name" style={{ fontWeight: 600, fontSize: 15.5, color: 'var(--text)', whiteSpace: 'nowrap' }}>{s.name}</span>
          </div>
          <span className="ticker" style={{ fontSize: 11, color: 'var(--text-faint)', flex: 'none', marginTop: 3 }}>{s.code}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span className="num" style={{ fontSize: 26, fontWeight: 600, lineHeight: 1, color: up ? 'var(--up)' : 'var(--down)' }}>
            {s.price.toFixed(2)}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '3px 8px', borderRadius: 'var(--r-sm)',
            background: up ? 'var(--up-soft)' : 'var(--down-soft)', color: up ? 'var(--up)' : 'var(--down)',
            fontSize: 12.5, fontWeight: 700 }} className="num">
            <span style={{ fontSize: 10 }}>{up ? '▲' : '▼'}</span>{up ? '+' : ''}{s.chg.toFixed(2)}%
          </span>
        </div>
      </div>
      <div style={{ padding: '0 6px' }}>
        <CandleChart candles={s.candles} height={132} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '9px 16px 13px',
        borderTop: '1px solid var(--border)', marginTop: 4 }}>
        <span style={{ fontSize: 11, color: 'var(--text-faint)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 5, height: 5, borderRadius: 99, background: 'var(--accent-bright)' }} />{s.seg}
        </span>
        <span style={{ fontSize: 11, color: 'var(--accent-bright)', fontWeight: 600, opacity: 0.9 }}>盘面洞察 →</span>
      </div>
    </button>
  );
}

Object.assign(window, { Logo, Nav, Sidebar, StockCard, MarketStatus });
