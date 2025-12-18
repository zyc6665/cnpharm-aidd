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
        <h2 class="section-title">{{ t('home.scenarios.title') }}</h2>
        <p class="section-subtitle">{{ t('home.scenarios.subtitle') }}</p>
        <a-row :gutter="[24, 24]">
          <a-col v-for="(item, key) in scenarios" :key="key" :xs="24" :sm="12" :lg="6">
            <div class="scenario-card">
              <div class="scenario-icon">
                <component :is="item.icon" />
              </div>
              <h3 class="scenario-title">{{ t(`home.scenarios.items.${key}.title`) }}</h3>
              <p class="scenario-desc">{{ t(`home.scenarios.items.${key}.description`) }}</p>
            </div>
          </a-col>
        </a-row>
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
    ExperimentOutlined,
    NodeIndexOutlined,
    LineChartOutlined,
    EyeOutlined,
    ThunderboltOutlined,
    CloudOutlined,
    ApiOutlined,
    SafetyOutlined
  } from '@ant-design/icons-vue'

  const { t } = useI18n()

  const scenarios = {
    structure: { icon: ExperimentOutlined },
    docking: { icon: NodeIndexOutlined },
    analysis: { icon: LineChartOutlined },
    visualization: { icon: EyeOutlined }
  }

  const features = {
    gpu: { icon: ThunderboltOutlined },
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

  .scenario-card {
    .card();
    text-align: center;
    height: 100%;

    .scenario-icon {
      font-size: 48px;
      color: @accent-color;
      margin-bottom: @spacing-md;
    }

    .scenario-title {
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      margin-bottom: @spacing-sm;
    }

    .scenario-desc {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
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
