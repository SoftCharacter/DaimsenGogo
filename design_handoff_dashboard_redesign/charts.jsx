/* global React */
const { useMemo } = React;

// ---------- Candlestick mini chart (card) ----------
function CandleChart({ candles, height = 150, showRef = true }) {
  const W = 600, H = height, padX = 10, padTop = 10, padBot = 10;
  const { bars, refY } = useMemo(() => {
    const hi = Math.max(...candles.map((c) => c.h));
    const lo = Math.min(...candles.map((c) => c.l));
    const span = hi - lo || 1;
    const innerW = W - padX * 2;
    const innerH = H - padTop - padBot;
    const step = innerW / candles.length;
    const bw = Math.max(3, step * 0.62);
    const y = (v) => padTop + (1 - (v - lo) / span) * innerH;
    const bars = candles.map((c, i) => {
      const cx = padX + step * i + step / 2;
      const up = c.c >= c.o;
      return {
        cx, up,
        wickTop: y(c.h), wickBot: y(c.l),
        bodyTop: y(Math.max(c.o, c.c)), bodyBot: y(Math.min(c.o, c.c)), bw,
      };
    });
    const refY = y(candles[0].o);
    return { bars, refY };
  }, [candles, H]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: H, display: 'block' }}>
      {showRef && (
        <line x1={padX} x2={W - padX} y1={refY} y2={refY}
          stroke="var(--text-faint)" strokeWidth="1" strokeDasharray="3 5" opacity="0.5" />
      )}
      {bars.map((b, i) => {
        const col = b.up ? 'var(--up)' : 'var(--down)';
        const bodyH = Math.max(1.5, b.bodyBot - b.bodyTop);
        return (
          <g key={i}>
            <line x1={b.cx} x2={b.cx} y1={b.wickTop} y2={b.wickBot} stroke={col} strokeWidth="1.4" />
            <rect x={b.cx - b.bw / 2} y={b.bodyTop} width={b.bw} height={bodyH} fill={col} rx="0.5" />
          </g>
        );
      })}
    </svg>
  );
}

// ---------- Sparkline (overview / small) ----------
function Sparkline({ values, up, width = 120, height = 34 }) {
  const d = useMemo(() => {
    const hi = Math.max(...values), lo = Math.min(...values), span = hi - lo || 1;
    return values.map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = (1 - (v - lo) / span) * (height - 4) + 2;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }, [values, width, height]);
  const col = up ? 'var(--up)' : 'var(--down)';
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width, height }}>
      <path d={d} fill="none" stroke={col} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ---------- MA line chart (insight modal) ----------
function MALineChart({ series, range }) {
  const W = 900, H = 320, padL = 4, padR = 8, padT = 18, padB = 26;
  const { hi, lo } = range;
  const span = (hi - lo) * 1.04 || 1;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const n = series.closes.length;
  const x = (i) => padL + (i / (n - 1)) * innerW;
  const y = (v) => padT + (1 - (v - lo) / span) * innerH;
  const line = (arr) => arr.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .filter(Boolean).join(' ');
  const gridVals = [lo, lo + span * 0.5, hi];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
      {gridVals.map((v, i) => (
        <g key={i}>
          <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke="var(--grid)" strokeWidth="1" />
          <text x={padL + 4} y={y(v) - 5} fill="var(--text-faint)" fontSize="13" fontFamily="var(--font-mono)">{v.toFixed(2)}</text>
        </g>
      ))}
      <polyline points={line(series.closes)} fill="none" stroke="var(--price-line)" strokeWidth="1.4" opacity="0.85" />
      <polyline points={line(series.ma5)} fill="none" stroke="var(--ma5)" strokeWidth="1.6" />
      <polyline points={line(series.ma20)} fill="none" stroke="var(--ma20)" strokeWidth="1.6" />
      <polyline points={line(series.ma120)} fill="none" stroke="var(--ma120)" strokeWidth="1.6" />
      <polyline points={line(series.ma240)} fill="none" stroke="var(--ma240)" strokeWidth="1.6" />
    </svg>
  );
}

// ---------- MACD chart (insight modal) ----------
function MACDChart({ macd }) {
  const W = 900, H = 200, padL = 4, padR = 8, padT = 14, padB = 22;
  const { dif, dea, hist } = macd;
  const all = [...dif, ...dea, ...hist];
  const hi = Math.max(...all), lo = Math.min(...all), span = Math.max(hi, -lo) * 2.1 || 1;
  const mid = padT + (H - padT - padB) / 2;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const n = dif.length;
  const x = (i) => padL + (i / (n - 1)) * innerW;
  const y = (v) => mid - (v / span) * innerH;
  const bw = Math.max(0.8, innerW / n * 0.6);
  const poly = (arr) => arr.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
      <line x1={padL} x2={W - padR} y1={mid} y2={mid} stroke="var(--grid)" strokeWidth="1" />
      {hist.map((v, i) => {
        const up = v >= 0;
        const hgt = Math.abs(y(v) - mid);
        return <rect key={i} x={x(i) - bw / 2} y={up ? y(v) : mid} width={bw} height={Math.max(0.5, hgt)}
          fill={up ? 'var(--up)' : 'var(--down)'} opacity="0.85" />;
      })}
      <polyline points={poly(dif)} fill="none" stroke="var(--ma5)" strokeWidth="1.5" />
      <polyline points={poly(dea)} fill="none" stroke="var(--ma20)" strokeWidth="1.5" />
    </svg>
  );
}

Object.assign(window, { CandleChart, Sparkline, MALineChart, MACDChart });
