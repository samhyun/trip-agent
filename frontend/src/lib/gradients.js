// 이미지 대신 쓰는 플레이스홀더 그라디언트 (디자인 목업의 "[ 사진 ]" 톤 재현)
export const GRADIENTS = [
  'linear-gradient(135deg, oklch(0.55 0.09 220), oklch(0.62 0.11 255))',
  'linear-gradient(135deg, oklch(0.6 0.1 200), oklch(0.66 0.1 175))',
  'linear-gradient(135deg, oklch(0.5 0.08 155), oklch(0.58 0.1 135))',
  'linear-gradient(135deg, oklch(0.52 0.07 250), oklch(0.6 0.09 230))',
  'linear-gradient(135deg, oklch(0.55 0.08 210), oklch(0.62 0.09 190))',
  'linear-gradient(135deg, oklch(0.5 0.06 160), oklch(0.58 0.08 140))',
]

export function gradientFor(index) {
  return GRADIENTS[index % GRADIENTS.length]
}
