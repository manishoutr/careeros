import { useEffect, useState } from 'react'
import { api } from '../api.js'

function draftToText(d) {
  const lines = [d.name, 'Target: ' + d.target_role, '', d.summary, '', 'SKILLS',
    (d.skills || []).join(', '), '', 'EXPERIENCE']
  ;(d.experience || []).forEach((e) => lines.push(`${e.title} - ${e.company} (${e.period})`))
  lines.push('', 'EDUCATION')
  ;(d.education || []).forEach((e) =>
    lines.push(`${e.degree}${e.institution ? ' - ' + e.institution : ''} ${e.year || ''}`.trim()))
  return lines.join('\n')
}

export default function StudioView({ preselectJobId, onConsumed }) {
  const [jobs, setJobs] = useState([])
  const [jobId, setJobId] = useState('')
  const [output, setOutput] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/jobs?limit=500').then((js) => {
      setJobs(js)
      if (js.length) setJobId(String(preselectJobId && js.some((j) => j.id === preselectJobId) ? preselectJobId : js[0].id))
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (preselectJobId && jobs.some((j) => j.id === preselectJobId)) {
      setJobId(String(preselectJobId))
      generate(preselectJobId)
      onConsumed()
    }
  }, [preselectJobId, jobs])

  const generate = async (id = Number(jobId)) => {
    if (!id) { setError('Pick a job first.'); return }
    setError('')
    setOutput('loading')
    try {
      setOutput(await api('/api/tailor', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: id }),
      }))
    } catch (e) { setOutput(null); setError(e.message) }
  }

  const download = () => {
    if (!output || !output.draft) return
    const blob = new Blob([draftToText(output.draft)], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'tailored-resume.txt'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const d = output && output.draft
  return (
    <section className="view active">
      <h2>Resume studio</h2>
      <p className="hint">Picks a job and drafts a role-specific resume. Safety rule: it can only reuse
        facts from your profile - code rejects anything invented.</p>
      <div className="row">
        <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
          {jobs.length === 0 && <option>No jobs ingested</option>}
          {jobs.map((j) => <option key={j.id} value={j.id}>{j.title} - {j.company}</option>)}
        </select>
        <button className="btn" onClick={() => generate()}>Generate draft</button>
      </div>
      {error && <p className="hint">Error: {error}</p>}
      {output === 'loading' && <p className="hint">Building draft...</p>}
      {d && (
        <>
          <h3 style={{ marginTop: 12 }}>Draft for {output.job.title} at {output.job.company}</h3>
          <div className="card resume">
            <h3 className="r-name">{d.name}</h3>
            <div className="meta">Target: {d.target_role}</div>
            <p className="r-summary">{d.summary}</p>
            <h4>Skills</h4>
            <div>{(d.skills || []).map((x) => <span key={x} className="chip">{x}</span>)}</div>
            <h4>Experience</h4>
            {(d.experience || []).length === 0 && <p className="hint">None</p>}
            {(d.experience || []).map((e, i) => (
              <div key={i} className="r-entry"><strong>{e.title}</strong> - {e.company}
                <span className="meta">{e.period}</span></div>
            ))}
            <h4>Education</h4>
            {(d.education || []).length === 0 && <p className="hint">None</p>}
            {(d.education || []).map((e, i) => (
              <div key={i} className="r-entry">{e.degree}{e.institution ? ' - ' + e.institution : ''} {e.year || ''}</div>
            ))}
          </div>
          <button className="btn secondary" style={{ margin: '8px 0' }} onClick={download}>
            Download draft as .txt</button>
          <h3 style={{ marginTop: 12 }}>Changes to review ({output.changes.length})</h3>
          {output.changes.map((c, i) => (
            <div key={i} className="change">
              <span className="kind">{c.section} · {c.change}</span>
              <span className="before">{c.before}</span>
              <span className="after">{c.after}</span>
              <span className="source">Source: {c.source}</span>
            </div>
          ))}
        </>
      )}
    </section>
  )
}
