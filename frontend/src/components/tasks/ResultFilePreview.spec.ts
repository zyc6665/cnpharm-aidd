import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResultFilePreview from './ResultFilePreview.vue'
import type { VisualizationFilePreviewKind } from '@/domain/tasks'

const {
  fetchProtectedFileText,
  createProtectedObjectUrl,
  triggerProtectedFileDownload,
} = vi.hoisted(() => ({
  fetchProtectedFileText: vi.fn(),
  createProtectedObjectUrl: vi.fn(),
  triggerProtectedFileDownload: vi.fn(),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/utils/protected-file-access', () => ({
  fetchProtectedFileText,
  createProtectedObjectUrl,
  triggerProtectedFileDownload,
}))

const globalStubs = {
  AAlert: {
    props: ['message', 'description'],
    template: '<div data-testid="file-preview-alert">{{ message }}{{ description }}</div>',
  },
}

function mountPreview(file: Record<string, unknown>, previewKind: VisualizationFilePreviewKind) {
  return mount(ResultFilePreview, {
    props: { file, previewKind },
    global: { stubs: globalStubs },
  })
}

describe('ResultFilePreview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    createProtectedObjectUrl.mockResolvedValue({ url: 'blob:preview', revoke: vi.fn() })
  })

  it('按需读取并显示文本文件', async () => {
    fetchProtectedFileText.mockResolvedValue('line one\nline two')
    const wrapper = mountPreview(
      { id: 'log-1', filename: 'run.log', url: '/files/log-1/download' },
      'text'
    )

    await flushPromises()

    expect(fetchProtectedFileText).toHaveBeenCalledWith('/files/log-1/download')
    expect(wrapper.get('[data-testid="file-preview-text"]').text()).toContain('line one')
    expect(wrapper.get('[data-testid="file-preview-text"]').text()).toContain('line two')
  })

  it('自动格式化 JSON 文件', async () => {
    fetchProtectedFileText.mockResolvedValue('{"status":"ok","count":2}')
    const wrapper = mountPreview(
      { id: 'metadata-1', filename: 'metadata.json', url: '/files/metadata-1/download' },
      'json'
    )

    await flushPromises()

    const text = wrapper.get('[data-testid="file-preview-text"]').text()
    expect(text).toContain('"status": "ok"')
    expect(text).toContain('"count": 2')
  })

  it('使用受保护 Blob URL 显示图片', async () => {
    const wrapper = mountPreview(
      { id: 'image-1', filename: 'preview.png', url: '/files/image-1/download' },
      'image'
    )

    await flushPromises()

    expect(createProtectedObjectUrl).toHaveBeenCalledWith('/files/image-1/download')
    expect(wrapper.get('[data-testid="file-preview-image"]').attributes('src')).toBe('blob:preview')
  })

  it('未知文件只显示下载入口，不读取文件内容', async () => {
    const wrapper = mountPreview(
      { id: 'binary-1', filename: 'model.bin', url: '/files/binary-1/download' },
      'download'
    )

    await flushPromises()

    expect(fetchProtectedFileText).not.toHaveBeenCalled()
    expect(createProtectedObjectUrl).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="file-preview-download"]').exists()).toBe(true)

    await wrapper.get('[data-testid="file-preview-download"]').trigger('click')
    expect(triggerProtectedFileDownload).toHaveBeenCalledWith({
      id: 'binary-1',
      filename: 'model.bin',
      url: '/files/binary-1/download',
    })
  })

  it('读取失败时显示错误状态并保留下载入口', async () => {
    fetchProtectedFileText.mockRejectedValue(new Error('读取失败'))
    const wrapper = mountPreview(
      { id: 'log-2', filename: 'failed.log', url: '/files/log-2/download' },
      'text'
    )

    await flushPromises()

    expect(wrapper.get('[data-testid="file-preview-alert"]').text()).toContain('tasks.filePreviewLoadFailed')
    expect(wrapper.find('[data-testid="file-preview-download"]').exists()).toBe(true)
  })
})
