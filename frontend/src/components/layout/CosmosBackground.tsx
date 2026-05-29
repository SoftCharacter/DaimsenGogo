import { useMemo } from 'react'

/**
 * 深色星空地球冰原动态背景
 * 移植自设计交接包 cosmos.jsx：底图 + 暗角 + 地球辉光呼吸 +
 * 星点闪烁(72) + 暗面城市灯闪(14) + 流星(5) + 冰面反光/扫光。
 * 纯装饰层，pointer-events: none，不参与交互。
 */

/** 线性同余伪随机：固定种子保证布局稳定（不使用 Math.random） */
function rng(seed: number): () => number {
  let s = seed
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296
    return s / 4294967296
  }
}

export default function CosmosBackground() {
  const stars = useMemo(() => {
    const r = rng(20260529)
    return Array.from({ length: 72 }, () => ({
      x: r() * 100,
      y: Math.pow(r(), 1.3) * 62, // 越靠顶部天空越密
      s: 0.8 + r() * 1.9,
      dur: 2.2 + r() * 3.8,
      delay: -r() * 6,
    }))
  }, [])

  const city = useMemo(() => {
    const r = rng(77777)
    return Array.from({ length: 14 }, () => {
      const ang = r() * Math.PI * 2
      const rad = Math.pow(r(), 0.6) * 7.2
      return {
        x: 49.5 + Math.cos(ang) * rad,
        y: 30 + Math.sin(ang) * rad * 0.92,
        dur: 1.6 + r() * 2.6,
        delay: -r() * 4,
      }
    })
  }, [])

  const meteors = useMemo(() => {
    const r = rng(13131)
    return Array.from({ length: 5 }, () => ({
      x: 4 + r() * 62,
      y: 3 + r() * 26,
      w: 130 + r() * 90,
      dur: 7 + r() * 7,
      delay: -(r() * 14),
    }))
  }, [])

  return (
    <div className="cosmos" aria-hidden="true">
      <div className="cosmos-img" />
      <div className="cosmos-scrim" />
      <div className="cosmos-earth" />
      {stars.map((st, i) => (
        <span
          key={`s${i}`}
          className="cosmos-star"
          style={{
            left: `${st.x}%`,
            top: `${st.y}%`,
            width: st.s,
            height: st.s,
            animationDuration: `${st.dur}s`,
            animationDelay: `${st.delay}s`,
          }}
        />
      ))}
      {city.map((c, i) => (
        <span
          key={`c${i}`}
          className="cosmos-city"
          style={{
            left: `${c.x}%`,
            top: `${c.y}%`,
            animationDuration: `${c.dur}s`,
            animationDelay: `${c.delay}s`,
          }}
        />
      ))}
      {meteors.map((m, i) => (
        <span
          key={`m${i}`}
          className="cosmos-meteor"
          style={{
            left: `${m.x}%`,
            top: `${m.y}%`,
            width: m.w,
            animationDuration: `${m.dur}s`,
            animationDelay: `${m.delay}s`,
          }}
        />
      ))}
      <div className="cosmos-ice-glow" />
      <div className="cosmos-ice-sweep" />
    </div>
  )
}
