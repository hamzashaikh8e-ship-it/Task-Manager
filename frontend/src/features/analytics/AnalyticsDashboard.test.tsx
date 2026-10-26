import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AnalyticsDashboard from './AnalyticsDashboard'
import AchievementsPage from './AchievementsPage'

const mocks=vi.hoisted(()=>({analytics:vi.fn(),gamificationProfile:vi.fn()}))
vi.mock('../../api',()=>({api:{analytics:mocks.analytics,gamificationProfile:mocks.gamificationProfile}}))
const analytics={start_date:'2026-10-01',end_date:'2026-10-30',timezone:'Asia/Kolkata',total_tasks:2,completed_tasks:1,incomplete_tasks:1,overdue_tasks:1,completion_rate:50,status_breakdown:{TODO:1,IN_PROGRESS:0,DONE:1},priority_breakdown:{LOW:0,MEDIUM:1,HIGH:1,URGENT:0},daily_trend:[{date:'2026-10-30',completed:1,focus_seconds:1800,focus_sessions:1}],weekly_trend:[{week_start:'2026-10-26',completed:1,focus_seconds:1800}],range_completed_tasks:1,range_focus_seconds:1800,range_focus_sessions:1,today_date:'2026-10-30'}
const profile={total_xp:120,level:2,xp_in_level:20,xp_to_next_level:80,current_streak:3,longest_streak:5,last_activity_date:'2026-10-30',achievements:[{id:'a1',slug:'first_task',title:'First finish',description:'Complete your first task.',progress:1,target:1,unlocked_at:'2026-10-29T12:00:00'},{id:'a2',slug:'ten_tasks',title:'Ten done',description:'Complete ten different tasks.',progress:4,target:10,unlocked_at:null}],point_events:[{id:'p1',source_type:'TASK_COMPLETION',source_id:'task-1',points:10,created_at:'2026-10-30T10:00:00'}]}
describe('analytics and achievements pages',()=>{
 beforeEach(()=>{vi.clearAllMocks();mocks.analytics.mockResolvedValue(analytics);mocks.gamificationProfile.mockResolvedValue(profile)})
 it('loads real analytics and requests a new date range',async()=>{render(<AnalyticsDashboard timezone="Asia/Kolkata"/>);expect(await screen.findByRole('img',{name:'50 percent of tasks completed'})).toBeTruthy();expect(screen.getByText('Overdue')).toBeTruthy();expect(mocks.analytics).toHaveBeenCalledOnce();fireEvent.click(screen.getByRole('button',{name:'7D'}));await waitFor(()=>expect(mocks.analytics).toHaveBeenCalledTimes(2))})
 it('shows loading errors and retries analytics requests',async()=>{mocks.analytics.mockRejectedValueOnce(new Error('Analytics unavailable')).mockResolvedValueOnce(analytics);render(<AnalyticsDashboard/>);expect((await screen.findByRole('alert')).textContent).toContain('Analytics unavailable');fireEvent.click(screen.getByRole('button',{name:'Retry'}));expect(await screen.findByRole('img',{name:'50 percent of tasks completed'})).toBeTruthy()})
 it('shows XP, streak, achievement progress and point ledger',async()=>{render(<AchievementsPage/>);expect(await screen.findByText('120 XP')).toBeTruthy();expect(screen.getByText('3')).toBeTruthy();expect(screen.getByText('4 / 10 progress')).toBeTruthy();expect(screen.getByText('+10 XP')).toBeTruthy();expect(screen.getByText(/Unlocked/)).toBeTruthy()})
})
