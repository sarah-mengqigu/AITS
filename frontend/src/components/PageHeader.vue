<template>
  <div class="page-header">
    <div class="page-header__main">
      <h1 class="page-header__title">
        {{ title }}
        <span v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</span>
      </h1>
      <p v-if="description" class="page-header__desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions || $slots.default" class="page-header__actions">
      <slot name="actions" />
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  description: { type: String, default: '' },
})
</script>
