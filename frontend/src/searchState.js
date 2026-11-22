// Search request bookkeeping for the Find view, kept free of React so it can
// be tested with plain node. Three states are kept distinct: loading (request
// in flight), error (request failed) and empty (answered with no matches).

export function createTracker() {
  let latest = 0
  return {
    begin() { latest += 1; return latest },
    // A response may only update the screen if no newer search has started.
    isCurrent(id) { return id === latest },
  }
}

export function describe(status, data, error) {
  if (status === 'loading') return 'Searching\u2026'
  if (status === 'error') return 'Error: ' + error
  if (status === 'idle') return 'Search to see matches'
  const results = (data && data.results) || []
  if (!results.length) return 'No jobs in the catalogue matched'
  const first = results[0].reasons[0] || ''
  const gate = /^(Remote requested|Internship\/entry-level requested|Location requested|No roles in)/.test(first)
    ? ' \u00b7 ' + first : ''
  return `${results.length} results${gate}`
}
