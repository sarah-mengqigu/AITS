import { describe, expect, it } from 'vitest'
import dayjs from 'dayjs'

import {
  EMPTY_TEXT,
  formatBytes,
  formatDate,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  getEnvironmentTypeText,
  getProjectTypeText,
  getRoleText,
  getStatusColor,
  getStatusTagType,
  getStatusText,
} from '@/utils/format'

describe('utils/format', () => {
  it('格式化日期，空值返回占位符', () => {
    expect(formatDate('2024-05-01T10:20:30Z')).toMatch(/^2024-05-0[12]$/)
    expect(formatDate(null)).toBe(EMPTY_TEXT)
    expect(formatDate('')).toBe(EMPTY_TEXT)
    expect(formatDate('not-a-date')).toBe(EMPTY_TEXT)
    expect(formatDateTime('2024-05-01T10:20:30')).toBe('2024-05-01 10:20:30')
  })

  it('格式化百分比与数字', () => {
    expect(formatPercent(98.456)).toBe('98.5%')
    expect(formatPercent(0)).toBe('0.0%')
    expect(formatPercent(null)).toBe(EMPTY_TEXT)
    expect(formatNumber(1234567)).toBe('1,234,567')
    expect(formatNumber(12.345, 1)).toBe('12.3')
    expect(formatNumber(undefined)).toBe(EMPTY_TEXT)
  })

  it('格式化时长', () => {
    expect(formatDuration(0)).toBe('0 ms')
    expect(formatDuration(850)).toBe('850 ms')
    expect(formatDuration(2500)).toBe('2.50 s')
    expect(formatDuration(125000)).toBe('2 min 5 s')
    expect(formatDuration(3723000)).toBe('1 h 2 min')
    expect(formatDuration(null)).toBe(EMPTY_TEXT)
  })

  it('格式化字节', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1048576)).toBe('1.0 MB')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(-1)).toBe(EMPTY_TEXT)
  })

  it('格式化相对时间', () => {
    expect(formatRelativeTime(dayjs().subtract(10, 'second').toISOString())).toBe('刚刚')
    expect(formatRelativeTime(dayjs().subtract(5, 'minute').toISOString())).toBe('5 分钟前')
    expect(formatRelativeTime(dayjs().subtract(3, 'hour').toISOString())).toBe('3 小时前')
    expect(formatRelativeTime(null)).toBe(EMPTY_TEXT)
  })

  it('状态文本 / 标签类型 / 颜色映射完整且有回退', () => {
    expect(getStatusText('passed')).toBe('通过')
    expect(getStatusText('running')).toBe('执行中')
    expect(getStatusText('unknown-status')).toBe('unknown-status')
    expect(getStatusText(null)).toBe('未知')
    expect(getStatusText(null, '未执行')).toBe('未执行')

    expect(getStatusTagType('passed')).toBe('success')
    expect(getStatusTagType('failed')).toBe('danger')
    expect(getStatusTagType('running')).toBe('warning')
    expect(getStatusTagType('unknown-status')).toBe('info')

    expect(getStatusColor('passed')).toBe('#16a34a')
    expect(getStatusColor('failed')).toBe('#dc2626')
    expect(getStatusColor(null)).toBe('#94a3b8')
  })

  it('业务枚举文案映射', () => {
    expect(getProjectTypeText('api')).toBe('API 接口测试')
    expect(getProjectTypeText('unknown')).toBe('unknown')
    expect(getRoleText('owner')).toBe('拥有者')
    expect(getRoleText('viewer')).toBe('只读')
    expect(getEnvironmentTypeText('staging')).toBe('预发布环境')
  })
})
