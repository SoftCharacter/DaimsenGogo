/* global React, MALineChart, MACDChart */
const { useState: useStateM } = React;

// ---------------- Model config ----------------
function ModelConfig() {
  const models = window.DG.MODELS;
  const [active, setActive] = useStateM(models.findIndex((m) => m.active));
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '36px 0' }}>
      <div style={{ maxWidth: 980, margin: '0 auto', padding: '0 32px' }}>
        <div className="fade-in" style={{ marginBottom: 24 }}>
          <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.22em', color: 'var(--accent-bright)' }}>SETTINGS</span>
          <h1 style={{ fontSize: 26, fontWeight: 700, margin: '8px 0 4px' }}>模型配置</h1>
          <p style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>配置 AI 供应商接入信息，并选择用于盘面洞察与供应链拆解的模型。</p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, alignItems: 'start' }}>
          {/* Provider form */}
          <div className="panel fade-in" style={{ padding: 22 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 18 }}>
              <span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--accent-bright)' }} />
              <h2 style={{ fontSize: 15, fontWeight: 700 }}>供应商配置</h2>
            </div>
            <Field label="供应商名称" value="deepseek" />
            <Field label="Base URL" value="https://token-plan-cn.xiaomimimo.com/v1" mono />
            <Field label="API Key" placeholder="已保存，留空则不修改" type="password" mono />
            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              <button style={{ cursor: 'pointer', border: 'none', borderRadius: 'var(--r-sm)', padding: '10px 22px', fontFamily: 'var(--font-cjk)',
                fontWeight: 700, fontSize: 13.5, color: '#fff', background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
                boxShadow: '0 10px 22px -12px var(--accent)' }}>保存配置</button>
              <button className="card" style={{ cursor: 'pointer', borderRadius: 'var(--r-sm)', padding: '10px 20px', fontFamily: 'var(--font-cjk)',
                fontWeight: 600, fontSize: 13.5, color: 'var(--accent-bright)', background: 'transparent', borderColor: 'var(--accent-line)' }}>
                获取模型列表
              </button>
            </div>
          </div>

          {/* Model list */}
          <div className="panel fade-in" style={{ padding: 22 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--accent-bright)' }} />
                <h2 style={{ fontSize: 15, fontWeight: 700 }}>可用模型</h2>
              </div>
              <span className="mono" style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{models.length} 个</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              {models.map((m, i) => {
                const on = active === i;
                return (
                  <button key={m.id} onClick={() => setActive(i)} className="card"
                    style={{ cursor: 'pointer', textAlign: 'left', padding: '13px 15px', display: 'flex', alignItems: 'center',
                      justifyContent: 'space-between', background: on ? 'var(--accent-soft)' : 'var(--surface)',
                      borderColor: on ? 'var(--accent-line)' : 'var(--border)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                      <span style={{ width: 16, height: 16, borderRadius: 99, border: '2px solid ' + (on ? 'var(--accent-bright)' : 'var(--border-strong)'),
                        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {on && <span style={{ width: 7, height: 7, borderRadius: 99, background: 'var(--accent-bright)' }} />}
                      </span>
                      <span className="mono" style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)' }}>{m.id}</span>
                      <span style={{ fontSize: 10.5, color: 'var(--text-faint)', background: 'var(--surface-3)', padding: '2px 8px', borderRadius: 99 }}>{m.tag}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span className="mono" style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{m.ctx}</span>
                      {on && <span style={{ fontSize: 10.5, fontWeight: 700, color: '#fff', background: 'var(--accent)', padding: '3px 9px', borderRadius: 99 }}>当前使用</span>}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, placeholder, type = 'text', mono }) {
  return (
    <label style={{ display: 'block', marginBottom: 15 }}>
      <span style={{ display: 'block', fontSize: 11.5, fontWeight: 600, color: 'var(--text-faint)', marginBottom: 7, letterSpacing: '0.04em' }}>{label}</span>
      <input defaultValue={value} placeholder={placeholder} type={type}
        className={mono ? 'mono' : ''}
        style={{ width: '100%', border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)',
          padding: '11px 13px', color: 'var(--text)', fontSize: 13.5, fontFamily: mono ? 'var(--font-mono)' : 'var(--font-cjk)',
          outline: 'none', transition: 'border-color 0.2s' }}
        onFocus={(e) => e.target.style.borderColor = 'var(--accent-line)'}
        onBlur={(e) => e.target.style.borderColor = 'var(--border)'} />
    </label>
  );
}

// ---------------- Insight modal ----------------
function InsightModal({ stock, onClose }) {
  if (!stock) return null;
  const data = window.DG.buildInsight(stock);
  const up = stock.chg >= 0;
  const legend = [['收盘', 'var(--price-line)'], ['MA5', 'var(--ma5)'], ['MA20', 'var(--ma20)'], ['MA120', 'var(--ma120)'], ['MA240', 'var(--ma240)']];
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 40, background: 'color-mix(in oklab, var(--bg) 55%, rgba(0,0,0,0.6))',
      backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 28, animation: 'fadeIn 0.25s' }}>
      <div onClick={(e) => e.stopPropagation()} className="panel" style={{ width: 'min(1240px, 96vw)', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column', overflow: 'hidden', animation: 'modalIn 0.32s var(--ease)' }}>
        {/* header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 24px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
            <h2 style={{ fontSize: 20, fontWeight: 700 }}>{stock.name}</h2>
            <span style={{ fontSize: 12.5, color: 'var(--text-dim)' }}>盘面洞察</span>
            <span className="ticker" style={{ fontSize: 12, color: 'var(--text-faint)' }}>{stock.code}</span>
            <span className="num" style={{ fontSize: 16, fontWeight: 700, color: up ? 'var(--up)' : 'var(--down)' }}>
              {stock.price.toFixed(2)} <span style={{ fontSize: 12.5 }}>{up ? '+' : ''}{stock.chg.toFixed(2)}%</span>
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-faint)' }}>生成 2026-05-29 19:12:37</span>
            <button onClick={onClose} className="card" style={{ cursor: 'pointer', borderRadius: 'var(--r-sm)', padding: '8px 16px',
              fontFamily: 'var(--font-cjk)', fontSize: 13, fontWeight: 600, color: 'var(--text-dim)', background: 'transparent' }}>关闭 ✕</button>
          </div>
        </div>
        {/* body */}
        <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 0, flex: 1, overflow: 'hidden' }}>
          {/* charts */}
          <div style={{ overflowY: 'auto', padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 16, borderRight: '1px solid var(--border)' }}>
            <ChartBlock title="日线均线" sub="收盘价 · MA5 / MA20 / MA120 / MA240" legend={legend} height={300}>
              <MALineChart series={data.series} range={data.range} />
            </ChartBlock>
            <ChartBlock title="指标看板" sub="MACD · DIF / DEA / 柱状" legend={[['DIF', 'var(--ma5)'], ['DEA', 'var(--ma20)'], ['MACD', 'var(--up)']]} height={196}>
              <MACDChart macd={data.series.macd} />
            </ChartBlock>
          </div>
          {/* interpretation */}
          <div style={{ overflowY: 'auto', padding: '20px 22px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700 }}>结构解读</h3>
              <button style={{ cursor: 'pointer', border: 'none', borderRadius: 'var(--r-sm)', padding: '7px 15px', fontFamily: 'var(--font-cjk)',
                fontWeight: 700, fontSize: 12.5, color: '#fff', background: 'linear-gradient(135deg, var(--accent-bright), var(--accent))',
                boxShadow: '0 8px 18px -10px var(--accent)' }}>✦ 智能解盘</button>
            </div>
            <div style={{ background: 'var(--accent-soft)', border: '1px solid var(--accent-line)', borderRadius: 'var(--r-sm)', padding: '12px 14px', marginBottom: 18 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-bright)', letterSpacing: '0.08em', marginBottom: 5 }}>大事提醒</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-dim)', lineHeight: 1.6 }}>近五年暂未取得风险提示、股权变动、重大事项类大事提醒。</div>
            </div>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-faint)', letterSpacing: '0.1em', marginBottom: 12 }}>综合解读</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {data.summary.map((s, i) => (
                <div key={i} style={{ display: 'flex', gap: 12 }}>
                  <span className="num" style={{ flex: 'none', width: 24, height: 24, borderRadius: 'var(--r-sm)', background: 'var(--surface-3)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, color: 'var(--accent-bright)' }}>{i + 1}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 3 }}>{s.k}</div>
                    <div style={{ fontSize: 12.5, color: 'var(--text-dim)', lineHeight: 1.65 }}>{s.v}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChartBlock({ title, sub, legend, height, children }) {
  return (
    <div className="card" style={{ background: 'var(--surface-2)', padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 700 }}>{title}</div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>{sub}</div>
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {legend.map(([l, c]) => (
            <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-dim)' }}>
              <span style={{ width: 12, height: 2.5, borderRadius: 2, background: c }} />{l}
            </span>
          ))}
        </div>
      </div>
      <div style={{ height }}>{children}</div>
    </div>
  );
}

window.ModelConfig = ModelConfig;
window.InsightModal = InsightModal;
