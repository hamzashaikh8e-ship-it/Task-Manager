import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Task } from '../../api'
import KanbanBoard, { moveTaskWithRollback } from './KanbanBoard'

const mocks = vi.hoisted(() => ({ tasks: vi.fn(), update: vi.fn() }))
vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api')
  return { ...actual, api: { ...actual.api, tasks: mocks.tasks, update: mocks.update } }
})

const task: Task = {
  id: 'task-1', owner_id: 'user-1', title: 'Prepare notes', description: 'Review the chapter',
  status: 'TODO', priority: 'HIGH', importance: 4, category: 'Study', estimated_minutes: 40,
  deadline: '2026-11-02T18:00:00', scheduled_start: '2026-11-02T09:00:00', scheduled_end: '2026-11-02T09:40:00',
  dependency_ids: [], reminder_enabled:false, reminder_lead_minutes:30, created_at: '2026-10-26T10:00:00', updated_at: '2026-10-26T10:00:00', completed_at: null,
}

describe('KanbanBoard', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.tasks.mockResolvedValue([task]); mocks.update.mockResolvedValue({ ...task, status: 'IN_PROGRESS' }) })
  afterEach(() => { vi.restoreAllMocks() })

  it('loads real task cards into their status columns and exposes accessible drag controls', async () => {
    render(<KanbanBoard />)
    expect(await screen.findByText('Prepare notes')).toBeTruthy()
    expect(screen.getByRole('region', { name: 'To Do column' }).textContent).toContain('Study')
    expect(screen.getByRole('button', { name: 'Drag task Prepare notes' })).toBeTruthy()
  })

  it('persists status moves with all task fields intact', async () => {
    const callbacks = { saved: vi.fn(), rollback: vi.fn(), failed: vi.fn() }
    await moveTaskWithRollback(task, 'IN_PROGRESS', mocks.update, callbacks)
    expect(mocks.update).toHaveBeenCalledWith('task-1', expect.objectContaining({
      status: 'IN_PROGRESS', title: 'Prepare notes', deadline: task.deadline,
      scheduled_start: task.scheduled_start, scheduled_end: task.scheduled_end,
      category: 'Study', dependency_ids: [],
    }))
    expect(callbacks.saved).toHaveBeenCalledWith(expect.objectContaining({ status: 'IN_PROGRESS' }))
  })

  it('restores the prior card position and reports an API failure', async () => {
    const callbacks = { saved: vi.fn(), rollback: vi.fn(), failed: vi.fn() }
    await moveTaskWithRollback(task, 'DONE', vi.fn().mockRejectedValue(new Error('offline')), callbacks)
    expect(callbacks.saved).not.toHaveBeenCalled()
    expect(callbacks.rollback).toHaveBeenCalledOnce()
    expect(callbacks.failed).toHaveBeenCalledWith('offline')
  })

  it('shows a recoverable error when tasks cannot load', async () => {
    mocks.tasks.mockRejectedValueOnce(new Error('offline'))
    render(<KanbanBoard />)
    expect((await screen.findByRole('alert')).textContent).toContain('offline')
  })
})
