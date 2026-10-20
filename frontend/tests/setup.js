import { afterEach } from 'vitest'

// 每个用例后清空持久化，避免 store 之间相互影响
afterEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})
