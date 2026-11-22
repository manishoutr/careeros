import { useEffect, useState } from 'react'
import { api } from './api.js'
import FindView from './views/Find.jsx'
import ProfileView from './views/Profile.jsx'
import AssistantView from './views/Assistant.jsx'
import StudioView from './views/Studio.jsx'

const VIEWS = [
  ['find', 'Find roles'],
  ['profile', 'Profile'],
  ['assistant', 'Assistant'],
  ['studio', 'Resume studio'],
]

export default function App() {
  const [view, setView] = useState('find')
  const [health, setHealth] = useState(null)
  const [profile, setProfile] = useState(null)
  const [tailorJobId, setTailorJobId] = useState(null)

  useEffect(() => { api('/api/health').then(setHealth).catch(() => {}) }, [])
  useEffect(() => { api('/api/profile').then(setProfile).catch(() => setProfile(null)) }, [])

  const openTailor = (jobId) => { setTailorJobId(jobId); setView('studio') }

  const badge = health
    ? `${health.llm_mode === 'claude' ? 'Claude connected' : 'Offline mode'} · ${health.active_jobs ?? health.jobs} jobs`
    : '...'

  return (
    <>
      <header className="top">
        <span className="brand">CareerOS</span>
        <span className="push">
          <span className={'mode' + (health && health.llm_mode === 'claude' ? ' claude' : '')}>{badge}</span>
        </span>
      </header>
      <div className="shell">
        <aside className="rail">
          <small className="rail-label">Your workspace</small>
          {VIEWS.map(([key, label]) => (
            <button key={key} className={'nav-item' + (view === key ? ' active' : '')}
                    onClick={() => setView(key)}>{label}</button>
          ))}
          <div className="rail-status">
            {profile
              ? <small><b>{profile.name || 'Profile'}</b><br />Profile ready<br />{profile.skills.length} skills on file</small>
              : <small>No profile yet</small>}
          </div>
        </aside>
        <main>
          {view === 'find' && <FindView onTailor={openTailor} />}
          {view === 'profile' && <ProfileView profile={profile} onProfile={setProfile} />}
          {view === 'assistant' && <AssistantView />}
          {view === 'studio' && <StudioView preselectJobId={tailorJobId} onConsumed={() => setTailorJobId(null)} />}
        </main>
      </div>
    </>
  )
}
