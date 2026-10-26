import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TaskManager from './TaskManager'
import type { Task } from '../../api'

const mockApi = vi.hoisted(() => ({
  tasks: vi.fn(), categories: vi.fn(), createCategory: vi.fn(), deleteCategory: vi.fn(),
  create: vi.fn(), update: vi.fn(), duplicate: vi.fn(), remove: vi.fn(),
}))
vi.mock('../../api', () => ({ api: mockApi, createIdempotencyKey: vi.fn(()=>'00000000-0000-4000-8000-000000000001') }))

const baseTask: Task = {
  id:'task-1', owner_id:'user-1', title:'Prepare notes', description:'Review the chapter', status:'TODO' as const,
  priority:'HIGH' as const, importance:4, category:'Study', estimated_minutes:40, deadline:'2026-11-02T18:00:00',
  dependency_ids:[], reminder_enabled:false, reminder_lead_minutes:30, created_at:'2026-10-26T10:00:00', updated_at:'2026-10-26T10:00:00', completed_at:null,
}

describe('TaskManager', () => {
  let records: Task[]
  afterEach(()=>{vi.restoreAllMocks()})
  beforeEach(() => {
    vi.clearAllMocks()
    records = [baseTask]
    mockApi.tasks.mockImplementation(async (query:Record<string,any>={}) => {
      let output = [...records]
      if (query.q) output = output.filter(task => (task.title+' '+task.description).toLowerCase().includes(query.q.toLowerCase()))
      if (query.status) output = output.filter(task => task.status===query.status)
      if (query.category) output = output.filter(task => task.category===query.category)
      return output
    })
    mockApi.categories.mockResolvedValue([{id:'cat-1',name:'Study'}])
    mockApi.createCategory.mockImplementation(async (name:string)=>({id:'cat-2',name}))
    mockApi.deleteCategory.mockResolvedValue(undefined)
    mockApi.create.mockImplementation(async (payload)=>{
      const created={...baseTask,id:'task-'+(records.length+1),...payload,created_at:'2026-10-26T11:00:00',updated_at:'2026-10-26T11:00:00'}
      records.push(created)
      return created
    })
    mockApi.update.mockImplementation(async (id,payload)=>{
      const index=records.findIndex(task=>task.id===id)
      records[index]={...records[index],...payload}
      return records[index]
    })
    mockApi.duplicate.mockImplementation(async id=>{
      const copy={...records.find(task=>task.id===id)!,id:'task-copy',title:records.find(task=>task.id===id)!.title+' (copy)'}
      records.push(copy)
      return copy
    })
    mockApi.remove.mockImplementation(async id=>{records=records.filter(task=>task.id!==id)})
    vi.spyOn(window,'confirm').mockReturnValue(true)
  })

  it('loads tasks and sends search and status filters to the API', async () => {
    const user=userEvent.setup()
    render(<TaskManager />)
    expect(await screen.findByText('Prepare notes')).toBeTruthy()
    await user.selectOptions(screen.getByRole('combobox',{name:'Filter by status'}),'DONE')
    await waitFor(()=>expect(mockApi.tasks).toHaveBeenCalledWith(expect.objectContaining({status:'DONE'})))
    await user.clear(screen.getByRole('textbox',{name:'Search tasks'}))
    await user.type(screen.getByRole('textbox',{name:'Search tasks'}),'chapter')
    await waitFor(()=>expect(mockApi.tasks).toHaveBeenCalledWith(expect.objectContaining({q:'chapter'})))
  })

  it('creates a task through the validated editor and refreshes the list', async () => {
    const user=userEvent.setup()
    render(<TaskManager />)
    await screen.findByText('Prepare notes')
    await user.click(screen.getByRole('button',{name:'New task'}))
    await user.type(screen.getByLabelText('Task title'),'Read references')
    await user.type(screen.getByLabelText('Description'),'Read two papers')
    await user.selectOptions(screen.getByLabelText('Category'),'Study')
    await user.selectOptions(screen.getByLabelText('Priority'),'URGENT')
    await user.type(screen.getByLabelText('Estimated minutes'),'55')
    fireEvent.change(screen.getByLabelText('Due date'),{target:{value:'2026-11-02'}})
    await user.selectOptions(screen.getByRole('listbox',{name:/Depends on/}),['task-1'])
    await user.click(screen.getByRole('button',{name:'Create task'}))
    await screen.findByText('Read references')
    expect(mockApi.create).toHaveBeenCalledWith(expect.objectContaining({
      title:'Read references', description:'Read two papers', category:'Study', priority:'URGENT', estimated_minutes:55,
      status:'TODO', dependency_ids:['task-1'], deadline:expect.stringContaining('2026-11-02'),
    }),expect.stringMatching(/^[0-9a-f-]{36}$/i))
    expect(screen.getByRole('status').textContent).toContain('Task created')
  })

  it('saves an opt-in deadline reminder with its lead time', async()=>{
    const user=userEvent.setup();render(<TaskManager/>);await screen.findByText('Prepare notes');await user.click(screen.getByRole('button',{name:'New task'}));await user.type(screen.getByLabelText('Task title'),'Reminder test');fireEvent.change(screen.getByLabelText('Due date'),{target:{value:'2026-11-04'}});await user.click(screen.getByLabelText('Remind me before deadline'));await user.selectOptions(screen.getByLabelText('Reminder lead time'),'60');await user.click(screen.getByRole('button',{name:'Create task'}));await waitFor(()=>expect(mockApi.create).toHaveBeenCalledWith(expect.objectContaining({reminder_enabled:true,reminder_lead_minutes:60,deadline:expect.stringContaining('2026-11-04')}),expect.any(String)))
  })

  it('does not expose removed breakdown, subtask, or voice controls', async()=>{
    render(<TaskManager/>);await screen.findByText('Prepare notes');await userEvent.setup().click(screen.getByRole('button',{name:'New task'}));
    expect(screen.queryByRole('button',{name:/voice|suggestions|subtask/i})).toBeNull();expect(screen.queryByLabelText('Parent task')).toBeNull();expect(screen.queryByText(/Break down a goal/i)).toBeNull();
  })

  it('duplicates a task and supports task-category setup', async () => {
    const user=userEvent.setup()
    render(<TaskManager />)
    await screen.findByText('Prepare notes')
    await user.click(screen.getByRole('button',{name:'Duplicate Prepare notes'}))
    expect(await screen.findByText('Prepare notes (copy)')).toBeTruthy()
    const categoryInput=screen.getByRole('textbox',{name:'New category name'})
    await user.type(categoryInput,'Home')
    await user.click(screen.getByRole('button',{name:/^Add$/}))
    await waitFor(()=>expect(mockApi.createCategory).toHaveBeenCalledWith('Home'))
  })

  it('edits, completes, reopens, and deletes a task from the list', async () => {
    const user=userEvent.setup()
    render(<TaskManager />)
    await screen.findByText('Prepare notes')
    await user.click(screen.getByRole('button',{name:'Edit Prepare notes'}))
    const title=screen.getByLabelText('Task title')
    await user.clear(title)
    await user.type(title,'Updated notes')
    await user.selectOptions(screen.getByLabelText('Status'),'DONE')
    await user.click(screen.getByRole('button',{name:'Save changes'}))
    await screen.findByText('Updated notes')
    expect(mockApi.update).toHaveBeenCalledWith('task-1',expect.objectContaining({title:'Updated notes',status:'DONE'}))
    await user.click(screen.getByRole('button',{name:'Reopen Updated notes'}))
    expect(await screen.findByRole('button',{name:'Complete Updated notes'})).toBeTruthy()
    await user.click(screen.getByRole('button',{name:'Delete Updated notes'}))
    await waitFor(()=>expect(mockApi.remove).toHaveBeenCalledWith('task-1'))
    expect(await screen.findByText('Your task list is clear')).toBeTruthy()
  })
})
