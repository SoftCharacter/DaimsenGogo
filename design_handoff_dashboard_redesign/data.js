// ---- Deterministic pseudo-random so charts are stable across reloads ----
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

// Generate `n` daily candles ending near `last` price, trending by `drift`.
function genCandles(seed, n, last, drift) {
  const rnd = mulberry32(seed);
  const out = [];
  // Work backwards from last price so the final close matches the quoted price.
  let close = last;
  for (let i = 0; i < n; i++) {
    const vol = (rnd() - 0.5) * 0.045 + drift * 0.004;
    const open = close * (1 + (rnd() - 0.5) * 0.03);
    const prevClose = close / (1 + vol);
    const high = Math.max(open, close) * (1 + rnd() * 0.025);
    const low = Math.min(open, close) * (1 - rnd() * 0.025);
    out.unshift({ o: prevClose, c: close, h: high, l: low });
    close = prevClose;
  }
  return out;
}

// Long series for the insight modal (price + MAs + MACD)
function genSeries(seed, n, last) {
  const rnd = mulberry32(seed);
  const closes = [];
  let c = last * 0.34; // start low, trend up
  for (let i = 0; i < n; i++) {
    const wobble = (rnd() - 0.5) * 0.05;
    const trend = 0.004 * Math.sin(i / 26) + 0.0016;
    c = c * (1 + wobble + trend);
    closes.push(c);
  }
  // normalize last value to `last`
  const k = last / closes[closes.length - 1];
  return closes.map((v) => v * k);
}

function ma(arr, p) {
  return arr.map((_, i) => {
    if (i < p - 1) return null;
    let s = 0; for (let j = i - p + 1; j <= i; j++) s += arr[j];
    return s / p;
  });
}

function ema(arr, p) {
  const k = 2 / (p + 1); const out = []; let prev = arr[0];
  arr.forEach((v, i) => { prev = i === 0 ? v : v * k + prev * (1 - k); out.push(prev); });
  return out;
}

function macd(closes) {
  const e12 = ema(closes, 12), e26 = ema(closes, 26);
  const dif = closes.map((_, i) => e12[i] - e26[i]);
  const dea = ema(dif, 9);
  const hist = dif.map((v, i) => (v - dea[i]) * 2);
  return { dif, dea, hist };
}

const STOCKS = [
  { name: '金钼股份', code: 'SH:601958', price: 24.17, chg: -9.98, seg: '有色金属矿产开采' },
  { name: '北方稀土', code: 'SH:600111', price: 48.62, chg: -4.63, seg: '有色金属矿产开采' },
  { name: '盛和资源', code: 'SH:600392', price: 21.89, chg: -5.77, seg: '有色金属矿产开采' },
  { name: '中国中冶', code: 'SH:601618', price: 2.83, chg: 1.43, seg: '冶炼与精炼' },
  { name: '中国铝业', code: 'SH:601600', price: 11.42, chg: 1.06, seg: '冶炼与精炼' },
  { name: '南山铝业', code: 'SH:600219', price: 5.20, chg: 0.39, seg: '冶炼与精炼' },
  { name: '云铝股份', code: 'SZ:000807', price: 28.49, chg: -0.97, seg: '金属锻造与铸造' },
  { name: '天山铝业', code: 'SZ:002532', price: 14.93, chg: -0.86, seg: '金属锻造与铸造' },
  { name: '江西铜业', code: 'SH:600362', price: 43.50, chg: 0.07, seg: '冶炼与精炼' },
  { name: '宝钛股份', code: 'SH:600456', price: 36.78, chg: 2.14, seg: '特种合金研发与生产' },
  { name: '西部超导', code: 'SH:688122', price: 58.31, chg: 3.27, seg: '特种合金研发与生产' },
  { name: '抚顺特钢', code: 'SH:600399', price: 19.44, chg: -1.52, seg: '特种合金研发与生产' },
  { name: '中航重机', code: 'SH:600765', price: 27.06, chg: 1.88, seg: '金属锻造与铸造' },
  { name: '派克新材', code: 'SH:605123', price: 64.20, chg: -2.31, seg: '金属锻造与铸造' },
  { name: '钢研高纳', code: 'SZ:300034', price: 18.77, chg: 0.92, seg: '特种合金研发与生产' },
  { name: '光威复材', code: 'SZ:300699', price: 32.55, chg: -0.44, seg: '机械加工与精密制造' },
  { name: '航发动力', code: 'SH:600893', price: 41.13, chg: 2.66, seg: '整机制造与系统集成' },
  { name: '中航沈飞', code: 'SH:600760', price: 52.88, chg: -3.05, seg: '整机制造与系统集成' },
].map((s) => {
  const seed = hashStr(s.code);
  return { ...s, candles: genCandles(seed, 30, s.price, s.chg) };
});

const SEGMENTS = [
  '全部', '有色金属矿产开采', '冶炼与精炼', '特种合金研发与生产', '金属锻造与铸造',
  '机械加工与精密制造', '表面处理与防护涂层', '整机制造与系统集成', '质量检测与军工认证', '零部件组装与集成',
];

const THEMES = [
  { name: '飞机军工有色金属供应链', desc: '飞机军工有色金属供应链涵盖钛、铝、特种钢、高温合金等有色金属在飞机制造和军工应用中的全流程，包括原材料开采、冶炼、合金生产、零部件加工、表面处理、检测及整机集成等环节，涉及军工级别材料的供应和制造。', count: 18, updated: '2 分钟前' },
  { name: '苹果Vision Pro产业链', desc: '围绕苹果 Vision Pro 及后续空间计算设备的核心供应链，涵盖光学模组、Micro-OLED 显示、传感器、芯片、结构件与精密组装等关键环节。', count: 24, updated: '1 小时前' },
];

const TASKS = [
  { name: '飞机军工有色金属供应链', status: 'completed', steps: '7/6', date: '05-29 18:40' },
  { name: '苹果Vision Pro产业链', status: 'completed', steps: '7/6', date: '05-28 09:12' },
];

const SUGGESTIONS = ['华为昇腾芯片供应链', '苹果Vision Pro产业链', '宁德时代电池供应链', '比亚迪智能驾驶产业链', '低空经济eVTOL产业链'];

const MODELS = [
  { id: 'deepseek-v4-flash', tag: '快速', ctx: '128K' },
  { id: 'deepseek-v4-pro', tag: '推理', ctx: '128K' },
  { id: 'gpt-5.4', tag: '通用', ctx: '256K' },
  { id: 'mimo-v2.5', tag: '当前使用', ctx: '200K', active: true },
];

// ---- Insight data for the stock detail modal ----
function buildInsight(stock) {
  const seed = hashStr(stock.code + 'insight');
  const N = 250;
  const closes = genSeries(seed, N, stock.price);
  const series = {
    closes,
    ma5: ma(closes, 5), ma20: ma(closes, 20), ma120: ma(closes, 120), ma240: ma(closes, 240),
    macd: macd(closes),
  };
  return {
    series,
    range: { lo: Math.min(...closes), hi: Math.max(...closes) },
    summary: [
      { k: '技术面', v: `最新收盘价 ${stock.price.toFixed(2)}，DIF -0.3586，DEA 0.1571，MACD 柱 -1.0313，短期动能转弱。` },
      { k: '筹码分布', v: '平均成本 51.46，盈利比例 11.91%，支撑位 46.88，压力位 50.92，近期筹码密集度抬升。' },
      { k: '股东结构', v: '股东人数由 2025-11-10 的 752,500 户降至 2026-05-20 的 634,199 户，变化 -118,301 户，筹码趋于集中。' },
      { k: '盈利趋势', v: '最近年报 2025 年报归母净利润 22.51 亿元，同比 +124.17%，盈利高增。' },
      { k: '大事提醒', v: '近五年暂未取得风险提示、股权变动、重大事项类大事提醒。' },
    ],
  };
}

window.DG = { STOCKS, SEGMENTS, THEMES, TASKS, SUGGESTIONS, MODELS, buildInsight };
