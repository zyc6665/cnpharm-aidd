<template>
  <div class="home-page">
    <!-- Hero Section -->
    <section class="hero-section">
      <div class="hero-shell">
        <div class="hero-copy">
          <div class="hero-kicker">
            <span class="kicker-mark"></span>
            CPUModel AIDD Workspace
          </div>
          <h1 class="hero-title">{{ t('home.hero.title') }}</h1>
          <p class="hero-subtitle">{{ t('home.hero.subtitle') }}</p>
          <p class="hero-description">{{ t('home.hero.description') }}</p>
          <div class="hero-actions">
            <router-link to="/tools">
              <a-button type="primary" size="large" class="btn-gold">
                {{ t('home.hero.getStarted') }}
              </a-button>
            </router-link>
            <a-button size="large" ghost>
              {{ t('home.hero.learnMore') }}
            </a-button>
          </div>
        </div>

        <div class="hero-preview" aria-hidden="true">
          <div class="preview-topbar">
            <div class="preview-window-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span class="preview-status">LIVE RUN</span>
          </div>

          <div class="preview-panel preview-pipeline">
            <div class="preview-panel-title">
              <span>Pipeline</span>
              <strong>05 steps</strong>
            </div>
            <div class="preview-stage" v-for="step in previewSteps" :key="step.label">
              <span class="stage-dot" :class="`stage-dot-${step.state}`"></span>
              <span class="stage-label">{{ step.label }}</span>
              <strong>{{ step.value }}</strong>
            </div>
          </div>

          <div class="preview-grid">
            <div class="preview-panel preview-structure">
              <div class="preview-panel-title">
                <span>Binding pocket</span>
                <strong>-9.8</strong>
              </div>
              <div class="structure-canvas">
                <span class="bond bond-a"></span>
                <span class="bond bond-b"></span>
                <span class="bond bond-c"></span>
                <span class="atom atom-a"></span>
                <span class="atom atom-b"></span>
                <span class="atom atom-c"></span>
                <span class="atom atom-d"></span>
                <span class="pocket-ring pocket-a"></span>
                <span class="pocket-ring pocket-b"></span>
              </div>
            </div>

            <div class="preview-panel preview-metrics">
              <div class="preview-panel-title">
                <span>Lead score</span>
                <strong>Rank 03</strong>
              </div>
              <div class="metric-row" v-for="metric in previewMetrics" :key="metric.label">
                <div class="metric-copy">
                  <span>{{ metric.label }}</span>
                  <strong>{{ metric.value }}</strong>
                </div>
                <div class="metric-track">
                  <span class="metric-fill" :style="{ width: metric.width }"></span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Scenarios Section -->
    <section class="scenarios-section">
      <div class="container">
        <h2 class="section-title">{{ t('home.workflow.title') }}</h2>
        <p class="section-subtitle">{{ t('home.workflow.subtitle') }}</p>
        <div class="workflow-entry">
          <router-link to="/workflow">
            <a-button type="primary" size="large" class="btn-gold">
              {{ t('workflow.entry.home') }}
            </a-button>
          </router-link>
        </div>
        <div class="workflow-flow">
          <template v-for="(item, index) in workflowSteps" :key="item.key">
            <div class="workflow-step">
              <div class="workflow-icon">
                <component :is="item.icon" />
              </div>
              <div class="workflow-index">0{{ index + 1 }}</div>
              <h3 class="workflow-title">{{ t(`home.workflow.items.${item.key}.title`) }}</h3>
              <p class="workflow-desc">{{ t(`home.workflow.items.${item.key}.description`) }}</p>
            </div>
            <div v-if="index < workflowSteps.length - 1" class="workflow-arrow">
              <RightOutlined />
            </div>
          </template>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="features-section">
      <div class="container">
        <h2 class="section-title">{{ t('home.features.title') }}</h2>
        <p class="section-subtitle">{{ t('home.features.subtitle') }}</p>
        <a-row :gutter="[24, 24]">
          <a-col v-for="(item, key) in features" :key="key" :xs="24" :sm="12" :lg="6">
            <div class="feature-card">
              <div class="feature-icon">
                <component :is="item.icon" />
              </div>
              <h3 class="feature-title">{{ t(`home.features.items.${key}.title`) }}</h3>
              <p class="feature-desc">{{ t(`home.features.items.${key}.description`) }}</p>
            </div>
          </a-col>
        </a-row>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
      <div class="container">
        <h2 class="cta-title">{{ t('home.cta.title') }}</h2>
        <p class="cta-description">{{ t('home.cta.description') }}</p>
        <router-link to="/register">
          <a-button type="primary" size="large" class="btn-gold">
            {{ t('home.cta.button') }}
          </a-button>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import {
    RightOutlined,
    SearchOutlined,
    ExperimentOutlined,
    NodeIndexOutlined,
    LineChartOutlined,
    CloudOutlined,
    ApiOutlined,
    SafetyOutlined
  } from '@ant-design/icons-vue'

  const { t } = useI18n()

  const workflowSteps = [
    { key: 'pocketExploration', icon: SearchOutlined },
    { key: 'moleculeGenerationOrVirtualScreening', icon: ExperimentOutlined },
    { key: 'molecularDockingAndAffinityPrediction', icon: NodeIndexOutlined },
    { key: 'propertyPrediction', icon: LineChartOutlined },
    { key: 'leadOptimization', icon: SafetyOutlined }
  ]

  const previewSteps = [
    { label: 'Pocket', value: '12 sites', state: 'done' },
    { label: 'Screening', value: '2.4k', state: 'done' },
    { label: 'Docking', value: 'running', state: 'active' },
    { label: 'ADMET', value: 'queued', state: 'idle' }
  ]

  const previewMetrics = [
    { label: 'Affinity', value: '92%', width: '92%' },
    { label: 'QED', value: '0.74', width: '74%' },
    { label: 'Safety', value: '0.81', width: '81%' }
  ]

  const features = {
    cloud: { icon: CloudOutlined },
    api: { icon: ApiOutlined },
    security: { icon: SafetyOutlined }
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .home-page {
    min-height: 100vh;
  }

  // Hero Section
  .hero-section {
    position: relative;
    overflow: hidden;
    min-height: 680px;
    display: flex;
    align-items: center;
    padding: 72px @spacing-lg 56px;
    background:
      linear-gradient(135deg, rgba(15, 12, 41, 0.96) 0%, rgba(24, 54, 73, 0.96) 48%, rgba(36, 36, 62, 0.98) 100%),
      repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.055) 0 1px, transparent 1px 96px),
      repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.04) 0 1px, transparent 1px 96px);

    &::before {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(115deg, rgba(255, 215, 0, 0.16), transparent 34%, rgba(58, 211, 181, 0.14) 72%, transparent);
      opacity: 0.84;
      pointer-events: none;
    }

    @media (max-width: @screen-md) {
      min-height: auto;
      padding: @spacing-xxl @spacing-md;
    }
  }

  .hero-shell {
    position: relative;
    z-index: 1;
    width: min(1180px, 100%);
    margin: 0 auto;
    display: grid;
    grid-template-columns: minmax(0, 0.95fr) minmax(430px, 1.05fr);
    gap: @spacing-xxl;
    align-items: center;

    @media (max-width: @screen-lg) {
      grid-template-columns: 1fr;
      gap: @spacing-xl;
    }
  }

  .hero-copy {
    max-width: 590px;
    text-align: left;

    @media (max-width: @screen-lg) {
      max-width: 760px;
    }
  }

  .hero-kicker {
    display: inline-flex;
    align-items: center;
    gap: @spacing-sm;
    margin-bottom: @spacing-lg;
    color: rgba(255, 255, 255, 0.78);
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
    text-transform: uppercase;
  }

  .kicker-mark {
    width: 10px;
    height: 10px;
    border: 2px solid @accent-color;
    border-radius: @border-radius-round;
    box-shadow: 0 0 16px rgba(255, 215, 0, 0.64);
  }

  .hero-title {
    font-size: @font-size-hero;
    line-height: 1.08;
    font-weight: @font-weight-bold;
    color: @text-color-primary;
    margin-bottom: @spacing-md;
    animation: fadeInUp 0.6s ease-out;

    @media (max-width: @screen-md) {
      font-size: @font-size-title;
    }
  }

  .hero-subtitle {
    font-size: @font-size-xxl;
    line-height: @line-height-tight;
    color: @accent-color;
    margin-bottom: @spacing-sm;
    animation: fadeInUp 0.6s ease-out 0.1s both;

    @media (max-width: @screen-md) {
      font-size: @font-size-lg;
    }
  }

  .hero-description {
    max-width: 540px;
    font-size: @font-size-lg;
    line-height: @line-height-loose;
    color: @text-color-secondary;
    margin-bottom: @spacing-xl;
    animation: fadeInUp 0.6s ease-out 0.2s both;

    @media (max-width: @screen-md) {
      font-size: @font-size-md;
    }
  }

  .hero-actions {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-md;
    justify-content: flex-start;
    animation: fadeInUp 0.6s ease-out 0.3s both;

    .ant-btn {
      min-width: 132px;
    }

    .ant-btn-ghost {
      color: @text-color-primary;
      border-color: rgba(255, 255, 255, 0.42);
      background: rgba(255, 255, 255, 0.04);

      &:hover {
        color: @accent-color;
        border-color: @accent-color;
      }
    }
  }

  .hero-preview {
    width: 100%;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: rgba(8, 12, 28, 0.72);
    box-shadow: 0 28px 80px rgba(0, 0, 0, 0.34);
    backdrop-filter: blur(18px);
    animation: fadeInUp 0.7s ease-out 0.15s both;

    @media (max-width: @screen-sm) {
      padding: @spacing-sm;
    }
  }

  .preview-topbar {
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 @spacing-sm;
    margin-bottom: @spacing-sm;
    color: rgba(255, 255, 255, 0.68);
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .preview-window-dots {
    display: flex;
    gap: 6px;

    span {
      width: 8px;
      height: 8px;
      border-radius: @border-radius-round;
      background: rgba(255, 255, 255, 0.28);

      &:nth-child(1) {
        background: #ff7a7a;
      }

      &:nth-child(2) {
        background: #ffd666;
      }

      &:nth-child(3) {
        background: #5cdb95;
      }
    }
  }

  .preview-status {
    color: #8fe8d4;
  }

  .preview-panel {
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: @border-radius-md;
    background: rgba(255, 255, 255, 0.07);
  }

  .preview-panel-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md @spacing-md @spacing-sm;
    color: rgba(255, 255, 255, 0.7);
    font-size: @font-size-xs;

    strong {
      color: @text-color-primary;
      font-family: @font-family-mono;
      font-size: @font-size-xs;
    }
  }

  .preview-pipeline {
    padding-bottom: @spacing-sm;
    margin-bottom: @spacing-sm;
  }

  .preview-stage {
    display: grid;
    grid-template-columns: 14px minmax(0, 1fr) auto;
    align-items: center;
    gap: @spacing-sm;
    min-height: 34px;
    margin: 0 @spacing-sm @spacing-xs;
    padding: 0 @spacing-sm;
    border-radius: @border-radius-sm;
    color: rgba(255, 255, 255, 0.72);
    background: rgba(255, 255, 255, 0.045);

    strong {
      color: @accent-color;
      font-family: @font-family-mono;
      font-size: @font-size-xs;
      font-weight: @font-weight-semibold;
    }
  }

  .stage-dot {
    width: 9px;
    height: 9px;
    border-radius: @border-radius-round;
    background: rgba(255, 255, 255, 0.3);
  }

  .stage-dot-done {
    background: #5cdb95;
  }

  .stage-dot-active {
    background: @accent-color;
    box-shadow: 0 0 14px rgba(255, 215, 0, 0.68);
  }

  .stage-label {
    overflow: hidden;
    color: @text-color-primary;
    font-weight: @font-weight-medium;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .preview-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.12fr) minmax(170px, 0.88fr);
    gap: @spacing-sm;

    @media (max-width: @screen-sm) {
      grid-template-columns: 1fr;
    }
  }

  .structure-canvas {
    position: relative;
    min-height: 230px;
    margin: 0 @spacing-md @spacing-md;
    overflow: hidden;
    border-radius: @border-radius-md;
    background:
      linear-gradient(145deg, rgba(143, 232, 212, 0.16), rgba(255, 215, 0, 0.08)),
      repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.06) 0 1px, transparent 1px 38px),
      repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.05) 0 1px, transparent 1px 38px);
  }

  .bond,
  .atom,
  .pocket-ring {
    position: absolute;
    display: block;
  }

  .bond {
    width: 112px;
    height: 3px;
    border-radius: @border-radius-sm;
    background: rgba(255, 255, 255, 0.34);
    transform-origin: left center;
  }

  .bond-a {
    left: 28%;
    top: 38%;
    transform: rotate(28deg);
  }

  .bond-b {
    left: 43%;
    top: 56%;
    transform: rotate(-30deg);
  }

  .bond-c {
    left: 33%;
    top: 66%;
    transform: rotate(12deg);
  }

  .atom {
    width: 24px;
    height: 24px;
    border-radius: @border-radius-round;
    border: 2px solid rgba(255, 255, 255, 0.72);
    background: #8fe8d4;
    box-shadow: 0 0 24px rgba(143, 232, 212, 0.42);
  }

  .atom-a {
    left: 23%;
    top: 32%;
  }

  .atom-b {
    left: 50%;
    top: 43%;
    background: @accent-color;
    box-shadow: 0 0 24px rgba(255, 215, 0, 0.46);
  }

  .atom-c {
    left: 62%;
    top: 30%;
    background: #91caff;
  }

  .atom-d {
    left: 42%;
    top: 70%;
    background: #ffadd2;
  }

  .pocket-ring {
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-radius: @border-radius-round;
  }

  .pocket-a {
    left: 15%;
    top: 18%;
    width: 150px;
    height: 150px;
  }

  .pocket-b {
    right: 10%;
    bottom: 12%;
    width: 118px;
    height: 118px;
  }

  .preview-metrics {
    padding-bottom: @spacing-sm;
  }

  .metric-row {
    padding: 0 @spacing-md @spacing-md;
  }

  .metric-copy {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-xs;
    color: rgba(255, 255, 255, 0.72);
    font-size: @font-size-xs;

    strong {
      color: @text-color-primary;
      font-family: @font-family-mono;
      font-size: @font-size-xs;
    }
  }

  .metric-track {
    height: 7px;
    overflow: hidden;
    border-radius: @border-radius-sm;
    background: rgba(255, 255, 255, 0.1);
  }

  .metric-fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #8fe8d4, @accent-color);
  }

  // Section 通用样式
  .section-title {
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    text-align: center;
    margin-bottom: @spacing-sm;
  }

  .section-subtitle {
    font-size: @font-size-lg;
    color: @text-color-light-secondary;
    text-align: center;
    margin-bottom: @spacing-xl;
  }

  // Scenarios Section
  .scenarios-section {
    padding: @spacing-xxl 0;
    background: @bg-light;
  }

  .workflow-flow {
    display: flex;
    align-items: stretch;
    justify-content: center;
    gap: @spacing-sm;
    flex-wrap: wrap;
  }

  .workflow-entry {
    display: flex;
    justify-content: center;
    margin-bottom: @spacing-xl;
  }

  .workflow-step {
    .card();
    text-align: center;
    width: 210px;
    min-height: 240px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    position: relative;

    @media (max-width: @screen-lg) {
      width: calc(50% - @spacing-lg);
    }

    @media (max-width: @screen-sm) {
      width: 100%;
      min-height: auto;
    }
  }

  .workflow-icon {
    width: 72px;
    height: 72px;
    border-radius: @border-radius-round;
    background: @accent-color-light;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 30px;
    color: @accent-color;
    margin-bottom: @spacing-md;
  }

  .workflow-index {
    font-size: @font-size-xs;
    font-weight: @font-weight-bold;
    letter-spacing: 0.12em;
    color: @accent-color;
    margin-bottom: @spacing-sm;
  }

  .workflow-title {
    font-size: @font-size-lg;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-sm;
  }

  .workflow-desc {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .workflow-arrow {
    display: flex;
    align-items: center;
    justify-content: center;
    color: @accent-color;
    font-size: 24px;
    min-width: 28px;

    @media (max-width: @screen-sm) {
      transform: rotate(90deg);
      width: 100%;
      min-height: 32px;
    }
  }

  // Features Section
  .features-section {
    padding: @spacing-xxl 0;
    background: @bg-light-secondary;
  }

  .feature-card {
    .card();
    text-align: center;
    height: 100%;

    .feature-icon {
      width: 64px;
      height: 64px;
      border-radius: @border-radius-round;
      background: @accent-color-light;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto @spacing-md;
      font-size: 28px;
      color: @accent-color;
    }

    .feature-title {
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      margin-bottom: @spacing-sm;
    }

    .feature-desc {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
    }
  }

  // CTA Section
  .cta-section {
    .gradient-bg();
    padding: @spacing-xxl 0;
    text-align: center;
  }

  .cta-title {
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    color: @text-color-primary;
    margin-bottom: @spacing-md;
  }

  .cta-description {
    font-size: @font-size-lg;
    color: @text-color-secondary;
    margin-bottom: @spacing-xl;
    max-width: 600px;
    margin-left: auto;
    margin-right: auto;
  }

  // 金色按钮
  .btn-gold {
    background: linear-gradient(135deg, @accent-color 0%, @accent-color-hover 100%);
    border: none;
    color: @bg-dark;
    font-weight: @font-weight-semibold;

    &:hover {
      background: linear-gradient(135deg, @accent-color-hover 0%, @accent-color 100%);
      transform: translateY(-2px);
      box-shadow: @shadow-glow;
    }
  }

  // 动画
  @keyframes fadeInUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
</style>
