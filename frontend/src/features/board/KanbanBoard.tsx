import { useEffect, useState } from 'react'
import { DndContext, DragEndEvent, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from '@dnd-kit/core'
import { AlertCircle, CalendarDays, GripVertical, Loader2, RefreshCw } from 'lucide-react'
import { api, Task, TaskInput, TaskStatus } from '../../api'
import { parseApiDate } from '../../utils/dates'

const columns: { status: TaskStatus; title: string; hint: string }[] = [
  { status: 'TODO', title: 'To Do', hint: 'Ready when you are' },
  { status: 'IN_PROGRESS', title: 'In Progress', hint: 'Work in motion' },
  { status: 'DONE', title: 'Done', hint: 'A little progress adds up' },
]

function statusPayload(task: Task, status: TaskStatus): TaskInput {
  return {
    title: task.title, description: task.description, status, priority: task.priority,
    importance: task.importance, category: task.category, estimated_minutes: task.estimated_minutes,
    deadline: task.deadline, scheduled_start: task.scheduled_start, scheduled_end: task.scheduled_end,
    dependency_ids: task.dependency_ids, reminder_enabled: task.reminder_enabled, reminder_lead_minutes: task.reminder_lead_minutes,
  }
}
export async function moveTaskWithRollback(task: Task, status: TaskStatus, update = api.update, callbacks: {
  saved: (task: Task) => void; rollback: () => void; failed: (message: string) => void
}) {
  try {
    callbacks.saved(await update(task.id, statusPayload(task, status)))
  } catch (reason) {
    callbacks.rollback()
    callbacks.failed(reason instanceof Error ? reason.message : 'Could not move this task. Its previous status was restored.')
  }
}

function BoardCard({ task }: { task: Task }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: task.id })
  const style = { transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined, opacity: isDragging ? 0.45 : 1 }
  return <article ref={setNodeRef} style={style} className="kanban-card">
    <button className="kanban-drag-handle" aria-label={`Drag task ${task.title}`} {...listeners} {...attributes}><GripVertical size={15}/></button>
    <div className="kanban-card-title">{task.title}</div>
    <div className="kanban-card-meta">
      <span className={`priority ${task.priority.toLowerCase()}`}>{task.priority.toLowerCase()}</span>
      {task.category && <span className="kanban-category">{task.category}</span>}
    </div>
    {task.deadline && <div className="kanban-deadline"><CalendarDays size={13}/>{parseApiDate(task.deadline).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</div>}
  </article>
}

function Lane({ status, title, hint, tasks }: { status: TaskStatus; title: string; hint: string; tasks: Task[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  return <section ref={setNodeRef} className={`kanban-lane ${isOver ? 'is-over' : ''}`} aria-label={`${title} column`}>
    <header className="kanban-lane-head"><div><h2>{title}</h2><p>{hint}</p></div><span>{tasks.length}</span></header>
    <div className="kanban-lane-body">{tasks.length ? tasks.map(task => <BoardCard key={task.id} task={task}/>) : <div className="kanban-empty-lane">Drop a task here</div>}</div>
  </section>
}

export default function KanbanBoard() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [search, setSearch] = useState('')
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }), useSensor(KeyboardSensor))

  async function refresh() {
    setLoading(true)
    try { setTasks(await api.tasks({ limit: 100, sort_by: 'created', sort_order: 'desc' })); setError('') }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load your board.') }
    finally { setLoading(false) }
  }
  useEffect(() => { void refresh() }, [])

  async function finishDrag(event: DragEndEvent) {
    if (!event.over) return
    const task = tasks.find(item => item.id === String(event.active.id))
    const destination = columns.find(column => column.status === String(event.over?.id))
    if (!task || !destination || task.status === destination.status) return
    const optimistic = tasks.map(item => item.id === task.id ? { ...item, status: destination.status } : item)
    setTasks(optimistic)
    setError('')
    setMessage('')
    await moveTaskWithRollback(task, destination.status, api.update, {
      saved: saved => { setTasks(current => current.map(item => item.id === saved.id ? saved : item)); setMessage(`Moved to ${destination.title}.`) },
      rollback: () => setTasks(current => current.map(item => item.id === task.id ? { ...item, status: task.status } : item)),
      failed: message => setError(message),
    })
  }

  const shown = tasks.filter(task => `${task.title} ${task.description} ${task.category ?? ''}`.toLowerCase().includes(search.toLowerCase()))
  return <div className="phase-page">
    <div className="phase-heading"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>Kanban board</h1><p>Move saved tasks through the work, one step at a time.</p></div><div className="phase-actions"><label className="board-search"><span className="sr-only">Search board</span><input aria-label="Search board" placeholder="Search tasks…" value={search} onChange={event => setSearch(event.target.value)}/></label><button className="secondary" onClick={() => void refresh()} disabled={loading}><RefreshCw size={15}/>{loading ? 'Refreshing…' : 'Refresh'}</button></div></div>
    {error && <div className="error-banner" role="alert"><AlertCircle size={15}/>{error}</div>}
    {message && <div className="success-banner" role="status">{message}</div>}
    {loading ? <div className="panel phase-loading"><Loader2 className="spin" size={20}/>Loading your tasks…</div> : tasks.length === 0 ? <div className="panel phase-empty"><h2>Your board is clear</h2><p>Create a task in My tasks and it will appear here.</p></div> : <DndContext sensors={sensors} onDragEnd={event => void finishDrag(event)}>
      <div className="kanban-board">{columns.map(column => <Lane key={column.status} {...column} tasks={shown.filter(task => task.status === column.status)}/>)}</div>
    </DndContext>}
  </div>
}

export { statusPayload }
