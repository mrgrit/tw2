import React from 'react'

export default function Admin() {
  return (
    <>
      <h1 style={{ color: 'var(--primary)' }}>관리자</h1>
      <div className="card" style={{ background: 'rgba(88,166,255,0.08)' }}>
        <b>Phase 7 예정</b>. 구현 예정 항목:
        <ul style={{ color: 'var(--fg-dim)', margin: '8px 0 0' }}>
          <li>진행중 공방전 — 강제 종료 / 삭제</li>
          <li>공방전 히스토리 + 사용자별 점수 통계</li>
          <li>Bastion 스크랩 게시판 — 승인 / 반려 / 시나리오 자동 생성 트리거</li>
          <li>Claude Code 시나리오 생성 콘솔 (자연어 → 시나리오/미션)</li>
        </ul>
      </div>
    </>
  )
}
