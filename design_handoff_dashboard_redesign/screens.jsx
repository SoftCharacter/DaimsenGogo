/* global React, StockCard, CandleChart, MALineChart, MACDChart */
const { useState: useStateS, useMemo: useMemoS } = React;

// ---------------- Dashboard ----------------
function Dashboard({ theme, stocks, onOpen }) {
  const [seg, setSeg] = useStateS('全部');
  const segs = window.DG.SEGMENTS;
  const list = useMemoS(() => seg === '全部' ? stocks : stocks.filter((s) => s.seg === seg), [seg, stocks]);

  const stats = useMemoS(() => {
    const up = stocks.filter((s) => s.chg > 0).length;
    const down = stocks.filter((s) => s.chg < 0).length;
    const flat = stocks.length - up - down;
    const avg = stocks.reduce((a, s) => a + s.chg, 0) / stocks.length;
    const top = [...stocks].sort((a, b) => b.chg - a.chg)[0];
    return { up, down, flat, avg, top };
  }, [stocks]);

  const segCount = (sg) => sg === '全部' ? stocks.length : stocks.filter((s) => s.seg === sg).length;

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px 40px' }}>
      {/* Header */}
      <div className="fade-in" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 32, marginBottom: 20 }}>
        <div style={{ maxWidth: 760 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.01em' }}>{theme.name}</h1>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent-bright)', background: 'var(--accent-soft)',
              padding: '4px 10px', borderRadius: 99, border: '1px solid var(--accent-line)' }}>{theme.count} 支成分股</span>
          </div>
          <p style={{ fontSize: 13.5, lineHeight: 1.7, color: 'var(--text-dim)' }}>{theme.desc}</p>
        </div>
        <OverviewPanel stats={stats} count={stocks.length} />
      </div>

      {/* Segment filters */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 22 }}>
        {segs.map((sg) => {
          const on = seg === sg;
          const c = segCount(sg);
          return (
            <button key={sg} onClick={() => setSeg(sg)}
              style={{ cursor: 'pointer', fontFamily: 'var(--font-cjk)', fontSize: 12.5, fontWeight: 600,
                padding: '7px 13px', borderRadius: 'var(--r-pill)', transition: 'all 0.2s var(--ease)',
                display: 'inline-flex', alignItems: 'center', gap: 7,
                border: '1px solid ' + (on ? 'var(--accent-line)' : 'var(--border)'),
                color: on ? '#fff' : 'var(--text-dim)',
                background: on ? 'var(--accent)' : 'var(--surface)' }}>
              {sg}
              <span className="mono" style={{ fontSize: 10.5, opacity: on ? 0.85 : 0.5,
                background: on ? 'rgba(255,255,255,0.18)' : 'var(--surface-3)', padding: '1px 6px', borderRadius: 99 }}>{c}</span>
            </button>
          );
        })}
      </div>

      {/* Card grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(var(--card-min, 330px), 1fr))', gap: 16 }}>
        {list.map((s, i) => <StockCard key={s.code} s={s} onOpen={onOpen} delay={i * 35} />)}
      </div>
    </div>
  );
}

// breadth + averages compact panel
function OverviewPanel({ stats, count }) {
  const upPct = (stats.up / count) * 100;
  const flatPct = (stats.flat / count) * 100;
  const avgUp = stats.avg >= 0;
  return (
    <div className="panel fade-in" style={{ flex: 'none', width: 340, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.16em', color: 'var(--text-faint)' }}>板块概览</span>
        <span className="num" style={{ fontSize: 13, fontWeight: 700, color: avgUp ? 'var(--up)' : 'var(--down)' }}>
          均 {avgUp ? '+' : ''}{stats.avg.toFixed(2)}%
        </span>
      </div>
      {/* breadth bar */}
      <div style={{ display: 'flex', height: 8, borderRadius: 99, overflow: 'hidden', background: 'var(--surface-3)' }}>
        <div style={{ width: `${upPct}%`, background: 'var(--up)' }} />
        <div style={{ width: `${flatPct}%`, background: 'var(--text-faint)' }} />
        <div style={{ flex: 1, background: 'var(--down)' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        {[['上涨', stats.up, 'var(--up)'], ['平盘', stats.flat, 'var(--text-dim)'], ['下跌', stats.down, 'var(--down)']].map(([l, v, c]) => (
          <div key={l} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span className="num" style={{ fontSize: 20, fontWeight: 700, color: c }}>{v}</span>
            <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{l}</span>
          </div>
        ))}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'flex-end', borderLeft: '1px solid var(--border)', paddingLeft: 16 }}>
          <span className="num" style={{ fontSize: 13, fontWeight: 700, color: 'var(--up)' }}>+{stats.top.chg.toFixed(2)}%</span>
          <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>领涨 {stats.top.name}</span>
        </div>
      </div>
    </div>
  );
}

// ---------------- AI Analysis ----------------
function AIAnalysis() {
  const [q, setQ] = useStateS('');
  const tasks = window.DG.TASKS;
  const sugg = window.DG.SUGGESTIONS;
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '40px 0' }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '0 32px' }}>
        {/* Hero input */}
        <div className="fade-in" style={{ textAlign: 'center', marginBottom: 14 }}>
          <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.22em', color: 'var(--accent-bright)' }}>AI 供应链分析</span>
          <h1 style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-0.02em', margin: '12px 0 8px' }}>
            描述产品、技术或事件，<br />AI 为你拆解<span style={{ color: 'var(--accent-bright)' }}>全链路</span>投资图谱
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text-dim)' }}>从上游原材料到下游整机集成，自动识别 A 股成分股并生成盘面洞察</p>
        </div>

        <div className="panel fade-in" style={{ padding: 10, marginTop: 26, display: 'flex', gap: 10, alignItems: 'center',
          maxWidth: 760, margin: '26px auto 0' }}>
          <span style={{ paddingLeft: 10, color: 'var(--text-faint)', fontSize: 18 }}>✦</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="例如：华为昇腾 950 芯片全供应链"
            style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', color: 'var(--text)',
              fontFamily: 'var(--font-cjk)', fontSize: 15, padding: '10px 0' }} />
          <button style={{ cursor: 'pointer', border: 'none', borderRadius: 'var(--r-sm)', padding: '12px 24px',
            fontFamily: 'var(--font-cjk)', fontWeight: 700, fontSize: 14, color: '#fff',
            background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))', boxShadow: '0 10px 24px -12px var(--accent)' }}>
            开始分析
          </button>
        </div>
        <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap', justifyContent: 'center', marginTop: 16 }}>
          <span style={{ fontSize: 12.5, color: 'var(--text-faint)', alignSelf: 'center' }}>试试：</span>
          {sugg.map((s) => (
            <button key={s} onClick={() => setQ(s)} className="card"
              style={{ cursor: 'pointer', fontFamily: 'var(--font-cjk)', fontSize: 12.5, color: 'var(--text-dim)',
                background: 'var(--surface)', padding: '7px 13px' }}>{s}</button>
          ))}
        </div>

        {/* History */}
        <div style={{ marginTop: 46 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.16em', color: 'var(--text-faint)' }}>历史任务</span>
            <span className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{tasks.length} 条记录</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14 }}>
            {tasks.map((t, i) => (
              <div key={i} className="card fade-in" style={{ animationDelay: `${i * 60}ms`, background: 'var(--surface)', padding: '16px 18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <span style={{ fontWeight: 600, fontSize: 15 }}>{t.name}</span>
                  <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--down)', background: 'var(--down-soft)',
                    padding: '3px 9px', borderRadius: 99 }}>● 已完成</span>
                </div>
                <div style={{ display: 'flex', gap: 14, margin: '12px 0 14px', color: 'var(--text-faint)', fontSize: 11.5 }}>
                  <span className="mono">{t.steps} 环节</span>
                  <span>·</span>
                  <span className="mono">{t.date}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button style={{ cursor: 'pointer', border: 'none', borderRadius: 'var(--r-sm)', padding: '8px 18px', fontFamily: 'var(--font-cjk)',
                    fontWeight: 600, fontSize: 12.5, color: '#fff', background: 'var(--accent)' }}>继续</button>
                  <button className="card" style={{ cursor: 'pointer', borderRadius: 'var(--r-sm)', padding: '8px 16px', fontFamily: 'var(--font-cjk)',
                    fontWeight: 600, fontSize: 12.5, color: 'var(--text-dim)', background: 'transparent' }}>删除</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

window.Dashboard = Dashboard;
window.AIAnalysis = AIAnalysis;
