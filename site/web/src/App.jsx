import { useState } from "react";
import { aiSide, facts, gnn, measurements, pipeline, privateSide, proofs, results, sql } from "./data.js";

function Section({ id, title, children }) {
  return (
    <section id={id} className="section">
      <div className="container grid">
        <h2>{title}</h2>
        <div className="body">{children}</div>
      </div>
    </section>
  );
}

function Bars({ title, rows }) {
  const max = Math.max(...rows.map(([, v]) => v));
  return (
    <div className="bars">
      <p className="bars-title">{title}</p>
      {rows.map(([name, v]) => (
        <div className={"bar" + (name === "Plan GNN" ? " strong" : "")} key={name}>
          <span>{name}</span>
          <div className="track"><div style={{ width: `${(v / max) * 100}%` }} /></div>
          <span className="mono">{v.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState("dba");

  return (
    <>
      <header className="header">
        <div className="container header-row">
          <a href="#top" className="wordmark">Blind Tuner</a>
          <nav>
            <a href="#architecture">Architecture</a>
            <a href="#results">Results</a>
            <a href="#gnn">GNN</a>
            <a href="#privacy">Privacy</a>
          </nav>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="container">
            <h1>Database tuning by AI that never sees your data.</h1>
            <p className="lead">
              The model works on a hashed shadow of the schema. Every recommendation is measured on a
              statistical twin before a DBA approves it.
            </p>
            <dl className="facts">
              {facts.map(([v, k]) => (
                <div key={k}><dt>{v}</dt><dd>{k}</dd></div>
              ))}
            </dl>
          </div>
        </section>

        <Section id="architecture" title="Architecture">
          <div className="arch">
            <div className="side">
              <h3>Private side</h3>
              <ul>{privateSide.map(([a, b]) => <li key={a}>{a}<span>{b}</span></li>)}</ul>
            </div>
            <div className="gate">
              <span>Gateway</span>
              <small>hash · strip · scan · ledger</small>
            </div>
            <div className="side">
              <h3>AI side</h3>
              <ul>{aiSide.map(([a, b]) => <li key={a}>{a}<span>{b}</span></li>)}</ul>
            </div>
          </div>
        </Section>

        <Section id="view" title="What the model sees">
          <div className="panel">
            <div className="panel-head">
              <span>Q1, weekly sales dashboard</span>
              <div className="segmented" role="group" aria-label="View">
                {Object.entries(sql).map(([k, v]) => (
                  <button key={k} aria-pressed={view === k} onClick={() => setView(k)}>{v.label}</button>
                ))}
              </div>
            </div>
            <pre>{sql[view].text}</pre>
            <p className="panel-foot">{sql[view].note}</p>
          </div>
        </Section>

        <Section id="pipeline" title="Pipeline">
          <ol className="pipeline">
            {pipeline.map(([t, d]) => <li key={t}><strong>{t}</strong><span>{d}</span></li>)}
          </ol>
        </Section>

        <Section id="results" title="Results">
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Query</th><th>Recommendation</th><th className="r">Before ms</th><th className="r">After ms</th><th className="r">Faster</th><th>Check</th></tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <tr key={r[0]}>
                    <td>{r[0]}</td><td>{r[1]}</td>
                    <td className="r mono">{r[2] || "–"}</td><td className="r mono">{r[3] || "–"}</td>
                    <td className="r mono strong">{r[4] || "–"}</td><td>{r[5]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-wrap">
            <table>
              <tbody>
                {measurements.map(([k, v]) => <tr key={k}><td>{k}</td><td className="r mono">{v}</td></tr>)}
              </tbody>
            </table>
          </div>
        </Section>

        <Section id="gnn" title="Plan GNN">
          <p className="big">{gnn.headline}</p>
          <p className="lead tight">lower median cost-estimation error than the PostgreSQL planner, on 17 query templates the model never saw in training.</p>
          <div className="bars-grid">
            <Bars title="Median q-error" rows={gnn.median} />
            <Bars title="95th percentile q-error" rows={gnn.p95} />
          </div>
          <p className="muted small">Reference model trained on 16,420 plans from DSB, TPC-H and QuickMart. Final weights in training.</p>
        </Section>

        <Section id="privacy" title="Privacy">
          <div className="proofs">
            {proofs.map(([t, r, d]) => (
              <div key={t}><p className="muted small">{t}</p><p className="proof-r">{r}</p><p>{d}</p></div>
            ))}
          </div>
        </Section>
      </main>

      <footer className="footer">
        <div className="container header-row">
          <span>Blind Tuner</span>
          <span>CodeUtsava X.0 · MIT licence</span>
        </div>
      </footer>
    </>
  );
}
