import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Task } from '../../api'
import CalendarPage from './CalendarPage'

const mocks = vi.hoisted(() => ({ calendarEvents: vi.fn(), update: vi.fn() }))
vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api')
  return { ...actual, api: { ...actual.api, calendarEvents: mocks.calendarEvents, update: mocks.update } }
})

function localTodayKey() {
  const today = new Date()
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
}
const task: Task = {
  id: 'calendar-task', owner_id: 'user-1', title: 'Write a spec', description: '', status: 'TODO', priority: 'HIGH', importance: 4,
  category: 'Planning', estimated_minutes: 35, deadline: new Date(`${localTodayKey()}T23:59:00`).toISOString().replace(/Z$/, ''),
  scheduled_start: `${localTodayKey()}T08:00:00`, scheduled_end: `${localTodayKey()}T08:35:00`,
  dependency_ids: [], reminder_enabled:false, reminder_lead_minutes:30, created_at: `${localTodayKey()}T10:00:00`, updated_at: `${localTodayKey()}T10:00:00`, completed_at: null,
}

describe('CalendarPage', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.calendarEvents.mockResolvedValue([task]); mocks.update.mockResolvedValue(task) })
  afterEach(() => { vi.restoreAllMocks() })

  it('loads real deadline and scheduled events and supports month, week, and day views', async () => {
    const user = userEvent.setup()
    render(<CalendarPage />)
    expect(await screen.findByRole('button', { name: `Deadline ${task.title}` })).toBeTruthy()
    expect(screen.getByRole('button', { name: new RegExp(`Scheduled .*${task.title}`) })).toBeTruthy()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Calendar view' }), 'week')
    expect(await screen.findByRole('grid', { name: 'week calendar' })).toBeTruthy()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Calendar view' }), 'day')
    expect(await screen.findByRole('grid', { name: 'day calendar' })).toBeTruthy()
  })

  it('opens a task and saves changed dates through the task API, then refreshes events', async () => {
    const user = userEvent.setup()
    render(<CalendarPage />)
    await user.click(await screen.findByRole('button', { name: `Deadline ${task.title}` }))
    fireEvent.change(screen.getByLabelText('Due date'), { target: { value: '2026-11-05' } })
    await user.click(screen.getByRole('button', { name: 'Save dates' }))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith('calendar-task', expect.objectContaining({
      deadline: expect.stringContaining('2026-11-05'), scheduled_start: expect.any(String), scheduled_end: expect.any(String), status: 'TODO',
    })))
    expect((await screen.findByRole('status')).textContent).toContain('Calendar dates saved.')
    expect(mocks.calendarEvents.mock.calls.length).toBeGreaterThanOrEqual(2)
  })
})
