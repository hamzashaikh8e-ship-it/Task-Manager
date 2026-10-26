import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

export default function ThemeToggle(){
 const [theme,setTheme]=useState<'light'|'dark'>(()=>localStorage.getItem('taskflow_theme')==='dark'?'dark':'light')
 useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('taskflow_theme',theme)},[theme])
 return <button className="icon-button theme-toggle" type="button" aria-pressed={theme==='dark'} aria-label={theme==='dark'?'Switch to light mode':'Switch to dark mode'} title={theme==='dark'?'Switch to light mode':'Switch to dark mode'} onClick={()=>setTheme(current=>current==='dark'?'light':'dark')}>{theme==='dark'?<Sun size={18}/>:<Moon size={18}/>}</button>
}
