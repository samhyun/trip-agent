import { useEffect, useState } from 'react'
import { fetchHotelDetail } from '../../lib/api'
import { won } from '../../lib/format'

// 호텔 상세 모달 — 카드에서 ID로 조회한 상세(사진 갤러리·편의시설·주소·체크인아웃·설명).
export default function HotelDetailModal({ hotel, city, onClose }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [idx, setIdx] = useState(0)
  const [mainBroken, setMainBroken] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setDetail(null)
    setError('')
    setIdx(0)
    fetchHotelDetail(hotel.id, city, controller.signal)
      .then(setDetail)
      .catch((e) => {
        if (e.name !== 'AbortError') setError('상세 정보를 불러오지 못했어요.')
      })
    return () => controller.abort() // 빠르게 닫거나 호텔 변경 시 요청 취소
  }, [hotel.id, city])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    // 모달 열려 있는 동안 배경 스크롤 잠금
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  useEffect(() => setMainBroken(false), [idx]) // 이미지 바뀌면 깨짐 상태 초기화

  // https 이미지만 (백엔드가 걸러주지만 방어적으로 한 번 더)
  const images = (detail?.images || []).filter((u) => /^https:\/\//i.test(u))
  const main = (!mainBroken && images[idx]) || hotel.image

  return (
    <div className="detail-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="detail-dialog" role="dialog" aria-modal="true" aria-label={`${hotel.name} 상세`}>
        <div className="detail-head">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            <span style={{ fontSize: 16, fontWeight: 800 }}>🏨 {hotel.name}</span>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>
              ★ {hotel.rating} · {hotel.region} · {won(hotel.price)}/박
            </span>
          </div>
          <button type="button" className="detail-close" onClick={onClose} aria-label="닫기">✕</button>
        </div>

        <div className="detail-body scroll-thin">
          {error && <div style={{ padding: 24, color: 'var(--muted)', fontSize: 13 }}>{error}</div>}
          {!detail && !error && <div style={{ padding: 24, color: 'var(--muted)', fontSize: 13 }}>상세 정보 불러오는 중…</div>}

          {detail && (
            <>
              {main && (
                <div className="detail-gallery">
                  <img src={main} alt="" className="detail-gallery__main" onError={() => setMainBroken(true)} />
                  {images.length > 1 && (
                    <div className="detail-gallery__thumbs scroll-thin">
                      {images.map((src, i) => (
                        <button
                          key={src}
                          type="button"
                          className={`detail-gallery__thumb${i === idx ? ' is-active' : ''}`}
                          onClick={() => setIdx(i)}
                        >
                          <img src={src} alt="" />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="detail-info">
                {detail.address && (
                  <div className="detail-row"><span>📍</span><span>{detail.address}</span></div>
                )}
                {(detail.checkin || detail.checkout) && (
                  <div className="detail-row">
                    <span>🕒</span>
                    <span>체크인 {detail.checkin || '-'} · 체크아웃 {detail.checkout || '-'}</span>
                  </div>
                )}
                {detail.phone && <div className="detail-row"><span>📞</span><span>{detail.phone}</span></div>}

                {detail.facilities?.length > 0 && (
                  <div>
                    <div className="detail-label">편의시설</div>
                    <div className="detail-chips">
                      {detail.facilities.map((f, i) => (
                        <span key={`${i}-${f}`} className="detail-chip">{f}</span>
                      ))}
                    </div>
                  </div>
                )}

                {detail.description && (
                  <div>
                    <div className="detail-label">소개</div>
                    <p className="detail-desc">{detail.description}</p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
