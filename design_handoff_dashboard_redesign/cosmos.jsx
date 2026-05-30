/* global React */
(function () {
  const { useMemo } = React;

  function rng(seed) { let s = seed; return () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296; }; }

  function CosmosBackground() {
    const stars = useMemo(() => {
      const r = rng(20260529); const arr = [];
      for (let i = 0; i < 72; i++) {
        const y = Math.pow(r(), 1.3) * 62;            // denser near top sky
        arr.push({
          x: r() * 100, y,
          s: 0.8 + r() * 1.9,
          dur: 2.2 + r() * 3.8,
          delay: -r() * 6,
        });
      }
      return arr;
    }, []);

    const city = useMemo(() => {
      const r = rng(77777); const arr = [];
      for (let i = 0; i < 14; i++) {
        // cluster over earth's lit/right side
        const ang = r() * Math.PI * 2; const rad = Math.pow(r(), 0.6) * 7.2;
        arr.push({
          x: 49.5 + Math.cos(ang) * rad,
          y: 30 + Math.sin(ang) * rad * 0.92,
          dur: 1.6 + r() * 2.6,
          delay: -r() * 4,
        });
      }
      return arr;
    }, []);

    const meteors = useMemo(() => {
      const r = rng(13131); const arr = [];
      for (let i = 0; i < 5; i++) {
        arr.push({
          x: 4 + r() * 62, y: 3 + r() * 26,
          w: 130 + r() * 90,
          dur: 7 + r() * 7,
          delay: -(r() * 14),
        });
      }
      return arr;
    }, []);

    return (
      <div className="cosmos" aria-hidden="true">
        <div className="cosmos-img" />
        <div className="cosmos-scrim" />
        <div className="cosmos-earth" />
        {stars.map((st, i) => (
          <span key={i} className="cosmos-star" style={{
            left: st.x + '%', top: st.y + '%', width: st.s, height: st.s,
            animationDuration: st.dur + 's', animationDelay: st.delay + 's',
          }} />
        ))}
        {city.map((c, i) => (
          <span key={'c' + i} className="cosmos-city" style={{
            left: c.x + '%', top: c.y + '%',
            animationDuration: c.dur + 's', animationDelay: c.delay + 's',
          }} />
        ))}
        {meteors.map((m, i) => (
          <span key={'m' + i} className="cosmos-meteor" style={{
            left: m.x + '%', top: m.y + '%', width: m.w,
            animationDuration: m.dur + 's', animationDelay: m.delay + 's',
          }} />
        ))}
        <div className="cosmos-ice-glow" />
        <div className="cosmos-ice-sweep" />
      </div>
    );
  }

  window.CosmosBackground = CosmosBackground;
})();
