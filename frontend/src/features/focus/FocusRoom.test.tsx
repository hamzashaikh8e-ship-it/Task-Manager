import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FocusRoom from './FocusRoom'

const mocks=vi.hoisted(()=>({focusSummary:vi.fn(),tasks:vi.fn(),startFocus:vi.fn(),focusAction:vi.fn()}))
vi.mock('../../api',()=>({api:{focusSummary:mocks.focusSummary,tasks:mocks.tasks,startFocus:mocks.startFocus,focusAction:mocks.focusAction}}))
const initial={today_seconds:0,week_seconds:0,history:[],active_session:null}
const session={id:'session-1',task_id:null,task_title:null,kind:'FOCUS',status:'ACTIVE',planned_minutes:25,elapsed_seconds:0,remaining_seconds:1500,started_at:new Date().toISOString(),paused_at:null,ended_at:null}
describe('FocusRoom',()=>{
 beforeEach(()=>{vi.clearAllMocks();mocks.focusSummary.mockResolvedValue(initial);mocks.tasks.mockResolvedValue([{id:'task-1',title:'Write report',status:'TODO'}]);mocks.startFocus.mockImplementation(async(data)=>({...session,task_id:data.task_id,task_title:data.task_id?'Write report':null}));mocks.focusAction.mockImplementation(async(_id,action)=>({...session,status:action==='pause'?'PAUSED':action==='finish'?'COMPLETED':'ACTIVE',elapsed_seconds:60}))})
 it('starts, pauses, resumes and finishes a persisted session',async()=>{const user=userEvent.setup();render(<FocusRoom/>);await screen.findByText('Ready when you are');await user.selectOptions(screen.getByLabelText('Link task (optional)'),'task-1');await user.click(screen.getByRole('button',{name:/Start session/}));expect(await screen.findByText('Working on: Write report · 25 minute focus')).toBeTruthy();await user.click(screen.getByRole('button',{name:/Pause/}));expect(mocks.focusAction).toHaveBeenLastCalledWith('session-1','pause');await user.click(screen.getByRole('button',{name:/Resume/}));expect(mocks.focusAction).toHaveBeenLastCalledWith('session-1','resume');await user.click(screen.getByRole('button',{name:/Finish/}));await waitFor(()=>expect(mocks.focusAction).toHaveBeenLastCalledWith('session-1','finish'));expect(await screen.findByText('Focus session saved to your history.')).toBeTruthy()})
it('recovers an active session and elapsed time from the server summary',async()=>{mocks.focusSummary.mockResolvedValue({...initial,active_session:{...session,status:'PAUSED',elapsed_seconds:75}});render(<FocusRoom/>);expect(await screen.findByText('Paused')).toBeTruthy();expect(screen.getByText('23:45')).toBeTruthy();expect(screen.getByText('No task linked · 25 minute focus')).toBeTruthy()})
 it('shows a clear server error when starting fails',async()=>{mocks.startFocus.mockRejectedValueOnce(new Error('Finish or reset your current session before starting another.'));const user=userEvent.setup();render(<FocusRoom/>);await user.click(await screen.findByRole('button',{name:/Start session/}));expect((await screen.findByRole('alert')).textContent).toContain('Finish or reset your current session')})
})
