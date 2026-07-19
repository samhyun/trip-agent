import { useEffect, useState } from 'react'
import { gradientFor } from '../../lib/gradients'

// http/https 이미지만 허용 (javascript:·data: 등 차단)
function isSafeImage(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url)
}

// 카드 썸네일 — 사진(image)이 있으면 렌더하고, 없거나 로드 실패면 색 그라데이션 + 라벨로 폴백.
export default function CardThumb({ image, gradient = 0, label, className, stripe = 8 }) {
  const [broken, setBroken] = useState(false)
  useEffect(() => setBroken(false), [image]) // 이미지 URL이 바뀌면 폴백 상태 초기화
  const showImage = isSafeImage(image) && !broken
  const backgroundImage = `${gradientFor(gradient)}, repeating-linear-gradient(45deg, oklch(1 0 0 / 0.06) 0 ${stripe}px, transparent ${stripe}px ${stripe * 2}px)`

  return (
    <div className={className} style={{ backgroundImage, position: 'relative', overflow: 'hidden' }}>
      {showImage ? (
        <img src={image} alt="" loading="lazy" className="card-thumb-img" onError={() => setBroken(true)} />
      ) : (
        label
      )}
    </div>
  )
}
