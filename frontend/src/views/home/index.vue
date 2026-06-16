<template>
  <div class="home-page">
    <!-- Hero Section -->
    <section class="hero-section">
      <div class="container">
        <div class="hero-panel">
          <div class="hero-panel-shell deck-surface">
            <div class="hero-shell">
              <div class="hero-copy">
                <div class="hero-kicker">
                  <span class="kicker-mark"></span>
                  CPUModel AIDD Workspace
                </div>
                <h1 class="hero-title">{{ t('home.hero.title') }}</h1>
                <p class="hero-subtitle">{{ t('home.hero.subtitle') }}</p>
                <p class="hero-description">{{ t('home.hero.description') }}</p>
                <div class="hero-meta" aria-hidden="true">
                  <div class="hero-meta-item">
                    <span class="hero-meta-label">Research mode</span>
                    <strong>Target to lead</strong>
                  </div>
                  <div class="hero-meta-item">
                    <span class="hero-meta-label">Workspace</span>
                    <strong>Reusable artifacts</strong>
                  </div>
                  <div class="hero-meta-item">
                    <span class="hero-meta-label">Focus</span>
                    <strong>Structures and pathology</strong>
                  </div>
                </div>
                <div class="hero-actions">
                  <router-link to="/tools">
                    <a-button type="primary" size="large" class="btn-panel-primary">
                      {{ t('home.hero.getStarted') }}
                    </a-button>
                  </router-link>
                  <a-button size="large" class="btn-panel-secondary">
                    {{ t('home.hero.learnMore') }}
                  </a-button>
                </div>
              </div>

              <div class="hero-preview" aria-hidden="true">
                <div class="hero-signal-bar">
                  <span class="hero-signal-track hero-signal-primary"></span>
                  <span class="hero-signal-track hero-signal-secondary"></span>
                </div>
                <div class="preview-topbar">
                  <div class="preview-window-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span class="preview-status">LIVE RUN</span>
                </div>

                <div class="hero-preview-stack">
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
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Unified Deck Section -->
    <section class="home-deck-section">
      <div class="container">
        <div ref="deckRevealRef" class="home-deck-shell" :class="{ 'section-visible': isDeckVisible }">
          <div class="deck-section-head" :class="{ 'section-visible': isDeckVisible }">
            <div class="workflow-bridge" aria-hidden="true">
              <span class="workflow-bridge-mark"></span>
              <span class="workflow-bridge-copy">CPUModel AIDD Deck</span>
            </div>

            <h2 class="section-title">{{ t('home.workflow.title') }}</h2>
            <p class="section-subtitle">{{ t('home.workflow.subtitle') }}</p>
          </div>

          <div class="workflow-layer">
            <div class="workflow-shell" :class="{ 'section-visible': isDeckVisible }">
              <div class="workflow-shell-head" :class="{ 'section-visible': isDeckVisible }">
                <div class="workflow-entry">
                  <router-link to="/workflow">
                    <a-button type="primary" size="large" class="btn-panel-primary">
                      {{ t('workflow.entry.home') }}
                    </a-button>
                  </router-link>
                </div>
              </div>

              <div class="workflow-track">
                <template v-for="(item, index) in workflowSteps" :key="item.key">
                  <article
                    class="workflow-step-card"
                    :class="{ 'section-visible': isDeckVisible }"
                    :style="{ '--reveal-delay': `${140 + index * 90}ms` }"
                  >
                    <span class="workflow-step-glow" aria-hidden="true"></span>
                    <div class="workflow-step-kicker">0{{ index + 1 }}</div>
                    <div class="workflow-step-copy">
                      <div class="workflow-icon">
                        <component :is="item.icon" />
                      </div>
                      <h3 class="workflow-title">{{ t(`home.workflow.items.${item.key}.title`) }}</h3>
                      <p class="workflow-desc">{{ t(`home.workflow.items.${item.key}.description`) }}</p>
                    </div>
                  </article>

                  <div
                    v-if="index < workflowSteps.length - 1"
                    class="workflow-connector"
                    :class="{ 'section-visible': isDeckVisible }"
                    :style="{ '--reveal-delay': `${180 + index * 90}ms` }"
                    aria-hidden="true"
                  >
                    <span class="workflow-connector-line"></span>
                    <RightOutlined />
                    <span class="workflow-connector-line"></span>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <div class="deck-bridge" :class="{ 'section-visible': isDeckVisible }" :style="{ '--reveal-delay': '520ms' }">
            <span class="deck-panel-divider" aria-hidden="true"></span>
            <p class="deck-bridge-copy">{{ t('home.foundation.subtitle') }}</p>
            <span class="deck-panel-divider" aria-hidden="true"></span>
          </div>

          <div class="platform-layer">
            <div class="foundation-head" :class="{ 'section-visible': isDeckVisible }">
              <h2 class="section-title">{{ t('home.foundation.title') }}</h2>
            </div>

            <div
              class="foundation-shell"
              :class="{ 'section-visible': isDeckVisible }"
              :style="{ '--reveal-delay': '620ms' }"
            >
              <div class="foundation-grid">
                <article
                  class="foundation-panel foundation-panel-paiwsit"
                  :class="{ 'section-visible': isDeckVisible }"
                  :style="{ '--reveal-delay': '720ms' }"
                >
                  <div class="foundation-card-head">
                    <div class="foundation-kicker">{{ t('home.foundation.paiwsit.kicker') }}</div>
                    <h3 class="foundation-title">{{ t('home.foundation.paiwsit.title') }}</h3>
                    <p class="foundation-card-tagline">{{ t('home.foundation.paiwsit.kicker') }}</p>
                    <p class="foundation-description">{{ t('home.foundation.paiwsit.description') }}</p>
                  </div>

                  <ul class="foundation-points">
                    <li v-for="(pointKey, index) in foundationPaiwsitPoints" :key="pointKey" class="foundation-point">
                      <span class="foundation-point-index">0{{ index + 1 }}</span>
                      <span class="foundation-point-copy">{{ t(`home.foundation.paiwsit.points.${pointKey}`) }}</span>
                    </li>
                  </ul>

                  <div class="foundation-card-footer">
                    <div class="foundation-actions">
                      <a
                        href="http://www.paiwsit.com/"
                        target="_blank"
                        rel="noreferrer"
                        class="foundation-link"
                      >
                        <a-button type="primary" size="large" class="btn-panel-primary">
                          {{ t('home.foundation.paiwsit.action') }}
                        </a-button>
                      </a>
                    </div>
                  </div>
                </article>

                <article
                  class="foundation-panel foundation-panel-cpupdb"
                  :class="{ 'section-visible': isDeckVisible }"
                  :style="{ '--reveal-delay': '810ms' }"
                >
                  <div class="foundation-card-head">
                    <div class="foundation-kicker">{{ t('home.foundation.cpupdb.kicker') }}</div>
                    <h3 class="foundation-title">{{ t('home.foundation.cpupdb.title') }}</h3>
                    <p class="foundation-card-tagline">{{ t('home.foundation.cpupdb.kicker') }}</p>
                    <p class="foundation-description">{{ t('home.foundation.cpupdb.description') }}</p>
                  </div>

                  <ul class="foundation-points">
                    <li v-for="(pointKey, index) in foundationCpupdbPoints" :key="pointKey" class="foundation-point">
                      <span class="foundation-point-index">0{{ index + 1 }}</span>
                      <span class="foundation-point-copy">{{ t(`home.foundation.cpupdb.points.${pointKey}`) }}</span>
                    </li>
                  </ul>

                  <div class="foundation-card-footer">
                    <div class="foundation-actions">
                      <a
                        href="https://www.cpupdb.com"
                        target="_blank"
                        rel="noreferrer"
                        class="foundation-link"
                      >
                        <a-button size="large" class="btn-outline-light">
                          {{ t('home.foundation.cpupdb.action') }}
                        </a-button>
                      </a>
                      <a
                        href="https://www.cpupdb.com/help.html"
                        target="_blank"
                        rel="noreferrer"
                        class="foundation-help-link"
                      >
                        {{ t('home.foundation.cpupdb.help') }}
                      </a>
                    </div>
                  </div>
                </article>

                <article
                  class="foundation-panel foundation-panel-platform"
                  :class="{ 'section-visible': isDeckVisible }"
                  :style="{ '--reveal-delay': '900ms' }"
                >
                  <div class="foundation-card-head">
                    <div class="foundation-kicker">{{ t('home.foundation.platform.kicker') }}</div>
                    <h3 class="foundation-title">{{ t('home.foundation.platform.title') }}</h3>
                    <p class="foundation-card-tagline">{{ t('home.foundation.platform.kicker') }}</p>
                    <p class="foundation-description">{{ t('home.foundation.platform.description') }}</p>
                  </div>

                  <ul class="foundation-points">
                    <li v-for="(pointKey, index) in foundationPlatformPoints" :key="pointKey" class="foundation-point">
                      <span class="foundation-point-index">0{{ index + 1 }}</span>
                      <span class="foundation-point-copy">{{ t(`home.foundation.platform.points.${pointKey}`) }}</span>
                    </li>
                  </ul>

                  <div class="foundation-card-footer">
                    <div class="foundation-actions">
                      <router-link to="/workflow">
                        <a-button size="large" class="btn-outline-light">
                          {{ t('home.foundation.platform.action') }}
                        </a-button>
                      </router-link>
                    </div>
                  </div>
                </article>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
      <div class="container">
        <div class="cta-panel">
          <div class="cta-panel-shell deck-surface">
            <h2 class="cta-title">{{ t('home.cta.title') }}</h2>
            <p class="cta-description">{{ t('home.cta.description') }}</p>
            <router-link to="/register">
              <a-button type="primary" size="large" class="btn-panel-primary">
                {{ t('home.cta.button') }}
              </a-button>
            </router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
  import { onBeforeUnmount, onMounted, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import {
    RightOutlined,
    SearchOutlined,
    ExperimentOutlined,
    NodeIndexOutlined,
    LineChartOutlined,
    SafetyOutlined
  } from '@ant-design/icons-vue'

  const { t } = useI18n()
  const deckRevealRef = ref<HTMLElement | null>(null)
  const isDeckVisible = ref(false)

  let revealObserver: IntersectionObserver | null = null

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

  const foundationPaiwsitPoints = ['annotatedSlides', 'aiHeatmap', 'pathologyEvidence']
  const foundationCpupdbPoints = ['structures', 'dynamics', 'analysis']
  const foundationPlatformPoints = ['groupedTools', 'reusableArtifacts', 'chainedWorkflow']

  onMounted(() => {
    if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
      isDeckVisible.value = true
      return
    }

    revealObserver = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return

          if (entry.target === deckRevealRef.value) {
            isDeckVisible.value = true
          }

          revealObserver?.unobserve(entry.target)
        })
      },
      {
        threshold: 0.24,
        rootMargin: '0px 0px -10% 0px'
      }
    )

    if (deckRevealRef.value) {
      revealObserver.observe(deckRevealRef.value)
    }
  })

  onBeforeUnmount(() => {
    revealObserver?.disconnect()
    revealObserver = null
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .home-page {
    min-height: 100vh;
    --deck-stack-gap: @spacing-lg;
  }

  .deck-surface {
    position: relative;
    border: 1px solid rgba(124, 152, 185, 0.2);
    border-radius: 32px;
    background: linear-gradient(145deg, rgba(255, 255, 255, 0.78) 0%, rgba(247, 251, 255, 0.96) 100%);
    box-shadow: 0 24px 72px rgba(18, 38, 63, 0.08);
    backdrop-filter: blur(18px);
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      inset: 0;
      background:
        linear-gradient(130deg, rgba(24, 144, 255, 0.08), transparent 38%, rgba(255, 215, 0, 0.08)),
        repeating-linear-gradient(90deg, rgba(15, 23, 42, 0.025) 0 1px, transparent 1px 92px),
        repeating-linear-gradient(0deg, rgba(15, 23, 42, 0.02) 0 1px, transparent 1px 92px);
      opacity: 0.95;
      pointer-events: none;
    }
  }

  // Hero Section
  .hero-section {
    position: relative;
    padding: 72px 0 @spacing-xxl;
    background:
      radial-gradient(circle at top left, rgba(24, 144, 255, 0.11), transparent 32%),
      radial-gradient(circle at bottom right, rgba(255, 215, 0, 0.08), transparent 30%),
      linear-gradient(180deg, #f4f8fd 0%, #eff5fb 100%);
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      inset: 0;
      background:
        repeating-linear-gradient(90deg, rgba(15, 23, 42, 0.03) 0 1px, transparent 1px 92px),
        repeating-linear-gradient(0deg, rgba(15, 23, 42, 0.025) 0 1px, transparent 1px 92px);
      pointer-events: none;
    }

    @media (max-width: @screen-md) {
      min-height: auto;
      padding: @spacing-xxl 0;
    }
  }

  .hero-panel {
    position: relative;
    z-index: 1;
  }

  .hero-panel-shell {
    padding: @spacing-xl;
  }

  .hero-shell {
    position: relative;
    z-index: 1;
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
    max-width: 540px;
    text-align: left;

    @media (max-width: @screen-lg) {
      max-width: 720px;
    }
  }

  .hero-kicker {
    display: inline-flex;
    align-items: center;
    gap: @spacing-sm;
    margin-bottom: @spacing-lg;
    color: @text-color-light-secondary;
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
    color: @text-color-light-primary;
    margin-bottom: @spacing-md;
    animation: fadeInUp 0.6s ease-out;

    @media (max-width: @screen-md) {
      font-size: @font-size-title;
    }
  }

  .hero-subtitle {
    font-size: @font-size-xxl;
    line-height: @line-height-tight;
    color: #2468a2;
    margin-bottom: @spacing-sm;
    animation: fadeInUp 0.6s ease-out 0.1s both;

    @media (max-width: @screen-md) {
      font-size: @font-size-lg;
    }
  }

  .hero-description {
    max-width: 500px;
    font-size: @font-size-lg;
    line-height: @line-height-loose;
    color: @text-color-light-secondary;
    margin-bottom: @spacing-xl;
    animation: fadeInUp 0.6s ease-out 0.2s both;

    @media (max-width: @screen-md) {
      font-size: @font-size-md;
    }
  }

  .hero-meta {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: @spacing-sm;
    margin-bottom: @spacing-xl;

    @media (max-width: @screen-md) {
      grid-template-columns: 1fr;
    }
  }

  .hero-meta-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 10px 12px;
    border: 1px solid rgba(124, 152, 185, 0.16);
    border-radius: @border-radius-lg;
    background: rgba(255, 255, 255, 0.54);

    strong {
      color: @text-color-light-primary;
      font-size: @font-size-sm;
      font-weight: @font-weight-semibold;
      line-height: 1.4;
    }
  }

  .hero-meta-label {
    color: @text-color-light-tertiary;
    font-family: @font-family-mono;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
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
  }

  .hero-preview {
    width: 100%;
    border: 1px solid rgba(124, 152, 185, 0.18);
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: rgba(237, 244, 252, 0.9);
    box-shadow: 0 28px 80px rgba(18, 38, 63, 0.14);
    backdrop-filter: blur(18px);
    animation: fadeInUp 0.7s ease-out 0.15s both;

    @media (max-width: @screen-sm) {
      padding: @spacing-sm;
    }
  }

  .hero-signal-bar {
    display: flex;
    gap: 8px;
    margin-bottom: @spacing-sm;
  }

  .hero-signal-track {
    display: block;
    height: 4px;
    border-radius: 999px;
  }

  .hero-signal-primary {
    width: 128px;
    background: linear-gradient(90deg, @accent-color, #8fe8d4);
  }

  .hero-signal-secondary {
    width: 72px;
    background: rgba(24, 144, 255, 0.16);
  }

  .hero-preview-stack {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .preview-topbar {
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 @spacing-sm;
    margin-bottom: @spacing-sm;
    color: @text-color-light-secondary;
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
        background: #ff8f8f;
      }

      &:nth-child(2) {
        background: #ffd98c;
      }

      &:nth-child(3) {
        background: #7bd7ac;
      }
    }
  }

  .preview-status {
    color: #8fe8d4;
  }

  .preview-panel {
    border: 1px solid rgba(124, 152, 185, 0.16);
    border-radius: @border-radius-md;
    background: rgba(255, 255, 255, 0.66);
  }

  .preview-panel-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md @spacing-md @spacing-sm;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;

    strong {
      color: @text-color-light-primary;
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
    color: @text-color-light-secondary;
    background: rgba(241, 246, 252, 0.92);

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
    background: rgba(15, 23, 42, 0.16);
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
      linear-gradient(145deg, rgba(143, 232, 212, 0.14), rgba(255, 215, 0, 0.08)),
      repeating-linear-gradient(90deg, rgba(15, 23, 42, 0.04) 0 1px, transparent 1px 38px),
      repeating-linear-gradient(0deg, rgba(15, 23, 42, 0.035) 0 1px, transparent 1px 38px);
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
    color: @text-color-light-secondary;
    font-size: @font-size-xs;

    strong {
      color: @text-color-light-primary;
      font-family: @font-family-mono;
      font-size: @font-size-xs;
    }
  }

  .metric-track {
    height: 7px;
    overflow: hidden;
    border-radius: @border-radius-sm;
    background: rgba(15, 23, 42, 0.08);
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

  // Unified Deck Section
  .home-deck-section {
    position: relative;
    padding: @spacing-xxl 0 @spacing-xxl;
    background:
      radial-gradient(circle at top left, rgba(24, 144, 255, 0.11), transparent 32%),
      radial-gradient(circle at bottom right, rgba(255, 215, 0, 0.08), transparent 30%),
      linear-gradient(180deg, #f4f8fd 0%, #eff5fb 100%);
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      inset: 0;
      background:
        repeating-linear-gradient(90deg, rgba(15, 23, 42, 0.03) 0 1px, transparent 1px 92px),
        repeating-linear-gradient(0deg, rgba(15, 23, 42, 0.025) 0 1px, transparent 1px 92px);
      pointer-events: none;
    }
  }

  .home-deck-section .container {
    max-width: 1480px;
  }

  .home-deck-shell {
    padding: @spacing-xl;
    border-radius: 34px;
  }

  .deck-section-head,
  .workflow-layer,
  .platform-layer,
  .deck-bridge,
  .workflow-shell {
    position: relative;
    z-index: 1;
  }

  .deck-section-head {
    --reveal-delay: 30ms;
    margin-bottom: @spacing-xl;
    text-align: center;
  }

  .workflow-layer {
    --reveal-delay: 90ms;
  }

  .platform-layer {
    --reveal-delay: 580ms;
  }

  .home-deck-shell,
  .deck-section-head,
  .workflow-layer,
  .deck-bridge,
  .platform-layer,
  .workflow-shell,
  .workflow-shell-head,
  .workflow-step-card,
  .workflow-connector,
  .foundation-head,
  .foundation-shell,
  .foundation-panel {
    opacity: 0;
    transform: translate3d(0, 28px, 0);
    transition:
      opacity 0.72s ease,
      transform 0.72s cubic-bezier(0.22, 1, 0.36, 1),
      box-shadow 0.72s ease;
    transition-delay: var(--reveal-delay, 0ms);
    will-change: opacity, transform;
  }

  .workflow-connector {
    transform: translate3d(0, 18px, 0) scaleX(0.94);
  }

  .home-deck-shell.section-visible,
  .deck-section-head.section-visible,
  .workflow-layer.section-visible,
  .deck-bridge.section-visible,
  .platform-layer.section-visible,
  .workflow-shell.section-visible,
  .workflow-shell-head.section-visible,
  .workflow-step-card.section-visible,
  .workflow-connector.section-visible,
  .foundation-head.section-visible,
  .foundation-shell.section-visible,
  .foundation-panel.section-visible {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }

  .workflow-shell {
    padding: @spacing-lg;
    border: 1px solid rgba(124, 152, 185, 0.16);
    border-radius: 30px;
    background: rgba(255, 255, 255, 0.46);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.48);
  }

  .workflow-shell-head {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: @spacing-lg;
    text-align: center;
  }

  .workflow-bridge {
    display: inline-flex;
    align-items: center;
    gap: @spacing-sm;
    margin-bottom: @spacing-md;
    padding: 7px 14px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.05);
    color: @text-color-light-secondary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .workflow-bridge-mark {
    width: 10px;
    height: 10px;
    border-radius: @border-radius-round;
    background: linear-gradient(135deg, @accent-color, #8fe8d4);
    box-shadow: 0 0 14px rgba(255, 215, 0, 0.42);
  }

  .workflow-track {
    display: flex;
    align-items: stretch;
    justify-content: center;
    gap: 6px;
    flex-wrap: nowrap;

    @media (max-width: 1320px) {
      flex-wrap: wrap;
      gap: @spacing-sm;
    }
  }

  .workflow-entry {
    display: flex;
    justify-content: center;
    margin-top: @spacing-md;
  }

  .workflow-step-card {
    position: relative;
    flex: 1 1 180px;
    max-width: 192px;
    min-height: 264px;
    padding: @spacing-lg;
    border: 1px solid rgba(116, 140, 171, 0.16);
    border-radius: 24px;
    background: rgba(255, 255, 255, 0.74);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.56),
      0 18px 36px rgba(18, 38, 63, 0.08);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    overflow: hidden;
    transition:
      transform @transition-base,
      box-shadow @transition-base,
      border-color @transition-base;

    &:hover {
      transform: translateY(-6px);
      border-color: rgba(255, 215, 0, 0.28);
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.58),
        0 24px 48px rgba(18, 38, 63, 0.12);
    }

    @media (max-width: @screen-sm) {
      max-width: none;
      min-height: auto;
    }
  }

  .workflow-step-glow {
    position: absolute;
    inset: -10% auto auto 50%;
    width: 160px;
    height: 160px;
    border-radius: @border-radius-round;
    background: radial-gradient(circle, rgba(24, 144, 255, 0.13) 0%, rgba(255, 215, 0, 0.08) 48%, transparent 72%);
    transform: translateX(-50%);
    pointer-events: none;
  }

  .workflow-step-kicker,
  .workflow-step-copy {
    position: relative;
    z-index: 1;
  }

  .workflow-step-kicker {
    display: inline-flex;
    width: fit-content;
    padding: 6px 12px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.06);
    color: @accent-color;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    font-weight: @font-weight-bold;
    letter-spacing: 0.08em;
  }

  .workflow-step-copy {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: flex-start;
    justify-content: flex-end;
    gap: @spacing-md;
    text-align: left;
  }

  .workflow-icon {
    width: 68px;
    height: 68px;
    border-radius: 22px;
    background: linear-gradient(145deg, rgba(255, 215, 0, 0.2), rgba(24, 144, 255, 0.12));
    border: 1px solid rgba(255, 255, 255, 0.62);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    color: @accent-color;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.58);
  }

  .workflow-title {
    margin: 0;
    font-size: @font-size-xl;
    font-weight: @font-weight-semibold;
    line-height: @line-height-tight;
    color: @text-color-light-primary;
  }

  .workflow-desc {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-md;
    line-height: @line-height-loose;
  }

  .workflow-connector {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    min-width: 32px;
    color: rgba(24, 144, 255, 0.58);
    font-size: 18px;

    @media (max-width: 1320px) {
      display: none;
    }
  }

  .workflow-connector-line {
    width: 14px;
    height: 1px;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(24, 144, 255, 0.14), rgba(255, 215, 0, 0.6), rgba(143, 232, 212, 0.28));
    box-shadow: 0 0 12px rgba(255, 215, 0, 0.14);
  }

  .workflow-connector.section-visible {
    svg {
      animation: connectorPulse 2.2s ease-in-out infinite;
    }

    .workflow-connector-line {
      animation: connectorGlow 2.2s ease-in-out infinite;
    }
  }

  .deck-bridge {
    display: grid;
    grid-template-columns: minmax(40px, 1fr) auto minmax(40px, 1fr);
    align-items: center;
    gap: @spacing-md;
    margin: @spacing-xl 0;
  }

  .deck-bridge-copy {
    margin: 0;
    max-width: 70ch;
    color: @text-color-light-secondary;
    font-size: @font-size-md;
    line-height: @line-height-loose;
    text-align: center;
  }

  .deck-panel-divider {
    display: block;
    height: 1px;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(24, 144, 255, 0.1), rgba(255, 215, 0, 0.5), rgba(24, 144, 255, 0.1));
  }

  .foundation-shell {
    position: relative;
    padding: @spacing-lg 0 0;
    border: none;
    background: transparent;
    box-shadow: none;
    backdrop-filter: none;
  }

  .foundation-head {
    --reveal-delay: 620ms;
    margin-bottom: @spacing-lg;
    text-align: center;
  }

  .foundation-grid {
    display: grid;
    grid-template-columns: repeat(12, minmax(0, 1fr));
    gap: @spacing-lg;

    @media (max-width: 1280px) {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    @media (max-width: @screen-lg) {
      grid-template-columns: 1fr;
    }
  }

  .foundation-panel {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
    min-height: 100%;
    padding: @spacing-xl;
    border: 1px solid rgba(116, 140, 171, 0.18);
    border-radius: 24px;
    background: rgba(255, 255, 255, 0.7);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      inset: 0;
      opacity: 0.9;
      pointer-events: none;
    }

    @media (min-width: 1281px) {
      grid-column: span 3;
    }
  }

  .foundation-panel-paiwsit {
    @media (min-width: 1281px) {
      grid-column: span 6;
    }
  }

  .foundation-panel-paiwsit::before {
    background:
      radial-gradient(circle at top left, rgba(179, 38, 30, 0.16), transparent 34%),
      linear-gradient(135deg, rgba(190, 74, 47, 0.18), transparent 42%, rgba(255, 215, 0, 0.1));
  }

  .foundation-panel-platform::before {
    background: linear-gradient(135deg, rgba(24, 144, 255, 0.12), transparent 42%, rgba(143, 232, 212, 0.1));
  }

  .foundation-panel-cpupdb::before {
    background: linear-gradient(135deg, rgba(255, 215, 0, 0.12), transparent 38%, rgba(24, 144, 255, 0.08));
  }

  .foundation-kicker,
  .foundation-card-head,
  .foundation-card-footer,
  .foundation-card-tagline,
  .foundation-title,
  .foundation-description,
  .foundation-actions,
  .foundation-points {
    position: relative;
    z-index: 1;
  }

  .foundation-kicker {
    display: inline-flex;
    width: fit-content;
    padding: 6px 12px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.06);
    color: @text-color-light-secondary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .foundation-title {
    margin: 0;
    color: @text-color-light-primary;
    font-size: @font-size-xxl;
    font-weight: @font-weight-bold;
    line-height: @line-height-tight;
  }

  .foundation-card-head {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .foundation-card-tagline {
    margin: -2px 0 0;
    color: #2468a2;
    font-family: @font-family-mono;
    font-size: 11px;
    font-weight: @font-weight-semibold;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .foundation-description {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-md;
    line-height: @line-height-loose;
    max-width: 42ch;
  }

  .foundation-panel-paiwsit .foundation-description {
    max-width: 58ch;
  }

  .foundation-points {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .foundation-point {
    display: grid;
    grid-template-columns: 46px minmax(0, 1fr);
    gap: @spacing-md;
    align-items: start;
    padding: @spacing-md;
    border: 1px solid rgba(130, 154, 182, 0.16);
    border-radius: @border-radius-lg;
    background: rgba(255, 255, 255, 0.74);
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;

    &:hover {
      transform: translateY(-2px);
      border-color: rgba(24, 144, 255, 0.24);
      box-shadow: 0 12px 28px rgba(18, 38, 63, 0.08);
    }
  }

  .foundation-point-index {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 46px;
    height: 46px;
    border-radius: @border-radius-round;
    background: linear-gradient(135deg, rgba(24, 144, 255, 0.14), rgba(255, 215, 0, 0.16));
    color: @text-color-light-primary;
    font-family: @font-family-mono;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
  }

  .foundation-point-copy {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    line-height: @line-height-loose;
  }

  .foundation-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-md;
    margin-top: auto;
    padding-top: @spacing-sm;
  }

  .foundation-card-footer {
    margin-top: auto;
  }

  .foundation-link {
    display: inline-flex;
  }

  .foundation-help-link {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    text-decoration: none;

    &:hover {
      color: @accent-color;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .workflow-shell,
    .deck-section-head,
    .workflow-layer,
    .deck-bridge,
    .platform-layer,
    .workflow-shell-head,
    .workflow-step-card,
    .workflow-connector,
    .foundation-head,
    .foundation-shell,
    .foundation-panel {
      opacity: 1 !important;
      transform: none !important;
      transition: none !important;
      animation: none !important;
    }
  }

  // CTA Section
  .cta-section {
    position: relative;
    padding: 0 0 @spacing-xxl;
    background:
      radial-gradient(circle at top left, rgba(24, 144, 255, 0.11), transparent 32%),
      radial-gradient(circle at bottom right, rgba(255, 215, 0, 0.08), transparent 30%),
      linear-gradient(180deg, #eff5fb 0%, #f6fbff 100%);
    text-align: center;
  }

  .cta-panel {
    position: relative;
    z-index: 1;
  }

  .cta-panel-shell {
    padding: @spacing-xxl @spacing-xl;
  }

  .cta-title {
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    color: @text-color-light-primary;
    margin-bottom: @spacing-md;
  }

  .cta-description {
    font-size: @font-size-lg;
    color: @text-color-light-secondary;
    margin-bottom: @spacing-xl;
    max-width: 600px;
    margin-left: auto;
    margin-right: auto;
  }

  .btn-panel-primary {
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

  .btn-panel-secondary,
  .btn-outline-light {
    border: 1px solid rgba(24, 144, 255, 0.28);
    background: rgba(255, 255, 255, 0.8);
    color: @text-color-light-primary;
    font-weight: @font-weight-semibold;

    &:hover {
      border-color: @accent-color;
      color: @accent-color;
      background: rgba(255, 255, 255, 0.96);
      transform: translateY(-2px);
    }
  }

  .hero-section,
  .home-deck-section,
  .cta-section {
    .btn-panel-primary {
      box-shadow: 0 14px 28px rgba(255, 215, 0, 0.16);

      &:hover {
        box-shadow: 0 18px 34px rgba(255, 215, 0, 0.22);
      }
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

  @keyframes connectorPulse {
    0%,
    100% {
      opacity: 0.54;
      transform: translateY(0);
    }

    50% {
      opacity: 1;
      transform: translateY(-2px);
    }
  }

  @keyframes connectorGlow {
    0%,
    100% {
      opacity: 0.5;
      box-shadow: 0 0 12px rgba(255, 215, 0, 0.12);
    }

    50% {
      opacity: 1;
      box-shadow: 0 0 18px rgba(255, 215, 0, 0.24);
    }
  }
</style>
