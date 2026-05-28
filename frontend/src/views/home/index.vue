<template>
  <div class="home-page">
    <!-- Hero Section -->
    <section class="hero-section">
      <div class="hero-content">
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
    .gradient-bg();
    min-height: calc(100vh - @header-height);
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: @spacing-xxl @spacing-lg;
  }

  .hero-content {
    max-width: 800px;
  }

  .hero-title {
    font-size: @font-size-hero;
    font-weight: @font-weight-bold;
    color: @accent-color;
    margin-bottom: @spacing-md;
    animation: fadeInUp 0.6s ease-out;

    @media (max-width: @screen-md) {
      font-size: @font-size-title;
    }
  }

  .hero-subtitle {
    font-size: @font-size-xxl;
    color: @text-color-primary;
    margin-bottom: @spacing-sm;
    animation: fadeInUp 0.6s ease-out 0.1s both;

    @media (max-width: @screen-md) {
      font-size: @font-size-lg;
    }
  }

  .hero-description {
    font-size: @font-size-lg;
    color: @text-color-secondary;
    margin-bottom: @spacing-xl;
    animation: fadeInUp 0.6s ease-out 0.2s both;

    @media (max-width: @screen-md) {
      font-size: @font-size-md;
    }
  }

  .hero-actions {
    display: flex;
    gap: @spacing-md;
    justify-content: center;
    animation: fadeInUp 0.6s ease-out 0.3s both;

    .ant-btn-ghost {
      color: @text-color-primary;
      border-color: @text-color-tertiary;

      &:hover {
        color: @accent-color;
        border-color: @accent-color;
      }
    }
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
