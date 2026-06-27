<template>
  <main class="auth-shell">
    <section class="auth-shell__brand" aria-hidden="true">
      <div class="auth-shell__brand-mark">CPUModel</div>
      <div class="auth-shell__signal-board">
        <div class="signal-row">
          <span>Docking</span>
          <strong>-9.8 kcal/mol</strong>
        </div>
        <div class="signal-row">
          <span>Screening</span>
          <strong>2.4k ligands</strong>
        </div>
        <div class="signal-row">
          <span>ADMET</span>
          <strong>Ready</strong>
        </div>
      </div>
    </section>

    <section class="auth-shell__card" aria-labelledby="auth-shell-title">
      <div class="auth-shell__heading">
        <p class="auth-shell__eyebrow">CPUModel Workspace</p>
        <h1 id="auth-shell-title" class="auth-shell__title">{{ title }}</h1>
        <p v-if="description" class="auth-shell__description">{{ description }}</p>
      </div>
      <slot />
    </section>
  </main>
</template>

<script setup lang="ts">
  defineProps<{
    title: string
    description?: string
  }>()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .auth-shell {
    min-height: 100vh;
    display: grid;
    grid-template-columns: minmax(320px, 0.9fr) minmax(360px, 520px);
    align-items: center;
    justify-content: center;
    gap: @spacing-xxl;
    padding: @spacing-xxl @spacing-lg;
    background:
      linear-gradient(135deg, rgba(15, 12, 41, 0.97) 0%, rgba(24, 54, 73, 0.95) 52%, rgba(36, 36, 62, 0.98) 100%),
      repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.06) 0 1px, transparent 1px 88px),
      repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.04) 0 1px, transparent 1px 88px);
  }

  .auth-shell__brand {
    width: min(520px, 100%);
    color: @text-color-primary;
  }

  .auth-shell__brand-mark {
    margin-bottom: @spacing-xl;
    color: @accent-color;
    font-size: @font-size-hero;
    font-weight: @font-weight-bold;
    line-height: @line-height-tight;
  }

  .auth-shell__signal-board {
    display: grid;
    gap: @spacing-sm;
    max-width: 420px;
    padding: @spacing-md;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: @border-radius-md;
    background: rgba(8, 12, 28, 0.52);
    box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
    backdrop-filter: blur(16px);
  }

  .signal-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    min-height: 38px;
    padding: 0 @spacing-sm;
    border-radius: @border-radius-sm;
    background: rgba(255, 255, 255, 0.055);
    color: rgba(255, 255, 255, 0.74);
    font-size: @font-size-sm;

    strong {
      color: @accent-color;
      font-family: @font-family-mono;
      font-size: @font-size-xs;
      font-weight: @font-weight-semibold;
    }
  }

  .auth-shell__card {
    width: min(100%, 520px);
    padding: @spacing-xl;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    box-shadow: @shadow-xl;
  }

  .auth-shell__heading {
    margin-bottom: @spacing-xl;
    text-align: left;
  }

  .auth-shell__eyebrow {
    margin: 0 0 @spacing-xs;
    color: @accent-color-hover;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
    text-transform: uppercase;
  }

  .auth-shell__title {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    line-height: @line-height-tight;
  }

  .auth-shell__description {
    margin: @spacing-sm 0 0;
    color: @text-secondary;
    font-size: @font-size-md;
    line-height: @line-height-base;
  }

  @media (max-width: @screen-lg) {
    .auth-shell {
      grid-template-columns: minmax(0, 520px);
      gap: @spacing-xl;
    }

    .auth-shell__brand {
      width: 100%;
    }

    .auth-shell__brand-mark {
      margin-bottom: @spacing-md;
      font-size: @font-size-title;
    }
  }

  @media (max-width: @screen-sm) {
    .auth-shell {
      padding: @spacing-lg @spacing-md;
    }

    .auth-shell__brand {
      display: none;
    }

    .auth-shell__card {
      padding: @spacing-lg;
    }

    .auth-shell__title {
      font-size: @font-size-xxl;
    }
  }
</style>
