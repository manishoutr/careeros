import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

export default function AssistantView() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const logRef = useRef(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages])

  const send = async () => {
    const msg = input.trim()
    if (!msg) return
    setInput('')
    setMessages((m) => [...m, { who: 'You', text: msg }])
    try {
      const res = await api('/api/assistant/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      })
      setMessages((m) => [...m, {
        who: res.mode === 'claude' ? 'CareerOS (Claude)' : 'CareerOS (offline)',
        text: res.answer, trace: res.tool_trace,
      }])
    } catch (e) {
      setMessages((m) => [...m, { who: 'CareerOS', text: 'Error: ' + e.message }])
    }
  }

  return (
    <section className="view active">
      <h2>Career assistant</h2>
      <p className="hint">Answers are grounded in your profile and the job catalogue via tool calls.
        Offline mode uses deterministic logic and says so.</p>
      <div id="chat-log" ref={logRef}>
        {messages.map((m, i) => (
          <div key={i} className={'msg ' + (m.who === 'You' ? 'user' : 'assistant')}>
            <span className="who">{m.who}</span>{m.text}
            {m.trace && m.trace.length > 0 &&
              <div className="trace">tools: {m.trace.map((t) => t.tool).join(', ')}</div>}
          </div>
        ))}
      </div>
      <div className="searchbar">
        <input value={input} onChange={(e) => setInput(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && send()}
               placeholder="Which jobs fit my profile?" />
        <button className="btn" onClick={send}>Send</button>
      </div>
    </section>
  )
}
