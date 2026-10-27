<template>
  <main class="auth-shell">
    <!--
      左侧品牌区。原来是「Docking -9.8 kcal/mol / Screening 2.4k ligands / ADMET Ready」
      的假数据看板——那是产品线的营销稿，摆在内网登录页上既不真实（数据是编的）
      也不承担任何功能。改为陈述平台的三条能力边界，口径取自 docs/01 §2 的建设目标。
    -->
    <section class="auth-shell__brand" aria-hidden="true">
      <div class="auth-shell__brand-head">
        <img src="@/assets/logo.svg" alt="" class="auth-shell__logo" />
        <div>
          <p class="auth-shell__eyebrow">{{ PLATFORM_EYEBROW }}</p>
          <h2 class="auth-shell__brand-mark">{{ PLATFORM_NAME }}</h2>
        </div>
      </div>

      <ul class="auth-shell__highlights">
        <li v-for="item in highlights" :key="item.title" class="highlight-row">
          <span class="highlight-index">{{ item.index }}</span>
          <div>
            <strong>{{ item.title }}</strong>
            <p>{{ item.description }}</p>
          </div>
        </li>
      </ul>

      <p class="auth-shell__notice">
        本平台部署于中国医药内网，全部计算在本地算力节点执行，不产生任何外部网络调用。
      </p>
    </section>

    <section class="auth-shell__card" aria-labelledby="auth-shell-title">
      <div class="auth-shell__heading">
        <p class="auth-shell__eyebrow">{{ PLATFORM_SHORT_NAME }}</p>
        <h1 id="auth-shell-title" class="auth-shell__title">{{ title }}</h1>
        <p v-if="description" class="auth-shell__description">{{ description }}</p>
      </div>
      <slot />
    </section>
  </main>
</template>

<script setup lang="ts">
  import { PLATFORM_EYEBROW, PLATFORM_NAME, PLATFORM_SHORT_NAME } from '@/config/brand'

  defineProps<{
    title: string
    description?: string
  }>()

  // 三条能力陈述，全部对应 docs/01 §2 的建设目标，不是宣传语。
  const highlights = [
    {
      index: '01',
      title: '对象化研发主线',
      description: '靶点 → 结构 → 口袋 → 候选物 → 任务 → 结果，同一项目内串成一条可回溯的链路。',
    },
    {
      index: '02',
      title: '结果可追溯',
      description: '每次执行固化输入快照、执行环境、运行参数、输出产物与归属关系，可一键导出追溯包。',
    },
    {
      index: '03',
      title: '算力统一调度',
      description: 'DCU 与 CPU 任务统一排队，按项目配额准入，卡位与镜像随部署版本一同纳管。',
    },
  ]
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .auth-shell {
    min-height: 100vh;
    display: grid;
    grid-template-columns: minmax(360px, 1fr) minmax(360px, 480px);
    align-items: center;
    justify-content: center;
    gap: @spacing-xxl;
    padding: @spacing-xxl @spacing-xl;
    background:
      radial-gradient(circle at 18% 22%, rgba(59, 130, 246, 0.16), transparent 55%),
      linear-gradient(135deg, #07080f 0%, #0d1420 55%, #0a0d16 100%);
  }

  .auth-shell__brand {
    width: min(560px, 100%);
    color: @text-color-primary;
  }

  .auth-shell__brand-head {
    display: flex;
    align-items: center;
    gap: @spacing-md;
    margin-bottom: @spacing-xl;
  }

  .auth-shell__logo {
    width: 52px;
    height: 52px;
    flex: 0 0 52px;
  }

  .auth-shell__brand-mark {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-title;
    font-weight: @font-weight-bold;
    line-height: @line-height-tight;
    letter-spacing: 0.01em;
  }

  .auth-shell__highlights {
    display: grid;
    gap: @spacing-md;
    max-width: 520px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .highlight-row {
    display: grid;
    grid-template-columns: 40px 1fr;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: @border-radius-lg;
    background: rgba(255, 255, 255, 0.03);

    strong {
      display: block;
      margin-bottom: 2px;
      color: @text-primary;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
    }

    p {
      margin: 0;
      color: rgba(203, 213, 225, 0.78);
      font-size: @font-size-sm;
      line-height: @line-height-base;
    }
  }

  .highlight-index {
    color: @accent-color-hover;
    font-family: @font-family-mono;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
    letter-spacing: 0.08em;
  }

  .auth-shell__notice {
    max-width: 520px;
    margin: @spacing-lg 0 0;
    padding-left: @spacing-md;
    border-left: 2px solid rgba(59, 130, 246, 0.4);
    color: rgba(148, 163, 184, 0.9);
    font-size: @font-size-xs;
    line-height: @line-height-loose;
  }

  .auth-shell__card {
    width: min(100%, 480px);
    padding: @spacing-xl;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-lg;
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
    letter-spacing: 0.06em;
  }

  .auth-shell__title {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-xxl;
    font-weight: @font-weight-bold;
    line-height: @line-height-tight;
  }

  .auth-shell__description {
    margin: @spacing-sm 0 0;
    color: @text-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  @media (max-width: @screen-lg) {
    .auth-shell {
      grid-template-columns: minmax(0, 480px);
      gap: @spacing-xl;
      padding: @spacing-xl @spacing-lg;
    }

    .auth-shell__brand {
      width: 100%;
    }

    .auth-shell__brand-mark {
      font-size: @font-size-xl;
    }

    .auth-shell__logo {
      width: 40px;
      height: 40px;
      flex-basis: 40px;
    }

    .auth-shell__highlights {
      display: none;
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
      font-size: @font-size-xl;
    }
  }
</style>
