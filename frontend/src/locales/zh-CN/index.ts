const workflowSteps = {
  pocketExploration: {
    title: '口袋探索',
    description: '快速识别靶点结构中的关键结合口袋与可成药位点'
  },
  moleculeGenerationOrVirtualScreening: {
    title: '分子生成或虚拟筛选',
    description: '围绕已知口袋特征生成候选分子，或通过虚拟筛选快速缩小候选空间'
  },
  molecularDockingAndAffinityPrediction: {
    title: '分子对接及结合亲和力预测',
    description: '评估候选分子与靶点口袋的结合姿态，并预测潜在结合亲和力'
  },
  propertyPrediction: {
    title: '性质预测',
    description: '联合评估活性、理化性质与 ADMET 等关键指标'
  },
  leadOptimization: {
    title: '先导化合物优化',
    description: '基于多目标结果迭代筛选并优化先导化合物设计'
  }
}

export default {
  // 通用
  common: {
    theme: '主题',
    confirm: '确认',
    cancel: '取消',
    save: '保存',
    delete: '删除',
    edit: '编辑',
    create: '创建',
    search: '搜索',
    reset: '重置',
    submit: '提交',
    back: '返回',
    loading: '加载中...',
    success: '操作成功',
    error: '操作失败',
    noData: '暂无数据',
    more: '更多',
    all: '全部',
    actions: '操作',
    status: '状态',
    time: '时间',
    name: '名称',
    description: '描述',
    home: '首页',
    refresh: '刷新',
    refreshSuccess: '刷新成功',
    download: '下载',
    clear: '清除',
    expand: '展开侧栏',
    collapse: '收起侧栏',
    totalItems: '共 {total} 条',
    copySuccess: '复制成功',
    required: '为必填项',
    optional: '可选',
    createdAt: '创建时间',
    updatedAt: '更新时间',
    seconds: '秒',
    sort: '排序'
  },

  // 导航
  nav: {
    home: '首页',
    workspace: '工作台',
    tools: '工具',
    cpupdb: 'CPUPDB',
    tasks: '任务',
    workflow: '工作流',
    researchBoards: '科研白板',
    admin: '管理',
    login: '登录',
    register: '注册',
    logout: '退出登录',
    profile: '个人中心',
    settings: '设置',
    favorites: '收藏'
  },
  command: {
    placeholder: '搜索页面、命令…',
    noResults: '无匹配结果',
    newTask: '创建新任务',
    toggleTheme: '切换主题',
    group: {
      navigate: '页面导航',
      actions: '快捷操作'
    }
  },

  // 工作台
  workspace: {
    title: '工作台',
    researchTitle: '研究项目',
    createProject: '新建项目',
    recentProjects: '最近项目',
    projectCount: '共 {count} 个可访问项目',
    continueResearch: '继续研究',
    openProject: '项目总览',
    emptyProjects: '还没有研究项目',
    attentionTitle: '待审批与失败任务',
    emptyAttention: '暂无待审批或失败任务',
    pendingApproval: '等待审批',
    taskNeedsAttention: '需要处理',
    recentArtifacts: '最近 Artifact',
    emptyArtifacts: '暂无 Artifact',
    unknownArtifactType: '未知类型',
    loadFailed: '研究工作台加载失败',
    loadFailedHint: '无法获取最新项目数据，请检查网络后重试。',
    overviewLoadFailed: '任务与 Artifact 暂时不可用',
    overviewLoadFailedHint: '项目列表已加载，任务和 Artifact 概览接口暂时失败，可稍后重试。',
    schemaMigrationLoadFailed: '数据库迁移未完成',
    schemaMigrationLoadFailedHint: '当前数据库结构落后于后端代码，请先执行 Alembic 迁移后再刷新工作台。',
    retry: '重试',
    project: {
      name: '项目名称',
      namePlaceholder: '例如：EGFR 口袋研究',
      nameRequired: '请输入项目名称',
      goal: '研究目标',
      goalPlaceholder: '描述需要验证的科学问题或预期结果',
      noGoal: '尚未设置研究目标',
      createFailed: '项目创建失败，请重试',
      archive: '归档',
      archiveSuccess: '研究项目已归档',
      archiveFailed: '项目归档失败，请重试',
      deleteConfirm: '确认删除该研究项目？删除后关联白板、工作流和项目记录将不可恢复。',
      deleteSuccess: '研究项目已删除',
      deleteFailed: '项目删除失败，请重试',
      status: {
        draft: '草稿',
        active: '进行中',
        completed: '已完成',
        archived: '已归档',
        frozen: '已冻结'
      }
    },
    goodMorning: '早上好',
    goodAfternoon: '下午好',
    goodEvening: '晚上好',
    recentTasks: '最近任务',
    noRecentTasks: '还没有任务，开始你的第一个计算',
    startFirst: '浏览工具',
    quickActions: '快速操作',
    newWorkflow: '新建工作流',
    browseTools: '浏览工具',
    viewTasks: '查看任务',
    activeWorkflows: '活跃工作流',
  },

  // 首页
  home: {
    title: '首页',
    badge: 'AI 驱动的科学计算平台',
    hero: {
      title: '从靶点到先导化合物，一个工作台完成',
      description: '口袋识别、虚拟筛选、分子对接、ADMET 预测——所有计算环节在同一平台上编排、执行、追溯',
      cta: '免费注册',
      secondary: '浏览工具',
    },
    values: {
      reproducible: {
        title: '可复现',
        desc: '完整的输入链追溯、版本化工作流、不可变制品——每一次计算都有据可查',
      },
      composable: {
        title: '可编排',
        desc: '将工具组合为工作流 DAG，支持条件分支、循环迭代、并行计算',
      },
      trusted: {
        title: '可信任',
        desc: 'GPU 调度、文件去重、权限控制——为科研计算打造的生产级基础设施',
      },
    },
    capabilities: {
      title: 'AIDD 全流程覆盖',
      subtitle: '沿着药物发现管线，从靶点分析到先导优化，每个阶段都有工具支撑',
    },
    platform: {
      title: '开放平台',
      desc: 'CPUModel 与 PAIWSIT、CPUPDB 等科学数据库深度集成，构建从数据到发现的完整链路',
      cta: '开始使用',
    },
    workflow: {
      title: '平台功能',
      subtitle: '沿着 AIDD 流程打通从口袋识别到先导优化的核心计算环节',
      items: workflowSteps
    },
    features: {
      title: '平台特性',
      subtitle: '专业、高效、易用',
      items: {
        gpu: {
          title: 'GPU 加速',
          description: '支持 NVIDIA GPU 加速计算，大幅提升处理速度'
        },
        cloud: {
          title: '云端处理',
          description: '无需本地安装，随时随地访问使用'
        },
        api: {
          title: 'API 集成',
          description: '提供完整的 RESTful API，轻松集成到您的工作流'
        },
        security: {
          title: '数据安全',
          description: '企业级数据加密与隐私保护'
        }
      }
    },
    foundation: {
      title: '靶点发现与平台底座',
      subtitle: '从肿瘤病理图像入口、结构与口袋依据，到实际 AIDD 计算工作台，首页按 PAIWSIT、CPUPDB 与 CPUModel 串起研究路径。',
      paiwsit: {
        kicker: 'Target Discovery Entry',
        title: 'PAIWSIT',
        description: 'PAIWSIT 是面向肿瘤研究的病理学家标注与 AI 赋能全切片图像数据库，可作为从组织病理表型切入靶点发现与机制研究的数据入口。',
        points: {
          annotatedSlides: '提供病理学家标注的肿瘤全切片图像资源',
          aiHeatmap: '支持 AI 辅助异常区域识别与热图可视化',
          pathologyEvidence: '为靶点发现提供病理表型与组织层证据'
        },
        action: '访问 PAIWSIT'
      },
      cpupdb: {
        kicker: 'Pocket Data Foundation',
        title: 'CPUPDB',
        description: '从病理与生物学线索进一步下钻到蛋白结构、口袋、多构象和相互作用分析，为后续筛选与设计提供结构依据。',
        points: {
          structures: '覆盖蛋白结构、配体、口袋与结合位点信息',
          dynamics: '引入动力学数据，用于观察构象变化与隐蔽口袋',
          analysis: '支持从检索、Explore、Dynamics 到 Detail 的连续分析'
        },
        action: '访问 CPUPDB',
        help: '查看帮助文档'
      },
      platform: {
        kicker: 'AIDD Workbench',
        title: 'CPUModel 工作台',
        description: '将靶点线索、结构数据与计算工具接到同一个工作台中，继续完成筛选、对接、性质评估与结果复用。',
        points: {
          groupedTools: '按研究分组组织工具与流程路径',
          reusableArtifacts: '在任务之间复用历史产物继续计算',
          chainedWorkflow: '串联口袋识别、筛选、对接与性质评估'
        },
        action: '进入工具工作台'
      }
    },
    tools: {
      title: '热门工具',
      subtitle: '最受欢迎的计算工具',
      viewAll: '查看全部工具'
    },
    cta: {
      title: '立即开始您的研究',
      description: '注册即可免费使用基础功能，开启计算生物学之旅',
      button: '免费注册'
    }
  },

  workflow: {
    title: '工具工作台',
    subtitle: '按研究分组浏览工具，在同一空间复用历史产物并继续发起计算任务',
    entry: {
      home: '进入工具工作台',
      tools: '按分组使用工具'
    },
    mode: {
      manual: '手动模式',
      agent: '项目智能体'
    },
    workbenchHeader: {
      kicker: '工作流工作台',
      titleFallback: '未命名工作流'
    },
    statusSummary: {
      ready: '可运行',
      blocked: '阻塞',
      running: '运行中',
      completed: '完成',
      failed: '失败'
    },
    definition: {
      namePlaceholder: '流程名称',
      loadPlaceholder: '已保存流程',
      new: '新建',
      save: '保存',
      load: '加载',
      duplicate: '复制',
      archive: '归档',
      archiveConfirm: '确认归档当前流程？归档后默认列表不再显示，可保留运行记录。',
      delete: '删除',
      templateLabel: '流程模式',
      projectScoped: '项目工作流',
      runWorkflowDefinition: '运行工作流'
    },
    persistence: {
      untitledWorkflow: '未命名流程',
      duplicateName: '{name} 副本',
      saved: '流程已保存',
      duplicated: '流程已复制',
      archived: '流程已归档',
      deleted: '流程已删除',
      draftSaved: '工作流草稿已保存',
      runCanceled: '工作流运行已取消',
      nodeRetried: '工作流节点已重试',
      loaded: '流程已加载'
    },
    autoRepair: {
      reasonWithRoles: '{targetNodeTitle} 的 {inputSlotName} 需要{requiredRoles}，可通过 {toolName} 自动补齐。',
      reasonWithoutRoles: '{targetNodeTitle} 的 {inputSlotName} 需要先准备或转换输入产物，可通过 {toolName} 自动补齐。',
      roleSeparator: '、'
    },
    artifactRoles: {
      atom_pocket_pdb: '原子口袋 PDB',
      metadata_json: '元数据 JSON',
      pocket_metadata_json: '口袋元数据 JSON',
      preparation_report_json: '处理报告 JSON',
      prepared_pdb: '已处理 PDB',
      prepared_pqr: '已处理 PQR',
      raw_structure_file: '原始结构文件',
      receptor_pdbqt: '受体 PDBQT',
      report_json: '报告 JSON',
      report_markdown: '报告 Markdown',
      residue_pocket_pdb: '残基口袋 PDB',
      structure_2d_sdf: '2D 配体 SDF',
      structure_3d_sdf: '3D 配体 SDF',
      structure_file: '结构文件',
      table_file: '表格文件'
    },
    canvasPresets: {
      kicker: '流程编排',
      unsaved: '未保存的工作台编排',
      namePlaceholder: '输入流程名称',
      loadPlaceholder: '加载已保存流程',
      refresh: '刷新流程',
      new: '新建流程',
      save: '保存流程',
      duplicate: '复制流程',
      delete: '删除流程',
      deleteConfirm: '确认删除当前流程？运行记录不会被删除。',
      copyName: '{name} 副本',
      run: '一键创建运行',
      nameRequired: '请先填写流程名称',
      emptyDefinition: '当前没有可保存的工具节点',
      invalidDefinition: '当前工作流存在循环依赖或无效连线，请调整节点依赖后再继续',
      invalidDefinitionDetail: '当前工作流无效：{reason}',
      saved: '流程已保存',
      duplicated: '流程已复制',
      deleted: '流程已删除',
      runCreated: '工作流运行已创建：{id}',
      requiredInputs: '运行输入',
      emptyRunInputs: '当前工作流没有全局运行输入。请在节点结果的配置页选择工具、填写参数，或直接运行单个节点。',
      runHistory: '运行历史',
      emptyRunHistory: '暂无工作流运行记录',
      refreshRuns: '刷新运行',
      loadMoreRuns: '加载更多运行',
      allRunsLoaded: '已加载全部运行记录',
      viewRunDetail: '查看详情',
      selectInputArtifact: '选择产物文件',
      autoFillInputs: '自动填充',
      missingInputs: '请先选择必需输入：{inputs}',
      syncRun: '同步运行',
      cancelRun: '取消运行',
      retryNode: '重试节点',
      viewNodeTasks: '查看该节点任务',
      runSynced: '工作流运行状态已同步',
      restoreRunFailed: '最近一次工作流运行已不可访问',
      emptyRunDetail: '未找到工作流运行详情',
      runStatus: '最近一次运行',
      nodeProgress: '{completed}/{total} 个节点完成',
      taskId: '任务：{id}',
      toolVersion: '版本：{id}',
      inputFileIds: '输入文件：{ids}',
      outputSemanticTypes: '输出语义：{types}',
      missingSemanticOutputs: '缺失输出：{types}',
      presets: {
        fullPipeline: {
          name: '完整 AIDD 流程',
          description: '从蛋白结构输入开始，串联口袋识别、分子生成、对接、性质预测与先导优化。'
        },
        proteinToPocket: {
          name: 'Protein PDB 到口袋预测',
          description: '从蛋白结构出发，快速识别潜在口袋并输出后续可用的口袋结构。'
        },
        pocketToGeneration: {
          name: 'Pocket PDB 到分子生成',
          description: '基于已有口袋结构生成候选分子，用于后续筛选或对接。'
        },
        proteinLigandToDocking: {
          name: 'Protein + ligand 到对接与亲和力',
          description: '使用蛋白与候选分子直接评估结合姿态与亲和力结果。'
        },
        generationToProperty: {
          name: '分子生成结果到性质预测',
          description: '对已有候选分子进行理化性质与 ADMET 相关评估。'
        },
        pubchemToAdmet: {
          name: 'PubChem 到基础 ADMET',
          description: '从 PubChem 配体开始，串联配体处理、SMILES 转换、RDKit 属性和 MolP-PC 基础 ADMET。'
        }
      }
    },
    nodeState: {
      ready: '可运行',
      running: '运行中',
      completed: '已完成',
      failed: '失败',
      missingTool: '缺少工具',
      invalidated: '需重跑',
      waitingInput: '等待输入',
      inputNode: '输入节点',
      pending: '待准备'
    },
    nodeType: {
      input: '输入',
      tool: '工具',
      result: '结果',
      artifact: '产物',
      condition: '条件',
      map: '批量',
      loop: '循环'
    },
    canvas: {
      title: '流程画布',
      nodes: '{count} 个节点',
      edges: '{count} 条连线',
      zoomOut: '缩小',
      zoomIn: '放大',
      resetZoom: '复位'
    },
    canvasNode: {
      titleFallback: '未命名节点',
      connectTo: '连接到此节点',
      connectFrom: '从此节点连接',
      run: '运行',
      delete: '删除节点',
      inputs: '输入 {count}',
      outputs: '输出 {count}',
      noIo: '暂无输入输出约束',
      previewHint: '选择节点查看配置与结果'
    },
    canvasEdge: {
      delete: '删除连线 {edgeId}'
    },
    workbenchSidebar: {
      expand: '展开侧边栏',
      collapse: '折叠侧边栏',
      resize: '调整侧边栏宽度'
    },
    nodeRun: {
      loginPrompt: '请登录后选择已保存产物',
      autoBoundTitle: '已自动绑定上游产物',
      runCurrentNode: '运行当前节点',
      reset: '重置',
      selectToolFirst: '请先选择真实工具再配置节点',
      standardArtifactDescription: '标准产物类型：{artifactType}',
      upstreamNodeFallback: '上游节点'
    },
    palette: {
      title: '工具库',
      toolsAvailable: '{count} 个工具可用',
      searchPlaceholder: '搜索 PDB、配体、对接、ADMET...',
      quickFilterTitle: '常用场景',
      showAdvanced: '高级筛选',
      hideAdvanced: '收起高级',
      filterTitle: '筛选条件',
      filterStage: '按阶段筛选',
      filterInput: '按输入语义筛选',
      filterOutput: '按输出语义筛选',
      filterExecutor: '按执行器筛选',
      addNode: '添加节点',
      dragOrClick: '拖拽或点击添加',
      quickFilters: {
        all: '全部'
      },
      categories: {
        external_database_fetch: '外部数据库',
        protein_fetch: '蛋白获取',
        ligand_fetch: '配体获取',
        protein_preparation: '蛋白处理',
        ligand_preparation: '配体处理',
        ligand_format_conversion: '格式转换',
        conformer_generation: '构象生成',
        property_prediction: '分子性质',
        admet_prediction: 'ADMET 预测',
        toxicity_prediction: '毒性预测',
        synthetic_accessibility: '合成可及性',
        molecular_docking: '分子对接',
        docking_rescore: '打分重排',
        molecular_dynamics: '分子动力学',
        interaction_analysis: '相互作用分析',
        other_tools: '其他工具'
      },
      empty: '暂无匹配工具，请调整筛选条件或搜索关键词'
    },
    preflight: {
      title: '运行前检查',
      readyCount: '可运行 {count}',
      blockedCount: '阻塞 {count}',
      completedCount: '完成 {count}',
      failedCount: '失败 {count}',
      metricReady: '可运行',
      metricBlocked: '阻塞',
      metricCompleted: '完成',
      metricFailed: '失败',
      summaryTitle: '流程运行建议',
      resourceTitle: '资源需求',
      resourceEmpty: '当前节点组合没有额外资源要求。',
      issueTitle: '检查项',
      noIssues: '当前没有阻塞问题，可以继续运行可执行节点。',
      viewNode: '查看节点',
      runReadyNodes: '运行可执行节点',
      applyAutoRepair: '一键补齐准备节点',
      autoRepairTitle: '可自动补齐',
      runHint: '会按依赖顺序运行已满足输入条件的节点，遇到失败会暂停。',
      hintRunning: '已有节点正在运行，建议等待当前任务结束后再继续。',
      hintBlocked: '可以先运行已就绪节点，阻塞节点会在上游产物生成后自动进入可运行状态。',
      hintReady: '当前已有节点满足运行条件，可以启动流程推进。',
      hintEmpty: '请先补齐工具选择、输入文件或上游产物，再启动流程。',
      fallback: {
        nodeTitle: '未命名节点',
        sourceNode: '上游节点',
        filename: '未知文件',
        toolSlug: '未指定工具',
        inputArtifact: '输入产物'
      },
      primary: {
        runnableNodes: '有 {count} 个节点可运行',
        missingWorkflowInput: '请先补齐工作流输入',
        invalidToolContract: '部分工具契约不可执行，请先修复节点工具配置',
        invalidSemanticEdge: '部分连线无效，请先修复节点依赖关系',
        needsPreparationOrConversion: '存在标准产物需要准备或转换',
        invalidArtifactBinding: '存在不可用的标准产物绑定',
        empty: '当前没有可运行节点'
      },
      issues: {
        missingTool: {
          title: '缺少工具选择',
          detail: '当前节点有多个候选工具，请先选择一个再运行。'
        },
        missingWorkflowInput: {
          title: '缺少工作流输入',
          detail: '请先为 {semanticType} 选择可用文件。'
        },
        waitingUpstream: {
          title: '等待上游产物',
          detail: '请先运行 {sourceNodeTitle}，成功后 {semanticType} 会自动绑定到当前节点。'
        },
        waitingInput: {
          title: '等待输入连线',
          detail: '当前节点声明了必需输入，但还没有配置可用的输入来源。'
        },
        invalidFileExtension: {
          title: '输入文件格式不匹配',
          detail: '所选文件 {filename} 不符合 {semanticType} 的扩展名要求。'
        },
        invalidSemanticEdge: {
          title: '连线产物类型无效',
          detail: '连线产物类型 {semanticType} 与上下游节点定义不匹配。'
        },
        invalidToolContract: {
          title: '工具契约不可执行',
          detail: '绑定工具 {toolSlug} 没有有效的工作流契约，或当前已被禁用。'
        },
        needsPreparation: {
          title: '需要先准备输入产物',
          detail: '当前节点输入产物不满足工具要求，请先运行匹配的准备工具。'
        },
        needsConversion: {
          title: '需要先转换输入产物',
          detail: '当前节点输入产物需要先完成格式转换，工具才能继续消费。'
        },
        invalidArtifactBinding: {
          title: '标准产物绑定无效',
          detail: '当前节点的标准产物绑定不可用，请重新选择输入或检查上游输出。'
        },
        running: {
          title: '节点正在运行',
          detail: '请等待当前任务结束后再调度下游节点。'
        },
        failed: {
          title: '节点任务失败',
          detail: '请先检查任务日志、参数或输入文件，再决定是否重新运行。'
        },
        invalidated: {
          title: '节点需要重新运行',
          detail: '上游输入或参数已发生变化，请重新运行当前节点以刷新结果。'
        }
      },
      savedBinding: {
        missing: '已保存的 {slotName} 绑定 {artifactId} 不在当前可用产物列表中，请重新选择输入。',
        mismatch: '已保存的 {slotName} 绑定 {artifactId} 与当前输入要求不匹配，请重新选择输入。'
      },
      binding: {
        suggestion: '建议运行：{suggestedTool}。',
        fallbackPreparation: '{target} 需要先完成准备。',
        fallbackConversion: '{target} 需要先完成转换。',
        fallbackInvalid: '{target} 绑定不可用。'
      }
    },
    inspector: {
      noSelectedNode: '未选择节点',
      configTab: '配置',
      dependenciesTab: '依赖',
      resultsTab: '结果',
      toolSelector: '工具选择',
      selectTool: '选择工具',
      noToolRequired: '当前节点无需工具。',
      nodeParameters: '节点参数',
      runWorkflow: '运行工作流',
      viewTaskDetail: '查看任务详情',
      recommendedEdges: '推荐连线',
      noRecommendedEdges: '暂无推荐连线',
      upstreamEdge: '上游连线',
      artifactFallback: '产物',
      deleteEdge: '删除连线',
      sourceNode: '上游节点',
      artifactType: '产物类型',
      addEdge: '添加连线',
      requiredInput: '必需输入',
      missingArtifact: '缺少上游产物',
      noRequiredInput: '当前节点无需输入',
      producedOutput: '产出结果',
      noProducedOutput: '当前节点暂无产出',
      taskResult: '任务结果',
      noTaskResult: '当前没有任务结果',
      outputFiles: '输出文件',
      downloadOutput: '下载输出',
      noOutputFiles: '当前还没有可下载的输出文件'
    },
    controlNodes: {
      title: '流程控制',
      condition: {
        title: '条件分支',
        description: '按分数或字段选择路径'
      },
      map: {
        title: '批量处理',
        description: '并行处理候选集合'
      },
      loop: {
        title: '循环优化',
        description: '重复运行内部工具直到达到收敛条件或迭代上限'
      }
    },
    runDetail: {
      title: '工作流运行详情',
      subtitle: '查看运行节点、任务和错误状态',
      canceled: '工作流运行已取消',
      nodeRetried: '工作流节点已重试'
    },
    resultsReport: {
      kicker: '结果中心',
      workflowNameFallback: '未命名工作流',
      reportTitleSuffix: '报告',
      decisionSummary: '决策摘要',
      export: '导出报告',
      nodeResults: '节点结果',
      successNodes: '成功节点',
      failedNodes: '失败节点',
      artifactSummary: '产物摘要',
      noArtifacts: '无产物',
      artifactSummaryLine: '共 {count} 个产物。',
      downloadFilename: 'workflow-report.md',
      table: {
        node: '节点',
        status: '状态',
        task: '任务',
        artifacts: '产物'
      },
      summary: {
        failed: '存在失败节点，建议先检查失败原因和输入产物。',
        ready: '已有可复核产物，可进入下一步筛选或团队评审。',
        empty: '暂无可用于决策的完整结果。'
      }
    },
    resultsSidebar: {
      tabs: {
        node: '节点结果',
        inputs: '运行配置',
        preflight: '预检',
        report: '结果报告',
        artifacts: '产物',
        history: '历史'
      }
    },
    inlinePreview: {
      empty: '暂无运行结果',
      running: '运行中',
      failed: '运行失败',
      failureFallback: '请查看任务日志定位失败原因。',
      expand: '放大查看',
      previewTitle: '结果预览',
      noPreviewableArtifacts: '任务已完成，暂无可预览产物'
    },
    runStatus: {
      pending: '等待中',
      ready: '就绪',
      running: '运行中',
      waiting_task: '等待任务',
      success: '已完成',
      failure: '失败',
      canceled: '已取消'
    },
    agent: {
      kicker: 'Project Agent',
      title: '项目智能体入口',
      subtitle: '选择项目并输入研究目标，平台会进入项目研究会话并使用新的 project agent-run 接口。',
      autoRouting: '项目会话',
      projectRequired: '智能体必须绑定项目',
      projectRequiredDescription: '智能体运行、审批、任务、产物和可视化统一回到项目上下文。',
      projectLabel: '所属项目',
      projectPlaceholder: '请选择项目',
      projectRequiredWarning: '请先选择项目',
      noProjects: '暂无可用项目，请先创建研究项目',
      draftWorkspace: '项目智能体',
      draftOnlyTitle: '进入项目研究页执行',
      draftOnlyDescription: 'Agent 执行统一放在项目研究页；任务、日志和产物都按项目权限与标准产物链路流转。',
      projectAgentTitle: '项目会话承载运行',
      projectAgentDescription: '这里不再创建旧智能体会话。进入项目研究页后选择标准蛋白产物并审批计划。',
      selectedProject: '当前项目：{name}',
      messageLabel: '研究目标',
      messagePlaceholder: '例如：说明研究目标与关注点，项目智能体会在研究页生成计划',
      inputType: '输入类型',
      proteinInput: '蛋白质 PDB',
      pocketInput: '口袋 PDB',
      fileLabel: '上传文件',
      inputFiles: '上传文件',
      selectInputFiles: '选择文件',
      fileAutoDetectHint: '自动识别文件类型：支持 PDB、CIF、SDF、CSV，草稿助手会结合文件名、内容和研究目标判断用途。',
      generationCount: '生成数量',
      generateDraft: '进入项目智能体',
      openProjectAgent: '进入项目智能体',
      projectRunHint: '输入文件与标准产物在项目研究页选择；这里仅创建项目会话并启动新 agent-run。',
      run: '进入项目智能体',
      sync: '刷新智能体',
      timeline: '草稿说明',
      analysis: 'LLM 分析过程',
      history: '草稿记录',
      noHistory: '暂无草稿记录',
      deleteHistory: '删除草稿记录',
      cascadeDeleteHistory: '同时清理关联记录',
      deleteHistoryConfirm: '确定删除这条草稿记录吗？',
      cascadeDeleteHistoryConfirm: '确定删除这条草稿记录，并同时清理关联记录吗？',
      empty: '生成草稿后会导入手动模式继续编辑。',
      noRun: '等待生成草稿',
      viewTask: '查看任务',
      uploadRequired: '请至少上传一个输入文件',
      loginRequired: '请先登录后进入项目智能体',
      defaultMessage: '根据项目产物和研究目标生成智能体执行计划',
      created: '工作流草稿已创建',
      draftGenerated: '项目智能体会话已创建',
      projectAgentOpened: '项目智能体会话已创建',
      deleted: '草稿记录已删除',
      cascadeDeleted: '草稿记录已删除，并清理 {tasks} 个任务、{artifacts} 个产物',
      pollFailed: '草稿状态刷新失败',
      pollRetryingHint: '平台会继续自动重试；如果状态长时间不更新，可以手动刷新。',
      pollSuspendedHint: '连续刷新失败，已暂停自动刷新，避免重复请求。请确认网络或后端服务恢复后手动刷新。',
      syncFailed: '刷新草稿失败，请稍后重试',
      status: {
        pending: '等待中',
        planning: '规划中',
        running: '运行中',
        waiting_task: '等待任务',
        success: '已完成',
        failure: '失败',
        canceled: '已取消'
      },
      stepStatus: {
        pending: '等待中',
        ready: '就绪',
        running: '运行中',
        waiting_task: '等待任务',
        success: '已完成',
        failure: '失败',
        skipped: '已跳过',
        canceled: '已取消'
      }
    },
    groups: {
      empty: '当前还没有可用分组',
      noTools: '当前分组下暂时没有可用工具',
      descriptionFallback: '这个分组正在等待管理员补充分组说明。',
      toolCount: '{count} 个工具',
      recommendedCount: '{count} 个推荐工具'
    },
    currentGroup: {
      label: '当前分组'
    },
    currentTool: {
      label: '当前工具',
      descriptionFallback: '请在当前分组内选择一个工具开始使用。',
      runAction: '运行当前工具',
      runHint: '支持本地上传，也支持直接复用“我的产物”中的历史输出文件。',
      viewDetail: '查看工具详情',
      viewTask: '查看任务详情',
      lastTask: '最近一次任务',
      preflightTitle: '运行前检查',
      preflightHint: '根据工具契约检查必需输入、可复用产物和预期输出。',
      preflightReady: '可运行',
      preflightMissing: '需补充输入',
      matchedInput: '已匹配',
      missingInput: '缺少输入',
      invalidInputFormat: '格式不匹配',
      expectedOutputs: '预期输出',
      empty: '请选择当前分组中的一个工具'
    },
    toolStatus: {
      recommended: '推荐',
      available: '可用',
      unavailable: '暂未上线',
      availableCount: '{count} 个可用工具',
      missingCount: '{count} 个暂未上线'
    },
    boundSources: {
      title: '当前自动绑定来源',
      waiting: '等待上游结果'
    },
    artifacts: {
      currentGroup: '当前分组产物',
      recentGroup: '我的最近产物',
      emptyCurrentGroup: '当前分组还没有可复用产物',
      emptyRecent: '你还没有可复用的历史输出文件',
      ungroupedGroup: '未分组工具',
      locatePath: '定位到表单',
      taskLabel: '任务',
      sourceToolLabel: '来源工具',
      generatedAtLabel: '生成时间',
      sourceTool: '来源工具：{tool}',
      generatedAt: '生成时间：{time}',
      taskCount: '{count} 个产物',
      moreArtifacts: '还有 {count} 个产物，进入任务详情查看'
    },
    steps: workflowSteps,
    nodes: {
      inputProtein: {
        title: '蛋白结构输入',
        description: '上传或选择 Protein PDB 文件，作为口袋识别和对接的公共输入。'
      },
      inputPocket: {
        title: '口袋结构输入',
        description: '上传或选择 Pocket PDB 文件，直接进入分子生成阶段。'
      },
      inputLigand: {
        title: '配体结构输入',
        description: '上传候选配体结构文件，用于后续对接或分析。'
      },
      inputGeneratedLigand: {
        title: '候选分子输入',
        description: '复用历史生成分子或上传候选分子文件，用于下游评估。'
      },
      fetchPubChem: {
        title: 'Fetch PubChem Ligand',
        description: '按 PubChem CID 获取配体结构，输出标准 ligand_structure@1。'
      },
      ligandPreparation: {
        title: 'Ligand Preparation',
        description: '对配体进行加氢、构象和格式准备，保留标准配体结构。'
      },
      sdfToSmiles: {
        title: 'SDF 转 SMILES 表',
        description: '把配体结构转换为 MolP-PC 和 RDKit 可复用的 molecule_table@1。'
      },
      rdkitProperties: {
        title: 'RDKit Properties',
        description: '计算基础理化描述符，作为 ADMET 前的独立性质步骤。'
      },
      molpPcAdmet: {
        title: 'MolP-PC 基础 ADMET',
        description: '使用已登记的 MolP-PC 工具输出 ADMET 表格和科学说明附件。'
      },
      resultSummary: {
        title: '优化结果汇总',
        description: '汇总最终先导优化结果与关键输出，便于复核与导出。'
      },
      resultPocket: {
        title: '口袋结果',
        description: '查看口袋预测结果，为下游分子生成准备输入。'
      },
      resultGeneratedLigand: {
        title: '分子生成结果',
        description: '查看生成的候选分子，供后续对接或性质预测复用。'
      },
      resultDocking: {
        title: '对接结果',
        description: '查看对接姿态与亲和力输出，辅助筛选候选分子。'
      },
      resultProperty: {
        title: '性质预测结果',
        description: '查看理化与 ADMET 预测结果，辅助后续决策。'
      },
      resultAdmet: {
        title: '基础 ADMET 结果',
        description: '查看 MolP-PC 输出的预测表格、模型版本和科学说明附件。'
      }
    },
    columns: {
      groups: '工具分组',
      groupsHint: '按研究主题查看可用工具与推荐项，不强制固定执行顺序。',
      tools: '工具与参数',
      toolsHint: '在当前分组中选择工具、填写参数，并按需复用历史产物文件。',
      artifacts: '我的产物',
      artifactsHint: '这里展示你自己的历史输出文件，可在任意工具的文件参数中直接复用。'
    }
  },

  // 认证
  auth: {
    login: '登录',
    register: '注册',
    forgotPassword: '忘记密码',
    forgotPasswordDesc: '输入您注册时使用的邮箱，我们将发送重置密码的验证码',
    username: '用户名',
    email: '邮箱',
    password: '密码',
    confirmPassword: '确认密码',
    newPassword: '新密码',
    confirmNewPassword: '确认新密码',
    rememberMe: '记住我',
    noAccount: '没有账号？',
    hasAccount: '已有账号？',
    goRegister: '立即注册',
    goLogin: '立即登录',
    loginSuccess: '登录成功',
    registerSuccess: '注册成功',
    logoutSuccess: '退出成功',
    loginRequired: '请先登录',
    // 验证码
    verificationCode: '验证码',
    sendCode: '发送验证码',
    codeSent: '验证码已发送',
    resendCode: '重新发送',
    resendCodeIn: '{seconds}秒后重新发送',
    invalidCode: '验证码错误或已过期',
    // 密码强度
    passwordWeak: '弱',
    passwordMedium: '中',
    passwordStrong: '强',
    passwordVeryStrong: '非常强',
    // 找回密码步骤
    step1Email: '填写邮箱',
    step2Verify: '验证身份',
    step3Reset: '重置密码',
    sendResetCode: '发送重置验证码',
    codeSentTo: '验证码已发送至 {email}',
    verifyCode: '验证',
    resetPassword: '重置密码',
    resetSuccess: '密码重置成功',
    resetSuccessDesc: '您的密码已成功重置，请使用新密码登录',
    // 用户协议
    agreementPrefix: '我已阅读并同意',
    termsOfService: '服务条款',
    agreementAnd: '和',
    privacyPolicy: '隐私政策',
    validation: {
      usernameRequired: '请输入用户名',
      usernameLength: '用户名长度为 3-20 个字符',
      usernameFormat: '用户名只能包含字母、数字和下划线',
      emailRequired: '请输入邮箱',
      emailInvalid: '请输入有效的邮箱地址',
      passwordRequired: '请输入密码',
      passwordLength: '密码长度至少为 6 个字符',
      confirmPasswordRequired: '请确认密码',
      passwordMismatch: '两次输入的密码不一致',
      codeRequired: '请输入验证码',
      codeLength: '验证码为6位数字',
      agreementRequired: '请阅读并同意服务条款和隐私政策'
    }
  },

  // 工具
  tools: {
    title: '工具',
    subtitle: '发现和使用强大的计算生物学工具',
    detail: '工具详情',
    list: '工具列表',
    search: '搜索工具...',
    category: '分类',
    allCategories: '全部分类',
    tags: '标签',
    filterTags: '按标签筛选',
    usageCount: '使用次数',
    viewCount: '浏览次数',
    viewDetail: '查看详情',
    runCount: '运行次数',
    runs: '次运行',
    favoriteCount: '收藏数',
    version: '版本',
    changelog: '更新日志',
    gpuRequirements: 'GPU 要求',
    gpuMemory: 'GPU 显存',
    timeout: '超时时间',
    toolInfo: '工具信息',
    status: '状态',
    favorite: '收藏',
    unfavorite: '取消收藏',
    run: '运行',
    parameters: '参数设置',
    inputFiles: '输入文件',
    submit: '提交任务',
    history: '历史版本',
    noTools: '暂无工具',
    // 工具视图
    publicTools: '公开工具',
    myTools: '我的工具',
    favorites: '收藏夹',
    favoriteTools: '我的收藏',
    customTools: '自定义工具',
    allTools: '全部',
    // 工具来源
    providerType: {
      platform: '官方',
      user: '社区'
    },
    // 审核状态
    reviewStatus: {
      all: '全部状态',
      not_required: '无需审核',
      pending: '待审核',
      approved: '已通过',
      rejected: '已拒绝'
    },
    // 审核相关
    submitReview: '提交审核',
    resubmitReview: '重新提交',
    reviewPending: '审核中，请耐心等待',
    reviewRejected: '审核未通过',
    rejectReason: '拒绝原因',
    // 创建/编辑工具
    createTool: '创建工具',
    editTool: '编辑工具',
    basicInfo: '基本信息',
    toolName: '工具名称',
    toolNamePlaceholder: '请输入工具名称',
    toolSlug: '工具标识',
    toolSlugPlaceholder: '请输入工具标识（英文小写、数字、短横线）',
    slugHint: '用于URL中标识工具，只能包含小写字母、数字和短横线',
    descriptionPlaceholder: '请输入工具描述...',
    selectCategory: '请选择分类',
    selectTags: '请选择标签',
    icon: '图标',
    iconUrl: '图标URL',
    iconPlaceholder: '输入 emoji 或留空',
    iconHint: '支持 emoji 表情作为图标',
    iconUrlPlaceholder: '输入图标URL（可选）',
    runConfig: '运行配置',
    gpuRequired: '需要 GPU',
    gpuMemoryMb: 'GPU 显存 (MB)',
    timeoutSec: '超时时间 (秒)',
    isPublic: '公开工具',
    publicYes: '公开（其他用户可见）',
    publicNo: '私有（仅自己可见）',
    // 验证消息
    nameRequired: '请输入工具名称',
    nameLength: '工具名称长度为 2-100 个字符',
    slugRequired: '请输入工具标识',
    slugFormat: '工具标识只能包含小写字母、数字和短横线',
    slugLength: '工具标识长度为 2-50 个字符',
    descriptionLength: '描述最多 500 个字符',
    // 操作结果
    createSuccess: '工具创建成功',
    updateSuccess: '工具更新成功',
    loadFailed: '加载工具信息失败',
    // 排序
    sortPopular: '按热度',
    sortNewest: '按最新',
    sortName: '按名称',
    // 空状态
    noFavorites: '暂无收藏的工具',
    noCustomTools: '暂无自定义工具',
    browseTools: '浏览工具',
    fileSourceUpload: '本地上传',
    fileSourceArtifact: '我的产物',
    selectArtifact: '选择历史产物',
    noArtifacts: '暂无可复用产物',
    selectCompatibleArtifact: '按层级选择兼容产物',
    selectArtifactGroup: '先选择工具分组',
    selectArtifactTool: '再选择工具',
    selectArtifactTask: '再选择任务',
    selectArtifactOutput: '最后选择产物',
    artifactGroupLabel: '工具分组',
    artifactToolLabel: '工具',
    artifactTaskLabel: '任务',
    artifactOutputLabel: '产物',
    artifactGroupMeta: '按工作台分组浏览可复用来源',
    artifactToolMeta: '查看该工具下的历史任务',
    artifactSelectedTag: '已选中',
    clearArtifactSelection: '清除产物选择',
    artifactFocusTag: '右侧定位',
    artifactSummarySelected: '当前已选产物',
    artifactSummaryFocused: '右侧已定位到来源路径',
    artifactSummaryPending: '当前路径',
    noCompatibleArtifacts: '没有匹配当前输入格式的任务产物',
    // 工具详情
    free: '免费',
    introduction: '工具介绍',
    viewIntroduction: '工具介绍',
    documentationMarkdown: '介绍文档 Markdown',
    documentationMarkdownHint: '支持 Markdown。内容将随当前工具版本保存，修改后需要创建新版本。',
    modelOverview: '模型介绍',
    parameterDocs: '参数说明',
    outputDocs: '输出文件',
    outputPatterns: '输出路径规则',
    defaultValue: '默认值',
    fieldType: '类型',
    valueRange: '范围',
    noDocumentation: '暂无详细介绍',
    features: '功能特点',
    howToUse: '使用方法',
    step: '步骤',
    references: '参考文献',
    paper: '论文',
    documentation: '文档',
    relatedTools: '相关工具',
    noRelatedTools: '暂无相关工具',
    formatInfo: '格式说明',
    inputFormats: '支持的输入格式',
    outputFormats: '输出格式',
    selectFile: '选择文件',
    loadExample: '加载示例参数',
    exampleInput: '示例输入',
    viewExample: '查看示例',
    hideExample: '收起示例',
    exampleParams: '示例参数',
    exampleFiles: '示例文件',
    useExample: '使用示例',
    exampleHint: '可一键填充示例参数并绑定示例输入文件',
    exampleFileBound: '已绑定示例文件',
    exampleFileMissing: '文件缺失',
    exampleFilePreview: '示例文件预览',
    preview: '预览',
    previewUnavailable: '不可预览',
    previewTruncated: '文件较大，仅展示前 64KB 内容',
    exampleLoaded: '已加载示例参数',
    runTool: '运行工具',
    switchingVersion: '切换到版本 {version}',
    avgDuration: '平均耗时'
  },

  // 任务
  tasks: {
    title: '任务中心',
    subtitle: '管理和监控您的计算任务',
    detail: '任务详情',
    taskDetail: '任务详情',
    list: '任务列表',
    create: '创建任务',
    name: '任务名称',
    namePlaceholder: '可选，留空将自动生成',
    // 标签页
    allTasks: '全部任务',
    runningTasks: '运行中',
    attentionTasks: '需要关注',
    historyTasks: '历史任务',
    // 状态
    status: {
      pending: '等待中',
      running: '运行中',
      success: '已完成',
      failure: '失败',
      canceled: '已取消'
    },
    statusPending: '等待中',
    statusRunning: '运行中',
    statusSuccess: '已完成',
    statusFailure: '失败',
    statusCanceled: '已取消',
    // 筛选
    searchPlaceholder: '搜索任务名称或ID...',
    filterByTool: '按工具筛选',
    startDate: '开始日期',
    endDate: '结束日期',
    workflowScope: {
      active: '已按工作流上下文过滤：{scope}',
      run: '运行 {id}',
      definition: '流程 {id}',
      node: '节点 {id}'
    },
    // 监控
    realTimeMonitor: '实时监控',
    autoRefreshOn: '自动刷新',
    autoRefreshOff: '手动刷新',
    // 操作
    progress: '进度',
    logs: '日志',
    result: '结果',
    inputParams: '输入参数',
    inputFiles: '输入文件',
    outputFiles: '输出文件',
    outputResults: '输出结果',
    resultVisualization: '结果可视化',
    csvPreview: 'CSV 结果预览',
    csvVisualizationHint: '检测到 CSV 结果后，将按表格展示数据，并在可识别的 SMILES 列旁直接渲染二维分子结构。',
    csvSummary: '共 {rows} 行，{columns} 列。表格区域支持独立滚动，便于浏览长结果集。',
    csvStructure: '分子结构',
    csvLoadFailed: 'CSV 结果加载失败',
    csvEmpty: 'CSV 结果为空',
    csvEmptyDesc: '当前结果文件没有可展示的数据行，请先检查工具输出是否正常。',
    csvFileMissing: '缺少 CSV 文件下载地址',
    jsonResultFields: '{count} 个字段',
    jsonResultItems: '{count} 项',
    jsonResultRaw: '原始 JSON',
    visualizationHint: '系统会优先叠加输入口袋与生成分子，便于快速检查构象与结合位置。',
    visualizationFiles: '可视化文件',
    visualizationSelectableHint: '检测到多个三维结果，输入结构会保持固定，点击列表即可逐个查看生成分子或对接姿态。',
    visualizationResultList: '输出结果列表',
    visualizationResultListDesc: '共 {count} 个结果项，当前三维视图一次只展示选中的一个输出。',
    visualizationInputPinned: '固定输入结构',
    visualizationLoading: '正在加载三维结果...',
    visualizationFailed: '三维结果加载失败',
    visualizationUnsupported: '当前输出文件暂不支持在线预览',
    visualizationUnsupportedDesc: '目前已接入 PDB / mmCIF / PDBQT / SDF / MOL2 在线可视化，其它格式仍可直接下载。',
    visualizationPartialSupport: '部分结果文件未接入在线预览',
    visualizationPartialSupportDesc: '已优先展示可识别的结构或分子文件，其余文件请通过下方下载查看。',
    cancel: '取消',
    retry: '重试',
    delete: '删除',
    download: '下载',
    downloadAll: '下载全部',
    exportMolpPcCsv: '导出 MolP-Pc CSV',
    exportMolpPcCsvSuccess: '已导出 MolP-Pc CSV',
    exportMolpPcCsvNoSource: '没有可用于导出的 CSV 产物',
    exportMolpPcCsvNoSmiles: '当前 CSV 产物缺少 SMILES 列，无法导出 MolP-Pc CSV',
    scientificAttachments: '科学附件引用',
    scientificModelCard: '模型卡',
    scientificVerificationRecord: '验证记录',
    scientificEvidenceLevel: '证据等级',
    standardArtifactsMissing: '标准产物缺失或不合规',
    failureStderr: '错误输出 stderr',
    failureStdout: '标准输出 stdout',
    allTaskTypes: '全部类型',
    agentTasks: '智能体任务',
    standaloneToolTasks: '独立工具任务',
    agentRun: '智能体会话',
    agentRunSteps: '会话工具任务',
    agentRunProgress: '{completed}/{total} 步完成，{failed} 步失败',
    agentViewTask: '查看任务',
    agentNoLinkedTask: '暂无关联任务',
    viewDetail: '查看详情',
    viewTool: '查看工具',
    goToTools: '去创建任务',
    // 确认
    cancelConfirm: '确定取消此任务？',
    cancelConfirmContent: '取消后任务将停止运行，已产生的结果可能会丢失。',
    deleteConfirm: '确定删除此任务？',
    deleteConfirmContent: '删除后任务记录将无法恢复。',
    retryConfirm: '确定重试此任务？',
    // 成功消息
    cancelSuccess: '任务已取消',
    deleteSuccess: '任务已删除',
    retrySuccess: '任务已重新提交',
    // 时间
    createdAt: '创建时间',
    startedAt: '开始时间',
    completedAt: '完成时间',
    duration: '耗时',
    runningTime: '运行时长',
    // 时间轴
    timeline: '任务时间线',
    created: '任务创建',
    started: '开始执行',
    completed: '执行完成',
    failed: '执行失败',
    canceled: '已取消',
    // 工具信息
    toolInfo: '工具信息',
    toolNotFound: '工具信息不可用',
    unknownTool: '未知工具',
    // 错误
    errorMessage: '错误信息',
    noLogs: '暂无日志',
    moreLogs: '还有 {count} 条日志，进入任务详情查看完整日志',
    notFound: '任务不存在',
    notFoundDesc: '您查找的任务可能已被删除或不存在',
    // 空状态
    noTasks: '暂无任务',
    noRunningTasks: '当前没有运行中的任务',
    noAttentionTasks: '当前没有需要关注的失败任务',
    noHistoryTasks: '暂无历史任务'
  },

  // 用户中心
  user: {
    title: '用户中心',
    profile: '个人资料',
    settings: '账户设置',
    favorites: '我的收藏',
    // 个人资料
    changePassword: '修改密码',
    oldPassword: '原密码',
    newPassword: '新密码',
    avatar: '头像',
    uploadAvatar: '上传头像',
    avatarUploaded: '头像上传成功',
    avatarUploadFailed: '头像上传失败',
    avatarTypeError: '只能上传图片文件',
    avatarSizeError: '图片大小不能超过2MB',
    createdAt: '注册时间',
    changeEmail: '修改邮箱',
    newEmail: '新邮箱',
    verifyCode: '验证码',
    sendCode: '发送验证码',
    enterNewEmail: '请输入新邮箱',
    codeSent: '验证码已发送',
    emailChanged: '邮箱修改成功',
    enterOldPassword: '请输入原密码',
    passwordChanged: '密码修改成功',
    // 设置
    notificationSettings: '通知设置',
    emailNotification: '邮件通知',
    taskCompleteNotify: '任务完成通知',
    taskFailNotify: '任务失败通知',
    systemNotify: '系统通知',
    marketingNotify: '营销通知',
    privacySettings: '隐私设置',
    profileVisibility: '个人资料可见性',
    public: '公开',
    friendsOnly: '仅好友可见',
    private: '仅自己可见',
    showTaskHistory: '显示任务历史',
    accountSecurity: '账号安全',
    twoFactorAuth: '两步验证',
    twoFactorAuthDesc: '启用两步验证提高账号安全性',
    twoFactorSetup: '正在配置两步验证...',
    disableTwoFactor: '关闭两步验证',
    disableTwoFactorDesc: '关闭后账号安全性将降低，确定要关闭吗？',
    twoFactorDisabled: '两步验证已关闭',
    loginDevices: '登录设备',
    loginDevicesDesc: '管理您账号的登录设备',
    manage: '管理',
    currentDevice: '当前设备',
    logoutDevice: '下线',
    logoutDeviceConfirm: '确定要将此设备下线吗？',
    deviceLoggedOut: '设备已下线',
    deleteAccount: '注销账号',
    deleteAccountDesc: '注销后账号数据将无法恢复',
    deleteAccountConfirm: '确定要注销账号吗？',
    deleteAccountConfirmContent: '注销后您的所有数据将被永久删除，此操作不可撤销。',
    confirmDelete: '确认注销',
    deleteAccountProcess: '正在处理注销请求...',
    // 收藏
    noFavorites: '暂无收藏的工具',
    exploreTool: '去发现工具',
    unfavoriteConfirm: '确定取消收藏？',
    unfavoriteConfirmContent: '取消收藏后可以随时重新收藏',
    unfavoriteSuccess: '已取消收藏',
    // 退出
    logoutConfirm: '确定要退出登录吗？',
    logoutConfirmContent: '退出后需要重新登录才能使用完整功能',
    // 角色
    role: {
      user: '普通用户',
      admin: '管理员'
    }
  },

  // 管理后台
  admin: {
    title: '管理后台',
    dashboard: '仪表盘',
    dashboardSubtitle: '集中查看用户、工具与任务运行情况，快速判断平台健康度',
    users: '用户管理',
    tools: '工具管理',
    tasks: '任务管理',
    system: '系统设置',
    backToSite: '返回前台',
    stats: {
      totalUsers: '用户总数',
      totalTools: '工具总数',
      totalTasks: '任务总数',
      activeTasks: '活跃任务',
      gpuUsage: 'GPU 使用率',
      storageUsage: '存储使用'
    },
    // 仪表盘
    todayNew: '今日新增',
    activeCount: '活跃数',
    runningNow: '正在运行',
    taskTrend: '任务趋势',
    taskCount: '任务数量',
    successRate: '成功率',
    systemStatus: '系统状态',
    cpuUsage: 'CPU使用率',
    memoryUsage: '内存使用率',
    diskUsage: '磁盘使用率',
    gpuMemory: 'GPU显存',
    serviceStatus: '服务状态',
    running: '运行中',
    stopped: '已停止',
    recentTasks: '最近任务',
    recentUsers: '最近用户',
    toolName: '工具名称',
    role: '角色',
    registerTime: '注册时间',
    // 用户管理
    createUser: '创建用户',
    editUser: '编辑用户',
    userInfo: '用户信息',
    keyword: '关键词',
    searchUserPlaceholder: '搜索用户名或邮箱...',
    status: '状态',
    active: '活跃',
    disabled: '已禁用',
    inactive: '未激活',
    banned: '已封禁',
    pending: '待审核',
    createUserSuccess: '用户创建成功',
    selectRole: '请选择角色',
    selectStatus: '请选择状态',
    resetPassword: '重置密码',
    resetPasswordConfirm: '确定要重置密码吗？',
    resetPasswordConfirmContent: '将为用户 {username} 重置密码',
    resetPasswordSuccess: '密码已重置',
    softDeleteUser: '软删除',
    softDeleteUserConfirm: '确定要软删除此用户吗？',
    softDeleteUserConfirmContent: '软删除后用户 {username} 将无法登录，但相关数据会保留',
    softDeleteUserSuccess: '用户已软删除',
    hardDeleteUser: '真删除',
    hardDeleteUserConfirm: '确定要彻底删除此用户吗？',
    hardDeleteUserConfirmContent: '彻底删除用户 {username} 后，将级联清理其任务、文件、工具和会话数据，且无法恢复',
    hardDeleteUserSuccess: '用户已彻底删除',
    banUser: '封禁用户',
    banUserConfirm: '确定要封禁此用户吗？',
    banUserConfirmContent: '封禁后用户 {username} 将无法登录',
    banUserSuccess: '用户已封禁',
    unbanUser: '解除封禁',
    unbanUserSuccess: '已解除封禁',
    deleteUserConfirm: '确定要删除此用户吗？',
    deleteUserConfirmContent: '删除用户 {username} 后，其所有数据将被清除',
    // 工具管理
    createTool: '创建工具',
    editTool: '编辑工具',
    importToolConfig: '导入配置',
    importToolConfigTitle: '导入 platform_tool.json',
    importToolConfigDescription: '粘贴或读取 AI 生成的 platform_tool.json，系统会自动校验并创建工具与版本',
    importToolConfigPlaceholder: '请粘贴完整的 platform_tool.json 内容',
    importToolConfigFromFile: '从 JSON 文件读取',
    importToolConfigPublish: '导入后直接发布',
    importToolConfigSuccess: '工具配置导入成功',
    importToolConfigRequired: '请先粘贴 platform_tool.json 内容',
    importToolConfigInvalid: 'platform_tool.json 不是有效的 JSON',
    toolsSubtitle: '统一维护工具目录与分类归属',
    toolPackages: 'Tool Package',
    toolPackagesSubtitle: '以标准 Artifact 与模型侧 adapter 作为新模型部署主路径',
    workbenchGroups: '工作台分组',
    workbenchGroupsSubtitle: '维护工具工作台分组、推荐顺序与映射关系',
    toolCategories: '分类管理',
    toolCategoriesSubtitle: '集中维护工具分类、状态与排序',
    createCategory: '新建分类',
    editCategory: '编辑分类',
    categoryName: '分类名称',
    categorySlug: '分类标识',
    enterCategoryName: '请输入分类名称',
    enterCategorySlug: '请输入分类标识',
    invalidCategorySlug: '分类标识只能包含小写字母、数字和连字符',
    deleteCategoryConfirm: '确定要删除此分类吗？',
    deleteCategoryConfirmContent: '删除分类 {name} 后将无法恢复',
    searchToolPlaceholder: '搜索工具名称或代码...',
    categoryStructure: '结构预测',
    categoryDocking: '分子对接',
    categorySequence: '序列分析',
    categoryVisualization: '可视化',
    maintenance: '维护中',
    statistics: '统计',
    toolCode: '工具代码',
    enterToolName: '请输入工具名称',
    enterToolCode: '请输入工具代码',
    enterDescription: '请输入描述',
    selectCategory: '请选择分类',
    enterVersion: '请输入版本号',
    enterServiceUrl: '请输入服务地址',
    serviceUrl: '服务地址',
    gpuRequired: '需要GPU',
    configParams: '配置参数',
    paramsConfigTip: '请输入工具参数的JSON Schema配置',
    paramsJsonPlaceholder: '请输入有效的JSON格式参数配置',
    invalidJson: 'JSON格式无效',
    deactivate: '停用',
    activate: '启用',
    setMaintenance: '设为维护',
    deleteToolConfirm: '确定要删除此工具吗？',
    deleteToolConfirmContent: '删除工具 {name} 后，相关任务记录将被保留',
    // 任务管理
    totalTasks: '总任务数',
    runningTasks: '运行中',
    pendingTasks: '等待中',
    failedTasks: '失败',
    searchTaskPlaceholder: '搜索任务名称或ID...',
    tool: '工具',
    user: '用户',
    dateRange: '日期范围',
    taskInfo: '任务信息',
    clearCompleted: '清理已完成',
    clearCompletedConfirm: '确定要清理已完成的任务吗？',
    clearCompletedConfirmContent: '将删除所有已完成、失败和已取消的任务记录',
    selected: '已选择 {count} 项',
    batchCancel: '批量取消',
    batchDelete: '批量删除',
    batchCancelConfirm: '确定要批量取消选中的任务吗？',
    batchDeleteConfirm: '确定要批量删除选中的任务吗？',
    // 系统设置
    generalSettings: '基本设置',
    taskSettings: '任务设置',
    storageSettings: '存储设置',
    emailSettings: '邮件设置',
    systemInfo: '系统信息',
    systemSubtitle: '管理运行状态、配置快照与 Agent 模型服务',
    systemOverview: '系统概览',
    modelServices: '模型服务',
    modelServicesSubtitle: '配置 Agent 自动规划时使用的 OpenAI-compatible 模型服务',
    createModelService: '新增模型服务',
    editModelService: '编辑模型服务',
    providerType: '服务类型',
    baseUrl: 'Base URL',
    modelName: '模型名称',
    apiKey: 'API Key',
    apiKeyPlaceholder: '留空则保留原 API Key',
    defaultService: '默认服务',
    enabled: '启用',
    timeoutSeconds: '超时时间',
    maxTokens: '最大 Tokens',
    temperature: '温度',
    runtimeSettings: '运行参数',
    lastTest: '最近测试',
    setDefault: '设为默认',
    modelServiceCreated: '模型服务已创建',
    modelServiceUpdated: '模型服务已更新',
    modelServiceDeleted: '模型服务已删除',
    defaultModelServiceUpdated: '默认模型服务已更新',
    confirmDeleteModelService: '确定要删除该模型服务吗？',
    noApiKey: '未配置 Key',
    configuredApiKey: '已配置 Key',
    siteSettings: '站点设置',
    siteName: '站点名称',
    siteDescription: '站点描述',
    contactEmail: '联系邮箱',
    allowRegistration: '允许注册',
    maintenanceMode: '维护模式',
    maintenanceModeDesc: '启用后普通用户将无法访问站点',
    taskConfig: '任务配置',
    maxConcurrentTasks: '最大并发任务数',
    maxConcurrentTasksDesc: '系统同时运行的最大任务数量',
    taskTimeout: '任务超时时间',
    minutes: '分钟',
    days: '天',
    maxRetries: '最大重试次数',
    cleanupDays: '自动清理天数',
    cleanupDaysDesc: '超过此天数的已完成任务将被自动清理',
    runtimeStats: '运行统计',
    configSnapshot: '配置快照',
    environment: '运行环境',
    debugMode: '调试模式',
    hostname: '主机名',
    cacheBackend: '缓存后端',
    storageBackend: '存储后端',
    taskQueue: '任务队列',
    cpuCount: 'CPU核心数',
    memoryTotal: '总内存',
    memoryAvailable: '可用内存',
    diskTotal: '磁盘总量',
    diskFree: '磁盘可用',
    totalFiles: '文件总数',
    activeConnections: '活动连接数',
    storageConfig: '存储配置',
    storageType: '存储类型',
    localStorage: '本地存储',
    storagePath: '存储路径',
    endpoint: '服务端点',
    accessKey: '访问密钥',
    secretKey: '密钥',
    bucket: '存储桶',
    maxFileSize: '最大文件大小',
    testConnection: '测试连接',
    connectionSuccess: '连接成功',
    smtpConfig: 'SMTP配置',
    smtpHost: 'SMTP服务器',
    smtpPort: 'SMTP端口',
    smtpUser: 'SMTP用户名',
    smtpPassword: 'SMTP密码',
    senderName: '发件人名称',
    senderEmail: '发件人邮箱',
    useTLS: '使用TLS',
    sendTestEmail: '发送测试邮件',
    testEmailSent: '测试邮件已发送',
    version: '版本',
    buildTime: '构建时间',
    pythonVersion: 'Python版本',
    nodeVersion: 'Node版本',
    os: '操作系统',
    uptime: '运行时间',
    database: '数据库',
    redis: 'Redis',
    gpuInfo: 'GPU信息',
    gpuName: 'GPU名称',
    gpuUtilization: 'GPU利用率',
    gpuTemperature: '温度'
  },

  // 错误页面
  error: {
    forbidden: '无权限访问',
    notFound: '页面不存在',
    serverError: '服务器错误',
    backHome: '返回首页',
    '403': {
      title: '403',
      description: '抱歉，您没有权限访问此页面'
    },
    '404': {
      title: '404',
      description: '抱歉，您访问的页面不存在'
    }
  },

  // 页脚
  footer: {
    copyright: '© 2024 CPUModel. 保留所有权利。',
    about: '关于我们',
    contact: '联系我们',
    docs: '文档',
    privacy: '隐私政策',
    terms: '服务条款'
  }
}
