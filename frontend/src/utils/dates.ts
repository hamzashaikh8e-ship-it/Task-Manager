/** API datetimes without an offset are UTC by contract. */
export function parseApiDate(value: string) {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
}

export function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function apiLocalDateKey(value?: string | null) {
  return value ? localDateKey(parseApiDate(value)) : ''
}
