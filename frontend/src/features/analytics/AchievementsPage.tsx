import { useEffect, useState } from 'react'
import { Award, Flame, Sparkles, Trophy } from 'lucide-react'
import { api, GamificationProfile } from '../../api'

export default function AchievementsPage(){
 const [profile,setProfile]=useState<GamificationProfile|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('')
 async function load(){setLoading(true);setError('');try{setProfile(await api.gamificationProfile())}catch(e){setError(e instanceof Error?e.message:'Could not load achievements.')}finally{setLoading(false)}}
 useEffect(()=>{void load()},[])
 if(loading)return <div className="phase-page"><div className="task-state"><span className="spin-dot"/> Loading your progress…</div></div>
 if(error)return <div className="phase-page"><div className="error-banner" role="alert">{error}</div><button className="secondary" onClick={()=>void load()}>Try again</button></div>
 if(!profile)return null
 const percent=profile.xp_in_level/(profile.xp_in_level+profile.xp_to_next_level)*100
 return <div className="phase-page achievements-page"><div className="phase-heading"><div><p className="eyebrow">PROGRESS THAT ADDS UP</p><h1>Achievements</h1><p>Earn XP by finishing tasks and qualifying focus sessions.</p></div><div className="streak-chip"><Flame size={17}/><b>{profile.current_streak}</b><span>day streak</span></div></div>
 <section className="panel level-card"><div className="level-head"><div><span>LEVEL</span><b>{profile.level}</b></div><div><strong>{profile.total_xp} XP</strong><small>{profile.xp_to_next_level} XP to level {profile.level+1}</small></div></div><div className="level-track"><i style={{width:`${percent}%`}}/></div><div className="level-foot"><span>{profile.xp_in_level} / {profile.xp_in_level+profile.xp_to_next_level} XP</span><span>Longest streak: {profile.longest_streak} days</span></div></section>
 <div className="achievement-layout"><section className="panel achievement-panel"><div className="panel-head"><div><h2><Trophy size={15}/> Milestones</h2><p>Progress is based on qualifying activity.</p></div></div><div className="achievement-grid">{profile.achievements.map(item=><article className={`achievement-card ${item.unlocked_at?'unlocked':''}`} key={item.slug}><div className="achievement-icon">{item.unlocked_at?<Award size={19}/>:<Sparkles size={18}/>}</div><div className="achievement-copy"><b>{item.title}</b><p>{item.description}</p>{item.unlocked_at?<small>Unlocked {new Date(item.unlocked_at+'Z').toLocaleDateString()}</small>:<><div className="achievement-progress"><i style={{width:`${item.target?item.progress/item.target*100:0}%`}}/></div><small>{item.progress.toLocaleString()} / {item.target.toLocaleString()} progress</small></>}</div></article>)}</div></section>
 <section className="panel points-panel"><div className="panel-head"><div><h2><Sparkles size={15}/> XP ledger</h2><p>Recent awarded points</p></div></div>{profile.point_events.length===0?<div className="analytics-empty">Complete a task or focus session to earn XP.</div>:profile.point_events.map(event=><div className="point-row" key={event.id}><span>{event.source_type==='TASK_COMPLETION'?'Task completed':'Focus session'}</span><b>+{event.points} XP</b><small>{new Date(event.created_at+'Z').toLocaleDateString()}</small></div>)}</section></div></div>
}
