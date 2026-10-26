import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('authenticated API requests',()=>{
 afterEach(()=>{localStorage.clear();vi.unstubAllGlobals()})
 it('clears an expired session and emits the auth-expired event',async()=>{
  localStorage.setItem('taskflow_token','expired-token')
  const listener=vi.fn()
  window.addEventListener('taskflow:auth-expired',listener)
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:401,json:async()=>({detail:'Invalid or expired access token'})}))
  await expect(api.me()).rejects.toThrow('Your session expired. Please sign in again.')
  expect(localStorage.getItem('taskflow_token')).toBeNull()
  expect(listener).toHaveBeenCalledOnce()
  window.removeEventListener('taskflow:auth-expired',listener)
 })
 it('sends the same idempotency key with an task create retry',async()=>{
  localStorage.setItem('taskflow_token','session-token')
  const fetchMock=vi.fn().mockResolvedValue({ok:true,status:201,json:async()=>({id:'task-1'})})
  vi.stubGlobal('fetch',fetchMock)
  await api.create({title:'Review arrays',description:'',status:'TODO',priority:'HIGH',importance:4,category:null,estimated_minutes:30,deadline:null,scheduled_start:null,scheduled_end:null,dependency_ids:[],reminder_enabled:false,reminder_lead_minutes:30},'00000000-0000-4000-8000-000000000001')
  const request=fetchMock.mock.calls[0][1] as RequestInit
  expect((request.headers as Record<string,string>)['Idempotency-Key']).toBe('00000000-0000-4000-8000-000000000001')
 })
 it('revokes the server session on logout and clears local credentials',async()=>{
  localStorage.setItem('taskflow_token','session-token')
  const fetchMock=vi.fn().mockResolvedValue({ok:true,status:204})
  vi.stubGlobal('fetch',fetchMock)
  await api.logout()
  expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/v1\/auth\/logout$/)
  expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('POST')
  expect(((fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string,string>).Authorization).toBe('Bearer session-token')
  expect(localStorage.getItem('taskflow_token')).toBeNull()
 })
})
