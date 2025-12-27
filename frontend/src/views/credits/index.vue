<template>
  <div class="credits-page">
    <div class="container">
      <div class="page-header">
        <h1 class="page-title">{{ t('credits.title') }}</h1>
        <p class="page-subtitle">{{ t('credits.subtitle') }}</p>
      </div>

      <!-- 积分概览卡片 -->
      <div class="credits-overview">
        <a-row :gutter="24">
          <!-- 当前积分 -->
          <a-col :xs="24" :sm="12" :lg="6">
            <div class="overview-card balance">
              <div class="card-icon">
                <WalletOutlined />
              </div>
              <div class="card-content">
                <div class="card-value">{{ userStore.credits }}</div>
                <div class="card-label">{{ t('credits.currentBalance') }}</div>
              </div>
              <a-button type="primary" @click="showRechargeModal = true">
                {{ t('credits.recharge') }}
              </a-button>
            </div>
          </a-col>

          <!-- 今日签到 -->
          <a-col :xs="24" :sm="12" :lg="6">
            <div class="overview-card signin" :class="{ signed: signInInfo?.already_signed }">
              <div class="card-icon">
                <CalendarOutlined />
              </div>
              <div class="card-content">
                <div class="card-value">{{ signInInfo?.signed_days || 0 }}</div>
                <div class="card-label">{{ t('credits.signedDays') }}</div>
              </div>
              <a-button
                type="primary"
                :disabled="signInInfo?.already_signed"
                :loading="signing"
                @click="handleSignIn"
              >
                {{ signInInfo?.already_signed ? t('credits.alreadySigned') : t('credits.signIn') }}
              </a-button>
            </div>
          </a-col>

          <!-- 会员状态 -->
          <a-col :xs="24" :sm="12" :lg="6">
            <div class="overview-card membership" :class="[userStore.role]">
              <div class="card-icon">
                <CrownOutlined />
              </div>
              <div class="card-content">
                <div class="card-value">{{ getMembershipName() }}</div>
                <div class="card-label" v-if="userStore.memberExpireAt">
                  {{ t('credits.expireAt') }}: {{ formatDate(userStore.memberExpireAt) }}
                </div>
                <div class="card-label" v-else>
                  {{ t('credits.upgradeTip') }}
                </div>
              </div>
              <a-button @click="activeTab = 'membership'">
                {{ userStore.role === 'vip' ? t('credits.renew') : t('credits.upgrade') }}
              </a-button>
            </div>
          </a-col>

          <!-- 邀请奖励 -->
          <a-col :xs="24" :sm="12" :lg="6">
            <div class="overview-card invite">
              <div class="card-icon">
                <GiftOutlined />
              </div>
              <div class="card-content">
                <div class="card-value">{{ inviteCount }}</div>
                <div class="card-label">{{ t('credits.invitedUsers') }}</div>
              </div>
              <a-button @click="showInviteModal = true">
                {{ t('credits.inviteFriends') }}
              </a-button>
            </div>
          </a-col>
        </a-row>
      </div>

      <!-- 标签页切换 -->
      <div class="content-tabs">
        <a-tabs v-model:activeKey="activeTab">
          <a-tab-pane key="packages" :tab="t('credits.rechargePackages')">
            <!-- 积分套餐 -->
            <div class="packages-section">
              <a-row :gutter="[24, 24]">
                <a-col v-for="pkg in creditPackages" :key="pkg.id" :xs="24" :sm="12" :lg="6">
                  <div
                    class="package-card"
                    :class="{ recommended: pkg.recommended, selected: selectedPackage?.id === pkg.id }"
                    @click="selectPackage(pkg)"
                  >
                    <div v-if="pkg.recommended" class="recommended-badge">
                      {{ t('credits.recommended') }}
                    </div>
                    <div class="package-credits">
                      <ThunderboltOutlined />
                      <span class="credits-amount">{{ pkg.credits }}</span>
                      <span class="credits-label">{{ t('common.credits') }}</span>
                    </div>
                    <div v-if="pkg.bonus" class="package-bonus">
                      +{{ pkg.bonus }} {{ t('credits.bonus') }}
                    </div>
                    <div class="package-price">
                      <span class="currency">¥</span>
                      <span class="amount">{{ pkg.price }}</span>
                    </div>
                    <div class="package-unit">
                      ≈ ¥{{ (pkg.price / (pkg.credits + (pkg.bonus || 0))).toFixed(3) }}/{{ t('credits.perCredit') }}
                    </div>
                  </div>
                </a-col>
              </a-row>

              <div v-if="selectedPackage" class="checkout-section">
                <div class="checkout-summary">
                  <span>{{ t('credits.selectedPackage') }}:</span>
                  <span class="package-info">
                    {{ selectedPackage.credits }}
                    <span v-if="selectedPackage.bonus"> (+{{ selectedPackage.bonus }})</span>
                    {{ t('common.credits') }}
                  </span>
                  <span class="total-price">¥{{ selectedPackage.price }}</span>
                </div>
                <a-button type="primary" size="large" @click="handlePurchase">
                  {{ t('credits.purchaseNow') }}
                </a-button>
              </div>
            </div>
          </a-tab-pane>

          <a-tab-pane key="membership" :tab="t('credits.membershipPlans')">
            <!-- 会员套餐 -->
            <div class="membership-section">
              <a-row :gutter="[24, 24]">
                <a-col v-for="plan in membershipPlans" :key="plan.id" :xs="24" :sm="12" :lg="6">
                  <div
                    class="membership-card"
                    :class="{ recommended: plan.recommended, current: userStore.role === plan.id }"
                  >
                    <div v-if="plan.recommended" class="recommended-badge">
                      {{ t('credits.bestValue') }}
                    </div>
                    <div v-if="userStore.role === plan.id" class="current-badge">
                      {{ t('credits.currentPlan') }}
                    </div>
                    <h3 class="plan-name">{{ plan.name }}</h3>
                    <div class="plan-price">
                      <span class="currency">¥</span>
                      <span class="amount">{{ plan.price }}</span>
                      <span class="period">/{{ plan.period }}</span>
                    </div>
                    <ul class="plan-features">
                      <li v-for="(feature, idx) in plan.features" :key="idx">
                        <CheckOutlined />
                        {{ feature }}
                      </li>
                    </ul>
                    <div class="plan-credits">
                      <ThunderboltOutlined />
                      {{ plan.credits_monthly }} {{ t('credits.creditsMonthly') }}
                    </div>
                    <div v-if="plan.discount < 1" class="plan-discount">
                      {{ t('credits.toolDiscount') }}: {{ (plan.discount * 100).toFixed(0) }}%
                    </div>
                    <a-button
                      type="primary"
                      block
                      :disabled="userStore.role === plan.id"
                      @click="handleSubscribe(plan)"
                    >
                      {{ userStore.role === plan.id ? t('credits.currentPlan') : t('credits.subscribe') }}
                    </a-button>
                  </div>
                </a-col>
              </a-row>
            </div>
          </a-tab-pane>

          <a-tab-pane key="history" :tab="t('credits.transactionHistory')">
            <!-- 交易记录 -->
            <div class="history-section">
              <div class="history-filters">
                <a-select
                  v-model:value="historyType"
                  :placeholder="t('credits.filterByType')"
                  style="width: 150px"
                  allow-clear
                  @change="fetchTransactions"
                >
                  <a-select-option value="recharge">{{ t('credits.typeRecharge') }}</a-select-option>
                  <a-select-option value="consume">{{ t('credits.typeConsume') }}</a-select-option>
                  <a-select-option value="reward">{{ t('credits.typeReward') }}</a-select-option>
                  <a-select-option value="refund">{{ t('credits.typeRefund') }}</a-select-option>
                  <a-select-option value="signin">{{ t('credits.typeSignin') }}</a-select-option>
                  <a-select-option value="invite">{{ t('credits.typeInvite') }}</a-select-option>
                </a-select>
                <a-range-picker
                  v-model:value="historyDateRange"
                  @change="fetchTransactions"
                />
              </div>

              <a-table
                :columns="transactionColumns"
                :data-source="transactions"
                :loading="transactionsLoading"
                :pagination="pagination"
                @change="handleTableChange"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'type'">
                    <a-tag :color="getTypeColor(record.type)">
                      {{ getTypeName(record.type) }}
                    </a-tag>
                  </template>
                  <template v-if="column.key === 'amount'">
                    <span :class="record.amount > 0 ? 'amount-positive' : 'amount-negative'">
                      {{ record.amount > 0 ? '+' : '' }}{{ record.amount }}
                    </span>
                  </template>
                  <template v-if="column.key === 'created_at'">
                    {{ formatTime(record.created_at) }}
                  </template>
                </template>
              </a-table>
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>

    <!-- 充值弹窗 -->
    <a-modal
      v-model:open="showRechargeModal"
      :title="t('credits.recharge')"
      :footer="null"
      width="600px"
    >
      <div class="recharge-modal">
        <div class="quick-packages">
          <div
            v-for="pkg in creditPackages.slice(0, 4)"
            :key="pkg.id"
            class="quick-package"
            :class="{ selected: quickSelectedPackage?.id === pkg.id }"
            @click="quickSelectedPackage = pkg"
          >
            <div class="pkg-credits">{{ pkg.credits }}</div>
            <div class="pkg-price">¥{{ pkg.price }}</div>
          </div>
        </div>
        <a-divider>{{ t('credits.orCustomAmount') }}</a-divider>
        <a-input-number
          v-model:value="customCredits"
          :min="100"
          :step="100"
          :placeholder="t('credits.customCreditsPlaceholder')"
          style="width: 100%"
        />
        <div class="modal-footer">
          <a-button @click="showRechargeModal = false">{{ t('common.cancel') }}</a-button>
          <a-button type="primary" @click="handleQuickRecharge">
            {{ t('credits.confirmRecharge') }}
          </a-button>
        </div>
      </div>
    </a-modal>

    <!-- 邀请弹窗 -->
    <a-modal
      v-model:open="showInviteModal"
      :title="t('credits.inviteFriends')"
      :footer="null"
      width="500px"
    >
      <div class="invite-modal">
        <div class="invite-code-section">
          <p>{{ t('credits.inviteCodeLabel') }}</p>
          <div class="invite-code">
            <span>{{ userStore.user?.invitation_code || 'N/A' }}</span>
            <a-button type="link" @click="copyInviteCode">
              <CopyOutlined />
            </a-button>
          </div>
        </div>
        <a-divider />
        <div class="invite-rules">
          <h4>{{ t('credits.inviteRules') }}</h4>
          <ul>
            <li>{{ t('credits.inviteRule1') }}</li>
            <li>{{ t('credits.inviteRule2') }}</li>
            <li>{{ t('credits.inviteRule3') }}</li>
          </ul>
        </div>
        <div class="invite-share">
          <p>{{ t('credits.shareLink') }}</p>
          <a-input
            :value="inviteLink"
            readonly
            :addonAfter="null"
          >
            <template #addonAfter>
              <a-button type="link" @click="copyInviteLink">
                <CopyOutlined />
              </a-button>
            </template>
          </a-input>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  WalletOutlined,
  CalendarOutlined,
  CrownOutlined,
  GiftOutlined,
  ThunderboltOutlined,
  CheckOutlined,
  CopyOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import { useUserStore, useCreditsStore } from '@/stores'
import type { CreditPackage, MembershipInfo, CreditTransaction, CreditTransactionType, SignInInfo } from '@/types/models'

const { t } = useI18n()
const userStore = useUserStore()
const creditsStore = useCreditsStore()

// 状态
const activeTab = ref('packages')
const showRechargeModal = ref(false)
const showInviteModal = ref(false)
const signing = ref(false)
const signInInfo = ref<SignInInfo | null>(null)
const inviteCount = ref(0)

// 套餐选择
const selectedPackage = ref<CreditPackage | null>(null)
const quickSelectedPackage = ref<CreditPackage | null>(null)
const customCredits = ref<number | null>(null)

// 交易记录
const historyType = ref<CreditTransactionType | undefined>()
const historyDateRange = ref<[Dayjs, Dayjs] | null>(null)
const transactions = ref<CreditTransaction[]>([])
const transactionsLoading = ref(false)
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})

// 积分套餐数据
const creditPackages = computed<CreditPackage[]>(() => [
  { id: 'pkg-100', name: '体验包', credits: 100, price: 10 },
  { id: 'pkg-500', name: '基础包', credits: 500, price: 45, bonus: 50 },
  { id: 'pkg-1000', name: '标准包', credits: 1000, price: 80, bonus: 150, recommended: true },
  { id: 'pkg-5000', name: '专业包', credits: 5000, price: 350, bonus: 1000 }
])

// 会员套餐数据
const membershipPlans = computed<MembershipInfo[]>(() => [
  {
    id: 'free',
    name: t('credits.planFree'),
    price: 0,
    period: t('credits.forever'),
    features: [
      t('credits.feature1Free'),
      t('credits.feature2Free'),
      t('credits.feature3Free')
    ],
    credits_monthly: 0,
    discount: 1
  },
  {
    id: 'basic',
    name: t('credits.planBasic'),
    price: 29,
    period: t('credits.month'),
    features: [
      t('credits.feature1Basic'),
      t('credits.feature2Basic'),
      t('credits.feature3Basic'),
      t('credits.feature4Basic')
    ],
    credits_monthly: 100,
    discount: 0.95
  },
  {
    id: 'standard',
    name: t('credits.planStandard'),
    price: 99,
    period: t('credits.month'),
    features: [
      t('credits.feature1Standard'),
      t('credits.feature2Standard'),
      t('credits.feature3Standard'),
      t('credits.feature4Standard'),
      t('credits.feature5Standard')
    ],
    credits_monthly: 500,
    discount: 0.85,
    recommended: true
  },
  {
    id: 'premium',
    name: t('credits.planPremium'),
    price: 299,
    period: t('credits.month'),
    features: [
      t('credits.feature1Premium'),
      t('credits.feature2Premium'),
      t('credits.feature3Premium'),
      t('credits.feature4Premium'),
      t('credits.feature5Premium'),
      t('credits.feature6Premium')
    ],
    credits_monthly: 2000,
    discount: 0.7
  }
])

// 交易记录表格列
const transactionColumns = [
  { title: t('credits.transactionType'), dataIndex: 'type', key: 'type' },
  { title: t('credits.transactionAmount'), dataIndex: 'amount', key: 'amount' },
  { title: t('credits.transactionBalance'), dataIndex: 'balance', key: 'balance' },
  { title: t('credits.transactionDesc'), dataIndex: 'description', key: 'description' },
  { title: t('credits.transactionTime'), dataIndex: 'created_at', key: 'created_at' }
]

// 计算属性
const inviteLink = computed(() => {
  const code = userStore.user?.invitation_code
  return code ? `${window.location.origin}/register?invite=${code}` : ''
})

// 方法
const getMembershipName = () => {
  const names: Record<string, string> = {
    guest: t('credits.planGuest'),
    user: t('credits.planFree'),
    vip: t('credits.planVIP'),
    admin: t('credits.planAdmin')
  }
  return names[userStore.role] || t('credits.planFree')
}

const formatDate = (date: string) => {
  return dayjs(date).format('YYYY-MM-DD')
}

const formatTime = (time: string) => {
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

const getTypeColor = (type: CreditTransactionType) => {
  const colors: Record<CreditTransactionType, string> = {
    recharge: 'green',
    consume: 'red',
    reward: 'gold',
    refund: 'blue',
    signup: 'purple',
    signin: 'cyan',
    invite: 'magenta'
  }
  return colors[type]
}

const getTypeName = (type: CreditTransactionType) => {
  const names: Record<CreditTransactionType, string> = {
    recharge: t('credits.typeRecharge'),
    consume: t('credits.typeConsume'),
    reward: t('credits.typeReward'),
    refund: t('credits.typeRefund'),
    signup: t('credits.typeSignup'),
    signin: t('credits.typeSignin'),
    invite: t('credits.typeInvite')
  }
  return names[type]
}

const selectPackage = (pkg: CreditPackage) => {
  selectedPackage.value = pkg
}

const handleSignIn = async () => {
  signing.value = true
  try {
    await creditsStore.signIn()
    signInInfo.value = {
      ...signInInfo.value!,
      already_signed: true,
      signed_days: (signInInfo.value?.signed_days || 0) + 1
    }
    message.success(t('credits.signInSuccess'))
  } finally {
    signing.value = false
  }
}

const handlePurchase = () => {
  if (!selectedPackage.value) return
  message.info(t('credits.paymentRedirect'))
  // TODO: 跳转支付页面
}

const handleSubscribe = (_plan: MembershipInfo) => {
  message.info(t('credits.subscribeRedirect'))
  // TODO: 跳转订阅页面
}

const handleQuickRecharge = () => {
  const pkg = quickSelectedPackage.value
  const custom = customCredits.value
  if (!pkg && !custom) {
    message.warning(t('credits.selectPackageFirst'))
    return
  }
  showRechargeModal.value = false
  message.info(t('credits.paymentRedirect'))
  // TODO: 跳转支付页面
}

const copyInviteCode = async () => {
  const code = userStore.user?.invitation_code
  if (code) {
    await navigator.clipboard.writeText(code)
    message.success(t('common.copySuccess'))
  }
}

const copyInviteLink = async () => {
  if (inviteLink.value) {
    await navigator.clipboard.writeText(inviteLink.value)
    message.success(t('common.copySuccess'))
  }
}

const fetchTransactions = async () => {
  transactionsLoading.value = true
  try {
    const params: Record<string, unknown> = {
      page: pagination.value.current,
      page_size: pagination.value.pageSize
    }
    if (historyType.value) {
      params.type = historyType.value
    }
    if (historyDateRange.value) {
      params.start_date = historyDateRange.value[0].format('YYYY-MM-DD')
      params.end_date = historyDateRange.value[1].format('YYYY-MM-DD')
    }
    const res = await creditsStore.fetchTransactions(params)
    transactions.value = res.items
    pagination.value.total = res.total
  } finally {
    transactionsLoading.value = false
  }
}

const handleTableChange = (pag: { current: number; pageSize: number }) => {
  pagination.value.current = pag.current
  pagination.value.pageSize = pag.pageSize
  fetchTransactions()
}

const fetchSignInInfo = async () => {
  try {
    signInInfo.value = await creditsStore.getSignInInfo()
  } catch {
    // 错误已处理
  }
}

onMounted(() => {
  fetchSignInInfo()
  fetchTransactions()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.credits-page {
  padding: @spacing-xl 0;
  min-height: calc(100vh - @header-height - @footer-height);
}

.page-header {
  text-align: center;
  margin-bottom: @spacing-xl;
}

.page-title {
  font-size: @font-size-xxxl;
  font-weight: @font-weight-bold;
  margin-bottom: @spacing-sm;
}

.page-subtitle {
  color: @text-color-light-secondary;
  font-size: @font-size-lg;
}

// 概览卡片
.credits-overview {
  margin-bottom: @spacing-xl;
}

.overview-card {
  .card();
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: @spacing-md;
  padding: @spacing-lg;
  height: 100%;

  .card-icon {
    font-size: 32px;
    width: 64px;
    height: 64px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  &.balance .card-icon {
    background: @primary-color-light;
    color: @primary-color;
  }

  &.signin .card-icon {
    background: @success-color-light;
    color: @success-color;
  }

  &.signin.signed .card-icon {
    background: @success-color;
    color: #fff;
  }

  &.membership .card-icon {
    background: @warning-color-light;
    color: @warning-color;
  }

  &.membership.vip .card-icon {
    background: linear-gradient(135deg, #ffd700 0%, #ff8c00 100%);
    color: #fff;
  }

  &.invite .card-icon {
    background: @accent-color-light;
    color: @accent-color;
  }

  .card-value {
    font-size: @font-size-xxl;
    font-weight: @font-weight-bold;
    color: @text-color-light;
  }

  .card-label {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }
}

// 内容标签页
.content-tabs {
  .card();
}

// 积分套餐
.package-card {
  .card();
  text-align: center;
  cursor: pointer;
  position: relative;
  transition: all @transition-duration;

  &:hover {
    transform: translateY(-4px);
    border-color: @primary-color;
  }

  &.selected {
    border-color: @primary-color;
    box-shadow: 0 0 0 2px @primary-color-light;
  }

  &.recommended {
    border-color: @warning-color;
  }

  .recommended-badge {
    position: absolute;
    top: -12px;
    right: 12px;
    background: @warning-color;
    color: #fff;
    padding: 2px 12px;
    border-radius: @border-radius-sm;
    font-size: @font-size-sm;
  }

  .package-credits {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: @spacing-xs;
    margin-bottom: @spacing-sm;

    .anticon {
      font-size: 24px;
      color: @warning-color;
    }

    .credits-amount {
      font-size: @font-size-xxl;
      font-weight: @font-weight-bold;
    }

    .credits-label {
      color: @text-color-light-secondary;
    }
  }

  .package-bonus {
    color: @success-color;
    font-size: @font-size-sm;
    margin-bottom: @spacing-sm;
  }

  .package-price {
    margin-bottom: @spacing-xs;

    .currency {
      font-size: @font-size-md;
      color: @error-color;
    }

    .amount {
      font-size: @font-size-xxl;
      font-weight: @font-weight-bold;
      color: @error-color;
    }
  }

  .package-unit {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }
}

.checkout-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: @spacing-xl;
  padding: @spacing-lg;
  background: @bg-color-light;
  border-radius: @border-radius-md;

  .checkout-summary {
    display: flex;
    align-items: center;
    gap: @spacing-md;

    .package-info {
      font-weight: @font-weight-medium;
    }

    .total-price {
      font-size: @font-size-xl;
      font-weight: @font-weight-bold;
      color: @error-color;
    }
  }
}

// 会员套餐
.membership-card {
  .card();
  text-align: center;
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;

  &.recommended {
    border-color: @primary-color;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  }

  &.current {
    border-color: @success-color;
  }

  .recommended-badge,
  .current-badge {
    position: absolute;
    top: -12px;
    right: 12px;
    padding: 2px 12px;
    border-radius: @border-radius-sm;
    font-size: @font-size-sm;
    color: #fff;
  }

  .recommended-badge {
    background: @primary-color;
  }

  .current-badge {
    background: @success-color;
  }

  .plan-name {
    font-size: @font-size-lg;
    font-weight: @font-weight-bold;
    margin-bottom: @spacing-md;
  }

  .plan-price {
    margin-bottom: @spacing-lg;

    .currency {
      font-size: @font-size-md;
    }

    .amount {
      font-size: @font-size-xxxl;
      font-weight: @font-weight-bold;
    }

    .period {
      color: @text-color-light-secondary;
    }
  }

  .plan-features {
    list-style: none;
    padding: 0;
    margin: 0 0 @spacing-lg 0;
    text-align: left;
    flex: 1;

    li {
      padding: @spacing-xs 0;
      display: flex;
      align-items: center;
      gap: @spacing-sm;
      color: @text-color-light-secondary;

      .anticon {
        color: @success-color;
      }
    }
  }

  .plan-credits,
  .plan-discount {
    padding: @spacing-sm;
    background: @bg-color-light;
    border-radius: @border-radius-sm;
    margin-bottom: @spacing-sm;
    font-size: @font-size-sm;

    .anticon {
      color: @warning-color;
      margin-right: @spacing-xs;
    }
  }
}

// 交易记录
.history-section {
  .history-filters {
    display: flex;
    gap: @spacing-md;
    margin-bottom: @spacing-lg;
  }
}

.amount-positive {
  color: @success-color;
  font-weight: @font-weight-medium;
}

.amount-negative {
  color: @error-color;
  font-weight: @font-weight-medium;
}

// 充值弹窗
.recharge-modal {
  .quick-packages {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: @spacing-md;
    margin-bottom: @spacing-lg;
  }

  .quick-package {
    text-align: center;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    cursor: pointer;
    transition: all @transition-duration;

    &:hover,
    &.selected {
      border-color: @primary-color;
      background: @primary-color-light;
    }

    .pkg-credits {
      font-size: @font-size-lg;
      font-weight: @font-weight-bold;
    }

    .pkg-price {
      color: @text-color-light-secondary;
    }
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: @spacing-md;
    margin-top: @spacing-lg;
  }
}

// 邀请弹窗
.invite-modal {
  .invite-code-section {
    text-align: center;

    .invite-code {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: @spacing-sm;
      font-size: @font-size-xxl;
      font-weight: @font-weight-bold;
      color: @primary-color;
      padding: @spacing-md;
      background: @primary-color-light;
      border-radius: @border-radius-md;
    }
  }

  .invite-rules {
    h4 {
      margin-bottom: @spacing-sm;
    }

    ul {
      padding-left: @spacing-lg;
      color: @text-color-light-secondary;

      li {
        margin-bottom: @spacing-xs;
      }
    }
  }

  .invite-share {
    margin-top: @spacing-lg;
  }
}

// 响应式
@media (max-width: @breakpoint-md) {
  .recharge-modal .quick-packages {
    grid-template-columns: repeat(2, 1fr);
  }

  .checkout-section {
    flex-direction: column;
    gap: @spacing-md;
  }
}
</style>
