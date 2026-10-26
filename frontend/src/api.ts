const API = import.meta.env.VITE_API_URL ?? '/api/v1'
export type TaskStatus = 'TODO'|'IN_PROGRESS'|'DONE'
export type TaskPriority = 'LOW'|'MEDIUM'|'HIGH'|'URGENT'
export type Task = { id: string; owner_id: string; title: string; description: string; status: TaskStatus; priority: TaskPriority; importance: number; category?: string|null; estimated_minutes?: number|null; deadline?: string|null; scheduled_start?: string|null; scheduled_end?: string|null; dependency_ids: string[]; created_at: string; updated_at: string; completed_at?: string|null; reminder_enabled: boolean; reminder_lead_minutes: number }
export type TaskInput = Pick<Task,'title'|'description'|'status'|'priority'|'importance'|'category'|'estimated_minutes'|'deadline'|'scheduled_start'|'scheduled_end'|'dependency_ids'|'reminder_enabled'|'reminder_lead_minutes'>
export type Category = { id: string; name: string }
export type Recommendation = {task_id:string;title:string;score:number;priority:TaskPriority;deadline:string|null;estimated_minutes:number|null;explanation:string[]}
export type Reminder = {id:string;task_id:string;task_title:string;deadline:string;due_at:string;status:'PENDING'|'SENT'|'CANCELLED';delivered_at:string|null;timezone:string}
export type Notification = {id:string;task_id:string|null;title:string;message:string;created_at:string;read_at:string|null}
export type FocusSession = {id:string;task_id:string|null;task_title:string|null;kind:'FOCUS'|'BREAK';status:'ACTIVE'|'PAUSED'|'COMPLETED'|'CANCELLED';planned_minutes:number;elapsed_seconds:number;remaining_seconds:number;started_at:string;paused_at:string|null;ended_at:string|null}
export type FocusSummary = {today_seconds:number;week_seconds:number;history:FocusSession[];active_session:FocusSession|null}
export type Analytics = {start_date:string;end_date:string;timezone:string;total_tasks:number;completed_tasks:number;incomplete_tasks:number;overdue_tasks:number;completion_rate:number;status_breakdown:Record<string,number>;priority_breakdown:Record<string,number>;daily_trend:{date:string;completed:number;focus_seconds:number;focus_sessions:number}[];weekly_trend:{week_start:string;completed:number;focus_seconds:number}[];range_completed_tasks:number;range_focus_seconds:number;range_focus_sessions:number;today_date:string}
export type Achievement = {id:string;slug:string;title:string;description:string;progress:number;target:number;unlocked_at:string|null}
export type PointEvent = {id:string;source_type:string;source_id:string;points:number;created_at:string}
export type GamificationProfile = {total_xp:number;level:number;xp_in_level:number;xp_to_next_level:number;current_streak:number;longest_streak:number;last_activity_date:string|null;achievements:Achievement[];point_events:PointEvent[]}
export type Availability = {id:string;kind:'WORKING_HOURS'|'COMMITMENT';weekday:number|null;local_start:string|null;local_end:string|null;starts_at:string|null;ends_at:string|null;title:string|null}
export type PlanItem = {id:string;task_id:string|null;item_type:'TASK'|'BREAK'|'COMMITMENT'|'UNSCHEDULED';title:string;starts_at:string|null;ends_at:string|null;reason:string|null;position:number}
export type DailyPlan = {id:string;plan_date:string;timezone:string;status:'DRAFT'|'APPROVED';available_minutes:number|null;break_minutes:number;break_every_minutes:number;generated_at:string;approved_at:string|null;items:PlanItem[]}
export type TaskQuery = { q?: string; status?: TaskStatus; priority?: TaskPriority; category?: string; deadline_from?: string; deadline_to?: string; sort_by?: 'created'|'updated'|'deadline'|'priority'|'title'; sort_order?: 'asc'|'desc'; offset?: number; limit?: number }
type User = { id: string; email: string; full_name: string; timezone: string }
function token() { return localStorage.getItem('taskflow_token') }
export function createIdempotencyKey(){try{if(typeof crypto!=='undefined'&&crypto.randomUUID)return crypto.randomUUID()}catch{}return `${Date.now()}-${Math.random()}-${Math.random()}`}
function apiErrorDetail(detail:unknown):string|undefined{
  if(typeof detail==='string')return detail
  if(Array.isArray(detail))return detail.map((issue:any)=>{
    const location=Array.isArray(issue?.loc)?issue.loc.slice(1).join('.'):''
    return `${location?`${location}: `:''}${issue?.msg||'Invalid value'}`
  }).join('; ')
  if(detail&&typeof detail==='object')return JSON.stringify(detail)
  return undefined
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response:Response
  try {
    response = await fetch(`${API}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(token() ? { Authorization: `Bearer ${token()}` } : {}), ...options.headers } })
  } catch (error) {
    const reason=error instanceof Error?error.message:'Network request failed'
    throw new Error(`Could not reach the TaskFlow API at ${API}. Check that FastAPI is running and CORS allows ${window.location.origin}. (${reason})`)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    if (response.status === 401 && token()) {
      localStorage.removeItem('taskflow_token')
      window.dispatchEvent(new Event('taskflow:auth-expired'))
      throw new Error('Your session expired. Please sign in again.')
    }
    throw new Error(apiErrorDetail(body.detail) ?? `Request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}
export const api = {
  async auth(path: 'register'|'login', data: object) { const result = await request<{access_token:string;user:User}>(`/auth/${path}`, {method:'POST',body:JSON.stringify(data)}); localStorage.setItem('taskflow_token', result.access_token); return result.user },
  async logout() { try { await request<void>('/auth/logout',{method:'POST'}) } finally { localStorage.removeItem('taskflow_token') } },
  me: () => request<User>('/users/me'),
  tasks: (query:TaskQuery={}) => { const params=new URLSearchParams(); Object.entries(query).forEach(([key,value])=>{if(value!==undefined&&value!==''&&value!==null)params.set(key,String(value))}); return request<Task[]>(`/tasks${params.size?`?${params.toString()}`:''}`) },
  calendarEvents: (start:string,end:string) => { const params=new URLSearchParams({start,end}); return request<Task[]>(`/calendar/events?${params.toString()}`) },
  categories: () => request<Category[]>('/categories'),
  createCategory: (name:string) => request<Category>('/categories',{method:'POST',body:JSON.stringify({name})}),
  deleteCategory: (id:string) => request<void>(`/categories/${id}`,{method:'DELETE'}),
  create: (data:TaskInput,idempotencyKey?:string) => request<Task>('/tasks',{method:'POST',body:JSON.stringify(data),...(idempotencyKey?{headers:{'Idempotency-Key':idempotencyKey}}:{})}),
  update: (id:string,data:TaskInput) => request<Task>(`/tasks/${id}`,{method:'PUT',body:JSON.stringify(data)}),
  duplicate: (id:string) => request<Task>(`/tasks/${id}/duplicate`,{method:'POST'}),
  remove: (id:string) => request<void>(`/tasks/${id}`,{method:'DELETE'}),
  recommendations: (available_minutes?:number) => request<Recommendation[]>(`/planner/recommendations${available_minutes===undefined?'':`?available_minutes=${available_minutes}`}`),
  availability: () => request<Availability[]>('/planner/availability'),
  addAvailability: (data:object) => request<Availability>('/planner/availability',{method:'POST',body:JSON.stringify(data)}),
  removeAvailability: (id:string) => request<void>(`/planner/availability/${id}`,{method:'DELETE'}),
  generatePlan: (data:object) => request<DailyPlan>('/planner/plans/generate',{method:'POST',body:JSON.stringify(data)}),
  plan: (date:string) => request<DailyPlan|null>(`/planner/plans?plan_date=${date}`),
  editPlanItem: (planId:string,itemId:string,data:object) => request<DailyPlan>(`/planner/plans/${planId}/items/${itemId}`,{method:'PUT',body:JSON.stringify(data)}),
  approvePlan: (planId:string) => request<DailyPlan>(`/planner/plans/${planId}/approve`,{method:'POST'}),
  updateTimezone: (timezone:string) => request<User>('/users/preferences',{method:'PUT',body:JSON.stringify({timezone})}),
  reminders: () => request<Reminder[]>('/reminders'),
  notifications: (limit=30) => request<Notification[]>(`/notifications?limit=${limit}`),
  unreadNotifications: () => request<{count:number}>('/notifications/unread-count'),
  readNotification: (id:string) => request<Notification>(`/notifications/${id}/read`,{method:'POST'}),
  readAllNotifications: () => request<Notification[]>('/notifications/read-all',{method:'POST'}),
  focusSummary: () => request<FocusSummary>('/focus/summary'),
  analytics: (start:string,end:string) => request<Analytics>(`/analytics/overview?${new URLSearchParams({start_date:start,end_date:end})}`),
  gamificationProfile: () => request<GamificationProfile>('/gamification/profile'),
  startFocus: (data:{kind:'FOCUS'|'BREAK';planned_minutes:number;task_id:string|null}) => request<FocusSession>('/focus/sessions',{method:'POST',body:JSON.stringify(data)}),
  focusAction: (id:string,action:'pause'|'resume'|'finish'|'reset') => request<FocusSession>(`/focus/sessions/${id}/${action}`,{method:'POST'}),
}
