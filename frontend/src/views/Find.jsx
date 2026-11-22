import { useEffect, useState } from 'react'
import { api } from '../api.js'

function Bar({ label, value }) {
  const pct = Math.round(value * 100)
  return (
    <>
      <div className="bar-label">{label} · {pct}</div>
      <div className="bar"><div className="fill" style={{ width: pct + '%' }}></div></div>
    </>
  )
}

function sourceLabel(job) {
  return 'via ' + job.source
}

function MatchPanel({ result, onTailor }) {
  const [gap, setGap] = useState(null)
  const [gapState, setGapState] = useState('idle')
  const r = result
  const reasons = r.reasons.filter((x) => !x.startsWith('Remote requested'))

  const loadGap = async () => {
    setGapState('loading')
    try { setGap(await api(`/api/jobs/${r.job.id}/skill-gap`)); setGapState('ok') }
    catch (e) { setGapState(e.message) }
  }

  return (
    <section className="match-col">
      <small className="panel-label">Why this matches</small>
      <div className="score-row">
        <span className="score">{Math.round(r.scores.total * 100)}</span>
        <span className="score-sub">/ 100<br />{r.job.title} · {r.job.company}</span>
      </div>
      <Bar label="Relevance" value={r.scores.relevance} />
      <Bar label="Skills" value={r.scores.skills} />
      <Bar label="Location" value={r.scores.location} />
      <Bar label="Experience" value={r.scores.experience} />
      <ul className="reasons">{reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
      <div className="row">
        <button className="btn" onClick={() => onTailor(r.job.id)}>Tailor my resume</button>
        <button className="btn secondary" onClick={loadGap}>
          {gapState === 'loading' ? 'Checking...' : 'Skill gaps'}
        </button>
      </div>
      {gapState === 'ok' && gap && (
        <div className="card" style={{ marginTop: 10 }}>
          <small className="panel-label">Skill gaps ({Math.round(gap.coverage * 100)}% covered)</small>
          {gap.matched.length > 0 && <p><strong>You have:</strong> {gap.matched.join(', ')}</p>}
          {gap.missing.length > 0
            ? <ul className="reasons">{gap.advice.map((a, i) => <li key={i}>{a}</li>)}</ul>
            : <p>No gaps - your profile covers every listed skill.</p>}
        </div>
      )}
      {gapState !== 'ok' && gapState !== 'idle' && gapState !== 'loading' &&
        <p className="hint">Skill-gap check failed: {gapState}</p>}
    </section>
  )
}

export default function FindView({ onTailor }) {
  const [query, setQuery] = useState('')
  const [remoteOnly, setRemoteOnly] = useState(false)
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null)
  const [meta, setMeta] = useState('Search to see matches')
  const [searched, setSearched] = useState(false)

  const [feed, setFeed] = useState(null)
  useEffect(() => { api('/api/jobs/sync/status').then(setFeed).catch(() => {}) }, [])

  const runSearch = async (q = query, remote = remoteOnly) => {
    let finalQ = q.trim()
    if (!finalQ) return
    if (remote && !/\bremote\b/i.test(finalQ)) finalQ += ' remote'
    setSearched(true)
    setSelected(null)
    try {
      const data = await api('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: finalQ, k: 10 }),
      })
      setResults(data.results)
      const note = data.results.length && data.results[0].reasons[0].startsWith('Remote requested')
        ? data.results[0].reasons[0] : null
      setMeta(data.results.length
        ? `${data.results.length} results${note ? ' · ' + note : ''}`
        : 'No jobs in the catalogue matched')
      if (data.results.length) setSelected(0)
    } catch (e) {
      setMeta('Error: ' + e.message)
      setResults([])
    }
  }

  return (
    <section className="view active">
      <h2>Find your next role.</h2>
      <p className="hint"><strong>Real listings only.</strong> Every result comes from a public job
        feed (Remotive, Arbeitnow, company boards on Greenhouse) and links to the original posting.
        {feed && feed.last_success_at
          ? ` Feeds refresh automatically about every ${feed.interval_hours} hours; last refreshed ${feed.last_success_at.replace('T', ' ').replace('Z', ' UTC')}, ${feed.real_active_jobs} open listings.`
          : ' The first refresh from the live feeds is running or still waiting; results appear once it finishes.'}</p>
      <div className="searchbar">
        <input value={query} onChange={(e) => setQuery(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && runSearch()}
               placeholder='Try "backend internships using Python in India"' />
        <button className="btn" onClick={() => runSearch()}>Search &#8599;</button>
      </div>
      <div className="filter-row">
        <button className={'pill-toggle' + (remoteOnly ? ' on' : '')} aria-pressed={remoteOnly}
                onClick={() => { const v = !remoteOnly; setRemoteOnly(v); if (query.trim()) runSearch(query, v) }}>
          Remote only
        </button>
        <small className="muted">{meta}</small>
      </div>
      <div className="split">
        <section className="results-col">
          {!searched && <p className="hint">Matches appear here. Select one to see why it fits.</p>}
          {searched && results.length === 0 && <p className="hint">No jobs in the catalogue matched.</p>}
          {results.map((r, i) => (
            <div key={r.job.id} className={'card' + (i === selected ? ' selected' : '')}
                 onClick={() => setSelected(i)}>
              <div className="card-head"><h3>{r.job.title}</h3>
                <span className="score-inline">{Math.round(r.scores.total * 100)}</span></div>
              <div className="meta">{r.job.company} · {r.job.location} · {r.job.job_type} · {r.job.level}</div>
              <div className="meta">
                <span className="chip">{sourceLabel(r.job)}</span>
                {r.job.posted_date && <span> posted {r.job.posted_date}</span>}
                {r.job.url &&
                  <span> · <a href={r.job.url} target="_blank" rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}>apply ↗</a></span>}
              </div>
              {i === selected &&
                <div>{r.job.skills.map((s) => <span key={s} className="chip">{s}</span>)}</div>}
            </div>
          ))}
        </section>
        {selected !== null && results[selected] &&
          <MatchPanel result={results[selected]} onTailor={onTailor} />}
      </div>
    </section>
  )
}
