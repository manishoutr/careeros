import test from 'node:test'
import assert from 'node:assert/strict'
import { createTracker, describe } from './searchState.js'

test('a stale response cannot overwrite a newer search', () => {
  const t = createTracker()
  const first = t.begin()
  const second = t.begin()
  assert.equal(t.isCurrent(first), false)
  assert.equal(t.isCurrent(second), true)
})

test('loading, error, empty and results read differently', () => {
  assert.equal(describe('loading'), 'Searching\u2026')
  assert.match(describe('error', null, 'boom'), /^Error: boom/)
  assert.equal(describe('ok', { results: [] }), 'No jobs in the catalogue matched')
  assert.equal(describe('idle'), 'Search to see matches')
  const data = { results: [{ reasons: ['Internship/entry-level requested: showing only x.'] }] }
  assert.match(describe('ok', data), /^1 results · Internship/)
})
