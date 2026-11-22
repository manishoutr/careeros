import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function ProfileView({ profile, onProfile }) {
  const [name, setName] = useState('')
  const [skills, setSkills] = useState('')
  const [exp, setExp] = useState([])
  const [status, setStatus] = useState('')
  const [saveStatus, setSaveStatus] = useState('')

  useEffect(() => {
    if (profile) {
      setName(profile.name || '')
      setSkills((profile.skills || []).join(', '))
      setExp((profile.experience || []).map((e) => `${e.title} at ${e.company} (${e.period})`))
    }
  }, [profile])

  const upload = async (e) => {
    const file = e.target.files[0]
    if (!file) { setStatus('Choose a file first.'); return }
    const fd = new FormData()
    fd.append('file', file)
    setStatus('Parsing...')
    try {
      const p = await api('/api/profile/resume', { method: 'POST', body: fd })
      onProfile(p)
      setStatus('Parsed. Review and correct below.')
    } catch (err) { setStatus('Error: ' + err.message) }
  }

  const save = async () => {
    if (!profile) return
    const updated = { ...profile, name, skills: skills.split(',').map((s) => s.trim()).filter(Boolean) }
    updated.experience = exp.map((line, i) => {
      const m = line.match(/^(.*?)\s+at\s+(.*?)\s*\((.*?)\)\s*$/)
      return m ? { ...profile.experience[i], title: m[1], company: m[2], period: m[3] }
               : profile.experience[i]
    })
    try {
      await api('/api/profile', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated),
      })
      onProfile(updated)
      setSaveStatus('Saved.')
    } catch (err) { setSaveStatus('Error: ' + err.message) }
  }

  return (
    <section className="view active">
      <h2>Candidate profile</h2>
      <p className="hint">Upload a PDF or TXT resume. Every parsed field is editable - corrections are saved verbatim.</p>
      <div className="row">
        <input type="file" accept=".pdf,.txt,.md" onChange={upload} />
      </div>
      <p className="muted">{status}</p>
      {!profile && <p className="hint">No profile yet.</p>}
      {profile && (
        <div className="card">
          <div className="field-row"><label>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="field-row"><label>Skills (comma-separated, editable)</label>
            <input value={skills} onChange={(e) => setSkills(e.target.value)} /></div>
          <div className="field-row"><label>Experience</label>
            {exp.length === 0 && <p className="hint">None detected</p>}
            {exp.map((line, i) => (
              <input key={i} value={line}
                     onChange={(e) => setExp(exp.map((x, j) => (j === i ? e.target.value : x)))} />
            ))}
          </div>
          <div className="field-row"><label>Education</label>
            {(profile.education || []).length === 0 && <p className="hint">None detected</p>}
            {(profile.education || []).map((e, i) => (
              <div key={i}>{e.degree}{e.institution ? ' - ' + e.institution : ''} {e.year}</div>
            ))}
          </div>
        </div>
      )}
      {profile && (
        <div className="row">
          <button className="btn" onClick={save}>Save corrections</button>
          <span className="muted">{saveStatus}</span>
        </div>
      )}
    </section>
  )
}
