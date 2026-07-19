let counter = 0

export function nextId(prefix = 'm') {
  counter += 1
  return `${prefix}-${counter}`
}
