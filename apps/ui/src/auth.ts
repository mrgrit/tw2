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

// 세션은 **탭 단위**(sessionStorage)로 격리한다. localStorage 는 같은 브라우저의 모든 탭이
// 공유하므로, 한 탭에서 레드팀·다른 탭에서 블루팀으로 로그인하면 토큰이 섞인다.
// sessionStorage 는 탭마다 독립적이라 계정이 섞이지 않는다(탭을 닫으면 로그아웃).
const store = window.sessionStorage

// 과거 localStorage 에 남은 토큰/유저(섞임의 원인) 제거 — 일회성 마이그레이션.
try {
  window.localStorage.removeItem(TOKEN_KEY)
  window.localStorage.removeItem(USER_KEY)
} catch { /* ignore */ }

export function getToken(): string | null {
  return store.getItem(TOKEN_KEY)
}

export function getUser(): User | null {
  const raw = store.getItem(USER_KEY)
  return raw ? JSON.parse(raw) as User : null
}

export function login(token: string, user: User): void {
  store.setItem(TOKEN_KEY, token)
  store.setItem(USER_KEY, JSON.stringify(user))
}

export function logout(): void {
  store.removeItem(TOKEN_KEY)
  store.removeItem(USER_KEY)
}

export function isAuthed(): boolean {
  return !!getToken()
}

export function isAdmin(): boolean {
  return getUser()?.role === 'admin'
}
