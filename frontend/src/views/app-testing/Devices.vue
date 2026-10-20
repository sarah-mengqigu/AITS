<template>
  <div class="tab-panel">
    <el-alert
      type="info"
      show-icon
      :closable="false"
      title="Sonic 设备代理"
      description="设备列表来自 Sonic 服务（后端读取 SONIC_BASE_URL）。远控需要监听 jmuxer 的 WebSocket 地址，前端未内置 jmuxer 时以文本形式展示地址。"
    />

    <el-alert
      v-if="notConfigured || (!devices.length && !loading)"
      type="warning"
      show-icon
      :closable="false"
      title="未获取到 Sonic 设备"
      :description="SONIC_GUIDANCE"
    />

    <div class="page-card">
      <div class="card-title">
        <span>在线设备（{{ devices.length }}）</span>
        <el-button size="small" :icon="Refresh" :loading="loading" @click="loadDevices">刷新</el-button>
      </div>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <DataTable
        :data="devices"
        :loading="loading"
        :show-pagination="false"
        empty-text="Sonic 未返回设备：请确认已配置 SONIC_BASE_URL 且设备已上线"
      >
        <el-table-column label="设备名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.name }}</template>
        </el-table-column>
        <el-table-column label="UDID" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.udid }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平台" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="PLATFORM_TAG_TYPE[row.platform] || 'info'" effect="light">
              {{ getPlatformText(row.platform) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="型号" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.model || '—' }}</template>
        </el-table-column>
        <el-table-column label="系统版本" width="120">
          <template #default="{ row }">{{ row.version || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="/在线|online|ONLINE/i.test(row.statusText) ? 'success' : 'info'" effect="light">
              {{ row.statusText || '未知' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" :loading="remoteLoadingUdid === row.udid" @click="handleRemote(row)">
              远控
            </el-button>
          </template>
        </el-table-column>
      </DataTable>
    </div>

    <el-dialog v-model="detailVisible" title="设备详情" width="640px">
      <el-alert
        v-if="detailNotConfigured"
        type="warning"
        show-icon
        :closable="false"
        title="未配置 Sonic"
        :description="SONIC_GUIDANCE"
      />
      <template v-else>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="UDID">
            <span class="mono">{{ detailDevice.udid || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="设备名">{{ detailDevice.name }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ getPlatformText(detailDevice.platform) }}</el-descriptions-item>
          <el-descriptions-item label="型号">{{ detailDevice.model || '—' }}</el-descriptions-item>
        </el-descriptions>
        <h4 class="section-title">原始信息</h4>
        <JsonViewer :value="detail" :max-height="320" />
      </template>
    </el-dialog>

    <el-dialog v-model="remoteVisible" title="设备远控" width="720px">
      <el-alert
        v-if="remoteNotConfigured"
        type="warning"
        show-icon
        :closable="false"
        title="未配置 Sonic，无法远控"
        :description="SONIC_GUIDANCE"
      />
      <template v-else>
        <el-alert
          v-if="remoteError"
          type="error"
          show-icon
          :closable="false"
          :title="remoteError"
        />
        <template v-else>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="WebSocket 地址">
              <div class="ws-row">
                <span class="mono">{{ remoteInfo.wsUrl || '—' }}</span>
                <el-button v-if="remoteInfo.wsUrl" link type="primary" @click="copyWsUrl">复制</el-button>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="jmuxer 配置">
              <span class="mono">{{ JSON.stringify(remoteInfo.jmuxer || {}) }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            class="mt-16"
            type="info"
            show-icon
            :closable="false"
            title="未安装 jmuxer 播放器依赖"
            description="当前仅展示远控 WebSocket 地址与视频参数。安装 jmuxer 依赖后即可在此页面内嵌实时画面；也可将地址复制到 Sonic 官方远控页面使用。"
          />
          <div class="remote-placeholder">实时画面占位（jmuxer 未安装）</div>
        </template>
      </template>
      <template #footer>
        <el-button @click="remoteVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import DataTable from '@/components/DataTable.vue'
import JsonViewer from '@/components/JsonViewer.vue'

import { appTestingApi } from '@/api/appTesting'
import {
  PLATFORM_TAG_TYPE,
  SONIC_GUIDANCE,
  describeSonicError,
  formatDevice,
  getPlatformText,
  isSonicNotConfigured,
  normalizeDeviceList,
  normalizeRemoteInfo,
} from './utils'

const props = defineProps({
  projectId: { type: Number, default: null },
})

const devices = ref([])
const loading = ref(false)
const errorMessage = ref('')
const notConfigured = ref(false)

const detailVisible = ref(false)
const detail = ref(null)
const detailNotConfigured = ref(false)
const detailDevice = ref({})

const remoteVisible = ref(false)
const remoteLoadingUdid = ref('')
const remoteNotConfigured = ref(false)
const remoteError = ref('')
const remoteInfo = ref({ wsUrl: '', jmuxer: {} })

async function loadDevices() {
  loading.value = true
  errorMessage.value = ''
  notConfigured.value = false
  try {
    const payload = await appTestingApi.listDevices(
      props.projectId ? { project: props.projectId } : {},
    )
    if (isSonicNotConfigured(payload)) {
      notConfigured.value = true
      devices.value = []
    } else {
      devices.value = normalizeDeviceList(payload).map((device) => formatDevice(device))
    }
  } catch (error) {
    devices.value = []
    errorMessage.value = describeSonicError(error) || '设备列表加载失败'
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  detailVisible.value = true
  detail.value = null
  detailNotConfigured.value = false
  detailDevice.value = row
  try {
    const data = await appTestingApi.retrieveDevice(
      row.udid,
      props.projectId ? { project: props.projectId } : {},
    )
    detail.value = data
    if (isSonicNotConfigured(data)) {
      detailNotConfigured.value = true
      return
    }
    if (data?.device && typeof data.device === 'object') {
      detailDevice.value = formatDevice(data.device)
    }
  } catch (error) {
    detailNotConfigured.value = false
    ElMessage.error(describeSonicError(error) || '设备详情加载失败')
  }
}

async function handleRemote(row) {
  remoteVisible.value = true
  remoteLoadingUdid.value = row.udid
  remoteNotConfigured.value = false
  remoteError.value = ''
  remoteInfo.value = { wsUrl: '', jmuxer: {} }
  try {
    const data = await appTestingApi.deviceRemote(
      row.udid,
      props.projectId ? { project: props.projectId } : {},
    )
    if (isSonicNotConfigured(data)) {
      remoteNotConfigured.value = true
      return
    }
    const info = normalizeRemoteInfo(data)
    remoteInfo.value = info
    if (!info.wsUrl) {
      remoteError.value = '未获取到远控地址，请确认设备在线后重试'
    }
  } catch (error) {
    const message = describeSonicError(error)
    if (isSonicNotConfigured(error?.response?.data)) {
      remoteNotConfigured.value = true
    } else {
      remoteError.value = message || '获取远控信息失败'
    }
  } finally {
    remoteLoadingUdid.value = ''
  }
}

async function copyWsUrl() {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(remoteInfo.value.wsUrl || '')
      ElMessage.success('远控地址已复制')
    } else {
      ElMessage.warning('当前浏览器不支持剪贴板，请手动复制')
    }
  } catch (error) {
    ElMessage.error(`复制失败：${error?.message || '浏览器不支持'}`)
  }
}

watch(() => props.projectId, loadDevices)
onMounted(loadDevices)
</script>

<style scoped>
.section-title {
  margin: 18px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.ws-row {
  display: flex;
  align-items: center;
  gap: 8px;
  word-break: break-all;
}

.remote-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  margin-top: 12px;
  border: 1px dashed var(--aits-border);
  border-radius: 8px;
  background: #f8fafc;
  color: var(--aits-text-secondary);
  font-size: 13px;
}
</style>
