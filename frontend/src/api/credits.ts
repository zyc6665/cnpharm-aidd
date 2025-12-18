import { get, post } from './request'
import type { ApiResponse } from '@/types/api'
import type { CreditTransaction, CreditPackage, MembershipInfo, PaginatedResponse, PaginationParams, SignInInfo } from '@/types/models'

// 获取积分交易记录
export const getTransactions = (params?: PaginationParams & Record<string, unknown>): Promise<ApiResponse<PaginatedResponse<CreditTransaction>>> => {
  return get<PaginatedResponse<CreditTransaction>>('/credits/transactions', params as Record<string, unknown>)
}

// 获取积分套餐列表
export const getPackages = (): Promise<ApiResponse<CreditPackage[]>> => {
  return get<CreditPackage[]>('/credits/packages')
}

// 创建充值订单
export const createRechargeOrder = (packageId: string): Promise<ApiResponse<{
  order_id: string
  amount: number
  payment_url: string
}>> => {
  return post<{ order_id: string; amount: number; payment_url: string }>('/credits/recharge', { package_id: packageId })
}

// 获取会员计划列表
export const getMembershipPlans = (): Promise<ApiResponse<MembershipInfo[]>> => {
  return get<MembershipInfo[]>('/membership/plans')
}

// 创建会员订单
export const createMembershipOrder = (planId: string): Promise<ApiResponse<{
  order_id: string
  amount: number
  payment_url: string
}>> => {
  return post<{ order_id: string; amount: number; payment_url: string }>('/membership/subscribe', { plan_id: planId })
}

// 获取当前会员信息
export const getCurrentMembership = (): Promise<ApiResponse<{
  plan: string
  expire_at: string
  auto_renew: boolean
}>> => {
  return get<{ plan: string; expire_at: string; auto_renew: boolean }>('/membership/current')
}

// 取消自动续费
export const cancelAutoRenew = (): Promise<ApiResponse<null>> => {
  return post<null>('/membership/cancel-auto-renew')
}

// 查询订单状态
export const getOrderStatus = (orderId: string): Promise<ApiResponse<{
  order_id: string
  status: 'pending' | 'paid' | 'failed' | 'canceled'
  amount: number
  created_at: string
}>> => {
  return get<{ order_id: string; status: 'pending' | 'paid' | 'failed' | 'canceled'; amount: number; created_at: string }>(`/orders/${orderId}`)
}

// 每日签到
export const signIn = (): Promise<ApiResponse<SignInInfo>> => {
  return post<SignInInfo>('/credits/signin')
}

// 获取签到信息
export const getSignInInfo = (): Promise<ApiResponse<SignInInfo>> => {
  return get<SignInInfo>('/credits/signin/info')
}
