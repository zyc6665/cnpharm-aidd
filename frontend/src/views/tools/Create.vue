<template>
  <div class="tool-create-page">
    <div class="container">
      <AppPageHeader :title="isEdit ? t('tools.editTool') : t('tools.createTool')">
        <template #actions>
        <a-button @click="goBack">
          <ArrowLeftOutlined />
          {{ t('common.back') }}
        </a-button>
        </template>
      </AppPageHeader>

      <SkeletonDetail v-if="loading" />
        <a-card v-else class="form-card">
          <a-form
            ref="formRef"
            class="tool-form"
            :model="formState"
            :rules="formRules"
            layout="vertical"
            @finish="handleSubmit"
          >
            <!-- 基本信息 -->
            <a-divider orientation="left">{{ t('tools.basicInfo') }}</a-divider>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.toolName')" name="name">
                  <a-input
                    v-model:value="formState.name"
                    :placeholder="t('tools.toolNamePlaceholder')"
                    :max-length="100"
                    show-count
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.toolSlug')" name="slug">
                  <a-input
                    v-model:value="formState.slug"
                    :placeholder="t('tools.toolSlugPlaceholder')"
                    :max-length="50"
                    show-count
                  />
                  <template #extra>
                    <span class="form-extra">{{ t('tools.slugHint') }}</span>
                  </template>
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('common.description')" name="description">
              <a-textarea
                v-model:value="formState.description"
                :placeholder="t('tools.descriptionPlaceholder')"
                :rows="4"
                :max-length="500"
                show-count
              />
            </a-form-item>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.category')" name="category_id">
                  <a-select
                    v-model:value="formState.category_id"
                    :placeholder="t('tools.selectCategory')"
                    allow-clear
                  >
                    <a-select-option v-for="cat in categories" :key="cat.id" :value="cat.id">
                      {{ cat.name }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.tags')" name="tag_ids">
                  <a-select
                    v-model:value="formState.tag_ids"
                    :placeholder="t('tools.selectTags')"
                    mode="multiple"
                    allow-clear
                  >
                    <a-select-option v-for="tag in tags" :key="tag.id" :value="tag.id">
                      <a-tag :color="tag.color" size="small">{{ tag.name }}</a-tag>
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.icon')" name="icon">
                  <a-input
                    v-model:value="formState.icon"
                    :placeholder="t('tools.iconPlaceholder')"
                  />
                  <template #extra>
                    <span class="form-extra">{{ t('tools.iconHint') }}</span>
                  </template>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.iconUrl')" name="icon_url">
                  <a-input
                    v-model:value="formState.icon_url"
                    :placeholder="t('tools.iconUrlPlaceholder')"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 运行配置 -->
            <a-divider orientation="left">{{ t('tools.runConfig') }}</a-divider>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.timeoutSec')" name="timeout_sec">
                  <a-input-number
                    v-model:value="formState.timeout_sec"
                    :min="60"
                    :max="86400"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('tools.isPublic')" name="is_public">
              <a-switch v-model:checked="formState.is_public" />
              <span class="switch-label">{{ formState.is_public ? t('tools.publicYes') : t('tools.publicNo') }}</span>
            </a-form-item>

            <!-- 版本信息 -->
            <a-divider orientation="left">版本信息</a-divider>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item label="版本号" name="version">
                  <a-input
                    v-model:value="formState.version"
                    placeholder="例如：1.0.0"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="16">
                <a-form-item label="版本说明" name="notes">
                  <a-input
                    v-model:value="formState.notes"
                    placeholder="简要说明此版本的特点"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="更新日志" name="changelog">
              <a-textarea
                v-model:value="formState.changelog"
                placeholder="详细描述此版本的更新内容"
                :rows="3"
              />
            </a-form-item>

            <!-- 工具类型 -->
            <a-divider orientation="left">工具类型</a-divider>

            <a-alert
              class="tool-package-primary-path"
              type="info"
              show-icon
              message="新工具主路径：Tool Package v2"
              description="模型部署时通过 adapter 把原始输入输出转换为平台标准 Artifact 输入/输出槽；下方旧版 ToolVersion.config 表单仅用于兼容已有工具。"
            />

            <a-form-item label="工具类型" name="tool_type">
              <a-radio-group v-model:value="formState.tool_type">
                <a-radio value="remote_api">远程API</a-radio>
                <a-radio value="docker_image">Docker镜像</a-radio>
                <a-radio value="python_script">Python脚本</a-radio>
                <a-radio value="ssh_job">SSH作业</a-radio>
              </a-radio-group>
            </a-form-item>

            <!-- API配置 -->
            <template v-if="formState.tool_type === 'remote_api'">
              <a-divider orientation="left">API配置</a-divider>

              <a-form-item label="API地址" name="api_endpoint" :rules="[{ required: true, message: '请输入API地址' }]">
                <a-input
                  v-model:value="formState.api_endpoint"
                  placeholder="https://api.example.com/predict"
                />
              </a-form-item>

              <a-form-item label="请求方法" name="api_method">
                <a-select v-model:value="formState.api_method">
                  <a-select-option value="GET">GET</a-select-option>
                  <a-select-option value="POST">POST</a-select-option>
                </a-select>
              </a-form-item>

              <a-form-item label="请求头（可选）" name="api_headers">
                <StructuredKeyValueEditor
                  v-model="apiHeaderEntries"
                  add-label="添加请求头"
                  key-placeholder="请求头名称，如 Authorization"
                  value-placeholder="请求头值"
                />
                <template #extra>
                  <span class="form-extra">每个请求头单独填写；请使用密钥引用，避免保存明文凭证。</span>
                </template>
              </a-form-item>
            </template>

            <!-- Docker配置 -->
            <template v-if="formState.tool_type === 'docker_image'">
              <a-divider orientation="left">Docker配置</a-divider>

              <a-form-item label="Docker镜像" name="docker_image" :rules="[{ required: true, message: '请输入Docker镜像名称' }]">
                <a-input
                  v-model:value="formState.docker_image"
                  placeholder="例如：python:3.9-slim"
                />
              </a-form-item>

              <a-form-item label="启动命令（可选）" name="docker_command">
                <StructuredStringListEditor
                  v-model="dockerCommandItems"
                  add-label="添加命令参数"
                  empty-text="未设置时使用镜像默认命令"
                  placeholder="一个完整命令项，如 /app/main.py"
                />
                <template #extra>
                  <span class="form-extra">每行是一个命令项，包含空格的单项不会被拆分。</span>
                </template>
              </a-form-item>

              <a-form-item label="环境变量（可选）" name="docker_env">
                <StructuredKeyValueEditor
                  v-model="dockerEnvEntries"
                  add-label="添加环境变量"
                  key-placeholder="变量名，如 MODEL_PATH"
                  value-placeholder="变量值，如 /models"
                />
              </a-form-item>
            </template>

            <!-- Python脚本配置 -->
            <template v-if="formState.tool_type === 'python_script'">
              <a-divider orientation="left">Python脚本配置</a-divider>

              <a-form-item label="脚本路径" name="python_script" :rules="[{ required: true, message: '请输入Python脚本路径' }]">
                <a-input
                  v-model:value="formState.python_script"
                  placeholder="例如：/app/scripts/predict.py"
                />
              </a-form-item>

              <a-form-item label="脚本参数（可选）" name="python_args">
                <StructuredStringListEditor
                  v-model="pythonArgumentItems"
                  add-label="添加脚本参数"
                  empty-text="暂无额外脚本参数"
                  placeholder="一个完整参数，如 --batch-size 或 32"
                />
                <template #extra>
                  <span class="form-extra">参数按列表传递，不经过 shell 解析。</span>
                </template>
              </a-form-item>
            </template>

            <!-- SSH 作业配置 -->
            <template v-if="formState.tool_type === 'ssh_job'">
              <a-divider orientation="left">SSH作业配置</a-divider>

              <a-row :gutter="24">
                <a-col :span="16">
                  <a-form-item label="远端主机" name="ssh_host" :rules="[{ required: true, message: '请输入远端主机地址' }]">
                    <a-input
                      v-model:value="formState.ssh_host"
                      placeholder="例如：gpu-node-01.internal"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="SSH端口" name="ssh_port">
                    <a-input-number
                      v-model:value="formState.ssh_port"
                      :min="1"
                      :max="65535"
                      style="width: 100%"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item label="SSH用户" name="ssh_username" :rules="[{ required: true, message: '请输入SSH用户名' }]">
                    <a-input
                      v-model:value="formState.ssh_username"
                      placeholder="例如：platform_runner"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="认证方式" name="ssh_auth_type">
                    <a-select v-model:value="formState.ssh_auth_type">
                      <a-select-option value="key">私钥引用</a-select-option>
                      <a-select-option value="password">密码引用</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item
                    v-if="formState.ssh_auth_type === 'password'"
                    label="密码引用"
                    name="ssh_password_ref"
                    :rules="[{ required: true, message: '请输入密码引用名' }]"
                  >
                    <a-input
                      v-model:value="formState.ssh_password_ref"
                      placeholder="例如：ssh_gpu_node_01_password"
                    />
                    <template #extra>
                      <span class="form-extra">引用 Worker 节点预置的 SSH 密码，不在配置中保存明文密码</span>
                    </template>
                  </a-form-item>
                  <a-form-item
                    v-else
                    label="私钥引用"
                    name="ssh_auth_ref"
                    :rules="[{ required: true, message: '请输入私钥引用名' }]"
                  >
                    <a-input
                      v-model:value="formState.ssh_auth_ref"
                      placeholder="例如：ssh_gpu_node_01"
                    />
                    <template #extra>
                      <span class="form-extra">引用 Worker 节点预置的 SSH 私钥，不在配置中保存明文密钥</span>
                    </template>
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item label="运行模式" name="ssh_runner_mode">
                    <a-select v-model:value="formState.ssh_runner_mode">
                      <a-select-option value="docker_exec">docker_exec</a-select-option>
                      <a-select-option value="shell">shell</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="远端任务根目录" name="ssh_remote_base_dir" :rules="[{ required: true, message: '请输入远端任务根目录' }]">
                    <a-input
                      v-model:value="formState.ssh_remote_base_dir"
                      placeholder="例如：/srv/platform-jobs"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item label="统一入口脚本" name="ssh_entrypoint" :rules="[{ required: true, message: '请输入统一入口脚本路径' }]">
                    <a-input
                      v-model:value="formState.ssh_entrypoint"
                      placeholder="例如：/app/platform_run.sh"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-if="formState.ssh_runner_mode === 'docker_exec'" :span="12">
                  <a-form-item label="远端容器名" name="ssh_container_name" :rules="[{ required: true, message: '请输入远端容器名' }]">
                    <a-input
                      v-model:value="formState.ssh_container_name"
                      placeholder="例如：targetdiff-prod"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-else :span="12">
                  <a-form-item label="运行设备（可选）" name="ssh_device">
                    <a-input
                      v-model:value="formState.ssh_device"
                      placeholder="例如：cuda:0"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row v-if="formState.ssh_runner_mode === 'docker_exec'" :gutter="24">
                <a-col :span="12">
                  <a-form-item label="容器内任务根目录（可选）" name="ssh_container_base_dir">
                    <a-input
                      v-model:value="formState.ssh_container_base_dir"
                      placeholder="例如：/workspace/platform-jobs"
                    />
                    <template #extra>
                      <span class="form-extra">宿主机与容器内挂载路径不一致时填写</span>
                    </template>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="运行设备（可选）" name="ssh_device">
                    <a-input
                      v-model:value="formState.ssh_device"
                      placeholder="例如：cuda:0"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item label="环境变量（可选）" name="ssh_env">
                <StructuredKeyValueEditor
                  v-model="sshEnvEntries"
                  add-label="添加环境变量"
                  key-placeholder="变量名，如 CUDA_VISIBLE_DEVICES"
                  value-placeholder="变量值"
                />
                <template #extra>
                  <span class="form-extra">环境变量会在远端入口脚本前注入。</span>
                </template>
              </a-form-item>

              <a-form-item label="输出文件匹配规则（可选）" name="ssh_output_globs">
                <StructuredStringListEditor
                  v-model="sshOutputGlobItems"
                  add-label="添加匹配规则"
                  empty-text="暂无输出文件匹配规则"
                  placeholder="例如 output/artifacts/**/*"
                />
                <template #extra>
                  <span class="form-extra">只允许匹配 output/ 目录下的文件。</span>
                </template>
              </a-form-item>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item label="执行后清理远端目录" name="ssh_cleanup_remote">
                    <a-switch v-model:checked="formState.ssh_cleanup_remote" />
                    <span class="switch-label">{{ formState.ssh_cleanup_remote ? '开启' : '关闭' }}</span>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="严格校验主机指纹" name="ssh_strict_host_key_checking">
                    <a-switch v-model:checked="formState.ssh_strict_host_key_checking" />
                    <span class="switch-label">{{ formState.ssh_strict_host_key_checking ? '开启' : '关闭' }}</span>
                  </a-form-item>
                </a-col>
              </a-row>
            </template>

            <!-- 参数定义 -->
            <a-divider orientation="left">参数定义</a-divider>

            <a-form-item label="输入参数Schema" name="input_schema">
              <a-textarea
                v-model:value="formState.input_schema"
                placeholder='{"type": "object", "properties": {"input": {"type": "string"}}}'
                :rows="5"
              />
              <template #extra>
                <span class="form-extra">JSON Schema格式，定义工具的输入参数结构</span>
              </template>
            </a-form-item>

            <a-form-item label="输出参数Schema" name="output_schema">
              <a-textarea
                v-model:value="formState.output_schema"
                placeholder='{"type": "object", "properties": {"result": {"type": "string"}}}'
                :rows="5"
              />
              <template #extra>
                <span class="form-extra">JSON Schema格式，定义工具的输出结果结构</span>
              </template>
            </a-form-item>

            <a-form-item :label="t('tools.documentationMarkdown')" name="documentation_markdown">
              <a-textarea
                v-model:value="formState.documentation_markdown"
                class="tool-documentation-editor"
                placeholder="## 模型介绍&#10;&#10;## 参数说明&#10;&#10;## 输出文件"
                :rows="10"
              />
              <template #extra>
                <span class="form-extra">{{ t('tools.documentationMarkdownHint') }}</span>
              </template>
            </a-form-item>

            <!-- Agent 编排能力 -->
            <a-divider orientation="left">旧版 Agent 语义映射（兼容）</a-divider>

            <a-form-item label="Agent 可用" name="agent_capability_enabled">
              <a-switch
                v-model:checked="formState.agent_capability_enabled"
                @change="handleAgentCapabilityToggle"
              />
              <span class="switch-label">{{ formState.agent_capability_enabled ? '开启' : '关闭' }}</span>
              <template #extra>
                <span class="form-extra">仅兼容旧工具；新工具应通过 Tool Package v2 声明标准 Artifact 输入/输出槽。</span>
              </template>
            </a-form-item>

            <template v-if="formState.agent_capability_enabled">
              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item label="Agent 能力" name="agent_capability">
                    <a-select v-model:value="formState.agent_capability">
                      <a-select-option value="pocket_prediction">口袋预测 pocket_prediction</a-select-option>
                      <a-select-option value="molecule_generation">分子生成 molecule_generation</a-select-option>
                      <a-select-option value="format_conversion">格式转换 format_conversion</a-select-option>
                      <a-select-option value="docking">分子对接 docking</a-select-option>
                      <a-select-option value="affinity_prediction">亲和力预测 affinity_prediction</a-select-option>
                      <a-select-option value="property_prediction">性质预测 property_prediction</a-select-option>
                      <a-select-option value="general_tool">通用工具 general_tool</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="Agent 阶段" name="agent_stage">
                    <a-input
                      v-model:value="formState.agent_stage"
                      placeholder="默认与能力一致，例如 molecule_generation"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <div class="agent-capability-block">
                <div class="agent-capability-header">
                  <span>输入语义映射（兼容）</span>
                  <a-button size="small" @click="addAgentInput">
                    <PlusOutlined />
                    添加输入
                  </a-button>
                </div>
                <a-row
                  v-for="(input, index) in formState.agent_inputs"
                  :key="`agent-input-${index}`"
                  :gutter="12"
                  class="agent-capability-row"
                >
                  <a-col :span="7">
                    <a-input v-model:value="input.semantic_type" placeholder="semantic_type，如 binding_pocket@1" />
                  </a-col>
                  <a-col :span="7">
                    <a-input v-model:value="input.field" placeholder="工具字段，如 protein_pdb" />
                  </a-col>
                  <a-col :span="7">
                    <a-input v-model:value="input.accepted_extensions" placeholder="扩展名，如 .pdb,.sdf" />
                  </a-col>
                  <a-col :span="3">
                    <a-button block danger @click="removeAgentInput(index)">
                      <DeleteOutlined />
                    </a-button>
                  </a-col>
                </a-row>
              </div>

              <div class="agent-capability-block">
                <div class="agent-capability-header">
                  <span>输出语义映射（兼容）</span>
                  <a-button size="small" @click="addAgentOutput">
                    <PlusOutlined />
                    添加输出
                  </a-button>
                </div>
                <a-row
                  v-for="(output, index) in formState.agent_outputs"
                  :key="`agent-output-${index}`"
                  :gutter="12"
                  class="agent-capability-row"
                >
                  <a-col :span="5">
                    <a-input v-model:value="output.semantic_type" placeholder="semantic_type，如 ligand_structure@1" />
                  </a-col>
                  <a-col :span="4">
                    <a-select v-model:value="output.source">
                      <a-select-option value="output_files">文件</a-select-option>
                      <a-select-option value="output_data">结果数据</a-select-option>
                    </a-select>
                  </a-col>
                  <a-col :span="4">
                    <a-input v-model:value="output.path" placeholder="数据路径，可选" />
                  </a-col>
                  <a-col :span="4">
                    <a-input v-model:value="output.match_extension" placeholder="扩展名，如 .sdf" />
                  </a-col>
                  <a-col :span="4">
                    <a-input v-model:value="output.filename_contains_any" placeholder="文件名关键词，逗号分隔" />
                  </a-col>
                  <a-col :span="2">
                    <a-switch v-model:checked="output.required" />
                  </a-col>
                  <a-col :span="1">
                    <a-button danger @click="removeAgentOutput(index)">
                      <DeleteOutlined />
                    </a-button>
                  </a-col>
                </a-row>
              </div>

              <a-form-item label="Agent 默认参数 JSON" name="agent_defaults">
                <a-textarea
                  v-model:value="agentDefaultsText"
                  placeholder='{"params.n_samples": 8, "params.device": "cuda:0"}'
                  :rows="3"
                />
              </a-form-item>
            </template>

            <!-- 提交按钮 -->
            <a-form-item class="form-actions">
              <a-space size="middle">
                <a-button size="large" @click="goBack">
                  {{ t('common.cancel') }}
                </a-button>
                <a-button type="primary" size="large" html-type="submit" :loading="submitting">
                  <SaveOutlined />
                  {{ isEdit ? t('common.save') : t('common.create') }}
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import {
    ArrowLeftOutlined,
    DeleteOutlined,
    PlusOutlined,
    SaveOutlined
  } from '@ant-design/icons-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import StructuredKeyValueEditor from '@/components/tools/StructuredKeyValueEditor.vue'
  import StructuredStringListEditor from '@/components/tools/StructuredStringListEditor.vue'
  import { useToolsStore } from '@/stores'
  import { createTool, createToolVersion, updateTool, getToolDetail } from '@/api/tools'
  import type { ToolCreateParams } from '@/types/models'
  import {
    keyValueEntriesToRecord,
    normalizeStringList,
    recordToKeyValueEntries,
    stringListForConfig,
    type KeyValueEntry
  } from '@/utils/tool-config-editors'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const submitting = ref(false)
  const originalVersion = ref('')
  const originalChangelog = ref('')
  const originalNotes = ref('')
  const originalConfigSnapshot = ref('')

  // 判断是编辑还是创建
  const isEdit = computed(() => route.name === 'AdminToolEdit' || route.name === 'ToolEdit')
  const toolId = computed(() => route.params.id as string)

  interface AgentCapabilityInputForm {
    semantic_type: string
    field: string
    accepted_extensions: string
  }

  interface AgentCapabilityOutputForm {
    semantic_type: string
    source: 'output_files' | 'output_data'
    path: string
    match_extension: string
    filename_contains_any: string
    required: boolean
  }

  // 扩展的表单状态接口
  interface ExtendedFormState extends ToolCreateParams {
    tag_ids: string[]
    // 版本信息
    version: string
    changelog: string
    notes: string
    // 工具类型
    tool_type: 'remote_api' | 'docker_image' | 'python_script' | 'ssh_job'
    // API配置
    api_endpoint: string
    api_method: 'GET' | 'POST'
    // Docker配置
    docker_image: string
    // Python配置
    python_script: string
    // SSH 配置
    ssh_host: string
    ssh_port: number
    ssh_username: string
    ssh_auth_type: 'key' | 'password'
    ssh_auth_ref: string
    ssh_password_ref: string
    ssh_runner_mode: 'docker_exec' | 'shell'
    ssh_remote_base_dir: string
    ssh_container_base_dir: string
    ssh_entrypoint: string
    ssh_container_name: string
    ssh_device: string
    ssh_cleanup_remote: boolean
    ssh_strict_host_key_checking: boolean
    // 参数定义
    input_schema: string  // JSON字符串
    output_schema: string  // JSON字符串
    documentation_markdown: string
    // Agent 编排能力
    agent_capability_enabled: boolean
    agent_capability: string
    agent_stage: string
    agent_inputs: AgentCapabilityInputForm[]
    agent_outputs: AgentCapabilityOutputForm[]
  }

  // 表单状态
  const formState = reactive<ExtendedFormState>({
    name: '',
    slug: '',
    description: '',
    category_id: '',
    icon: '',
    icon_url: '',
    is_public: true,
    gpu_required: false,
    gpu_memory_mb: undefined,
    timeout_sec: 3600,
    tag_ids: [],
    // 版本信息
    version: '1.0.0',
    changelog: '',
    notes: '',
    // 工具类型
    tool_type: 'remote_api',
    // API配置
    api_endpoint: '',
    api_method: 'POST',
    // Docker配置
    docker_image: '',
    // Python配置
    python_script: '',
    // SSH配置
    ssh_host: '',
    ssh_port: 22,
    ssh_username: '',
    ssh_auth_type: 'key',
    ssh_auth_ref: '',
    ssh_password_ref: '',
    ssh_runner_mode: 'docker_exec',
    ssh_remote_base_dir: '',
    ssh_container_base_dir: '',
    ssh_entrypoint: '',
    ssh_container_name: '',
    ssh_device: '',
    ssh_cleanup_remote: true,
    ssh_strict_host_key_checking: true,
    // 参数定义
    input_schema: '{}',
    output_schema: '{}',
    documentation_markdown: '',
    // Agent 编排能力
    agent_capability_enabled: false,
    agent_capability: 'molecule_generation',
    agent_stage: 'molecule_generation',
    agent_inputs: [],
    agent_outputs: []
  })

  const apiHeaderEntries = ref<KeyValueEntry[]>([])
  const dockerCommandItems = ref<string[]>([])
  const dockerEnvEntries = ref<KeyValueEntry[]>([])
  const pythonArgumentItems = ref<string[]>([])
  const sshEnvEntries = ref<KeyValueEntry[]>([])
  const sshOutputGlobItems = ref<string[]>([
    'output/result.json',
    'output/logs/run.log',
    'output/artifacts/**/*'
  ])
  const agentDefaultsText = ref('{}')

  const splitCommaList = (value: string): string[] => {
    return value
      .split(',')
      .map(item => item.trim())
      .filter(Boolean)
  }

  const joinStringList = (value: unknown): string => {
    return Array.isArray(value) ? value.map(item => String(item)).join(',') : ''
  }

  const createAgentInput = (): AgentCapabilityInputForm => ({
    semantic_type: '',
    field: '',
    accepted_extensions: ''
  })

  const createAgentOutput = (): AgentCapabilityOutputForm => ({
    semantic_type: '',
    source: 'output_files',
    path: '',
    match_extension: '',
    filename_contains_any: '',
    required: true
  })

  const addAgentInput = () => {
    formState.agent_inputs.push(createAgentInput())
  }

  const removeAgentInput = (index: number) => {
    formState.agent_inputs.splice(index, 1)
  }

  const addAgentOutput = () => {
    formState.agent_outputs.push(createAgentOutput())
  }

  const removeAgentOutput = (index: number) => {
    formState.agent_outputs.splice(index, 1)
  }

  const handleAgentCapabilityToggle = (checked: boolean | string | number) => {
    if (!checked) {
      return
    }
    if (formState.agent_inputs.length === 0) {
      addAgentInput()
    }
    if (formState.agent_outputs.length === 0) {
      addAgentOutput()
    }
    if (!formState.agent_stage.trim()) {
      formState.agent_stage = formState.agent_capability
    }
  }

  const formatJsonText = (value: unknown, fallback: string) => {
    if (value == null) {
      return fallback
    }

    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return fallback
    }
  }

  const isRecord = (value: unknown): value is Record<string, unknown> => {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
  }

  const normalizeForComparison = (value: unknown): unknown => {
    if (Array.isArray(value)) {
      return value.map(item => normalizeForComparison(item))
    }

    if (value && typeof value === 'object') {
      return Object.keys(value as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((acc, key) => {
          acc[key] = normalizeForComparison((value as Record<string, unknown>)[key])
          return acc
        }, {})
    }

    return value
  }

  const serializeForComparison = (value: unknown) => {
    try {
      return JSON.stringify(normalizeForComparison(value))
    } catch {
      return ''
    }
  }

  const parseAgentCapabilityIntoForm = (config: Record<string, unknown>) => {
    const rawCapability = config.agent_capability
    if (!isRecord(rawCapability)) {
      formState.agent_capability_enabled = false
      formState.agent_inputs = []
      formState.agent_outputs = []
      agentDefaultsText.value = '{}'
      return
    }

    formState.agent_capability_enabled = rawCapability.enabled === true
    formState.agent_capability = String(rawCapability.capability || 'molecule_generation')
    formState.agent_stage = String(rawCapability.stage || rawCapability.capability || 'molecule_generation')
    agentDefaultsText.value = formatJsonText(rawCapability.defaults || {}, '{}')

    formState.agent_inputs = Array.isArray(rawCapability.inputs)
      ? rawCapability.inputs.filter(isRecord).map(item => ({
        semantic_type: String(item.semantic_type || ''),
        field: String(item.field || item.semantic_type || ''),
        accepted_extensions: joinStringList(item.accepted_extensions)
      }))
      : []

    formState.agent_outputs = Array.isArray(rawCapability.outputs)
      ? rawCapability.outputs.filter(isRecord).map(item => {
        const match = isRecord(item.match) ? item.match : {}
        return {
          semantic_type: String(item.semantic_type || ''),
          source: item.source === 'output_data' ? 'output_data' : 'output_files',
          path: String(item.path || ''),
          match_extension: String(match.extension || ''),
          filename_contains_any: joinStringList(match.filename_contains_any),
          required: item.required !== false
        }
      })
      : []
  }

  const parseToolConfigIntoForm = (config?: Record<string, unknown>) => {
    if (!config || typeof config.type !== 'string') {
      return
    }

    parseAgentCapabilityIntoForm(config)

    if (config.type === 'remote_api') {
      formState.tool_type = 'remote_api'
      formState.api_endpoint = String(config.endpoint || '')
      formState.api_method = config.method === 'GET' ? 'GET' : 'POST'
      apiHeaderEntries.value = recordToKeyValueEntries(config.headers)
    } else if (config.type === 'docker_image') {
      formState.tool_type = 'docker_image'
      formState.docker_image = String(config.image || '')
      dockerCommandItems.value = normalizeStringList(config.command)
      dockerEnvEntries.value = recordToKeyValueEntries(config.env)
    } else if (config.type === 'python_script') {
      formState.tool_type = 'python_script'
      formState.python_script = String(config.script_path || config.script || '')
      pythonArgumentItems.value = normalizeStringList(config.args)
    } else if (config.type === 'ssh_job') {
      formState.tool_type = 'ssh_job'
      formState.ssh_host = String(config.host || '')
      formState.ssh_port = Number(config.port || 22)
      formState.ssh_username = String(config.username || '')
      formState.ssh_auth_type = config.auth_type === 'password' ? 'password' : 'key'
      formState.ssh_auth_ref = String(config.auth_ref || '')
      formState.ssh_password_ref = String(config.password_ref || '')
      formState.ssh_runner_mode = config.runner_mode === 'shell' ? 'shell' : 'docker_exec'
      formState.ssh_remote_base_dir = String(config.remote_base_dir || '')
      formState.ssh_container_base_dir = String(config.container_base_dir || '')
      formState.ssh_entrypoint = String(config.entrypoint || '')
      formState.ssh_container_name = String(config.container_name || '')
      formState.ssh_device = String(config.device || '')
      formState.ssh_cleanup_remote = config.cleanup_remote !== false
      formState.ssh_strict_host_key_checking = config.strict_host_key_checking !== false
      sshEnvEntries.value = recordToKeyValueEntries(config.env)
      sshOutputGlobItems.value = normalizeStringList(config.output_globs)
    }

    formState.input_schema = formatJsonText(config.input_schema || {}, '{}')
    formState.output_schema = formatJsonText(config.output_schema || {}, '{}')
    formState.documentation_markdown =
      typeof config.documentation_markdown === 'string'
        ? config.documentation_markdown
        : ''
  }

  // 表单验证规则
  const formRules: Record<string, Rule[]> = {
    name: [
      { required: true, message: t('tools.nameRequired'), trigger: 'blur' },
      { min: 2, max: 100, message: t('tools.nameLength'), trigger: 'blur' }
    ],
    slug: [
      { required: true, message: t('tools.slugRequired'), trigger: 'blur' },
      { pattern: /^[a-z0-9-]+$/, message: t('tools.slugFormat'), trigger: 'blur' },
      { min: 2, max: 50, message: t('tools.slugLength'), trigger: 'blur' }
    ],
    description: [
      { max: 500, message: t('tools.descriptionLength'), trigger: 'blur' }
    ]
  }

  // 分类和标签
  const categories = computed(() => toolsStore.categories)
  const tags = computed(() => toolsStore.tags)

  // 加载工具详情（编辑模式）
  const loadToolDetail = async () => {
    if (!isEdit.value || !toolId.value) return

    loading.value = true
    try {
      const res = await getToolDetail(toolId.value)
      const tool = res.data

      // 填充表单
      formState.name = tool.name
      formState.slug = tool.slug
      formState.description = tool.description || ''
      formState.category_id = tool.category_id || ''
      formState.icon = tool.icon || ''
      formState.icon_url = tool.icon_url || ''
      formState.is_public = tool.is_public ?? true
      formState.gpu_required = tool.gpu_required
      formState.gpu_memory_mb = tool.gpu_memory_mb
      formState.timeout_sec = tool.timeout_sec || 3600
      formState.tag_ids = tool.tags?.map(t => t.id) || []
      formState.version = tool.current_version?.version || formState.version
      formState.changelog = tool.current_version?.changelog || ''
      formState.notes = tool.current_version?.notes || ''
      originalVersion.value = tool.current_version?.version || ''
      originalChangelog.value = tool.current_version?.changelog || ''
      originalNotes.value = tool.current_version?.notes || ''
      originalConfigSnapshot.value = serializeForComparison(tool.current_version?.config || {})

      parseToolConfigIntoForm(tool.current_version?.config as Record<string, unknown> | undefined)
    } catch {
      message.error(t('tools.loadFailed'))
      router.push('/tools')
    } finally {
      loading.value = false
    }
  }

  // 提交表单
  const handleSubmit = async () => {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }

    submitting.value = true
    try {
      let apiHeaders: Record<string, string> = {}
      let dockerEnv: Record<string, string> = {}
      let sshEnv: Record<string, string> = {}
      let sshOutputGlobs: string[] = []
      let inputSchema: Record<string, unknown> = {}
      let outputSchema: Record<string, unknown> = {}
      let agentDefaults: Record<string, unknown> = {}

      try {
        if (formState.tool_type === 'remote_api') {
          apiHeaders = keyValueEntriesToRecord(apiHeaderEntries.value)
        }
        if (formState.tool_type === 'docker_image') {
          dockerEnv = keyValueEntriesToRecord(dockerEnvEntries.value)
        }
        if (formState.tool_type === 'ssh_job') {
          sshEnv = keyValueEntriesToRecord(sshEnvEntries.value)
          sshOutputGlobs = stringListForConfig(sshOutputGlobItems.value)
        }
      } catch (error) {
        message.error(error instanceof Error ? error.message : '结构化配置无效')
        submitting.value = false
        return
      }

      try {
        if (formState.input_schema.trim()) {
          inputSchema = JSON.parse(formState.input_schema)
        }
        if (formState.output_schema.trim()) {
          outputSchema = JSON.parse(formState.output_schema)
        }
        if (formState.agent_capability_enabled && agentDefaultsText.value.trim()) {
          agentDefaults = JSON.parse(agentDefaultsText.value)
          if (!isRecord(agentDefaults)) {
            throw new Error('agent defaults must be an object')
          }
        }
      } catch {
        message.error('JSON 格式错误，请检查配置')
        submitting.value = false
        return
      }

      if (formState.agent_capability_enabled) {
        const validInputCount = formState.agent_inputs.filter(input => input.semantic_type.trim()).length
        const validOutputCount = formState.agent_outputs.filter(output => output.semantic_type.trim()).length
        if (!formState.agent_capability.trim() || validInputCount === 0 || validOutputCount === 0) {
          message.error('Agent 编排能力需要填写能力、至少一个输入和至少一个输出')
          submitting.value = false
          return
        }
      }

      // 构建 config 对象
      const config: Record<string, unknown> = {
        type: formState.tool_type,
        timeout_sec: formState.timeout_sec,
        gpu_required: formState.gpu_required,
        input_schema: inputSchema,
        output_schema: outputSchema
      }

      if (formState.documentation_markdown.trim()) {
        config.documentation_markdown = formState.documentation_markdown.trim()
      }

      if (formState.agent_capability_enabled) {
        config.agent_capability = {
          enabled: true,
          capability: formState.agent_capability.trim(),
          stage: formState.agent_stage.trim() || formState.agent_capability.trim(),
          inputs: formState.agent_inputs
            .filter(input => input.semantic_type.trim())
            .map(input => ({
              semantic_type: input.semantic_type.trim(),
              field: input.field.trim() || input.semantic_type.trim(),
              accepted_extensions: splitCommaList(input.accepted_extensions)
            })),
          outputs: formState.agent_outputs
            .filter(output => output.semantic_type.trim())
            .map(output => {
              const match: Record<string, unknown> = {}
              if (output.match_extension.trim()) {
                match.extension = output.match_extension.trim()
              }
              const filenameContainsAny = splitCommaList(output.filename_contains_any)
              if (filenameContainsAny.length > 0) {
                match.filename_contains_any = filenameContainsAny
              }

              return {
                semantic_type: output.semantic_type.trim(),
                source: output.source,
                path: output.path.trim() || undefined,
                required: output.required,
                match: Object.keys(match).length > 0 ? match : undefined
              }
            }),
          defaults: agentDefaults
        }
      }

      if (formState.gpu_memory_mb !== undefined) {
        config.gpu_memory_mb = formState.gpu_memory_mb
      }

      // 根据工具类型添加特定配置
      if (formState.tool_type === 'remote_api') {
        config.endpoint = formState.api_endpoint
        config.method = formState.api_method
        if (Object.keys(apiHeaders).length > 0) {
          config.headers = apiHeaders
        }
      } else if (formState.tool_type === 'docker_image') {
        config.image = formState.docker_image
        const dockerCommand = stringListForConfig(dockerCommandItems.value)
        if (dockerCommand.length > 0) {
          config.command = dockerCommand
        }
        if (Object.keys(dockerEnv).length > 0) {
          config.env = dockerEnv
        }
      } else if (formState.tool_type === 'python_script') {
        config.script_path = formState.python_script
        const pythonArguments = stringListForConfig(pythonArgumentItems.value)
        if (pythonArguments.length > 0) {
          config.args = pythonArguments
        }
      } else if (formState.tool_type === 'ssh_job') {
        config.host = formState.ssh_host
        config.port = formState.ssh_port
        config.username = formState.ssh_username
        config.auth_type = formState.ssh_auth_type
        if (formState.ssh_auth_type === 'password') {
          config.password_ref = formState.ssh_password_ref
        } else {
          config.auth_ref = formState.ssh_auth_ref
        }
        config.runner_mode = formState.ssh_runner_mode
        config.remote_base_dir = formState.ssh_remote_base_dir
        config.entrypoint = formState.ssh_entrypoint
        config.cleanup_remote = formState.ssh_cleanup_remote
        config.strict_host_key_checking = formState.ssh_strict_host_key_checking

        if (formState.ssh_runner_mode === 'docker_exec') {
          config.container_name = formState.ssh_container_name
          if (formState.ssh_container_base_dir) {
            config.container_base_dir = formState.ssh_container_base_dir
          }
        }

        if (formState.ssh_device) {
          config.device = formState.ssh_device
        }

        if (Object.keys(sshEnv).length > 0) {
          config.env = sshEnv
        }

        if (sshOutputGlobs.length > 0) {
          config.output_globs = sshOutputGlobs
        }
      }

      // 构建提交数据
      const data: ToolCreateParams & { initial_version?: unknown } = {
        name: formState.name,
        slug: formState.slug,
        description: formState.description || undefined,
        category_id: formState.category_id,
        icon: formState.icon || undefined,
        icon_url: formState.icon_url || undefined,
        is_public: formState.is_public,
        gpu_required: formState.gpu_required,
        gpu_memory_mb: formState.gpu_required ? formState.gpu_memory_mb : undefined,
        timeout_sec: formState.timeout_sec,
        tag_ids: formState.tag_ids.length > 0 ? formState.tag_ids : undefined
      }

      const versionConfigChanged = isEdit.value && (
        formState.version !== originalVersion.value ||
        formState.changelog !== originalChangelog.value ||
        formState.notes !== originalNotes.value ||
        serializeForComparison(config) !== originalConfigSnapshot.value
      )

      if (versionConfigChanged && formState.version === originalVersion.value) {
        message.error('修改版本配置时请填写新的版本号')
        submitting.value = false
        return
      }

      // 添加版本信息（仅创建模式）
      if (!isEdit.value) {
        data.initial_version = {
          version: formState.version,
          changelog: formState.changelog || undefined,
          notes: formState.notes || undefined,
          config: config,
          is_active: true
        }
      }

      if (isEdit.value) {
        await updateTool(toolId.value, data)
        if (versionConfigChanged) {
          await createToolVersion(toolId.value, {
            version: formState.version,
            changelog: formState.changelog || undefined,
            notes: formState.notes || undefined,
            config,
            is_active: true
          })
        }
        message.success(versionConfigChanged ? '工具与版本更新成功' : t('tools.updateSuccess'))
      } else {
        const res = await createTool(data)
        message.success(t('tools.createSuccess'))
        // 跳转到工具详情页
        router.push(`/tools/${res.data.id}`)
        return
      }

      router.push('/admin/tools')
    } catch {
      // 错误已在请求层处理
    } finally {
      submitting.value = false
    }
  }

  const goBack = () => {
    router.back()
  }

  onMounted(async () => {
    // 加载分类和标签
    await Promise.all([
      toolsStore.fetchCategories(),
      toolsStore.fetchTags()
    ])

    // 编辑模式加载工具详情
    if (isEdit.value) {
      await loadToolDetail()
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-create-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .form-card {
    max-width: 900px;
    margin: 0 auto;
  }

  .form-extra {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }

  .tool-package-primary-path {
    margin-bottom: @spacing-lg;
  }

  .switch-label {
    margin-left: @spacing-sm;
    color: @text-color-light-secondary;
  }

  .agent-capability-block {
    margin-bottom: @spacing-lg;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
    background: @bg-color-light;
  }

  .agent-capability-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: @spacing-sm;
    color: @text-color-light-primary;
    font-weight: @font-weight-medium;
  }

  .agent-capability-row + .agent-capability-row {
    margin-top: @spacing-sm;
  }

  .form-actions {
    margin-top: @spacing-xl;
    padding-top: @spacing-lg;
    border-top: 1px solid @border-color-light;
    text-align: center;
  }

  :deep(.ant-divider-inner-text) {
    font-weight: @font-weight-semibold;
    color: @text-color-light-primary;
  }

  :deep(.ant-btn-primary) {
    background: @accent-color;
    border-color: @accent-color;

    &:hover {
      background: @accent-color-hover;
      border-color: @accent-color-hover;
    }
  }

  @media (max-width: @screen-md) {
    :deep(.tool-form .ant-col-8),
    :deep(.tool-form .ant-col-12),
    :deep(.tool-form .ant-col-16) {
      flex: 0 0 100%;
      max-width: 100%;
    }
  }
</style>
