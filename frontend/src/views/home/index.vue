<template>
  <div class="home-page">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-container">
        <div class="hero-badge">
          <span class="badge-dot"></span>
          {{ t('home.badge') }}
        </div>
        <h1 class="hero-title">{{ t('home.hero.title') }}</h1>
        <p class="hero-subtitle">{{ t('home.hero.description') }}</p>
        <div class="hero-actions">
          <a-button type="primary" size="large" @click="$router.push('/login')">
            {{ t('home.hero.cta') }}
          </a-button>
          <a-button size="large" class="btn-ghost" @click="$router.push('/tools')">
            {{ t('home.hero.secondary') }}
          </a-button>
        </div>
      </div>

      <!-- 产品预览面板（真实组件渲染，非 CSS mockup） -->
      <div class="hero-preview">
        <div class="preview-window">
          <div class="preview-chrome">
            <div class="chrome-dots"><span></span><span></span><span></span></div>
            <span class="chrome-title">{{ PLATFORM_SHORT_NAME }} Workspace</span>
          </div>
          <div class="preview-body">
            <div class="preview-sidebar">
              <div class="preview-logo"></div>
              <div class="preview-nav-item active"></div>
              <div class="preview-nav-item"></div>
              <div class="preview-nav-item"></div>
              <div class="preview-nav-item"></div>
            </div>
            <div class="preview-content">
              <div class="preview-card" v-for="i in 3" :key="i">
                <div class="preview-card-line w-60"></div>
                <div class="preview-card-line w-40"></div>
                <div class="preview-card-line w-80 mt-8"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="preview-window preview-window-offset">
          <div class="preview-chrome">
            <div class="chrome-dots"><span></span><span></span><span></span></div>
            <span class="chrome-title">Molecular Viewer — Binding Pose Analysis</span>
          </div>
          <div class="preview-body preview-molecule">
            <div class="mol-scaffold">
              <div class="mol-ring"></div>
              <div class="mol-bond b1"></div>
              <div class="mol-bond b2"></div>
              <div class="mol-bond b3"></div>
              <div class="mol-atom a1"></div>
              <div class="mol-atom a2"></div>
              <div class="mol-atom a3"></div>
              <div class="mol-pocket"></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 价值主张 -->
    <section class="values">
      <div class="values-grid">
        <article v-for="v in values" :key="v.key" class="value-card">
          <component :is="v.icon" class="value-icon" />
          <h3>{{ t(`home.values.${v.key}.title`) }}</h3>
          <p>{{ t(`home.values.${v.key}.desc`) }}</p>
        </article>
      </div>
    </section>

    <!-- 工作流能力 -->
    <section class="capabilities">
      <div class="section-head">
        <h2 class="section-title">{{ t('home.capabilities.title') }}</h2>
        <p class="section-desc">{{ t('home.capabilities.subtitle') }}</p>
      </div>
      <div class="capabilities-track">
        <div
          v-for="(step, i) in workflowSteps"
          :key="step.key"
          class="cap-step"
        >
          <div class="cap-step-icon">
            <component :is="step.icon" />
          </div>
          <strong>{{ t(`home.workflow.items.${step.key}.title`) }}</strong>
          <p>{{ t(`home.workflow.items.${step.key}.description`) }}</p>
          <span v-if="i < workflowSteps.length - 1" class="cap-connector" aria-hidden="true"></span>
        </div>
      </div>
    </section>

    <!-- 平台数字 -->
    <section class="platform">
      <div class="platform-grid">
        <div class="platform-panel">
          <h2 class="platform-title">{{ t('home.platform.title') }}</h2>
          <p class="platform-desc">{{ t('home.platform.desc') }}</p>
          <div class="platform-links">
            <router-link to="/login">
              <a-button type="primary" size="large">{{ t('home.platform.cta') }}</a-button>
            </router-link>
          </div>
        </div>
      </div>
    </section>

    <!-- Footer CTA -->
    <section class="cta">
      <h2 class="cta-title">{{ t('home.cta.title') }}</h2>
      <p class="cta-desc">{{ t('home.cta.description') }}</p>
      <router-link to="/login">
        <a-button type="primary" size="large">{{ t('home.cta.button') }}</a-button>
      </router-link>
    </section>

    <!-- Footer -->
    <footer class="footer">
      <div class="footer-inner">
        <span class="footer-brand">{{ PLATFORM_NAME }}</span>
        <nav class="footer-nav">
          <router-link to="/tools">{{ t('nav.tools') }}</router-link>
          <router-link to="/workflow">{{ t('nav.workflow') }}</router-link>
          <router-link to="/login">{{ t('nav.login') }}</router-link>
        </nav>
        <span class="footer-copy">{{ buildCopyright(year) }}</span>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { buildCopyright, PLATFORM_NAME, PLATFORM_SHORT_NAME } from '@/config/brand'
import {
  ApartmentOutlined,
  SyncOutlined,
  SafetyOutlined,
  SearchOutlined,
  ExperimentOutlined,
  NodeIndexOutlined,
  LineChartOutlined,
} from '@ant-design/icons-vue'

const { t } = useI18n()
const year = new Date().getFullYear()

const workflowSteps = [
  { key: 'pocketExploration', icon: SearchOutlined },
  { key: 'moleculeGenerationOrVirtualScreening', icon: ExperimentOutlined },
  { key: 'molecularDockingAndAffinityPrediction', icon: NodeIndexOutlined },
  { key: 'propertyPrediction', icon: LineChartOutlined },
  { key: 'leadOptimization', icon: SafetyOutlined },
]

const values = [
  { key: 'reproducible', icon: SyncOutlined },
  { key: 'composable', icon: ApartmentOutlined },
  { key: 'trusted', icon: SafetyOutlined },
]
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

// ── 全局 ──
.home-page {
  background: @bg-body;
  color: @text-primary;
  overflow-x: hidden;
}

// ── Hero ──
.hero {
  position: relative;
  padding: 120px @spacing-lg @spacing-xxl;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: @spacing-xxl;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 800px;
    height: 600px;
    background: radial-gradient(ellipse at center, @accent-color-light 0%, transparent 70%);
    pointer-events: none;
  }
}

.hero-container {
  position: relative;
  z-index: 1;
  text-align: center;
  max-width: 640px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: @spacing-sm;
  padding: 4px 12px;
  border-radius: 999px;
  background: @bg-elevated;
  border: 1px solid @border-color;
  color: @text-secondary;
  font-size: @font-size-xs;
  font-weight: @font-weight-medium;
  margin-bottom: @spacing-lg;
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: @border-radius-round;
  background: @success-color;
}

.hero-title {
  font-size: clamp(2.5rem, 5vw, 4rem);
  font-weight: @font-weight-bold;
  line-height: 1.08;
  letter-spacing: -0.03em;
  color: @text-primary;
  margin: 0 0 @spacing-md;
  text-wrap: balance;
}

.hero-subtitle {
  font-size: @font-size-lg;
  line-height: @line-height-loose;
  color: @text-secondary;
  max-width: 480px;
  margin: 0 auto @spacing-xl;
  text-wrap: pretty;
}

.hero-actions {
  display: flex;
  gap: @spacing-md;
  justify-content: center;
  flex-wrap: wrap;
}

.btn-ghost {
  background: transparent;
  border: 1px solid @border-color-hover;
  color: @text-secondary;

  &:hover {
    border-color: @accent-color-border;
    color: @text-primary;
  }
}

// ── 预览窗口 ──
.hero-preview {
  position: relative;
  z-index: 1;
  display: flex;
  gap: @spacing-lg;
  align-items: flex-start;
  max-width: 960px;
  width: 100%;

  @media (max-width: @screen-md) {
    flex-direction: column;
  }
}

.preview-window {
  flex: 1;
  border-radius: @border-radius-xl;
  overflow: hidden;
  border: 1px solid @border-color;
  box-shadow: @shadow-xl;
  background: @bg-surface;
}

.preview-window-offset {
  margin-top: 40px;

  @media (max-width: @screen-md) {
    margin-top: 0;
  }
}

.preview-chrome {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-sm @spacing-md;
  background: @bg-elevated;
  border-bottom: 1px solid @border-color;
}

.chrome-dots {
  display: flex;
  gap: 6px;

  span {
    width: 10px;
    height: 10px;
    border-radius: @border-radius-round;
    background: @text-disabled;

    // 三个圆点是模仿窗口控制按钮的装饰，红黄绿本身就是它的语义，
    // 不跟随主题改色（浅色主题下也应保持这三个固定色）。
    &:nth-child(1) { background: @error-color; }
    &:nth-child(2) { background: @warning-color; }
    &:nth-child(3) { background: @success-color; }
  }
}

.chrome-title {
  font-size: @font-size-xs;
  color: @text-tertiary;
  font-family: @font-family;
}

.preview-body {
  display: flex;
  min-height: 200px;
  padding: @spacing-sm;
  gap: @spacing-sm;
}

.preview-sidebar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 40px;
  flex-shrink: 0;
  padding: @spacing-xs 4px;
  background: @bg-elevated;
  border-radius: @border-radius-md;
}

.preview-logo {
  width: 20px;
  height: 20px;
  border-radius: @border-radius-sm;
  background: @accent-color;
  margin-bottom: @spacing-sm;
  align-self: center;
}

.preview-nav-item {
  height: 6px;
  width: 100%;
  border-radius: 2px;
  background: @text-disabled;

  &.active {
    background: @accent-color;
  }
}

.preview-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
}

.preview-card {
  padding: @spacing-sm;
  background: @bg-elevated;
  border-radius: @border-radius-md;
  border: 1px solid @border-color;
}

.preview-card-line {
  height: 8px;
  border-radius: 2px;
  background: @text-disabled;
  margin-bottom: 4px;

  &.w-60 { width: 60%; }
  &.w-40 { width: 40%; }
  &.w-80 { width: 80%; }
  &.mt-8 { margin-top: 8px; }
}

// ── 分子预览 ──
.preview-molecule {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 40% 50%, @accent-color-light, transparent 50%),
    @bg-surface;
}

.mol-scaffold {
  position: relative;
  width: 180px;
  height: 180px;
}

.mol-ring {
  position: absolute;
  top: 30px;
  left: 40px;
  width: 100px;
  height: 100px;
  border: 2px solid @accent-color-border;
  border-radius: @border-radius-round;
}

.mol-bond {
  position: absolute;
  height: 2px;
  background: @text-disabled;
  transform-origin: left center;
}

.b1 { top: 80px; left: 140px; width: 40px; transform: rotate(-30deg); }
.b2 { top: 120px; left: 150px; width: 35px; transform: rotate(20deg); }
.b3 { top: 60px; left: 30px; width: 30px; transform: rotate(-45deg); }

.mol-atom {
  position: absolute;
  width: 14px;
  height: 14px;
  border-radius: @border-radius-round;
  background: @accent-color;
  box-shadow: @shadow-glow;
}

.a1 { top: 73px; left: 133px; }
.a2 { top: 110px; left: 155px; }
.a3 { top: 83px; left: 175px; background: @success-color; box-shadow: 0 0 12px @success-color-light; }

.mol-pocket {
  position: absolute;
  top: 20px;
  left: 50px;
  width: 80px;
  height: 80px;
  border: 1px dashed @accent-color-border;
  border-radius: @border-radius-round;
}

// ── 价值主张 ──
.values {
  padding: @spacing-xxl @spacing-lg;
  max-width: @container-xl;
  margin: 0 auto;
}

.values-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: @spacing-lg;

  @media (max-width: @screen-md) {
    grid-template-columns: 1fr;
  }
}

.value-card {
  text-align: center;
  padding: @spacing-xl @spacing-lg;

  h3 {
    font-size: @font-size-lg;
    font-weight: @font-weight-semibold;
    color: @text-primary;
    margin: @spacing-md 0 @spacing-sm;
  }

  p {
    font-size: @font-size-sm;
    color: @text-secondary;
    line-height: @line-height-loose;
    margin: 0;
  }
}

.value-icon {
  font-size: 28px;
  color: @accent-color;
}

// ── 工作流能力 ──
.capabilities {
  padding: @spacing-xxl @spacing-lg;
  max-width: @container-xxl;
  margin: 0 auto;
}

.section-head {
  text-align: center;
  margin-bottom: @spacing-xl;
}

.section-title {
  font-size: @font-size-xxxl;
  font-weight: @font-weight-bold;
  color: @text-primary;
  margin: 0 0 @spacing-sm;
  letter-spacing: -0.02em;
}

.section-desc {
  font-size: @font-size-md;
  color: @text-secondary;
  margin: 0;
}

.capabilities-track {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: @spacing-lg;
  flex-wrap: wrap;
}

.cap-step {
  position: relative;
  flex: 1 1 160px;
  max-width: 200px;
  text-align: center;
  padding: @spacing-lg @spacing-sm;

  strong {
    display: block;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    color: @text-primary;
    margin: @spacing-sm 0;
  }

  p {
    font-size: @font-size-xs;
    color: @text-secondary;
    line-height: @line-height-loose;
    margin: 0;
  }
}

.cap-step-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  background: @accent-color-light;
  border-radius: @border-radius-lg;
  font-size: 22px;
  color: @accent-color;
}

.cap-connector {
  position: absolute;
  top: 24px;
  right: -50%;
  width: 100%;
  height: 1px;
  background: @border-color;

  @media (max-width: @screen-md) {
    display: none;
  }
}

// ── 平台面板 ──
.platform {
  padding: @spacing-xxl @spacing-lg;
}

.platform-grid {
  max-width: @container-lg;
  margin: 0 auto;
}

.platform-panel {
  text-align: center;
  padding: @spacing-xxl;
  background: @bg-elevated;
  border: 1px solid @border-color;
  border-radius: @border-radius-xl;
}

.platform-title {
  font-size: @font-size-xxl;
  font-weight: @font-weight-bold;
  color: @text-primary;
  margin: 0 0 @spacing-sm;
}

.platform-desc {
  font-size: @font-size-md;
  color: @text-secondary;
  max-width: 480px;
  margin: 0 auto @spacing-xl;
}

.platform-links {
  display: flex;
  gap: @spacing-md;
  justify-content: center;
  flex-wrap: wrap;
}

// ── CTA ──
.cta {
  padding: @spacing-xxl @spacing-lg;
  text-align: center;
}

.cta-title {
  font-size: @font-size-xxxl;
  font-weight: @font-weight-bold;
  color: @text-primary;
  margin: 0 0 @spacing-sm;
  letter-spacing: -0.02em;
}

.cta-desc {
  font-size: @font-size-md;
  color: @text-secondary;
  margin: 0 auto @spacing-xl;
  max-width: 480px;
}

// ── Footer ──
.footer {
  padding: @spacing-xl @spacing-lg;
  border-top: 1px solid @border-color;
}

.footer-inner {
  max-width: @container-xxl;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-md;
  flex-wrap: wrap;
}

.footer-brand {
  font-size: @font-size-sm;
  font-weight: @font-weight-semibold;
  color: @text-primary;
}

.footer-nav {
  display: flex;
  gap: @spacing-lg;

  a {
    font-size: @font-size-sm;
    color: @text-secondary;
    text-decoration: none;

    &:hover {
      color: @text-primary;
    }
  }
}

.footer-copy {
  font-size: @font-size-xs;
  color: @text-tertiary;
}

// ── 减动效 ──
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition: none !important;
  }
}
</style>
