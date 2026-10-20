import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadBlob, downloadJson, downloadResponse, downloadText, downloadUrl } from '@/utils/download'

describe('utils/download', () => {
  let clickSpy
  let createObjectURLSpy

  beforeEach(() => {
    vi.useFakeTimers()
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    createObjectURLSpy = vi.fn(() => 'blob:mock-url')
    window.URL.createObjectURL = createObjectURLSpy
    window.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('downloadText 创建 Blob 并触发下载，延时释放对象 URL', () => {
    downloadText('hello world', 'hello.txt')

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1)
    const blob = createObjectURLSpy.mock.calls[0][0]
    expect(blob).toBeInstanceOf(Blob)
    expect(blob.type).toContain('text/plain')
    expect(clickSpy).toHaveBeenCalledTimes(1)

    vi.runAllTimers()
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })

  it('downloadJson 序列化对象并使用 application/json', () => {
    downloadJson({ a: 1 }, 'data.json')

    const blob = createObjectURLSpy.mock.calls[0][0]
    expect(blob.type).toContain('application/json')
    expect(clickSpy).toHaveBeenCalledTimes(1)
  })

  it('downloadBlob 可下载二进制内容', () => {
    downloadBlob(new Blob(['abc'], { type: 'application/octet-stream' }), 'file.bin')
    expect(clickSpy).toHaveBeenCalledTimes(1)
  })

  it('downloadResponse 优先解析 Content-Disposition 中的文件名', () => {
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    const response = {
      data: new Blob(['report']),
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''%E6%B5%8B%E8%AF%95%E6%8A%A5%E5%91%8A.html",
      },
    }

    downloadResponse(response)

    expect(clickSpy).toHaveBeenCalledTimes(1)
    const anchor = appendSpy.mock.calls
      .map(([node]) => node)
      .find((node) => node && node.tagName === 'A')
    expect(anchor?.download).toBe('测试报告.html')
  })

  it('downloadUrl 直接使用链接下载', () => {
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    downloadUrl('https://example.com/report.html', 'report.html')

    expect(clickSpy).toHaveBeenCalledTimes(1)
    const anchor = appendSpy.mock.calls
      .map(([node]) => node)
      .find((node) => node && node.tagName === 'A')
    expect(anchor?.getAttribute('href')).toBe('https://example.com/report.html')
    expect(anchor?.download).toBe('report.html')
  })
})
