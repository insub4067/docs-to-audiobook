<template>
  <router-view></router-view>
  <BaseToast />
  <BaseActionSheet />
</template>

<script setup lang="ts">
import BaseToast from './components/ui/BaseToast.vue';
import BaseActionSheet from './components/ui/BaseActionSheet.vue';
</script>
