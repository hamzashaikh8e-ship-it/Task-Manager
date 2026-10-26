import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDownWideNarrow, ArrowUpDown, CalendarDays, Check, Clock3, Copy, ListFilter, Loader2, Pencil, Plus, Search, Tag, Trash2, X } from 'lucide-react'
import { api, Category, createIdempotencyKey, Task, TaskInput, TaskPriority, TaskQuery, TaskStatus } from '../../api'
import { parseApiDate } from '../../utils/dates'

type Props = { openCreate?: boolean; openTaskId?: string; onTaskOpened?: () => void; onCreateOpened?: () => void }
type Draft = TaskInput

function toDateInput(value?: string | null) {
  if (!value) return ''
  const date = parseApiDate(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}
function toDateTimeInput(value?: string | null) {
  if (!value) return ''
  const date = parseApiDate(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

function TaskEditor({ task, tasks, categories, saving, onClose, onSave }: {
  task?: Task; tasks: Task[]; categories: Category[]; saving: boolean; onClose: () => void;
  onSave: (data: Draft,idempotencyKey?:string) => Promise<void>
}) {
  const [title, setTitle] = useState(task?.title ?? '')
  const [description, setDescription] = useState(task?.description ?? '')
  const [status, setStatus] = useState<TaskStatus>(task?.status ?? 'TODO')
  const [priority, setPriority] = useState<TaskPriority>(task?.priority ?? 'MEDIUM')
  const [importance, setImportance] = useState(task?.importance ?? 3)
  const [category, setCategory] = useState(task?.category ?? '')
  const [duration, setDuration] = useState(task?.estimated_minutes ? String(task.estimated_minutes) : '')
  const [deadline, setDeadline] = useState(toDateInput(task?.deadline))
  const [reminderEnabled,setReminderEnabled]=useState(task?.reminder_enabled??false)
  const [reminderLead,setReminderLead]=useState(task?.reminder_lead_minutes??30)
  const [scheduledStart, setScheduledStart] = useState(toDateTimeInput(task?.scheduled_start))
  const [scheduledEnd, setScheduledEnd] = useState(toDateTimeInput(task?.scheduled_end))
  const [dependencies, setDependencies] = useState<string[]>(task?.dependency_ids ?? [])
  const [formError, setFormError] = useState('')
  const createKeyRef=useRef<string|null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!title.trim()) { setFormError('Add a task title to continue.'); return }
    try {
      setFormError('')
      // Read the native date control at submit time as well as tracking its
      // React state. This keeps date-picker commits reliable across browsers.
      const formDeadline = String(new FormData(event.currentTarget).get('deadline') ?? '')
      if (reminderEnabled && !formDeadline) { setFormError('Choose a due date to enable a reminder.'); return }
      if ((scheduledStart && !scheduledEnd) || (!scheduledStart && scheduledEnd)) {
        setFormError('Choose both a scheduled start and end time.')
        return
      }
      if (scheduledStart && scheduledEnd && new Date(scheduledEnd) <= new Date(scheduledStart)) {
        setFormError('Scheduled end must be after the start.')
        return
      }
      const draft:Draft={
        title: title.trim(), description: description.trim(), status, priority, importance,
        category: category || null,
        estimated_minutes: duration ? Number(duration) : null,
        deadline: formDeadline ? new Date(`${formDeadline}T23:59:00`).toISOString() : null,
        reminder_enabled: reminderEnabled, reminder_lead_minutes: reminderLead,
        scheduled_start: scheduledStart ? new Date(scheduledStart).toISOString() : null,
        scheduled_end: scheduledEnd ? new Date(scheduledEnd).toISOString() : null,
        dependency_ids: dependencies,
      }
      if(!task&&!createKeyRef.current)createKeyRef.current=createIdempotencyKey()
      await onSave(draft,task?undefined:createKeyRef.current||undefined)
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Could not save this task.')
    }
  }


  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <form className="task-modal task-editor" onSubmit={submit}>
      <button type="button" className="modal-close" onClick={onClose} aria-label="Close task editor"><X size={18}/></button>
      <p className="eyebrow">{task ? 'UPDATE YOUR TASK' : 'MAKE IT HAPPEN'}</p>
      <h2>{task ? 'Edit task' : 'Create a task'}</h2>
      {formError && <div className="error-banner" role="alert">{formError}</div>}
      <label>Task title<input name="title" required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder="What needs to get done?" autoFocus/></label>
      <label>Description<textarea name="description" maxLength={10000} value={description} onChange={event => setDescription(event.target.value)} placeholder="Add a little context…"/></label>
      <div className="task-form-grid">
        <label>Status<select value={status} onChange={event => setStatus(event.target.value as TaskStatus)}><option value="TODO">To do</option><option value="IN_PROGRESS">In progress</option><option value="DONE">Done</option></select></label>
        <label>Priority<select value={priority} onChange={event => setPriority(event.target.value as TaskPriority)}><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option><option value="URGENT">Urgent</option></select></label>
        <label>Importance<select value={importance} onChange={event => setImportance(Number(event.target.value))}>{[1,2,3,4,5].map(value=><option key={value} value={value}>{value} / 5</option>)}</select></label>
        <label>Category<select value={category} onChange={event => setCategory(event.target.value)}><option value="">No category</option>{categories.map(item=><option key={item.id} value={item.name}>{item.name}</option>)}</select></label>
        <label>Due date<input name="deadline" type="date" value={deadline} onChange={event => setDeadline(event.target.value)}/></label><label className="reminder-toggle"><input type="checkbox" checked={reminderEnabled} onChange={event=>setReminderEnabled(event.target.checked)}/> Remind me before deadline</label>{reminderEnabled&&<label>Reminder lead time<select value={reminderLead} onChange={event=>setReminderLead(Number(event.target.value))}><option value={0}>At deadline</option><option value={15}>15 minutes before</option><option value={30}>30 minutes before</option><option value={60}>1 hour before</option><option value={1440}>1 day before</option><option value={10080}>1 week before</option></select></label>}
        <label>Scheduled start<input type="datetime-local" value={scheduledStart} onChange={event => setScheduledStart(event.target.value)}/></label>
        <label>Scheduled end<input type="datetime-local" value={scheduledEnd} onChange={event => setScheduledEnd(event.target.value)}/></label>
        <label>Estimated minutes<input type="number" min="1" max="10080" value={duration} onChange={event => setDuration(event.target.value)} placeholder="e.g. 45"/></label>
      </div>
      <label>Depends on<select multiple size={Math.min(Math.max(tasks.filter(item=>item.id!==task?.id).length,2),4)} value={dependencies} onChange={event=>setDependencies(Array.from(event.target.selectedOptions,option=>option.value))}>{tasks.filter(item=>item.id!==task?.id).map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select><small className="field-hint">Use Ctrl or Command to select more than one prerequisite.</small></label>
      <div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button className="primary" disabled={saving}>{saving?<><Loader2 className="spin" size={15}/> Saving…</>:task?'Save changes':'Create task'}</button></div>
    </form>
  </div>
}

export default function TaskManager({ openCreate = false, openTaskId, onTaskOpened, onCreateOpened }: Props) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [allTasks, setAllTasks] = useState<Task[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [category, setCategory] = useState('')
  const [deadlineFrom, setDeadlineFrom] = useState('')
  const [deadlineTo, setDeadlineTo] = useState('')
  const [sortBy, setSortBy] = useState<TaskQuery['sort_by']>('created')
  const [sortOrder, setSortOrder] = useState<TaskQuery['sort_order']>('desc')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<Task | undefined>()
  const [newCategory, setNewCategory] = useState('')
  const [categoryBusy, setCategoryBusy] = useState(false)

  const query = useMemo<TaskQuery>(() => ({
    q: search.trim() || undefined,
    status: (status || undefined) as TaskStatus | undefined,
    priority: (priority || undefined) as TaskPriority | undefined,
    category: category || undefined,
    deadline_from: deadlineFrom || undefined,
    deadline_to: deadlineTo || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
    limit: 100,
  }), [search,status,priority,category,deadlineFrom,deadlineTo,sortBy,sortOrder])

  async function refresh(currentQuery = query, withLoading = false) {
    if (withLoading) setLoading(true)
    try {
      const [items, everything, tags] = await Promise.all([
        api.tasks(currentQuery),
        api.tasks({limit:100,sort_by:'title',sort_order:'asc'}),
        api.categories(),
      ])
      setTasks(items)
      setAllTasks(everything)
      setCategories(tags)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load your tasks.')
    } finally {
      if (withLoading) setLoading(false)
    }
  }

  useEffect(() => { void refresh(query, true) }, [query])
  useEffect(() => { if(openCreate){setEditing(undefined);setEditorOpen(true);onCreateOpened?.()} }, [openCreate,onCreateOpened])
  useEffect(() => { if(openTaskId){const found=allTasks.find(item=>item.id===openTaskId);if(found){setEditing(found);setEditorOpen(true);onTaskOpened?.()}} }, [openTaskId,allTasks,onTaskOpened])

  async function saveTask(data: Draft,idempotencyKey?:string) {
    setSaving(true)
    try {
      if (editing) await api.update(editing.id,data)
      else await api.create(data,idempotencyKey)
      setEditorOpen(false)
      setEditing(undefined)
      setMessage(editing ? 'Task changes saved.' : 'Task created.')
      await refresh(query)
    } catch (reason) {
      throw reason
    } finally {
      setSaving(false)
    }
  }

  async function updateStatus(task: Task) {
    try {
      await api.update(task.id,{title:task.title,description:task.description,status:task.status==='DONE'?'TODO':'DONE',priority:task.priority,importance:task.importance,category:task.category,estimated_minutes:task.estimated_minutes,deadline:task.deadline,scheduled_start:task.scheduled_start,scheduled_end:task.scheduled_end,dependency_ids:task.dependency_ids,reminder_enabled:task.reminder_enabled,reminder_lead_minutes:task.reminder_lead_minutes})
      setMessage(task.status==='DONE'?'Task reopened.':'Task completed.')
      await refresh(query)
    } catch (reason) { setError(reason instanceof Error?reason.message:'Could not update the task status.') }
  }

  async function duplicate(task: Task) {
    try { await api.duplicate(task.id); setMessage('Task duplicated.'); await refresh(query) }
    catch (reason) { setError(reason instanceof Error?reason.message:'Could not duplicate this task.') }
  }

  async function remove(task: Task) {
    if (!window.confirm(`Delete “${task.title}”?`)) return
    try { await api.remove(task.id); setMessage('Task deleted.'); await refresh(query) }
    catch (reason) { setError(reason instanceof Error?reason.message:'Could not delete this task.') }
  }

  async function addCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!newCategory.trim()) return
    setCategoryBusy(true)
    try {
      const created = await api.createCategory(newCategory.trim())
      setNewCategory('')
      setCategories(previous=>previous.some(item=>item.id===created.id)?previous:[...previous,created].sort((a,b)=>a.name.localeCompare(b.name)))
      setCategory(created.name)
      setMessage(`Category “${created.name}” added.`)
      setError('')
    } catch (reason) { setError(reason instanceof Error?reason.message:'Could not add this category.') }
    finally { setCategoryBusy(false) }
  }

  async function removeCategory(item: Category) {
    if (!window.confirm(`Delete category “${item.name}”? Tasks in it will become uncategorized.`)) return
    try {
      await api.deleteCategory(item.id)
      setCategories(previous=>previous.filter(categoryItem=>categoryItem.id!==item.id))
      if (category===item.name) setCategory('')
      await refresh(query)
      setMessage(`Category “${item.name}” deleted.`)
    } catch (reason) { setError(reason instanceof Error?reason.message:'Could not delete this category.') }
  }

  const openCount = allTasks.filter(task=>task.status!=='DONE').length
  const completedCount = allTasks.filter(task=>task.status==='DONE').length

  return <section className="task-workspace">
    <div className="task-page-heading"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>My tasks</h1><p>Keep the details, deadlines, and next steps in one place.</p></div><button className="primary" onClick={()=>{setEditing(undefined);setEditorOpen(true)}}><Plus size={17}/> New task</button></div>
    {(error||message)&&<div className={error?'task-alert error-banner':'task-alert success-banner'} role={error?'alert':'status'}>{error||message}<button aria-label="Dismiss message" onClick={()=>{setError('');setMessage('')}}><X size={15}/></button></div>}
    <div className="task-summary-cards"><div><span>Open tasks</span><b>{openCount}</b></div><div><span>Completed</span><b>{completedCount}</b></div><div><span>Showing</span><b>{tasks.length}</b></div></div>
    <section className="panel category-panel"><div className="category-panel-title"><div><Tag size={16}/><b>Categories</b></div><span>Organize tasks your way</span></div><div className="category-tools"><div className="category-chips">{categories.length===0?<span className="muted-caption">No categories yet</span>:categories.map(item=><span className="category-chip" key={item.id}>{item.name}<button aria-label={`Delete category ${item.name}`} onClick={()=>void removeCategory(item)}><X size={12}/></button></span>)}</div><form className="category-create" onSubmit={addCategory}><input aria-label="New category name" maxLength={80} value={newCategory} onChange={event=>setNewCategory(event.target.value)} placeholder="New category"/><button className="secondary" disabled={categoryBusy||!newCategory.trim()}><Plus size={14}/>{categoryBusy?'Adding':'Add'}</button></form></div></section>
    <section className="panel task-controls"><div className="task-search"><Search size={17}/><input aria-label="Search tasks" value={search} onChange={event=>setSearch(event.target.value)} placeholder="Search title or description…"/>{search&&<button aria-label="Clear search" onClick={()=>setSearch('')}><X size={14}/></button>}</div><div className="filter-controls"><label><ListFilter size={14}/><select aria-label="Filter by status" value={status} onChange={event=>setStatus(event.target.value)}><option value="">All statuses</option><option value="TODO">To do</option><option value="IN_PROGRESS">In progress</option><option value="DONE">Done</option></select></label><label><select aria-label="Filter by priority" value={priority} onChange={event=>setPriority(event.target.value)}><option value="">All priorities</option><option value="URGENT">Urgent</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option></select></label><label><select aria-label="Filter by category" value={category} onChange={event=>setCategory(event.target.value)}><option value="">All categories</option>{categories.map(item=><option key={item.id} value={item.name}>{item.name}</option>)}</select></label><label className="date-filter"><span>Due after</span><input aria-label="Due after" type="date" value={deadlineFrom} onChange={event=>setDeadlineFrom(event.target.value)}/></label><label className="date-filter"><span>Due before</span><input aria-label="Due before" type="date" value={deadlineTo} onChange={event=>setDeadlineTo(event.target.value)}/></label><label><ArrowDownWideNarrow size={14}/><select aria-label="Sort tasks" value={sortBy} onChange={event=>setSortBy(event.target.value as TaskQuery['sort_by'])}><option value="created">Created date</option><option value="updated">Recently updated</option><option value="deadline">Due date</option><option value="priority">Priority</option><option value="title">Title</option></select></label><button className="sort-direction" aria-label={`Sort ${sortOrder==='asc'?'descending':'ascending'}`} title={`Currently ${sortOrder==='asc'?'ascending':'descending'}`} onClick={()=>setSortOrder(value=>value==='asc'?'desc':'asc')}><ArrowUpDown size={16}/></button></div></section>
    <section className="panel task-results"><div className="task-results-heading"><div><h2>Task list</h2><p>{tasks.length} {tasks.length===1?'task':'tasks'} match the current view</p></div><button className="text-link" onClick={()=>{setSearch('');setStatus('');setPriority('');setCategory('');setDeadlineFrom('');setDeadlineTo('');setSortBy('created');setSortOrder('desc')}}>Reset filters</button></div>
      {loading?<div className="task-state"><Loader2 className="spin" size={24}/><b>Loading your tasks…</b></div>:tasks.length===0?<div className="task-state"><div className="empty-icon"><Check size={22}/></div><b>{allTasks.length?'No tasks match these filters':'Your task list is clear'}</b><span>{allTasks.length?'Try changing a filter or search term.':'Create a task to get your list started.'}</span>{allTasks.length===0&&<button className="primary" onClick={()=>setEditorOpen(true)}><Plus size={15}/> Create a task</button>}</div>:<div className="managed-task-list">{tasks.map(task=>{
        const blockers=task.dependency_ids.map(id=>allTasks.find(candidate=>candidate.id===id)).filter((item):item is Task=>Boolean(item))
        return <article className={`managed-task ${task.status==='DONE'?'is-done':''}`} key={task.id}>
          <button className={`task-check ${task.status==='DONE'?'checked':''}`} aria-label={`${task.status==='DONE'?'Reopen':'Complete'} ${task.title}`} onClick={()=>void updateStatus(task)}>{task.status==='DONE'&&<Check size={13}/>}</button>
          <div className="managed-task-body"><div className="managed-task-title"><h3>{task.title}</h3><span className={`priority ${task.priority.toLowerCase()}`}>{task.priority.toLowerCase()}</span><span className={`status-pill ${task.status.toLowerCase()}`}>{task.status==='IN_PROGRESS'?'In progress':task.status==='DONE'?'Done':'To do'}</span></div>{task.description&&<p>{task.description}</p>}<div className="managed-task-meta">{task.category&&<span className="meta-tag category"><Tag size={12}/>{task.category}</span>}{task.deadline&&<span className="meta-tag"><CalendarDays size={12}/>{parseApiDate(task.deadline).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'})}</span>}{task.estimated_minutes&&<span className="meta-tag"><Clock3 size={12}/>{task.estimated_minutes} min</span>}{blockers.length>0&&<span className="meta-tag relation">Depends on {blockers.map(item=>item.title).join(', ')}</span>}</div></div>
          <div className="task-actions"><button aria-label={`Edit ${task.title}`} title="Edit" onClick={()=>{setEditing(task);setEditorOpen(true)}}><Pencil size={15}/></button><button aria-label={`Duplicate ${task.title}`} title="Duplicate" onClick={()=>void duplicate(task)}><Copy size={15}/></button><button className="delete-task" aria-label={`Delete ${task.title}`} title="Delete" onClick={()=>void remove(task)}><Trash2 size={15}/></button></div>
        </article>
      })}</div>}
    </section>
    {editorOpen&&<TaskEditor task={editing} tasks={allTasks} categories={categories} saving={saving} onClose={()=>{setEditorOpen(false);setEditing(undefined)}} onSave={saveTask}/>}
  </section>
}
