export interface User {
  id: number
  email: string
  name: string
  role: 'student' | 'admin'
  is_active: boolean
  created_at: string
}

const TOKEN_KEY = 'tubewar.token'
const USER_KEY = 'tubewar.user'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser(): User | null {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) as User : null
}

export function login(token: string, user: User): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isAuthed(): boolean {
  return !!getToken()
}

export function isAdmin(): boolean {
  return getUser()?.role === 'admin'
}
