import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.ts'
import { isAuthed } from '../auth.ts'

// 드래그-질문 AI 튜터.
// 어느 페이지에서든 텍스트를 드래그하면 "AI에게 질문" 팝업이 뜨고, 누르면 현재 페이지 맥락 +
// 선택한 내용을 근거로 개인 GPU(Ollama) 모델에게 질의응답한다. (프로필에서 서버/모델 설정)

interface Message { role: 'user' | 'assistant'; content: string }

function pageContext() {
  const page_content = (document.querySelector('main') as HTMLElement | null)?.innerText?.slice(0, 4000) || ''
  return { page: window.location.pathname, title: document.title, page_content }
}

export default function AskAI() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [selection, setSelection] = useState('')   // 현재 질문에 묶인 드래그 내용
  const [loading, setLoading] = useState(false)
  const [popup, setPopup] = useState<{ text: string; x: number; y: number } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const pendingSel = useRef('')

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  // 텍스트 선택 감지 → 팝업
  const onMouseUp = useCallback((e: MouseEvent) => {
    // 위젯 내부( data-askai )에서의 선택은 무시
    if ((e.target as HTMLElement)?.closest?.('[data-askai]')) return
    const sel = window.getSelection()
    const text = sel?.toString().trim() || ''
    if (text.length < 5 || text.length > 2000) { setPopup(null); return }
    const range = sel?.getRangeAt(0)
    if (!range) return
    const r = range.getBoundingClientRect()
    setPopup({ text, x: r.left + r.width / 2, y: r.top - 8 })
  }, [])
  const onMouseDown = useCallback((e: MouseEvent) => {
    if ((e.target as HTMLElement)?.closest?.('[data-askai]')) return
    setPopup(null)
  }, [])
  useEffect(() => {
    document.addEventListener('mouseup', onMouseUp)
    document.addEventListener('mousedown', onMouseDown)
    return () => {
      document.removeEventListener('mouseup', onMouseUp)
      document.removeEventListener('mousedown', onMouseDown)
    }
  }, [onMouseUp, onMouseDown])

  function askAboutSelection() {
    const text = pendingSel.current || popup?.text || ''
    pendingSel.current = ''
    setPopup(null)
    setSelection(text)
    setOpen(true)
    window.getSelection()?.removeAllRanges()
    setTimeout(() => inputRef.current?.focus(), 80)
  }

  async function send() {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    const sel = selection
    setMessages(prev => [...prev, { role: 'user', content: sel ? `“${sel.slice(0, 120)}${sel.length > 120 ? '…' : ''}”\n\n${q}` : q }])
    setLoading(true)
    try {
      const ctx = pageContext()
      const d = await api<{ reply: string; model: string }>('/llm/ask', {
        method: 'POST',
        json: {
          question: q,
          context: { ...ctx, selection: sel },
          history: messages.slice(-10).map(m => ({ role: m.role, content: m.content.slice(0, 800) })),
        },
      })
      setMessages(prev => [...prev, { role: 'assistant', content: d.reply || '응답을 생성하지 못했습니다.' }])
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${e.message}` }])
    } finally {
      setLoading(false)
      setSelection('')   // 답변 후 선택 컨텍스트 해제(다음 질문은 새로 드래그)
    }
  }

  if (!isAuthed()) return null

  return (
    <div data-askai>
      {/* 선택 팝업 */}
      {popup && (
        <div
          onMouseDown={e => { e.stopPropagation(); e.preventDefault(); pendingSel.current = popup.text }}
          onClick={askAboutSelection}
          style={{
            position: 'fixed', left: popup.x, top: popup.y, transform: 'translate(-50%, -100%)',
            background: 'var(--primary)', color: '#fff', padding: '6px 12px', borderRadius: 8,
            fontSize: 13, fontWeight: 600, cursor: 'pointer', zIndex: 3000,
            boxShadow: '0 2px 10px rgba(0,0,0,0.35)', whiteSpace: 'nowrap', userSelect: 'none',
          }}
        >💬 AI에게 질문</div>
      )}

      {/* 플로팅 버튼 */}
      {!open && (
        <button onClick={() => setOpen(true)} title="AI 튜터" style={{
          position: 'fixed', bottom: 24, right: 24, width: 56, height: 56, borderRadius: '50%',
          background: 'var(--primary)', color: '#fff', border: 'none', fontSize: 22, fontWeight: 700,
          cursor: 'pointer', boxShadow: '0 4px 14px rgba(0,0,0,0.35)', zIndex: 1500,
        }}>AI</button>
      )}

      {/* 채팅 패널 */}
      {open && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, width: 400, maxWidth: 'calc(100vw - 32px)',
          height: 560, maxHeight: 'calc(100vh - 48px)', background: 'var(--bg, #161b22)',
          border: '1px solid var(--border)', borderRadius: 12, display: 'flex', flexDirection: 'column',
          zIndex: 1500, boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
        }}>
          <div className="row" style={{
            alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid var(--border)',
          }}>
            <span style={{ fontWeight: 700, color: 'var(--primary)', fontSize: 16, flex: 1 }}>
              🤖 AI 튜터 <span style={{ fontSize: 12, color: 'var(--fg-dim)', fontWeight: 400 }}>· 드래그해서 질문</span>
            </span>
            <button className="ghost" style={{ padding: '2px 10px' }} onClick={() => setOpen(false)}>✕</button>
          </div>

          <div style={{ flex: 1, overflow: 'auto', padding: '12px 14px' }}>
            {messages.length === 0 && (
              <div style={{ color: 'var(--fg-dim)', fontSize: 13, lineHeight: 1.6 }}>
                페이지의 미션 설명·로그·룰 등 <b>텍스트를 드래그</b>한 뒤 <b>"AI에게 질문"</b>을 누르면,
                선택한 내용과 이 페이지 맥락을 근거로 답해 드립니다. 그냥 질문만 입력해도 됩니다.
                <br /><br />※ 먼저 <b>내 프로필 → AI 모델(GPU 서버)</b> 에서 서버 연결·모델을 저장하세요.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} style={{
                marginBottom: 10, display: 'flex',
                justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div style={{
                  maxWidth: '85%', padding: '9px 13px', borderRadius: 12, fontSize: 14, lineHeight: 1.6,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  background: m.role === 'user' ? 'var(--primary)' : 'rgba(255,255,255,0.06)',
                  color: m.role === 'user' ? '#fff' : 'var(--fg)',
                }}>{m.content}</div>
              </div>
            ))}
            {loading && (
              <div style={{ color: 'var(--fg-dim)', fontSize: 13, padding: '4px 2px' }}>생각 중…</div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* 선택 컨텍스트 칩 */}
          {selection && (
            <div style={{
              margin: '0 14px', padding: '6px 10px', background: 'rgba(255,180,80,0.08)',
              borderLeft: '3px solid var(--primary)', borderRadius: 4, fontSize: 12,
              color: 'var(--fg-dim)', maxHeight: 56, overflow: 'hidden',
            }}>
              <b style={{ color: 'var(--primary)' }}>선택:</b> {selection.slice(0, 140)}{selection.length > 140 ? '…' : ''}
              <span onClick={() => setSelection('')} style={{ cursor: 'pointer', float: 'right', color: 'var(--fg-dim)' }}>✕</span>
            </div>
          )}

          <div style={{ padding: '10px 14px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8 }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="질문 입력 (Enter 전송 / Shift+Enter 줄바꿈)"
              rows={2}
              style={{ flex: 1, resize: 'none', fontSize: 14, fontFamily: 'inherit' }}
            />
            <button onClick={send} disabled={loading || !input.trim()} style={{ alignSelf: 'stretch' }}>
              전송
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
