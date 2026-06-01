/* global React */
(function () {
  const { useMemo } = React;
  function rng(seed) { let s = seed; return () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296; }; }

  // Warm daytime scene driven by the uploaded dune+planet artwork, with gentle
  // motion layers: sky glow breathe · drifting clouds · planet band flow + golden
  // rim · sand highlight sweep · fine wind-sand particles.
  function DayScene() {
    const sand = useMemo(() => {
      const r = rng(60606); const arr = [];
      for (let i = 0; i < 26; i++) {
        arr.push({ x: r() * 100, y: 70 + r() * 26, s: 1 + r() * 2.2, dur: 6 + r() * 8, delay: -r() * 12, drift: (r() * 2 - 1) });
      }
      return arr;
    }, []);
    const clouds = useMemo(() => ([
      { y: 12, w: 34, h: 9, dur: 42, delay: 0, op: 0.62 },
      { y: 24, w: 22, h: 6, dur: 33, delay: -18, op: 0.5 },
      { y: 34, w: 28, h: 8, dur: 54, delay: -30, op: 0.52 },
      { y: 48, w: 42, h: 11, dur: 66, delay: -50, op: 0.42 },
    ]), []);

    return (
      <div className="dayscene" aria-hidden="true">
        <div className="dayscene-img" />
        <div className="dayscene-skyglow" />
        {clouds.map((c, i) => (
          <span key={'cl' + i} className="day-cloud" style={{ top: c.y + '%', width: c.w + 'vw', height: c.h + 'vh', opacity: c.op, animationDuration: c.dur + 's', animationDelay: c.delay + 's' }} />
        ))}
        {/* planet golden rim + flowing bands */}
        <div className="day-planet">
          <div className="day-planet-disk"><div className="day-planet-bands" /></div>
          <div className="day-planet-rim" />
        </div>
        {/* sand surface highlight sweep */}
        <div className="day-sandsweep" />
        {/* fine wind-blown sand particles near the ground */}
        {sand.map((p, i) => (
          <span key={'sd' + i} className="day-sand" style={{ left: p.x + '%', top: p.y + '%', width: p.s, height: p.s, '--dx': (p.drift * 60) + 'px', animationDuration: p.dur + 's', animationDelay: p.delay + 's' }} />
        ))}
        <div className="dayscene-scrim" />
      </div>
    );
  }
  window.DayScene = DayScene;
})();
