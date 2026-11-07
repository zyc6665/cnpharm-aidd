<template>
  <div class="model-guide">
    <AppPageHeader
      title="模型接入教程"
      subtitle="从镜像构建到 K8s 版本发布：管理员添加、编辑和升级模型的标准流程"
    >
      <template #actions>
        <a-space>
          <a-button @click="router.push('/admin/tools')">返回模型工具</a-button>
          <a-button type="primary" @click="router.push('/admin/tool-packages')">
            登记模型交付包
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>

    <div class="model-guide__layout">
      <aside class="model-guide__toc">
        <a
          v-for="item in toc"
          :key="item.id"
          :href="`#${item.id}`"
          class="model-guide__toc-item"
        >
          {{ item.label }}
        </a>
      </aside>

      <main class="model-guide__content">
        <a-alert
          type="info"
          show-icon
          message="平台只负责调度，不负责构建镜像"
          description="模型镜像由模型开发者构建并推送到平台可访问的 Registry。管理员在平台登记 Tool Package v2、校验标准 Artifact 契约、注册 K8s 候选版本并完成冒烟后，模型才会对用户可见。"
          class="model-guide__lead"
        />

        <section id="overview" class="guide-section">
          <h2>一条模型从开发到上线的主链路</h2>
          <div class="guide-flow">
            <div v-for="(step, index) in flowSteps" :key="step.title" class="guide-flow__item">
              <span class="guide-flow__index">{{ index + 1 }}</span>
              <div>
                <strong>{{ step.title }}</strong>
                <p>{{ step.description }}</p>
              </div>
            </div>
          </div>
        </section>

        <section id="image" class="guide-section">
          <h2>1. 构建镜像</h2>
          <p>
            镜像必须使用与平台集群一致的架构（当前为 linux/amd64），并固定不可变 digest。
            平台按 <code>k8s_job</code> 启动容器，通过环境变量传入任务文件与结果目录。
          </p>
          <a-row :gutter="[16, 16]">
            <a-col :xs="24" :lg="12">
              <a-card size="small" title="镜像内必须实现的约定">
                <ul class="guide-list">
                  <li>读取 <code>DRP_TASK_FILE</code>（JSON）中的 <code>parameters</code>、<code>standard_inputs</code>。</li>
                  <li>把结构化结果写入 <code>DRP_RESULT_FILE</code>；文件产物写入 <code>/work/out</code>。</li>
                  <li>输入/输出文件名与 manifest 中声明的 Artifact 角色保持一致。</li>
                  <li>进程退出码 0 表示成功；异常退出要输出可读错误日志。</li>
                </ul>
              </a-card>
            </a-col>
            <a-col :xs="24" :lg="12">
              <a-card size="small" title="推荐目录结构">
                <pre class="guide-code">/opt/sciminer/
├── platform_adaptor/       # 平台请求/结果适配
├── model/                 # 模型代码与权重入口
└── run.py                 # 容器入口

# 构建并推送
docker build --platform linux/amd64 \
  -t registry.example/aidd/my-model:1.0.0 .
docker push registry.example/aidd/my-model:1.0.0
# 记录推送后的 sha256 digest</pre>
              </a-card>
            </a-col>
          </a-row>
        </section>

        <section id="contract" class="guide-section">
          <h2>2. 对齐标准 Artifact 契约</h2>
          <p>
            输入/输出不要自定义文件类型，统一使用平台标准 Artifact 类型。发布前平台会校验
            <code>artifacts.inputs</code>、<code>artifacts.outputs</code> 与镜像实际读写角色是否一致。
          </p>
          <a-table
            :columns="artifactColumns"
            :data-source="artifactRows"
            :pagination="false"
            size="small"
            row-key="type"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'type'">
                <code>{{ record.type }}</code>
              </template>
            </template>
          </a-table>
          <a-alert
            type="warning"
            show-icon
            message="常见错误"
            description="把 CSV 当作 ligand_sdf 上传、把口袋文件声明成 protein_structure、缺少 required 角色，都会在任务提交时被标准输入校验拦截。"
            class="guide-alert"
          />
        </section>

        <section id="manifest" class="guide-section">
          <h2>3. 编写 Tool Package v2 manifest</h2>
          <p>在「工具与模型 → 模型交付包」中可以直接使用向导生成，也可以粘贴完整 manifest。最小可用示例：</p>
          <pre class="guide-code">{
  "api_version": "aidd.sciminer/tool-package",
  "kind": "ToolPackage",
  "metadata": {
    "slug": "my-model",
    "name": "My Model",
    "version": "1.0.0",
    "description": "一句话说明模型能力"
  },
  "artifacts": {
    "inputs": [
      { "name": "protein_pdb", "type": "protein_structure@1", "required": true }
    ],
    "outputs": [
      { "name": "molecules", "type": "molecule_table@1", "cardinality": "one", "required": true }
    ]
  },
  "parameters_schema": {
    "type": "object",
    "properties": {
      "num_samples": { "type": "integer", "minimum": 1, "maximum": 1000, "default": 100 }
    },
    "additionalProperties": false
  },
  "variants": [
    {
      "accelerator": "gpu",
      "image": "registry.example/aidd/my-model@sha256:&lt;64位digest&gt;",
      "entrypoint": ["python", "/opt/sciminer/run.py"],
      "resources": { "cpu": "4", "memory": "16Gi", "gpu": 1 }
    }
  ]
}</pre>
        </section>

        <section id="publish" class="guide-section">
          <h2>4. 注册、冒烟与版本提升</h2>
          <a-steps direction="vertical" size="small" :current="4">
            <a-step title="登记交付包" description="填写或粘贴 manifest，平台解析标准 Artifact 契约与参数 Schema。" />
            <a-step title="校验与发布" description="校验通过后发布交付包；已发布交付包不可就地修改。" />
            <a-step title="注册 K8s 候选版本" description="填写镜像 digest、资源画像和变体；候选版本默认 inactive，不影响线上。" />
            <a-step title="真实冒烟" description="上传一组真实输入，确认 K8s Job Succeeded 且 result.json / 产物符合契约。" />
            <a-step title="提升为当前版本" description="冒烟通过后提升；需要回滚时保留历史版本，不删除旧版本。" />
          </a-steps>
        </section>

        <section id="edit" class="guide-section">
          <h2>5. 编辑模型与发布新版本</h2>
          <a-row :gutter="[16, 16]">
            <a-col :xs="24" :lg="12">
              <a-card size="small" title="编辑展示信息">
                <p>名称、描述、图标、标签、分类等展示字段可以直接保存，不会产生新版本。</p>
              </a-card>
            </a-col>
            <a-col :xs="24" :lg="12">
              <a-card size="small" title="修改运行配置">
                <p>镜像、资源、参数 Schema 变化时必须填写新的版本号，平台会创建一个新的 ToolVersion。</p>
              </a-card>
            </a-col>
          </a-row>
        </section>

        <section id="checklist" class="guide-section">
          <h2>发布前检查清单</h2>
          <ul class="guide-checklist">
            <li>镜像 digest 是 <code>sha256:...</code> 且节点可拉取</li>
            <li>输入/输出全部使用平台标准 Artifact 类型</li>
            <li>参数 Schema 的默认值和范围与镜像实现一致</li>
            <li>K8s 资源画像与 GPU/CPU/内存需求匹配</li>
            <li>真实冒烟通过，结果文件可被平台解析</li>
            <li>版本号、更新日志、展示信息完整</li>
          </ul>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import AppPageHeader from '@/components/common/AppPageHeader.vue'

const router = useRouter()

const toc = [
  { id: 'overview', label: '主链路' },
  { id: 'image', label: '构建镜像' },
  { id: 'contract', label: '标准契约' },
  { id: 'manifest', label: '编写 manifest' },
  { id: 'publish', label: '注册与发布' },
  { id: 'edit', label: '编辑与升级' },
  { id: 'checklist', label: '检查清单' },
]

const flowSteps = [
  { title: '构建镜像', description: '模型开发者构建 linux/amd64 镜像并推送到 Registry，记录 digest。' },
  { title: '登记交付包', description: '管理员登记 Tool Package v2，声明标准 Artifact 输入输出与参数 Schema。' },
  { title: '校验与发布', description: '平台校验契约完整性与镜像摘要，发布交付包。' },
  { title: '注册 K8s 版本', description: '注册候选 ToolVersion，配置资源画像；候选版本默认 inactive。' },
  { title: '冒烟与提升', description: '真实任务冒烟通过后提升为当前版本，对用户可见。' },
]

const artifactColumns = [
  { title: '标准类型', key: 'type', dataIndex: 'type', width: 220 },
  { title: '用途', key: 'usage', dataIndex: 'usage' },
  { title: '常见文件角色', key: 'roles', dataIndex: 'roles' },
]

const artifactRows = [
  { type: 'protein_structure@1', usage: '蛋白/受体结构', roles: 'prepared_pdb / structure_file' },
  { type: 'binding_pocket@1', usage: '结合口袋', roles: 'residue_pocket_pdb / atom_pocket_pdb / metadata_json' },
  { type: 'ligand_structure@1', usage: '小分子/配体结构', roles: 'structure_file' },
  { type: 'molecule_table@1', usage: '分子表格结果', roles: 'table_file' },
  { type: 'run_report@1', usage: '运行报告', roles: 'report_json' },
]
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.model-guide {
  padding: @spacing-lg 0;

  &__layout {
    display: grid;
    grid-template-columns: 180px minmax(0, 1fr);
    gap: @spacing-xl;
    align-items: start;
  }

  &__toc {
    position: sticky;
    top: @spacing-lg;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
    background: @bg-surface;
  }

  &__toc-item {
    padding: 8px 10px;
    border-radius: @border-radius-sm;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;

    &:hover {
      color: @primary-color;
      background: @bg-hover;
    }
  }

  &__content {
    min-width: 0;
  }

  &__lead {
    margin-bottom: @spacing-xl;
  }
}

.guide-section {
  margin-bottom: @spacing-xl;
  padding: @spacing-lg;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-base;
  background: @bg-surface;

  h2 {
    margin: 0 0 @spacing-md;
    color: @text-color-light-primary;
    font-size: 18px;
  }

  p {
    margin: 0 0 @spacing-md;
    color: @text-color-light-secondary;
    line-height: 1.8;
  }

  code {
    padding: 1px 6px;
    border-radius: 4px;
    background: @bg-elevated;
    color: @accent-color;
    font-family: @font-family-mono;
    font-size: 12px;
  }
}

.guide-flow {
  display: grid;
  gap: @spacing-sm;

  &__item {
    display: flex;
    gap: @spacing-md;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
    background: @bg-color-light;

    strong {
      color: @text-color-light-primary;
    }

    p {
      margin: 4px 0 0;
      font-size: @font-size-sm;
      line-height: 1.6;
    }
  }

  &__index {
    display: inline-flex;
    flex: 0 0 26px;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: @accent-color;
    color: #fff;
    font-weight: 600;
  }
}

.guide-code {
  margin: 0;
  padding: @spacing-md;
  overflow-x: auto;
  border-radius: @border-radius-base;
  background: @bg-elevated;
  color: @text-color-light-primary;
  font-family: @font-family-mono;
  font-size: 12px;
  line-height: 1.7;
}

.guide-list,
.guide-checklist {
  margin: 0;
  padding-left: 18px;
  color: @text-color-light-secondary;
  line-height: 1.9;
}

.guide-alert {
  margin-top: @spacing-md;
}

@media (max-width: @screen-md) {
  .model-guide__layout {
    grid-template-columns: 1fr;
  }

  .model-guide__toc {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
