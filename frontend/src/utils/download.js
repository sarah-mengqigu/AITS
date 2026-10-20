/** 浏览器端文件下载工具（Blob / 文本 / JSON / 直链）。 */

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename || 'download'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // 释放对象 URL，避免内存泄漏
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadBlob(blob, filename = 'download.bin') {
  if (typeof document === 'undefined') return
  triggerDownload(blob, filename)
}

export function downloadText(content, filename = 'download.txt', mime = 'text/plain;charset=utf-8') {
  downloadBlob(new Blob([content ?? ''], { type: mime }), filename)
}

export function downloadJson(data, filename = 'data.json') {
  downloadText(JSON.stringify(data, null, 2), filename, 'application/json;charset=utf-8')
}

/** 直接跳转下载（用于后端返回文件流/预签名地址）。 */
export function downloadUrl(url, filename = '') {
  if (!url || typeof document === 'undefined') return
  const link = document.createElement('a')
  link.href = url
  if (filename) link.download = filename
  link.target = '_blank'
  link.rel = 'noopener'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

/** 从 axios 二进制响应下载（携带后端 Content-Disposition 文件名优先）。 */
export function downloadResponse(response, fallbackName = 'download.bin') {
  const disposition = response?.headers?.['content-disposition'] || ''
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  let filename = fallbackName
  if (encoded) {
    try {
      filename = decodeURIComponent(encoded[1])
    } catch {
      filename = fallbackName
    }
  } else if (plain) {
    filename = plain[1]
  }
  downloadBlob(response?.data, filename)
}

export function openInNewTab(url) {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}
