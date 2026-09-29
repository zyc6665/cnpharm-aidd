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
            <template v-if="showTemplateQuickStart">
              <a-divider orientation="left">药物研发工具模板</a-divider>

              <div class="drug-template-panel">
                <a-alert
                  type="info"
                  show-icon
                  message="从标准模板创建工具草稿"
                  description="模板会固定药物研发能力、标准输入输出、resource_profile 和 smoke test；Docker、SSH、API 等部署参数仍按下方执行器配置填写。"
                />
                <a-row :gutter="16" class="drug-template-row">
                  <a-col :span="14">
                    <a-form-item label="药物研发工具模板">
                      <a-select
                        v-model:value="selectedToolTemplateKey"
                        placeholder="选择 ADMET、构象生成、Vina、MD 等模板"
                        allow-clear
                        @change="handleToolTemplateChange"
                      >
                        <a-select-option
                          v-for="template in toolTemplates"
                          :key="template.template_key"
                          :value="template.template_key"
                        >
                          {{ template.name }} · {{ template.capability }}
                        </a-select-option>
                      </a-select>
                    </a-form-item>
                  </a-col>
                  <a-col :span="10">
                    <a-form-item label="资源画像">
                      <div class="drug-template-resource">
                        {{ selectedToolTemplateResourceText || '选择模板后显示资源需求' }}
                      </div>
                    </a-form-item>
                  </a-col>
                </a-row>
                <div v-if="selectedToolTemplate" class="drug-template-implementation">
                  <strong>推荐实现：{{ selectedToolTemplate.implementation.provider }}</strong>
                  <span>
                    {{ selectedToolTemplate.implementation.runtime }}
                    · 推荐执行器 {{ selectedToolTemplate.implementation.recommended_executor }}
                  </span>
                  <a
                    v-if="selectedToolTemplate.implementation.project_url"
                    :href="selectedToolTemplate.implementation.project_url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    查看项目
                  </a>
                  <span v-if="selectedToolTemplate.implementation.notes">
                    {{ selectedToolTemplate.implementation.notes }}
                  </span>
                </div>
                <a-space>
                  <a-button
                    type="primary"
                    html-type="button"
                    :disabled="!selectedToolTemplateKey"
                    :loading="creatingTemplateDraft"
                    @click="handleCreateTemplateDraft"
                  >
                    <PlusOutlined />
                    从模板创建草稿
                  </a-button>
                  <span class="form-extra">
                    创建草稿会直接复用下方当前执行器配置，不会发布工具。
                  </span>
                </a-space>
              </div>
            </template>

            <template v-if="!isRemoteSelfRegister">
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
            </template>

            <template v-if="!isRemoteSelfRegister">
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
                <span class="switch-label">
                  {{ formState.is_public ? t('tools.publicYes') : t('tools.publicNo') }}
                </span>
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
            </template>

            <!-- 工具类型 -->
            <a-divider orientation="left">工具类型</a-divider>

            <a-alert
              class="tool-package-primary-path"
              type="info"
              show-icon
              message="新工具主路径：Tool Package v2"
              description="模型部署时通过 adapter 把原始输入输出转换为平台标准 Artifact 输入/输出槽；下方旧版 ToolVersion.config 表单仅用于兼容已有工具。"
            />

            <a-alert
              v-if="registrationMode === 'package'"
              type="success"
              show-icon
              :message="packageLoading ? '正在载入 Tool Package v2' : '已载入 Tool Package v2'"
              description="manifest 会自动绑定到新版本。请继续填写执行器连接信息，保存后即可生成平台 ToolVersion。"
            />

            <a-form-item label="工具类型" name="tool_type">
              <a-radio-group v-model:value="formState.tool_type">
                <a-radio value="remote_api">远程API</a-radio>
                <a-radio value="docker_image">Docker镜像</a-radio>
                <a-radio value="python_script">Python脚本</a-radio>
                <a-radio value="ssh_job">SSH作业</a-radio>
                <a-radio value="k8s_job">Kubernetes Job</a-radio>
              </a-radio-group>
            </a-form-item>

            <!-- API配置 -->
            <template v-if="formState.tool_type === 'remote_api'">
              <a-divider orientation="left">远程 API 注册</a-divider>

              <a-form-item label="注册方式" name="remote_api_registration_mode">
                <a-radio-group
                  v-model:value="formState.remote_api_registration_mode"
                  :disabled="isEdit"
                >
                  <a-radio value="self_register">服务自注册</a-radio>
                  <a-radio value="manual">旧版手动配置</a-radio>
                </a-radio-group>
                <template #extra>
                  <span class="form-extra">
                    服务自注册只需要填写服务根 URL，平台会读取固定 manifest 并创建草稿版本。
                  </span>
                </template>
              </a-form-item>

              <template v-if="isRemoteSelfRegister">
                <a-row :gutter="24">
                  <a-col :span="14">
                    <a-form-item
                      label="服务根 URL"
                      name="remote_base_url"
                      :rules="[{ required: true, message: '请输入服务根 URL' }]"
                    >
                      <a-input
                        v-model:value="formState.remote_base_url"
                        placeholder="https://model.example.com"
                      />
                      <template #extra>
                        <span class="form-extra">
                          平台会请求 /.well-known/sciminer-tool.json 完成自发现。
                        </span>
                      </template>
                    </a-form-item>
                  </a-col>
                  <a-col :span="10">
                    <a-form-item
                      :label="t('tools.category')"
                      name="category_id"
                      :rules="[{ required: true, message: '请选择工具分类' }]"
                    >
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
                </a-row>

                <a-row :gutter="24">
                  <a-col :span="8">
                    <a-form-item label="运行 smoke test" name="remote_run_smoke_test">
                      <a-switch v-model:checked="formState.remote_run_smoke_test" />
                      <span class="switch-label">
                        {{ formState.remote_run_smoke_test ? '开启' : '关闭' }}
                      </span>
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item label="成功后发布" name="remote_publish_on_success">
                      <a-switch
                        v-model:checked="formState.remote_publish_on_success"
                        :disabled="!formState.remote_run_smoke_test"
                      />
                      <span class="switch-label">
                        {{ formState.remote_publish_on_success ? '开启' : '关闭' }}
                      </span>
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="t('tools.isPublic')" name="is_public">
                      <a-switch v-model:checked="formState.is_public" />
                      <span class="switch-label">
                        {{ formState.is_public ? t('tools.publicYes') : t('tools.publicNo') }}
                      </span>
                    </a-form-item>
                  </a-col>
                </a-row>

                <a-row :gutter="24">
                  <a-col :span="8">
                    <a-form-item :label="t('tools.timeoutSec')" name="timeout_sec">
                      <a-input-number
                        v-model:value="formState.timeout_sec"
                        :min="60"
                        :max="86400"
                        style="width: 100%"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="t('tools.icon')" name="icon">
                      <a-input
                        v-model:value="formState.icon"
                        :placeholder="t('tools.iconPlaceholder')"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :span="8">
                    <a-form-item :label="t('tools.iconUrl')" name="icon_url">
                      <a-input
                        v-model:value="formState.icon_url"
                        :placeholder="t('tools.iconUrlPlaceholder')"
                      />
                    </a-form-item>
                  </a-col>
                </a-row>

                <div v-if="remoteRegisterResult" class="remote-register-result">
                  <div class="remote-register-result-header">
                    <div>
                      <div class="remote-register-result-title">远程 API 注册结果</div>
                      <div class="remote-register-result-subtitle">
                        manifest_sha256: <code>{{ remoteRegisterResult.manifest_sha256 }}</code>
                      </div>
                    </div>
                    <a-space>
                      <router-link :to="`/tools/${remoteRegisterResult.tool.id}`">
                        查看工具详情
                      </router-link>
                      <router-link
                        v-if="remoteRegisterResult.smoke_test_task_id"
                        :to="`/tasks/${remoteRegisterResult.smoke_test_task_id}`"
                      >
                        查看 smoke test 任务
                      </router-link>
                    </a-space>
                  </div>

                  <div class="remote-register-stage-title">注册诊断</div>
                  <div class="remote-register-stage-list">
                    <div
                      v-for="stage in remoteRegisterResult.stages"
                      :key="stage.name"
                      class="remote-register-stage"
                    >
                      <a-tag :color="remoteStageStatusDisplay(stage.status).color">
                        {{ remoteStageStatusDisplay(stage.status).text }}
                      </a-tag>
                      <span class="remote-register-stage-name">{{ stage.name }}</span>
                      <span class="remote-register-stage-message">{{ stage.message }}</span>
                    </div>
                  </div>
                </div>
              </template>

              <template v-else>
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

            <!-- Kubernetes Job 配置 -->
            <template v-if="formState.tool_type === 'k8s_job'">
              <a-divider orientation="left">Kubernetes Job 配置</a-divider>
              <a-alert
                type="info"
                show-icon
                message="受控集群执行"
                description="镜像和资源档位由工具版本声明；集群、Namespace、ServiceAccount 与凭据由平台执行环境统一管理。"
                class="executor-managed-alert"
              />
              <a-row :gutter="24">
                <a-col :span="16">
                  <a-form-item
                    label="镜像 digest"
                    name="k8s_image"
                    :rules="[{ required: true, message: '请输入不可变镜像引用' }, { pattern: /@sha256:[a-fA-F0-9]{64}$/, message: '镜像必须使用完整 SHA-256 digest' }]"
                  >
                    <a-input
                      v-model:value="formState.k8s_image"
                      placeholder="registry.example/model@sha256:64 位 digest"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item
                    label="资源档位"
                    name="k8s_resource_profile"
                    :rules="[{ required: true, message: '请输入资源档位' }]"
                  >
                    <a-input v-model:value="formState.k8s_resource_profile" placeholder="cpu-small / gpu-large" />
                  </a-form-item>
                </a-col>
              </a-row>
            </template>

            <template v-if="!isRemoteSelfRegister">
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
                <span class="switch-label">
                  {{ formState.agent_capability_enabled ? '开启' : '关闭' }}
                </span>
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
            </template>

            <template v-if="formState.tool_type === 'remote_api'">
              <a-divider orientation="left">远程服务容量</a-divider>
              <a-form-item label="容量管理方式" name="remote_capacity_mode">
                <a-select v-model:value="formState.remote_capacity_mode">
                  <a-select-option value="unmanaged">不由平台管理</a-select-option>
                  <a-select-option value="static">平台限制最大并发</a-select-option>
                </a-select>
                <template #extra>
                  <span class="form-extra">
                    静态并发适用于 AlphaFold 3、OpenDDE 等自建服务；相同服务必须使用相同容量组和并发上限。
                  </span>
                </template>
              </a-form-item>
              <template v-if="formState.remote_capacity_mode === 'static'">
                <a-row :gutter="24">
                  <a-col :span="12">
                    <a-form-item
                      label="容量共享组"
                      name="remote_capacity_group"
                      :rules="[{ required: true, message: '请输入容量共享组' }]"
                    >
                      <a-input
                        v-model:value="formState.remote_capacity_group"
                        placeholder="例如 alphafold3-production"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :span="6">
                    <a-form-item label="最大并发" name="remote_max_inflight">
                      <a-input-number
                        v-model:value="formState.remote_max_inflight"
                        :min="1"
                        :max="1000"
                        style="width: 100%"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :span="6">
                    <a-form-item label="容量租约（秒）" name="remote_lease_ttl_sec">
                      <a-input-number
                        v-model:value="formState.remote_lease_ttl_sec"
                        :min="60"
                        :max="86400"
                        style="width: 100%"
                      />
                    </a-form-item>
                  </a-col>
                </a-row>
              </template>
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
  import { useToolCreateEditorState } from '@/composables/useToolCreateEditorState'
  import {
    buildRemoteToolRegistrationPayload,
    buildToolAgentCapabilityEnablePatch,
    buildToolEditFormPatch,
    buildToolTemplateFormPatch,
    buildToolTemplateDraftPayload,
    createAgentCapabilityInputForm,
    createAgentCapabilityOutputForm,
    createToolCreateFormState,
    createToolCreateSubmission,
    formatToolTemplateResourceText,
    formatToolCreateSubmissionErrorMessage,
    buildToolVersionCreatePayload,
    remoteToolStageStatusDisplay,
    resolveToolCreateSubmissionBlocker,
    type ToolConfigFormPatch,
    type ToolCreateFormState
  } from '@/domain/tools'
  import type { ToolPackage } from '@/types/tool-packages'
  import { useToolsStore } from '@/stores'
  import { getToolPackage } from '@/api/tool-packages'
  import {
    createTool,
    createToolDraftFromTemplate,
    createToolVersion,
    getToolDetail,
    listToolTemplates,
    registerRemoteTool,
    type RemoteToolRegisterResult,
    type ToolTemplateSummary,
    updateTool
  } from '@/api/tools'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const submitting = ref(false)
  const remoteRegisterResult = ref<RemoteToolRegisterResult | null>(null)
  const toolTemplates = ref<ToolTemplateSummary[]>([])
  const selectedToolTemplateKey = ref<string>()
  const creatingTemplateDraft = ref(false)
  const originalVersion = ref('')
  const originalChangelog = ref('')
  const originalNotes = ref('')
  const originalConfigSnapshot = ref('')
  const packageManifest = ref<Record<string, unknown> | null>(null)
  const packageLoading = ref(false)

  // 判断是编辑还是创建
  const isEdit = computed(() => route.name === 'AdminToolEdit' || route.name === 'ToolEdit')
  const toolId = computed(() => route.params.id as string)
  const registrationMode = computed(() => {
    const mode = route.query.mode
    return mode === 'remote' || mode === 'advanced' || mode === 'template' || mode === 'package' ? mode : 'template'
  })
  const showTemplateQuickStart = computed(
    () => !isEdit.value && registrationMode.value !== 'remote' && registrationMode.value !== 'advanced' && registrationMode.value !== 'package'
  )

  // 表单状态
  const formState = reactive<ToolCreateFormState>(createToolCreateFormState())

  const isRemoteSelfRegister = computed(
    () => !isEdit.value &&
      formState.tool_type === 'remote_api' &&
      formState.remote_api_registration_mode === 'self_register'
  )

  const {
    apiHeaderEntries,
    dockerCommandItems,
    dockerEnvEntries,
    pythonArgumentItems,
    sshEnvEntries,
    sshOutputGlobItems,
    snapshot: editorStateSnapshot,
    applyPatch: applyEditorPatch,
  } = useToolCreateEditorState()
  const agentDefaultsText = ref('{}')

  const selectedToolTemplate = computed(() =>
    toolTemplates.value.find(template => template.template_key === selectedToolTemplateKey.value)
  )

  const selectedToolTemplateResourceText = computed(() => {
    return formatToolTemplateResourceText(selectedToolTemplate.value?.resource_profile)
  })

  const addAgentInput = () => {
    formState.agent_inputs.push(createAgentCapabilityInputForm())
  }

  const removeAgentInput = (index: number) => {
    formState.agent_inputs.splice(index, 1)
  }

  const addAgentOutput = () => {
    formState.agent_outputs.push(createAgentCapabilityOutputForm())
  }

  const removeAgentOutput = (index: number) => {
    formState.agent_outputs.splice(index, 1)
  }

  const loadToolTemplates = async () => {
    if (isEdit.value) {
      return
    }
    try {
      const response = await listToolTemplates()
      toolTemplates.value = response.data
    } catch {
      toolTemplates.value = []
    }
  }

  const handleToolTemplateChange = () => {
    const template = selectedToolTemplate.value
    if (!template) {
      return
    }

    const patch = buildToolTemplateFormPatch({
      currentToolType: formState.tool_type,
      template,
    })
    Object.assign(formState, patch.form)
    agentDefaultsText.value = patch.agentDefaultsText
  }

  const handleCreateTemplateDraft = async () => {
    if (!selectedToolTemplateKey.value) {
      message.error('请选择药物研发工具模板')
      return
    }
    try {
      await formRef.value?.validate()
    } catch {
      return
    }

    creatingTemplateDraft.value = true
    try {
      const draftResponse = await createToolDraftFromTemplate(
        selectedToolTemplateKey.value,
        buildToolTemplateDraftPayload(formState, editorStateSnapshot())
      )
      message.success('工具模板草稿创建成功')
      const createdToolId = draftResponse.data.tool.id
      router.push(`/tools/${createdToolId}`)
    } catch {
      // 错误已在请求层处理
    } finally {
      creatingTemplateDraft.value = false
    }
  }

  const handleAgentCapabilityToggle = (checked: boolean | string | number) => {
    if (!checked) {
      return
    }

    Object.assign(formState, buildToolAgentCapabilityEnablePatch(formState))
  }

  const applyToolFormPatch = (patch: ToolConfigFormPatch) => {
    Object.assign(formState, patch.form)
    applyEditorPatch(patch.editor)
    agentDefaultsText.value = patch.agentDefaultsText
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

  const remoteStageStatusDisplay = remoteToolStageStatusDisplay

  const handleRemoteSelfRegisterSubmit = async () => {
    submitting.value = true
    remoteRegisterResult.value = null
    try {
      const response = await registerRemoteTool(buildRemoteToolRegistrationPayload(formState))
      remoteRegisterResult.value = response.data
      message.success(
        response.data.smoke_test_task_id
          ? '远程工具已注册，smoke test 已创建，请查看下方任务入口'
          : '远程工具已注册为草稿'
      )
    } catch {
      // 错误已在请求层处理
    } finally {
      submitting.value = false
    }
  }

  const applyRegistrationMode = () => {
    if (isEdit.value) {
      return
    }
    if (registrationMode.value === 'remote') {
      formState.tool_type = 'remote_api'
      formState.remote_api_registration_mode = 'self_register'
      formState.remote_capacity_mode = 'static'
    } else if (registrationMode.value === 'advanced') {
      formState.tool_type = 'remote_api'
      formState.remote_api_registration_mode = 'manual'
      formState.remote_capacity_mode = 'static'
    } else if (registrationMode.value === 'package') {
      formState.tool_type = 'ssh_job'
      formState.remote_api_registration_mode = 'manual'
    }
  }

  const loadToolPackage = async () => {
    if (isEdit.value || registrationMode.value !== 'package') return
    const packageId = String(route.query.package_id || '')
    if (!packageId) return
    packageLoading.value = true
    try {
      const response = await getToolPackage(packageId)
      const pkg = response.data as ToolPackage
      const version = pkg.current_version
      if (!version?.manifest) {
        message.error('Tool Package 当前没有可用 manifest')
        return
      }
      packageManifest.value = version.manifest
      formState.name = pkg.name
      formState.slug = pkg.slug
      formState.description = pkg.description || ''
      formState.version = version.version
      formState.notes = '由 Tool Package v2 导入'
      const variants = Array.isArray(version.manifest.variants)
        ? version.manifest.variants.filter(item => item && typeof item === 'object') as Array<Record<string, unknown>>
        : []
      const variant = variants[0]
      if (variant) {
        const entrypoint = Array.isArray(variant.entrypoint)
          ? variant.entrypoint.map(item => String(item)).join(' ')
          : ''
        if (entrypoint) {
          formState.ssh_entrypoint = entrypoint
        }
        const resources = variant.resources && typeof variant.resources === 'object'
          ? variant.resources as Record<string, unknown>
          : {}
        const gpuMemory = Number(resources.gpu_memory_mb)
        if (Number.isFinite(gpuMemory) && gpuMemory > 0) {
          formState.gpu_required = true
          formState.gpu_memory_mb = gpuMemory
        }
      }
    } catch {
      message.error('Tool Package 加载失败')
    } finally {
      packageLoading.value = false
    }
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
      const patch = buildToolEditFormPatch(tool)

      applyToolFormPatch(patch)
      originalVersion.value = patch.originalVersion
      originalChangelog.value = patch.originalChangelog
      originalNotes.value = patch.originalNotes
      originalConfigSnapshot.value = patch.originalConfigSnapshot
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

    if (isRemoteSelfRegister.value) {
      await handleRemoteSelfRegisterSubmit()
      return
    }

    submitting.value = true
    try {
      let submission: ReturnType<typeof createToolCreateSubmission>
      try {
        submission = createToolCreateSubmission({
          formState,
          editorState: editorStateSnapshot(),
          agentDefaultsText: agentDefaultsText.value,
          isEdit: isEdit.value,
          originalVersion: originalVersion.value,
          originalChangelog: originalChangelog.value,
          originalNotes: originalNotes.value,
          originalConfigSnapshot: originalConfigSnapshot.value,
          toolPackageManifest: packageManifest.value || undefined
        })
      } catch (error) {
        message.error(formatToolCreateSubmissionErrorMessage(error))
        return
      }

      const blocker = resolveToolCreateSubmissionBlocker({
        submission,
        version: formState.version,
        originalVersion: originalVersion.value,
      })
      if (blocker) {
        message.error(blocker)
        return
      }

      if (isEdit.value) {
        await updateTool(toolId.value, submission.data)
        if (submission.versionConfigChanged) {
          await createToolVersion(
            toolId.value,
            buildToolVersionCreatePayload(formState, submission.config)
          )
        }
        message.success(submission.versionConfigChanged ? '工具与版本更新成功' : t('tools.updateSuccess'))
      } else {
        const res = await createTool(submission.data)
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
    applyRegistrationMode()
    // 加载分类和标签
    await Promise.all([
      toolsStore.fetchCategories(),
      toolsStore.fetchTags(),
      loadToolTemplates()
    ])

    // 编辑模式加载工具详情
    if (isEdit.value) {
      await loadToolDetail()
    } else {
      await loadToolPackage()
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

  .drug-template-panel {
    display: grid;
    gap: @spacing-md;
    margin-bottom: @spacing-lg;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
    background: @bg-color-light;
  }

  .drug-template-row {
    margin-top: @spacing-xs;
  }

  .drug-template-resource {
    min-height: 32px;
    padding: 5px 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .drug-template-implementation {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-xs @spacing-sm;
    padding: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: @bg-surface;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .drug-template-implementation strong {
    color: @text-color-light-primary;
  }

  .drug-template-implementation a {
    color: @primary-color;
  }

  .remote-register-result {
    margin: @spacing-lg 0;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
    background: @bg-color-light;
  }

  .remote-register-result-header {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    margin-bottom: @spacing-md;
  }

  .remote-register-result-title,
  .remote-register-stage-title {
    color: @text-color-light-primary;
    font-weight: @font-weight-semibold;
  }

  .remote-register-result-subtitle {
    margin-top: @spacing-xs;
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
    word-break: break-all;
  }

  .remote-register-stage-list {
    margin-top: @spacing-sm;
  }

  .remote-register-stage {
    display: flex;
    gap: @spacing-sm;
    align-items: center;
    padding: @spacing-xs 0;
  }

  .remote-register-stage-name {
    min-width: 140px;
    color: @text-color-light-primary;
    font-weight: @font-weight-medium;
  }

  .remote-register-stage-message {
    color: @text-color-light-secondary;
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
    .remote-register-result-header,
    .remote-register-stage {
      flex-direction: column;
      align-items: flex-start;
    }

    :deep(.tool-form .ant-col-8),
    :deep(.tool-form .ant-col-12),
    :deep(.tool-form .ant-col-16) {
      flex: 0 0 100%;
      max-width: 100%;
    }
  }
</style>
