import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CreditTransaction, CreditPackage, MembershipInfo, PaginatedResponse, SignInInfo } from '@/types/models'
import {
  getTransactions,
  getPackages,
  createRechargeOrder,
  getMembershipPlans,
  createMembershipOrder,
  signIn as apiSignIn,
  getSignInInfo as apiGetSignInInfo
} from '@/api/credits'

export const useCreditsStore = defineStore('credits', () => {
  // State
  const transactions = ref<CreditTransaction[]>([])
  const packages = ref<CreditPackage[]>([])
  const membershipPlans = ref<MembershipInfo[]>([])
  const signInInfo = ref<SignInInfo | null>(null)
  const loading = ref(false)
  const pagination = ref({
    page: 1,
    pageSize: 20,
    total: 0,
    totalPages: 0
  })

  // Getters
  const hasMoreTransactions = computed(() => pagination.value.page < pagination.value.totalPages)

  // Actions
  const fetchTransactions = async (params?: Record<string, unknown>) => {
    loading.value = true
    try {
      const page = (params?.page as number) || 1
      const pageSize = (params?.page_size as number) || 20
      const res = await getTransactions({ ...params, page, page_size: pageSize })
      const data = res.data as PaginatedResponse<CreditTransaction>
      if (page === 1) {
        transactions.value = data.items
      } else {
        transactions.value = [...transactions.value, ...data.items]
      }
      pagination.value = {
        page: data.page,
        pageSize: data.page_size,
        total: data.total,
        totalPages: data.total_pages
      }
      return data
    } finally {
      loading.value = false
    }
  }

  const loadMoreTransactions = async () => {
    if (!hasMoreTransactions.value || loading.value) return
    await fetchTransactions({ page: pagination.value.page + 1, page_size: pagination.value.pageSize })
  }

  const fetchPackages = async () => {
    loading.value = true
    try {
      const res = await getPackages()
      packages.value = res.data
      return res.data
    } finally {
      loading.value = false
    }
  }

  const fetchMembershipPlans = async () => {
    loading.value = true
    try {
      const res = await getMembershipPlans()
      membershipPlans.value = res.data
      return res.data
    } finally {
      loading.value = false
    }
  }

  const purchaseCredits = async (packageId: string) => {
    loading.value = true
    try {
      const res = await createRechargeOrder(packageId)
      return res.data
    } finally {
      loading.value = false
    }
  }

  const upgradeMembership = async (planId: string) => {
    loading.value = true
    try {
      const res = await createMembershipOrder(planId)
      return res.data
    } finally {
      loading.value = false
    }
  }

  const signIn = async () => {
    loading.value = true
    try {
      const res = await apiSignIn()
      signInInfo.value = res.data
      return res.data
    } finally {
      loading.value = false
    }
  }

  const getSignInInfo = async () => {
    try {
      const res = await apiGetSignInInfo()
      signInInfo.value = res.data
      return res.data
    } catch {
      // 静默处理
      return null
    }
  }

  const clearTransactions = () => {
    transactions.value = []
    pagination.value = {
      page: 1,
      pageSize: 20,
      total: 0,
      totalPages: 0
    }
  }

  return {
    // State
    transactions,
    packages,
    membershipPlans,
    signInInfo,
    loading,
    pagination,
    // Getters
    hasMoreTransactions,
    // Actions
    fetchTransactions,
    loadMoreTransactions,
    fetchPackages,
    fetchMembershipPlans,
    purchaseCredits,
    upgradeMembership,
    signIn,
    getSignInInfo,
    clearTransactions
  }
})
