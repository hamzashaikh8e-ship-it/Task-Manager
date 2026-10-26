import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import ThemeToggle from './ThemeToggle'

describe('ThemeToggle',()=>{
 beforeEach(()=>{localStorage.clear();delete document.documentElement.dataset.theme})
 it('switches between light and dark and persists the choice',()=>{
  render(<ThemeToggle/>);const button=screen.getByRole('button',{name:'Switch to dark mode'})
  fireEvent.click(button)
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(localStorage.getItem('taskflow_theme')).toBe('dark')
  fireEvent.click(screen.getByRole('button',{name:'Switch to light mode'}))
  expect(document.documentElement.dataset.theme).toBe('light')
  expect(localStorage.getItem('taskflow_theme')).toBe('light')
 })
 it('restores the saved theme after remount',()=>{localStorage.setItem('taskflow_theme','dark');render(<ThemeToggle/>);expect(document.documentElement.dataset.theme).toBe('dark')})
})
