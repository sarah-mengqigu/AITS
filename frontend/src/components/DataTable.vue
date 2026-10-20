<template>
  <div class="data-table">
    <el-table
      v-loading="loading"
      :data="data"
      :row-key="rowKey"
      border
      stripe
      :height="height"
      :max-height="maxHeight"
    >
      <slot />
      <template #empty>
        <slot name="empty">
          <el-empty :description="emptyText" :image-size="72" />
        </slot>
      </template>
    </el-table>

    <div v-if="showPagination && total > 0" class="pagination-bar">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="pageSizes"
        :disabled="loading"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  pageSizes: { type: Array, default: () => [10, 20, 50, 100] },
  emptyText: { type: String, default: '暂无数据' },
  rowKey: { type: [String, Function], default: 'id' },
  showPagination: { type: Boolean, default: true },
  height: { type: [String, Number], default: undefined },
  maxHeight: { type: [String, Number], default: undefined },
})

const emit = defineEmits(['update:page', 'update:pageSize', 'change'])

function handlePageChange(page) {
  emit('update:page', page)
  emit('change', { page, pageSize: props.pageSize })
}

function handleSizeChange(pageSize) {
  emit('update:pageSize', pageSize)
  emit('update:page', 1)
  emit('change', { page: 1, pageSize })
}
</script>

<style scoped>
.data-table {
  width: 100%;
}
</style>
