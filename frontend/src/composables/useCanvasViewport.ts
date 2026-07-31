import { computed, ref } from 'vue'

export function useCanvasViewport(initialZoom = 1) {
  const zoom = ref(initialZoom)
  const clamp = (value: number) => Math.min(1.6, Math.max(0.5, value))
  const setZoom = (value: number) => { zoom.value = clamp(value) }
  const zoomIn = () => setZoom(zoom.value + 0.1)
  const zoomOut = () => setZoom(zoom.value - 0.1)
  const resetZoom = () => setZoom(1)
  const surfaceStyle = computed(() => ({ transform: `scale(${zoom.value})`, transformOrigin: '0 0' }))
  return { zoom, zoomIn, zoomOut, resetZoom, setZoom, surfaceStyle }
}
