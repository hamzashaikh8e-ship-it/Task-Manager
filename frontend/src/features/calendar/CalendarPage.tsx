import { FormEvent, useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, Clock3, Loader2, Plus, X } from 'lucide-react'
import { api, Task } from '../../api'
import { apiLocalDateKey, parseApiDate } from '../../utils/dates'

type CalendarView = 'month' | 'week' | 'day'
type Range = { start: Date; end: Date; days: Date[] }

function dayOnly(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
function startOfDay(date: Date) { return new Date(date.getFullYear(), date.getMonth(), date.getDate()) }
function startOfWeek(date: Date) { const result = startOfDay(date); result.setDate(result.getDate() - ((result.getDay() + 6) % 7)); return result }
function addDays(date: Date, count: number) { const result = new Date(date); result.setDate(result.getDate() + count); return result }
function rangeFor(date: Date, view: CalendarView): Range {
  let start: Date
  let count: number
  if (view === 'month') {
    start = startOfWeek(new Date(date.getFullYear(), date.getMonth(), 1))
    count = 42
  } else if (view === 'week') {
    start = startOfWeek(date)
    count = 7
  } else {
    start = startOfDay(date)
    count = 1
  }
  const days = Array.from({ length: count }, (_, index) => addDays(start, index))
  return { start, end: addDays(start, count), days }
}
function asApiInstant(date: Date) { return date.toISOString() }
function localDateTime(value?: string | null) {
  if (!value) return ''
  const date = parseApiDate(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
function localInstant(value: string) { return value ? new Date(value).toISOString() : null }
function displayStart(value?: string | null) {
  if (!value) return ''
  return parseApiDate(value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}
function taskPayload(task: Task, deadline: string, scheduledStart: string, scheduledEnd: string) {
  return {
    title: task.title, description: task.description, status: task.status, priority: task.priority,
    importance: task.importance, category: task.category, estimated_minutes: task.estimated_minutes,
    deadline: deadline ? new Date(`${deadline}T23:59:00`).toISOString() : null,
    scheduled_start: localInstant(scheduledStart), scheduled_end: localInstant(scheduledEnd),
    dependency_ids: task.dependency_ids, reminder_enabled: task.reminder_enabled, reminder_lead_minutes: task.reminder_lead_minutes,
  }
}

function TaskDateEditor({ task, onClose, onSaved }: { task: Task; onClose: () => void; onSaved: () => void }) {
  const [deadline, setDeadline] = useState(apiLocalDateKey(task.deadline))
  const [scheduledStart, setScheduledStart] = useState(localDateTime(task.scheduled_start))
  const [scheduledEnd, setScheduledEnd] = useState(localDateTime(task.scheduled_end))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault()
    const form = new FormData(event.currentTarget as HTMLFormElement)
    const nextDeadline = String(form.get('deadline') ?? '')
    const nextStart = String(form.get('scheduled_start') ?? '')
    const nextEnd = String(form.get('scheduled_end') ?? '')
    if ((nextStart && !nextEnd) || (!nextStart && nextEnd)) { setError('Choose both a start and end time.'); return }
    if (nextStart && nextEnd && new Date(nextEnd) <= new Date(nextStart)) { setError('End time must be after the start time.'); return }
    setSaving(true); setError('')
    try { await api.update(task.id, taskPayload(task, nextDeadline, nextStart, nextEnd)); onSaved() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not update this task schedule.') }
    finally { setSaving(false) }
  }
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <form className="task-modal calendar-editor" onSubmit={submit}>
      <button type="button" className="modal-close" onClick={onClose} aria-label="Close date editor"><X size={18}/></button>
      <p className="eyebrow">TASK SCHEDULE</p><h2>{task.title}</h2>
      <p className="calendar-editor-copy">Times are shown in your browser’s local timezone. Saved schedule times are converted to UTC.</p>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <label>Due date<input aria-label="Due date" name="deadline" type="date" value={deadline} onChange={event => setDeadline(event.target.value)}/></label>
      <label>Scheduled start<input aria-label="Scheduled start" name="scheduled_start" type="datetime-local" value={scheduledStart} onChange={event => setScheduledStart(event.target.value)}/></label>
      <label>Scheduled end<input aria-label="Scheduled end" name="scheduled_end" type="datetime-local" value={scheduledEnd} onChange={event => setScheduledEnd(event.target.value)}/></label>
      <div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button className="primary" disabled={saving}>{saving ? 'Saving…' : 'Save dates'}</button></div>
    </form>
  </div>
}

export default function CalendarPage({ onCreateTask }: { onCreateTask?: () => void }) {
  const [date, setDate] = useState(() => startOfDay(new Date()))
  const [view, setView] = useState<CalendarView>('month')
  const [tasks, setTasks] = useState<Task[]>([])
  const [editing, setEditing] = useState<Task>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const range = useMemo(() => rangeFor(date, view), [date, view])
  const startISO = asApiInstant(range.start)
  const endISO = asApiInstant(range.end)

  async function refresh() {
    setLoading(true)
    try { setTasks(await api.calendarEvents(startISO, endISO)); setError('') }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load calendar events.') }
    finally { setLoading(false) }
  }
  useEffect(() => { void refresh() }, [startISO, endISO])

  function moveRange(direction: number) {
    const next = new Date(date)
    if (view === 'month') next.setMonth(next.getMonth() + direction)
    else next.setDate(next.getDate() + direction * (view === 'week' ? 7 : 1))
    setDate(startOfDay(next))
  }
  function title() {
    if (view === 'day') return date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
    if (view === 'week') return `${range.start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${addDays(range.end, -1).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`
    return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  }
  function itemsForDay(day: Date) {
    const key = dayOnly(day)
    const items: { task: Task; kind: 'Due' | 'Scheduled' }[] = []
    tasks.forEach(task => {
      if (apiLocalDateKey(task.deadline) === key) items.push({ task, kind: 'Due' })
      if (task.scheduled_start && dayOnly(parseApiDate(task.scheduled_start)) === key) items.push({ task, kind: 'Scheduled' })
    })
    return items
  }
  async function saved() {
    setEditing(undefined)
    setMessage('Calendar dates saved.')
    await refresh()
  }
  const headings = range.days.length > 1 ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] : [date.toLocaleDateString(undefined, { weekday: 'long' })]
  return <div className="phase-page calendar-page">
    <div className="phase-heading"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>Calendar</h1><p>Deadlines and scheduled work from your saved tasks.</p></div><div className="phase-actions"><button className="secondary" onClick={() => setDate(startOfDay(new Date()))}>Today</button><button className="icon-button calendar-nav" aria-label="Previous period" onClick={() => moveRange(-1)}><ArrowLeft size={17}/></button><button className="icon-button calendar-nav" aria-label="Next period" onClick={() => moveRange(1)}><ArrowRight size={17}/></button><select aria-label="Calendar view" value={view} onChange={event => setView(event.target.value as CalendarView)}><option value="month">Month</option><option value="week">Week</option><option value="day">Day</option></select>{onCreateTask && <button className="primary" onClick={onCreateTask}><Plus size={15}/>New task</button>}</div></div>
    <section className="panel calendar-panel">
      <header className="calendar-toolbar"><h2>{title()}</h2><div className="calendar-legend"><span><i className="legend-deadline"/>Due date</span><span><i className="legend-scheduled"/>Scheduled</span><span className="timezone-label"><Clock3 size={12}/>{Intl.DateTimeFormat().resolvedOptions().timeZone}</span></div></header>
      {error && <div className="error-banner calendar-error" role="alert">{error}<button className="text-link" onClick={() => void refresh()}>Retry</button></div>}
      {message && <div className="success-banner" role="status">{message}</div>}
      {loading ? <div className="phase-loading"><Loader2 className="spin" size={20}/>Loading calendar…</div> : <div className={`calendar-grid ${view}`} role="grid" aria-label={`${view} calendar`}>
        {headings.map((heading, index) => <div key={`${heading}-${index}`} className="calendar-weekday" role="columnheader">{heading}</div>)}
        {range.days.map(day => {
          const currentMonth = day.getMonth() === date.getMonth()
          const dayItems = itemsForDay(day)
          return <div key={dayOnly(day)} className={`calendar-cell ${view === 'month' && !currentMonth ? 'outside-month' : ''} ${dayOnly(day) === dayOnly(new Date()) ? 'is-today' : ''}`} role="gridcell" aria-label={day.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}>
            <button className="calendar-date" onClick={() => { setDate(startOfDay(day)); if (view === 'month') setView('day') }}>{day.getDate()}</button>
            <div className="calendar-events">{dayItems.map(({ task, kind }, index) => <button key={`${task.id}-${kind}-${index}`} className={`calendar-event ${kind.toLowerCase()} ${task.status === 'DONE' ? 'event-done' : ''}`} aria-label={`${kind === 'Due' ? 'Deadline' : `Scheduled ${displayStart(task.scheduled_start)}`} ${task.title}`} onClick={() => setEditing(task)}><span>{kind === 'Scheduled' && <b>{displayStart(task.scheduled_start)} · </b>}{kind === 'Due' && <b>Due · </b>}{task.title}</span></button>)}</div>
          </div>
        })}
      </div>}
      {!loading && tasks.length === 0 && <div className="calendar-empty">No deadlines or scheduled tasks in this period. Add dates to an existing task to see it here.</div>}
    </section>
    {editing && <TaskDateEditor task={editing} onClose={() => setEditing(undefined)} onSaved={() => void saved()}/>}
  </div>
}

export { rangeFor, taskPayload }
