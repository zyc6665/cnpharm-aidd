const workflowSteps = {
  pocketExploration: {
    title: 'Pocket Exploration',
    description: 'Identify binding pockets and druggable target regions from structural data'
  },
  moleculeGenerationOrVirtualScreening: {
    title: 'Molecule Generation or Virtual Screening',
    description: 'Generate pocket-aware candidates or narrow the search space rapidly through virtual screening'
  },
  molecularDockingAndAffinityPrediction: {
    title: 'Molecular Docking and Binding Affinity Prediction',
    description: 'Evaluate binding poses against target pockets and estimate potential binding affinity'
  },
  propertyPrediction: {
    title: 'Property Prediction',
    description: 'Predict potency, physicochemical traits and ADMET-related performance'
  },
  leadOptimization: {
    title: 'Lead Optimization',
    description: 'Iterate on multi-objective results to refine and prioritize lead compounds'
  }
}

export default {
  // Common
  common: {
    theme: 'Theme',
    confirm: 'Confirm',
    cancel: 'Cancel',
    save: 'Save',
    delete: 'Delete',
    edit: 'Edit',
    create: 'Create',
    search: 'Search',
    reset: 'Reset',
    submit: 'Submit',
    back: 'Back',
    loading: 'Loading...',
    success: 'Operation successful',
    error: 'Operation failed',
    noData: 'No data',
    more: 'More',
    all: 'All',
    actions: 'Actions',
    status: 'Status',
    time: 'Time',
    name: 'Name',
    description: 'Description',
    home: 'Home',
    refresh: 'Refresh',
    refreshSuccess: 'Refreshed successfully',
    download: 'Download',
    clear: 'Clear',
    expand: 'Expand sidebar',
    collapse: 'Collapse sidebar',
    totalItems: 'Total {total} items',
    copySuccess: 'Copied to clipboard',
    required: 'is required',
    optional: 'Optional',
    createdAt: 'Created At',
    updatedAt: 'Updated At',
    seconds: 'seconds',
    sort: 'Sort'
  },

  // Navigation
  nav: {
    home: 'Home',
    workspace: 'Workspace',
    tools: 'Tools',
    cpupdb: 'CPUPDB',
    tasks: 'Tasks',
    workflow: 'Workflow',
    admin: 'Admin',
    login: 'Login',
    register: 'Register',
    logout: 'Logout',
    profile: 'Profile',
    settings: 'Settings',
    favorites: 'Favorites'
  },
  command: {
    placeholder: 'Search pages, commands…',
    noResults: 'No results',
    newTask: 'New Task',
    toggleTheme: 'Toggle Theme',
    group: {
      navigate: 'Navigation',
      actions: 'Actions'
    }
  },

  // Workspace
  workspace: {
    title: 'Workspace',
    researchTitle: 'Research Projects',
    createProject: 'New Project',
    recentProjects: 'Recent Projects',
    projectCount: '{count} accessible projects',
    continueResearch: 'Continue',
    openProject: 'Overview',
    emptyProjects: 'No research projects yet',
    attentionTitle: 'Approvals & Failed Tasks',
    emptyAttention: 'No pending approvals or failed tasks',
    pendingApproval: 'Pending approval',
    taskNeedsAttention: 'Needs attention',
    recentArtifacts: 'Recent Artifacts',
    emptyArtifacts: 'No artifacts yet',
    unknownArtifactType: 'Unknown type',
    loadFailed: 'Research workspace failed to load',
    loadFailedHint: 'Latest project data is unavailable. Check your connection and retry.',
    overviewLoadFailed: 'Tasks and artifacts are temporarily unavailable',
    overviewLoadFailedHint: 'Projects loaded, but task and artifact overview failed. Retry when the service recovers.',
    schemaMigrationLoadFailed: 'Database migration is incomplete',
    schemaMigrationLoadFailedHint: 'The current database schema is behind the backend code. Run Alembic migrations before refreshing the workspace.',
    retry: 'Retry',
    project: {
      name: 'Project name',
      namePlaceholder: 'For example: EGFR pocket study',
      nameRequired: 'Enter a project name',
      goal: 'Research goal',
      goalPlaceholder: 'Describe the scientific question or expected result',
      noGoal: 'No research goal set',
      createFailed: 'Project creation failed. Please retry.',
      archive: 'Archive',
      archiveSuccess: 'Research project archived',
      archiveFailed: 'Project archive failed. Please retry.',
      deleteConfirm:
        'Delete this research project? Linked workflows and project records cannot be recovered.',
      deleteSuccess: 'Research project deleted',
      deleteFailed: 'Project deletion failed. Please retry.',
      status: {
        draft: 'Draft',
        active: 'Active',
        completed: 'Completed',
        archived: 'Archived',
        frozen: 'Frozen'
      }
    },
    goodMorning: 'Good morning',
    goodAfternoon: 'Good afternoon',
    goodEvening: 'Good evening',
    recentTasks: 'Recent Tasks',
    noRecentTasks: 'No tasks yet. Start your first computation.',
    startFirst: 'Browse Tools',
    quickActions: 'Quick Actions',
    newWorkflow: 'New Workflow',
    browseTools: 'Browse Tools',
    viewTasks: 'View Tasks',
    activeWorkflows: 'Active Workflows',
  },

  // Home
  home: {
    title: 'Home',
    badge: 'AI-Powered Scientific Computing',
    hero: {
      title: 'From target to lead compound, in one workspace',
      description: 'Pocket identification, virtual screening, molecular docking, ADMET prediction — all computational steps orchestrated, executed, and traced on one platform',
      cta: 'Get Started Free',
      secondary: 'Browse Tools',
    },
    values: {
      reproducible: {
        title: 'Reproducible',
        desc: 'Full input chain tracing, versioned workflows, immutable artifacts — every computation is auditable.',
      },
      composable: {
        title: 'Composable',
        desc: 'Chain tools into workflow DAGs with conditionals, loops, and parallel execution.',
      },
      trusted: {
        title: 'Trusted',
        desc: 'GPU scheduling, file deduplication, access control — production infrastructure for research computing.',
      },
    },
    capabilities: {
      title: 'Full AIDD Pipeline Coverage',
      subtitle: 'From target analysis to lead optimization, tools for every stage of the drug discovery pipeline.',
    },
    platform: {
      title: 'Open Platform',
      desc: 'CPUModel integrates deeply with PAIWSIT, CPUPDB, and other scientific databases — a complete chain from data to discovery.',
      cta: 'Get Started',
    },
    workflow: {
      title: 'Platform Functions',
      subtitle: 'Connect the core AIDD steps from pocket identification to lead optimization',
      items: workflowSteps
    },
    features: {
      title: 'Platform Features',
      subtitle: 'Professional, Efficient, User-friendly',
      items: {
        gpu: {
          title: 'GPU Acceleration',
          description: 'NVIDIA GPU accelerated computing for faster processing'
        },
        cloud: {
          title: 'Cloud Processing',
          description: 'No local installation required, access anywhere anytime'
        },
        api: {
          title: 'API Integration',
          description: 'Complete RESTful API for easy workflow integration'
        },
        security: {
          title: 'Data Security',
          description: 'Enterprise-grade encryption and privacy protection'
        }
      }
    },
    foundation: {
      title: 'Target Discovery & Platform Foundation',
      subtitle: 'The homepage now connects the research path from pathology-first target discovery, to structural pocket evidence, and then into the CPUModel AIDD workbench.',
      paiwsit: {
        kicker: 'Target Discovery Entry',
        title: 'PAIWSIT',
        description: 'PAIWSIT is a pathologists-annotated and AI-empowered tumor whole-slide image database that can serve as an entry point from tissue pathology phenotypes into target discovery and mechanism research.',
        points: {
          annotatedSlides: 'Provides pathologist-annotated tumor whole-slide image resources',
          aiHeatmap: 'Supports AI-assisted abnormal-region detection with heatmap visualization',
          pathologyEvidence: 'Adds pathology phenotype and tissue-level evidence for target discovery'
        },
        action: 'Visit PAIWSIT'
      },
      cpupdb: {
        kicker: 'Pocket Data Foundation',
        title: 'CPUPDB',
        description: 'It carries pathology and biology clues down into protein structures, pockets, multi-conformation states, and interaction analysis for later screening and design.',
        points: {
          structures: 'Covers protein structures, ligands, pockets, and binding-site information',
          dynamics: 'Brings in dynamics data to observe conformational shifts and cryptic pockets',
          analysis: 'Supports a continuous path from search to Explore, Dynamics, and Detail'
        },
        action: 'Visit CPUPDB',
        help: 'View Help Docs'
      },
      platform: {
        kicker: 'AIDD Workbench',
        title: 'CPUModel Workbench',
        description: 'CPUModel brings target clues, structural data, and computational tools into one workspace to continue screening, docking, property evaluation, and artifact reuse.',
        points: {
          groupedTools: 'Organize tools and research paths by themed groups',
          reusableArtifacts: 'Reuse historical artifacts between tasks to continue computation',
          chainedWorkflow: 'Chain pocket discovery, screening, docking, and property evaluation'
        },
        action: 'Open Tool Workbench'
      }
    },
    tools: {
      title: 'Popular Tools',
      subtitle: 'Most popular computational tools',
      viewAll: 'View All Tools'
    },
    cta: {
      title: 'Start Your Research Today',
      description: 'Register for free basic features and begin your computational biology journey',
      button: 'Sign Up Free'
    }
  },

  workflow: {
    title: 'Tool Workbench',
    subtitle: 'Browse tools by research group, reuse historical artifacts, and launch the next task from one workspace',
    entry: {
      home: 'Open Tool Workbench',
      tools: 'Use Tools by Group'
    },
    mode: {
      manual: 'Manual Mode',
    },
    workbenchHeader: {
      kicker: 'Workflow Workbench',
      titleFallback: 'Untitled Workflow'
    },
    statusSummary: {
      ready: 'Ready',
      blocked: 'Blocked',
      running: 'Running',
      completed: 'Completed',
      failed: 'Failed'
    },
    definition: {
      namePlaceholder: 'Flow name',
      loadPlaceholder: 'Saved flows',
      new: 'New',
      save: 'Save',
      load: 'Load',
      duplicate: 'Duplicate',
      archive: 'Archive',
      archiveConfirm: 'Archive the current flow? Archived flows are hidden from the default list and run records are kept.',
      delete: 'Delete',
      templateLabel: 'Flow mode',
      projectScoped: 'Project Workflow',
      runWorkflowDefinition: 'Run Workflow',
      startFullRun: 'Start Full Run'
    },
    persistence: {
      untitledWorkflow: 'Untitled Workflow',
      duplicateName: '{name} Copy',
      saved: 'Flow saved',
      duplicated: 'Flow duplicated',
      archived: 'Flow archived',
      deleted: 'Flow deleted',
      draftSaved: 'Workflow draft saved',
      runCanceled: 'Workflow run canceled',
      nodeRetried: 'Workflow node retried',
      loaded: 'Flow loaded',
      discardUnsavedTitle: 'Unsaved workflow changes',
      discardUnsavedContent: 'Discard the current workflow edits?',
      discardUnsavedConfirm: 'Discard changes',
      discardUnsavedCancel: 'Continue editing',
    },
    autoRepair: {
      reasonWithRoles: '{targetNodeTitle} {inputSlotName} requires {requiredRoles}; {toolName} can auto-repair it.',
      reasonWithoutRoles: '{targetNodeTitle} {inputSlotName} needs preparation or conversion before use; {toolName} can auto-repair it.',
      roleSeparator: ', '
    },
    artifactRoles: {
      atom_pocket_pdb: 'Atom pocket PDB',
      metadata_json: 'Metadata JSON',
      pocket_metadata_json: 'Pocket metadata JSON',
      preparation_report_json: 'Preparation report JSON',
      prepared_pdb: 'Prepared PDB',
      prepared_pqr: 'Prepared PQR',
      raw_structure_file: 'Raw structure file',
      receptor_pdbqt: 'Receptor PDBQT',
      report_json: 'Report JSON',
      report_markdown: 'Report Markdown',
      residue_pocket_pdb: 'Residue pocket PDB',
      structure_2d_sdf: '2D ligand SDF',
      structure_3d_sdf: '3D ligand SDF',
      structure_file: 'Structure file',
      table_file: 'Table file'
    },
    canvasPresets: {
      kicker: 'Flow Arrangement',
      unsaved: 'Unsaved workbench arrangement',
      namePlaceholder: 'Flow name',
      loadPlaceholder: 'Load saved flow',
      refresh: 'Refresh flows',
      new: 'New Flow',
      save: 'Save Flow',
      duplicate: 'Duplicate Flow',
      delete: 'Delete Flow',
      deleteConfirm: 'Delete the current flow? Run records will be kept.',
      copyName: '{name} Copy',
      run: 'Create Run',
      nameRequired: 'Enter a flow name first',
      emptyDefinition: 'No tool node is available to save',
      invalidDefinition: 'The workflow has a cycle or invalid link. Adjust node dependencies first.',
      invalidDefinitionDetail: 'Workflow definition is invalid: {reason}',
      saved: 'Flow saved',
      duplicated: 'Flow duplicated',
      deleted: 'Flow deleted',
      runCreated: 'Workflow run created: {id}',
      requiredInputs: 'Run Inputs',
      emptyRunInputs: 'This workflow has no global run inputs. Configure tools and parameters from the selected node, or run an individual node directly.',
      runHistory: 'Run History',
      emptyRunHistory: 'No workflow runs yet',
      refreshRuns: 'Refresh Runs',
      loadMoreRuns: 'Load More Runs',
      allRunsLoaded: 'All run records loaded',
      viewRunDetail: 'View Detail',
      toolVersionValue: 'Tool version {version}',
      inputBound: '{count} input(s) bound',
      outputSummary: 'Outputs: {types}',
      valueSeparator: ', ',
      selectInputArtifact: 'Select artifact file',
      uploadInput: 'Upload file',
      uploadingInput: 'Uploading',
      autoFillInputs: 'Auto Fill',
      missingInputs: 'Select required inputs first: {inputs}',
      syncRun: 'Sync Run',
      cancelRun: 'Cancel Run',
      retryNode: 'Retry Node',
      viewNodeTasks: 'View Node Records',
      runSynced: 'Workflow run status synced',
      restoreRunFailed: 'The latest workflow run is no longer available',
      emptyRunDetail: 'Workflow run detail is unavailable',
      runStatus: 'Latest Run',
      nodeProgress: '{completed}/{total} nodes complete',
      missingSemanticOutputs: 'Missing outputs: {types}',
      toolNames: {
        fetchPdb: 'Fetch PDB Structure',
        proteinPreparation: 'Protein Structure Repair',
        ligandPreparation: 'Ligand Preparation',
        moleculeStandardization: 'Molecule Standardization',
        pocketPrediction: 'Pocket Prediction',
        moleculeGeneration: 'Molecule Generation',
        admetPrediction: 'ADMET Prediction'
      },
      semanticOutputs: {
        proteinStructure: 'Protein structure',
        pocketStructure: 'Pocket structure',
        ligandStructure: 'Ligand structure',
        moleculeTable: 'Molecule table',
        admetTable: 'ADMET results'
      },
      parameterLabels: {
        pdbId: 'PDB ID',
        ph: 'pH',
        removeHydrogens: 'Remove hydrogens',
        neutralize: 'Neutralize',
        generate3d: 'Generate 3D conformer'
      },
      presets: {
        fullPipeline: {
          name: 'Full AIDD Pipeline',
          description: 'Start from a protein structure and chain pocket discovery, generation, docking, property prediction, and lead optimization.'
        },
        proteinToPocket: {
          name: 'Protein PDB to Pocket Prediction',
          description: 'Start from a protein structure and identify candidate pockets for downstream design work.'
        },
        pocketToGeneration: {
          name: 'Pocket PDB to Molecule Generation',
          description: 'Generate candidate molecules from an existing pocket structure for later screening or docking.'
        },
        proteinLigandToDocking: {
          name: 'Protein + Ligand to Docking and Affinity',
          description: 'Use a protein and candidate ligand directly to evaluate poses and affinity-related outputs.'
        },
        generationToProperty: {
          name: 'Molecule Generation to Property Prediction',
          description: 'Evaluate physicochemical and ADMET-related properties for existing candidate molecules.'
        },
        pubchemToAdmet: {
          name: 'PubChem to Basic ADMET',
          description: 'Start from a PubChem ligand and chain ligand preparation, SMILES conversion, RDKit properties, and MolP-PC Basic ADMET.'
        }
      }
    },
    nodeState: {
      ready: 'Ready',
      running: 'Running',
      completed: 'Completed',
      failed: 'Failed',
      missingTool: 'Tool Needed',
      invalidated: 'Needs Rerun',
      waitingInput: 'Waiting Input',
      inputNode: 'Input Node',
      pending: 'Pending'
    },
    nodeType: {
      input: 'Input',
      tool: 'Tool',
      result: 'Result',
      artifact: 'Artifact',
      condition: 'Condition',
      map: 'Map',
      loop: 'Loop'
    },
    canvas: {
      title: 'Flow Canvas',
      nodes: '{count} nodes',
      edges: '{count} edges',
      zoomOut: 'Zoom Out',
      zoomIn: 'Zoom In',
      resetZoom: 'Reset Zoom',
      fitView: 'Fit all nodes',
      connecting: 'Connecting'
    },
    canvasNode: {
      titleFallback: 'Untitled Node',
      connectTo: 'Connect to this node',
      connectFrom: 'Connect from this node',
      run: 'Run',
      configure: 'Configure',
      delete: 'Delete node',
      inputs: '{count} inputs',
      outputs: '{count} outputs',
      noIo: 'No input/output constraints',
      previewHint: 'Select a node to inspect configuration and results'
    },
    canvasEdge: {
      delete: 'Delete edge {edgeId}'
    },
    workbenchSidebar: {
      expand: 'Expand sidebar',
      collapse: 'Collapse sidebar',
      resize: 'Resize sidebar width'
    },
    nodeRun: {
      loginPrompt: 'Sign in to select saved artifacts',
      autoBoundTitle: 'Upstream artifacts auto-bound',
      runCurrentNode: 'Run Current Node',
      reset: 'Reset',
      selectToolFirst: 'Select a real tool before configuring this node',
      standardArtifactDescription: 'Standard artifact type: {artifactType}',
      upstreamNodeFallback: 'Upstream node'
    },
    palette: {
      title: 'Tool Library',
      toolsAvailable: '{count} tools available',
      searchPlaceholder: 'Search PDB, ligand, docking, ADMET...',
      quickFilterTitle: 'Common Tasks',
      showAdvanced: 'Advanced Filters',
      hideAdvanced: 'Hide Advanced',
      filterTitle: 'Filters',
      filterStage: 'Filter by stage',
      filterInput: 'Filter by input semantic',
      filterOutput: 'Filter by output semantic',
      addNode: 'Add node',
      dragOrClick: 'Drag or click to add',
      quickFilters: {
        all: 'All'
      },
      categories: {
        external_database_fetch: 'External Databases',
        protein_fetch: 'Protein Fetch',
        ligand_fetch: 'Ligand Fetch',
        protein_preparation: 'Protein Preparation',
        ligand_preparation: 'Ligand Preparation',
        ligand_format_conversion: 'Format Conversion',
        conformer_generation: 'Conformer Generation',
        property_prediction: 'Molecular Properties',
        admet_prediction: 'ADMET Prediction',
        toxicity_prediction: 'Toxicity Prediction',
        synthetic_accessibility: 'Synthetic Accessibility',
        molecular_docking: 'Molecular Docking',
        docking_rescore: 'Docking Rescore',
        molecular_dynamics: 'Molecular Dynamics',
        interaction_analysis: 'Interaction Analysis',
        other_tools: 'Other Tools'
      },
      empty: 'No matching tool. Adjust filters or search keywords.'
    },
    preflight: {
      title: 'Preflight Check',
      readyCount: 'Ready {count}',
      blockedCount: 'Blocked {count}',
      completedCount: 'Completed {count}',
      failedCount: 'Failed {count}',
      metricReady: 'Ready',
      metricBlocked: 'Blocked',
      metricCompleted: 'Completed',
      metricFailed: 'Failed',
      summaryTitle: 'Execution Guidance',
      resourceTitle: 'Resource Needs',
      resourceEmpty: 'This node set has no additional resource requirements.',
      issueTitle: 'Checks',
      noIssues: 'There is no blocking issue right now. You can continue with ready nodes.',
      viewNode: 'View Node',
      runReadyNodes: 'Start Full Workflow',
      applyAutoRepair: 'Auto-add preparation nodes',
      autoRepairTitle: 'Auto Repair Available',
      runHint: 'This creates a new full workflow run and schedules eligible nodes in dependency order.',
      hintRunning: 'Some nodes are already running. Wait for the current tasks to finish before continuing.',
      hintBlocked: 'You can run ready nodes first. Blocked nodes will become runnable after upstream artifacts are produced.',
      hintReady: 'Some nodes already satisfy run conditions and can be started now.',
      hintEmpty: 'Select the required tool, input file, or upstream artifact before starting the workflow.',
      fallback: {
        nodeTitle: 'Untitled Node',
        sourceNode: 'upstream node',
        filename: 'unknown file',
        toolSlug: 'unspecified tool',
        inputArtifact: 'input artifact'
      },
      primary: {
        runnableNodes: '{count} node(s) ready to run',
        missingWorkflowInput: 'Complete workflow inputs first',
        invalidToolContract: 'Some tool contracts are not executable; fix node tools first',
        invalidSemanticEdge: 'Some links are invalid; fix node dependencies first',
        needsPreparationOrConversion: 'Some standard artifacts need preparation or conversion',
        invalidArtifactBinding: 'Some standard artifact bindings are unavailable',
        empty: 'No runnable nodes right now'
      },
      issues: {
        missingTool: {
          title: 'Missing tool selection',
          detail: 'This node has multiple candidate tools. Select one before running.'
        },
        missingWorkflowInput: {
          title: 'Missing workflow input',
          detail: 'Select an available file for semantic input {semanticType} before continuing.'
        },
        waitingUpstream: {
          title: 'Waiting for upstream artifact',
          detail: 'Run {sourceNodeTitle} first; {semanticType} will bind to this node after success.'
        },
        waitingInput: {
          title: 'Waiting for input link',
          detail: 'This node declares required inputs, but no available input source is configured.'
        },
        invalidFileExtension: {
          title: 'Input file format mismatch',
          detail: 'Selected file {filename} does not match extension requirements for {semanticType}.'
        },
        invalidSemanticEdge: {
          title: 'Invalid link semantic type',
          detail: 'The link semantic type {semanticType} does not match upstream and downstream node definitions.'
        },
        invalidToolContract: {
          title: 'Tool contract is not executable',
          detail: 'The bound tool {toolSlug} has no valid workflow contract or is disabled.'
        },
        needsPreparation: {
          title: 'Input artifact needs preparation',
          detail: 'This node input artifact does not satisfy tool requirements. Run the matching preparation tool first.'
        },
        needsConversion: {
          title: 'Input artifact needs conversion',
          detail: 'This node input artifact must be converted before the tool can consume it.'
        },
        invalidArtifactBinding: {
          title: 'Invalid standard artifact binding',
          detail: 'This node standard artifact binding is unavailable. Select the input again or check upstream outputs.'
        },
        running: {
          title: 'Node is running',
          detail: 'Wait for the current task to finish before scheduling downstream nodes.'
        },
        failed: {
          title: 'Node task failed',
          detail: 'Check task logs, parameters, or input files before deciding whether to rerun.'
        },
        invalidated: {
          title: 'Node needs rerun',
          detail: 'Upstream inputs or parameters changed. Rerun this node to refresh results.'
        }
      },
      savedBinding: {
        missing: 'Saved {slotName} binding {artifactId} is not in the available artifact list. Select the input again.',
        mismatch: 'Saved {slotName} binding {artifactId} does not match current input requirements. Select the input again.'
      },
      binding: {
        suggestion: 'Suggested tool: {suggestedTool}.',
        fallbackPreparation: '{target} must be prepared first.',
        fallbackConversion: '{target} must be converted first.',
        fallbackInvalid: '{target} binding is unavailable.'
      }
    },
    inspector: {
      noSelectedNode: 'No selected node',
      configTab: 'Config',
      dependenciesTab: 'Dependencies',
      resultsTab: 'Results',
      toolSelector: 'Tool Selector',
      selectTool: 'Select tool',
      noToolRequired: 'This node does not require a tool.',
      nodeParameters: 'Node Parameters',
      runWorkflow: 'Run Workflow',
      configureNode: 'Configure Node',
      conditionSettings: 'Condition Settings',
      conditionOperator: 'Operator',
      conditionLeft: 'Left value or reference',
      conditionRight: 'Right value or reference',
      mapSettings: 'Map Settings',
      mapSource: 'Iterate over',
      mapParallelism: 'Maximum parallel tasks',
      conditionBranch: 'Condition branch',
      trueBranch: 'Condition true',
      falseBranch: 'Condition false',
      viewTaskDetail: 'View Task Detail',
      recommendedEdges: 'Suggested Edges',
      noRecommendedEdges: 'No suggested edge',
      upstreamEdge: 'Upstream Edge',
      artifactFallback: 'Artifact',
      deleteEdge: 'Delete Edge',
      sourceNode: 'Source Node',
      artifactType: 'Artifact Type',
      addEdge: 'Add Edge',
      requiredInput: 'Required Input',
      missingArtifact: 'Missing upstream artifact',
      noRequiredInput: 'No required input',
      producedOutput: 'Produced Output',
      noProducedOutput: 'No produced output',
      taskResult: 'Task Result',
      noTaskResult: 'No task result',
      resultSummary: 'Run Status',
      resultStatus: 'Current status',
      resultFileCount: '{count} result file(s)',
      resultFileTypeUnknown: 'File',
      downloadResult: 'Download',
      outputFiles: 'Output Files',
      downloadOutput: 'Download Output',
      noOutputFiles: 'No downloadable output file yet'
    },
    controlNodes: {
      title: 'Flow Control',
      condition: {
        title: 'Condition',
        description: 'Choose a path from scores or fields'
      },
      map: {
        title: 'Map',
        description: 'Process candidate collections in parallel'
      },
      loop: {
        title: 'Loop',
        description: 'Repeat inner tools until convergence or iteration limit'
      }
    },
    runDetail: {
      title: 'Workflow Run Detail',
      subtitle: 'Review run nodes, tasks, and error states',
      canceled: 'Workflow run canceled',
      nodeRetried: 'Workflow node retried'
    },
    resultsReport: {
      kicker: 'Results Center',
      workflowNameFallback: 'Untitled Workflow',
      reportTitleSuffix: 'Report',
      decisionSummary: 'Decision Summary',
      export: 'Export Report',
      nodeResults: 'Node Results',
      successNodes: 'Successful Nodes',
      failedNodes: 'Failed Nodes',
      artifactSummary: 'Artifact Summary',
      noArtifacts: 'No artifacts',
      artifactSummaryLine: '{count} artifacts total.',
      downloadFilename: 'workflow-report.md',
      table: {
        node: 'Node',
        status: 'Status',
        results: 'Results'
      },
      summary: {
        failed: 'Some nodes failed. Review failure reasons and input artifacts first.',
        ready: 'Reviewable artifacts are available for screening or team review.',
        empty: 'No complete result is available for decision-making yet.'
      }
    },
    resultsSidebar: {
      tabs: {
        node: 'Node Results',
        inputs: 'Run Inputs',
        preflight: 'Preflight',
        report: 'Report',
        artifacts: 'Artifacts',
        history: 'History'
      }
    },
    inlinePreview: {
      empty: 'No run result yet',
      running: 'Running',
      failed: 'Run failed',
      failureFallback: 'Check task logs to diagnose the failure.',
      expand: 'Expand Preview',
      previewTitle: 'Result Preview',
      noPreviewableArtifacts: 'Task completed with no previewable artifact',
      deferred: 'Select the node to load its result preview',
      outputCount: '{count} result file(s) or artifact(s) available'
    },
    runStatus: {
      pending: 'Pending',
      ready: 'Ready',
      running: 'Running',
      waiting_task: 'Waiting Task',
      success: 'Success',
      failure: 'Failure',
      canceled: 'Canceled'
    },
    groups: {
      empty: 'No workbench groups are available yet',
      noTools: 'No tool is available in this group yet',
      descriptionFallback: 'This group is waiting for the administrator to add a description.',
      toolCount: '{count} tools',
      recommendedCount: '{count} recommended'
    },
    currentGroup: {
      label: 'Current Group'
    },
    currentTool: {
      label: 'Current Tool',
      descriptionFallback: 'Pick a tool from the current group to start.',
      runAction: 'Run Current Tool',
      runHint: 'You can upload a local file or directly reuse a historical output from My Artifacts.',
      viewDetail: 'View Tool Detail',
      viewTask: 'View Task Detail',
      lastTask: 'Latest Task',
      preflightTitle: 'Preflight Check',
      preflightHint: 'Check required inputs, reusable artifacts, and expected outputs from the tool contract.',
      preflightReady: 'Ready',
      preflightMissing: 'Needs Input',
      matchedInput: 'Matched',
      missingInput: 'Missing',
      invalidInputFormat: 'Format Mismatch',
      expectedOutputs: 'Expected Outputs',
      empty: 'Select a tool from the current group'
    },
    toolStatus: {
      recommended: 'Recommended',
      available: 'Available',
      unavailable: 'Unavailable',
      availableCount: '{count} available',
      missingCount: '{count} unavailable'
    },
    boundSources: {
      title: 'Current Auto-bound Sources',
      waiting: 'Waiting for upstream result'
    },
    artifacts: {
      currentGroup: 'Current Group Artifacts',
      recentGroup: 'My Recent Artifacts',
      emptyCurrentGroup: 'No reusable artifact is available for this group yet',
      emptyRecent: 'You do not have any reusable output file yet',
      ungroupedGroup: 'Ungrouped Tools',
      locatePath: 'Locate in Form',
      taskLabel: 'Task',
      sourceToolLabel: 'Source Tool',
      generatedAtLabel: 'Generated At',
      sourceTool: 'Source Tool: {tool}',
      generatedAt: 'Generated At: {time}',
      taskCount: '{count} artifacts',
      moreArtifacts: '{count} more artifacts. Open task details to view all'
    },
    steps: workflowSteps,
    nodes: {
      inputProtein: {
        title: 'Protein Structure Input',
        description: 'Upload or reuse a Protein PDB file as the shared input for pocket discovery and docking.'
      },
      inputPocket: {
        title: 'Pocket Structure Input',
        description: 'Upload or reuse a Pocket PDB file to start directly from the generation stage.'
      },
      inputLigand: {
        title: 'Ligand Structure Input',
        description: 'Upload a candidate ligand structure for docking or later analysis.'
      },
      inputGeneratedLigand: {
        title: 'Generated Molecule Input',
        description: 'Reuse historical generated molecules or upload candidate molecules for downstream evaluation.'
      },
      fetchPubChem: {
        title: 'Fetch PubChem Ligand',
        description: 'Fetch a ligand structure by PubChem CID and emit standard ligand_structure@1.'
      },
      ligandPreparation: {
        title: 'Ligand Preparation',
        description: 'Prepare hydrogens, conformer, and format while keeping a standard ligand structure.'
      },
      sdfToSmiles: {
        title: 'SDF to SMILES Table',
        description: 'Convert ligand structures into molecule_table@1 for RDKit and MolP-PC reuse.'
      },
      rdkitProperties: {
        title: 'RDKit Properties',
        description: 'Calculate basic physicochemical descriptors before the ADMET prediction step.'
      },
      molpPcAdmet: {
        title: 'MolP-PC Basic ADMET',
        description: 'Use the registered MolP-PC tool to emit ADMET tables and scientific attachments.'
      },
      resultSummary: {
        title: 'Optimization Summary',
        description: 'Collect final lead optimization outputs for review and export.'
      },
      resultPocket: {
        title: 'Pocket Result',
        description: 'Review pocket prediction outputs before moving on to molecule generation.'
      },
      resultGeneratedLigand: {
        title: 'Generation Result',
        description: 'Review generated candidate molecules for downstream docking or property prediction.'
      },
      resultDocking: {
        title: 'Docking Result',
        description: 'Review binding poses and affinity-related outputs for candidate prioritization.'
      },
      resultProperty: {
        title: 'Property Prediction Result',
        description: 'Review physicochemical and ADMET predictions before the next decision.'
      },
      resultAdmet: {
        title: 'Basic ADMET Result',
        description: 'Review MolP-PC prediction tables, model version, and scientific attachments.'
      }
    },
    columns: {
      groups: 'Tool Groups',
      groupsHint: 'Browse tools by research theme and recommendations without enforcing a fixed order.',
      tools: 'Tools and Parameters',
      toolsHint: 'Choose a tool in the current group, fill in the parameters, and reuse historical files when needed.',
      artifacts: 'My Artifacts',
      artifactsHint: 'Your own historical output files appear here and can be reused in file fields across tools.'
    }
  },

  // Auth
  auth: {
    login: 'Login',
    register: 'Register',
    forgotPassword: 'Forgot Password',
    forgotPasswordDesc: 'Enter the email you used to register and we will send you a verification code',
    username: 'Username',
    email: 'Email',
    password: 'Password',
    confirmPassword: 'Confirm Password',
    newPassword: 'New Password',
    confirmNewPassword: 'Confirm New Password',
    rememberMe: 'Remember me',
    noAccount: "Don't have an account?",
    hasAccount: 'Already have an account?',
    goRegister: 'Sign up now',
    goLogin: 'Sign in now',
    loginSuccess: 'Login successful',
    registerSuccess: 'Registration successful',
    logoutSuccess: 'Logout successful',
    loginRequired: 'Please login first',
    // Verification code
    verificationCode: 'Verification Code',
    sendCode: 'Send Code',
    codeSent: 'Verification code sent',
    resendCode: 'Resend',
    resendCodeIn: 'Resend in {seconds}s',
    invalidCode: 'Invalid or expired verification code',
    // Password strength
    passwordWeak: 'Weak',
    passwordMedium: 'Medium',
    passwordStrong: 'Strong',
    passwordVeryStrong: 'Very Strong',
    // Password reset steps
    step1Email: 'Enter Email',
    step2Verify: 'Verify Identity',
    step3Reset: 'Reset Password',
    sendResetCode: 'Send Reset Code',
    codeSentTo: 'Code sent to {email}',
    verifyCode: 'Verify',
    resetPassword: 'Reset Password',
    resetSuccess: 'Password Reset Successful',
    resetSuccessDesc: 'Your password has been reset successfully. Please login with your new password',
    // Agreement
    agreementPrefix: 'I have read and agree to the',
    termsOfService: 'Terms of Service',
    agreementAnd: 'and',
    privacyPolicy: 'Privacy Policy',
    validation: {
      usernameRequired: 'Please enter username',
      usernameLength: 'Username must be 3-20 characters',
      usernameFormat: 'Username can only contain letters, numbers and underscores',
      emailRequired: 'Please enter email',
      emailInvalid: 'Please enter a valid email address',
      passwordRequired: 'Please enter password',
      passwordLength: 'Password must be at least 6 characters',
      confirmPasswordRequired: 'Please confirm password',
      passwordMismatch: 'Passwords do not match',
      codeRequired: 'Please enter verification code',
      codeLength: 'Verification code must be 6 digits',
      agreementRequired: 'Please read and agree to the Terms of Service and Privacy Policy'
    }
  },

  // Tools
  tools: {
    parameterJsonInvalid: 'Enter valid JSON',
    parameterJsonObject: 'Enter a JSON object',
    parameterJsonArray: 'Enter a JSON array',
    standardArtifactTypes: {
      proteinStructure: 'Protein Structure',
      bindingPocket: 'Binding Pocket',
      ligandStructure: 'Ligand Structure',
      moleculeTable: 'Molecule Table',
      runReport: 'Run Report'
    },
    title: 'Tools',
    subtitle: 'Discover and use powerful computational biology tools',
    detail: 'Tool Detail',
    list: 'Tool List',
    search: 'Search tools...',
    category: 'Category',
    allCategories: 'All Categories',
    tags: 'Tags',
    filterTags: 'Filter by tags',
    usageCount: 'Usage Count',
    viewCount: 'Views',
    viewDetail: 'View Details',
    runCount: 'Run Count',
    runs: 'runs',
    favoriteCount: 'Favorites',
    version: 'Version',
    changelog: 'Changelog',
    gpuRequirements: 'GPU Requirements',
    gpuMemory: 'GPU Memory',
    timeout: 'Timeout',
    toolInfo: 'Tool Info',
    status: 'Status',
    favorite: 'Favorite',
    unfavorite: 'Unfavorite',
    run: 'Run',
    useNow: 'Use now',
    parameters: 'Parameters',
    inputFiles: 'Input Files',
    submit: 'Submit Task',
    history: 'Version History',
    noTools: 'No tools available',
    noMatchingTools: 'No matching tools found',
    // Tool views
    publicTools: 'Public Tools',
    myTools: 'My Tools',
    favorites: 'Favorites',
    favoriteTools: 'My Favorites',
    customTools: 'Custom Tools',
    allTools: 'All',
    // Tool provider types
    providerType: {
      platform: 'Official',
      user: 'Community'
    },
    // Review status
    reviewStatus: {
      all: 'All Status',
      not_required: 'No Review Required',
      pending: 'Pending Review',
      approved: 'Approved',
      rejected: 'Rejected'
    },
    // Review related
    submitReview: 'Submit for Review',
    resubmitReview: 'Resubmit',
    reviewPending: 'Under review, please wait',
    reviewRejected: 'Review rejected',
    rejectReason: 'Rejection Reason',
    // Create/Edit tool
    createTool: 'Create Tool',
    editTool: 'Edit Tool',
    basicInfo: 'Basic Information',
    toolName: 'Tool Name',
    toolNamePlaceholder: 'Enter tool name',
    toolSlug: 'Tool Slug',
    toolSlugPlaceholder: 'Enter tool slug (lowercase letters, numbers, hyphens)',
    slugHint: 'Used in URL to identify the tool, only lowercase letters, numbers and hyphens allowed',
    descriptionPlaceholder: 'Enter tool description...',
    selectCategory: 'Select category',
    selectTags: 'Select tags',
    icon: 'Icon',
    iconUrl: 'Icon URL',
    iconPlaceholder: 'Enter emoji or leave empty',
    iconHint: 'Supports emoji as icon',
    iconUrlPlaceholder: 'Enter icon URL (optional)',
    runConfig: 'Run Configuration',
    gpuRequired: 'GPU Required',
    gpuMemoryMb: 'GPU Memory (MB)',
    timeoutSec: 'Timeout (seconds)',
    isPublic: 'Public Tool',
    publicYes: 'Public (visible to others)',
    publicNo: 'Private (only visible to you)',
    // Validation messages
    nameRequired: 'Please enter tool name',
    nameLength: 'Tool name must be 2-100 characters',
    slugRequired: 'Please enter tool slug',
    slugFormat: 'Tool slug can only contain lowercase letters, numbers and hyphens',
    slugLength: 'Tool slug must be 2-50 characters',
    descriptionLength: 'Description max 500 characters',
    // Operation results
    createSuccess: 'Tool created successfully',
    updateSuccess: 'Tool updated successfully',
    loadFailed: 'Failed to load tool information',
    // Sorting
    sortPopular: 'By Popularity',
    sortNewest: 'By Newest',
    sortName: 'By Name',
    // Empty states
    noFavorites: 'No favorite tools yet',
    noCustomTools: 'No custom tools yet',
    browseTools: 'Browse Tools',
    fileSourceUpload: 'Upload',
    fileSourceArtifact: 'My Artifacts',
    selectArtifact: 'Select Artifact',
    selectProjectArtifact: 'Select a project file',
    noArtifacts: 'No reusable artifacts yet',
    selectCompatibleArtifact: 'Select Compatible Artifact by Hierarchy',
    selectArtifactGroup: 'Select Group First',
    selectArtifactTool: 'Select Tool Next',
    selectArtifactTask: 'Select Task Next',
    selectArtifactOutput: 'Select Artifact Output',
    artifactGroupLabel: 'Group',
    artifactToolLabel: 'Tool',
    artifactTaskLabel: 'Task',
    artifactOutputLabel: 'Artifact',
    artifactGroupMeta: 'Browse reusable sources by workbench group',
    artifactToolMeta: 'View historical tasks for this tool',
    artifactSelectedTag: 'Selected',
    clearArtifactSelection: 'Clear artifact selection',
    artifactFocusTag: 'Panel Focus',
    artifactSummarySelected: 'Selected Artifact',
    artifactSummaryFocused: 'Path Focused from Panel',
    artifactSummaryPending: 'Current Path',
    noCompatibleArtifacts: 'No task artifact matches this input format',
    // Tool detail
    free: 'Free',
    introduction: 'Introduction',
    viewIntroduction: 'Introduction',
    documentationMarkdown: 'Introduction Markdown',
    documentationMarkdownHint: 'Supports Markdown. This content is saved with the current tool version, and changes require a new version.',
    modelOverview: 'Model Overview',
    parameterDocs: 'Parameters',
    outputDocs: 'Output Files',
    outputPatterns: 'Output Path Patterns',
    defaultValue: 'Default',
    fieldType: 'Type',
    valueRange: 'Range',
    noDocumentation: 'No detailed introduction is available yet.',
    features: 'Features',
    howToUse: 'How to Use',
    step: 'Step',
    references: 'References',
    paper: 'Paper',
    documentation: 'Documentation',
    relatedTools: 'Related Tools',
    noRelatedTools: 'No related tools',
    formatInfo: 'Format Info',
    inputFormats: 'Supported Input Formats',
    outputFormats: 'Output Formats',
    selectFile: 'Select File',
    exampleInput: 'Example Input',
    viewExample: 'View Example',
    hideExample: 'Hide Example',
    exampleFiles: 'Example Files',
    useExample: 'Use Example',
    exampleHint: 'Use this example to prepare the run input',
    exampleFileBound: 'Example file bound',
    exampleFileMissing: 'Missing',
    exampleFilePreview: 'Example File Preview',
    preview: 'Preview',
    previewUnavailable: 'Unavailable',
    previewTruncated: 'This file is large. Showing the first 64KB only.',
    exampleLoaded: 'Example applied',
    runTool: 'Run Tool',
    switchingVersion: 'Switching to version {version}',
    avgDuration: 'Avg Duration'
  },

  // Tasks
  tasks: {
    title: 'Task Center',
    subtitle: 'Manage and monitor your computing tasks',
    detail: 'Task Detail',
    taskDetail: 'Task Detail',
    list: 'Task List',
    create: 'Create Task',
    name: 'Task Name',
    namePlaceholder: 'Optional, leave blank to auto-generate',
    // Tabs
    allTasks: 'All Tasks',
    runningTasks: 'Running',
    attentionTasks: 'Needs Attention',
    historyTasks: 'History',
    // Status
    status: {
      pending: 'Pending',
      running: 'Running',
      success: 'Completed',
      failure: 'Failed',
      canceled: 'Canceled'
    },
    statusPending: 'Pending',
    statusRunning: 'Running',
    statusSuccess: 'Completed',
    statusFailure: 'Failed',
    statusCanceled: 'Canceled',
    // Filters
    searchPlaceholder: 'Search task name or ID...',
    filterByTool: 'Filter by tool',
    startDate: 'Start Date',
    endDate: 'End Date',
    workflowScope: {
      active: 'Filtered by workflow context: {scope}',
      run: 'Run {id}',
      definition: 'Workflow {id}',
      node: 'Node {id}'
    },
    // Monitor
    realTimeMonitor: 'Real-time Monitor',
    autoRefreshOn: 'Auto Refresh',
    autoRefreshOff: 'Manual',
    remoteRecovery: {
      title: 'Recovering remote task',
      failures: 'The remote service is unavailable. Recovery has failed {count} consecutive times.',
      nextAttempt: 'Next probe scheduled for {time}.',
      lastError: 'Last error: {error}',
      alertFilter: 'Recovery alert',
      alertedOnly: 'Alerted tasks only'
    },
    resourceWait: {
      title: 'Waiting for compute resources',
      gpuUnavailable: 'GPU resources are temporarily unavailable. The task will retry automatically.',
      quotaExceeded: 'The resource quota is exhausted. The task will retry when capacity is released.',
      workerCapacity: 'No current Worker can host the request. The task will retry automatically.',
      schedulerBusy: 'The scheduler is handling other resource requests. The task will retry automatically.',
      scopeDimension: '{scope} {dimension} quota is exhausted.',
      userScope: 'User',
      projectScope: 'Project',
      dimensions: {
        cpu: 'CPU',
        memory: 'memory',
        parallelism: 'parallelism',
        gpu: 'GPU'
      },
      nextAttempt: 'Next dispatch: {time}',
      retryCount: 'Resource retry count: {count}'
    },
    resourceReservation: {
      title: 'Resource dispatch reservation',
      status: 'Status: {status}',
      worker: 'Worker: {worker}',
      queue: 'Queue: {queue}',
      releaseReason: 'Release reason: {reason}',
      releaseError: 'Release error: {error}',
      statuses: {
        reserved: 'Reserved',
        claimed: 'Claimed by Worker',
        released: 'Released',
        releaseFailed: 'Release failed',
        notFound: 'Lease already absent'
      }
    },
    // Actions
    progress: 'Progress',
    logs: 'Logs',
    result: 'Result',
    inputParams: 'Input Parameters',
    inputFiles: 'Input Files',
    outputFiles: 'Output Files',
    outputResults: 'Output Results',
    resultVisualization: 'Result Visualization',
    csvPreview: 'CSV Preview',
    csvVisualizationHint: 'CSV outputs are rendered as a scrollable table, and recognized SMILES columns get an inline 2D molecule preview.',
    csvSummary: '{rows} rows and {columns} columns. The table area scrolls independently for long result sets.',
    csvStructure: 'Structure',
    csvLoadFailed: 'Failed to load CSV result',
    csvEmpty: 'CSV result is empty',
    csvEmptyDesc: 'No data rows are available in this result file. Check whether the tool produced the expected output.',
    csvFileMissing: 'Missing CSV file download URL',
    jsonResultFields: '{count} fields',
    jsonResultItems: '{count} items',
    jsonResultRaw: 'Raw JSON',
    visualizationHint: 'Input pocket files are overlaid with generated molecules first for quick inspection of binding poses.',
    visualizationFiles: 'visualization files',
    visualizationSelectableHint: 'Multiple 3D outputs were detected. The input structure stays fixed while you inspect one generated molecule or pose at a time.',
    visualizationResultList: 'Output Results',
    visualizationResultListDesc: '{count} result items are available. The 3D viewport shows one selected output at a time.',
    visualizationInputPinned: 'Pinned Input Structure',
    visualizationPrevious: 'View previous result',
    visualizationNext: 'View next result',
    visualizationLoading: 'Loading 3D results...',
    visualizationFailed: 'Failed to load 3D results',
    visualizationUnsupported: 'These output files are not supported for online preview yet',
    visualizationUnsupportedDesc: 'PDB / mmCIF / PDBQT / SDF / MOL2 previews are enabled first. Other files can still be downloaded directly.',
    filePreview: 'Result file',
    filePreviewFile: 'File',
    filePreviewLoading: 'Loading file content...',
    filePreviewLoadFailed: 'Failed to load file content',
    filePreviewTooLarge: 'This file is too large to load online',
    filePreviewTooLargeDesc: 'Download the file to inspect its complete content without affecting page performance.',
    filePreviewMissingUrl: 'Missing file download URL',
    filePreviewEmpty: 'No file content is available for preview',
    filePreviewDownloadOnly: 'This file is not supported for online parsing',
    filePreviewDownloadOnlyDesc: 'Download the file and open it with the corresponding local tool.',
    visualizationDownloadOnlyHint: '{count} file(s) are not supported for online parsing yet. Select a result item to download one.',
    cancel: 'Cancel',
    retry: 'Retry',
    delete: 'Delete',
    download: 'Download',
    downloadAll: 'Download All',
    exportMolpPcCsv: 'Export MolP-Pc CSV',
    exportMolpPcCsvSuccess: 'MolP-Pc CSV exported',
    exportMolpPcCsvNoSource: 'No CSV artifact is available for export',
    exportMolpPcCsvNoSmiles: 'The CSV artifact does not contain a SMILES column',
    scientificAttachments: 'Scientific Attachment References',
    scientificModelCard: 'Model Card',
    scientificVerificationRecord: 'Verification Record',
    scientificEvidenceLevel: 'Evidence Level',
    standardArtifactsMissing: 'Standard artifacts missing or invalid',
    failureStderr: 'Error Output stderr',
    failureStdout: 'Standard Output stdout',
    allTaskTypes: 'All Types',
    standaloneToolTasks: 'Standalone Tool Tasks',
    viewDetail: 'View Detail',
    viewTool: 'View Tool',
    goToTools: 'Create Task',
    // Confirmations
    cancelConfirm: 'Cancel this task?',
    cancelConfirmContent: 'The task will stop running and results may be lost.',
    deleteConfirm: 'Delete this task?',
    deleteConfirmContent: 'This action cannot be undone.',
    retryConfirm: 'Retry this task?',
    // Success messages
    cancelSuccess: 'Task canceled',
    deleteSuccess: 'Task deleted',
    retrySuccess: 'Task resubmitted',
    // Time
    createdAt: 'Created At',
    startedAt: 'Started At',
    completedAt: 'Completed At',
    duration: 'Duration',
    runningTime: 'Running Time',
    // Timeline
    timeline: 'Task Timeline',
    created: 'Task Created',
    started: 'Execution Started',
    completed: 'Execution Completed',
    failed: 'Execution Failed',
    canceled: 'Task Canceled',
    // Tool info
    toolInfo: 'Tool Information',
    toolNotFound: 'Tool info unavailable',
    unknownTool: 'Unknown Tool',
    // Errors
    errorMessage: 'Error Message',
    noLogs: 'No logs available',
    moreLogs: '{count} more logs are available. Open task details to inspect everything.',
    notFound: 'Task Not Found',
    notFoundDesc: 'The task you are looking for may have been deleted or does not exist',
    // Empty states
    noTasks: 'No tasks',
    noRunningTasks: 'No running tasks',
    noAttentionTasks: 'No failed tasks need attention',
    noHistoryTasks: 'No history tasks'
  },

  // User Center
  user: {
    title: 'User Center',
    profile: 'Profile',
    settings: 'Account Settings',
    favorites: 'My Favorites',
    // Profile
    changePassword: 'Change Password',
    oldPassword: 'Current Password',
    newPassword: 'New Password',
    avatar: 'Avatar',
    uploadAvatar: 'Upload Avatar',
    avatarUploaded: 'Avatar uploaded successfully',
    avatarUploadFailed: 'Avatar upload failed',
    avatarTypeError: 'Only image files are allowed',
    avatarSizeError: 'Image size cannot exceed 2MB',
    createdAt: 'Registered',
    changeEmail: 'Change Email',
    newEmail: 'New Email',
    verifyCode: 'Verification Code',
    sendCode: 'Send Code',
    enterNewEmail: 'Please enter new email',
    codeSent: 'Verification code sent',
    emailChanged: 'Email changed successfully',
    enterOldPassword: 'Please enter current password',
    passwordChanged: 'Password changed successfully',
    // Settings
    notificationSettings: 'Notification Settings',
    emailNotification: 'Email Notifications',
    taskCompleteNotify: 'Task Completion',
    taskFailNotify: 'Task Failure',
    systemNotify: 'System Notifications',
    marketingNotify: 'Marketing Notifications',
    privacySettings: 'Privacy Settings',
    profileVisibility: 'Profile Visibility',
    public: 'Public',
    friendsOnly: 'Friends Only',
    private: 'Private',
    showTaskHistory: 'Show Task History',
    accountSecurity: 'Account Security',
    twoFactorAuth: 'Two-Factor Authentication',
    twoFactorAuthDesc: 'Enable 2FA to enhance account security',
    twoFactorSetup: 'Setting up 2FA...',
    disableTwoFactor: 'Disable 2FA',
    disableTwoFactorDesc: 'Disabling 2FA will reduce account security. Are you sure?',
    twoFactorDisabled: '2FA has been disabled',
    loginDevices: 'Login Devices',
    loginDevicesDesc: 'Manage devices logged into your account',
    manage: 'Manage',
    currentDevice: 'Current Device',
    logoutDevice: 'Logout',
    logoutDeviceConfirm: 'Log out this device?',
    deviceLoggedOut: 'Device logged out',
    deleteAccount: 'Delete Account',
    deleteAccountDesc: 'Account data cannot be recovered after deletion',
    deleteAccountConfirm: 'Delete your account?',
    deleteAccountConfirmContent: 'All your data will be permanently deleted. This action cannot be undone.',
    confirmDelete: 'Confirm Delete',
    deleteAccountProcess: 'Processing deletion request...',
    // Favorites
    noFavorites: 'No favorite tools yet',
    exploreTool: 'Explore Tools',
    unfavoriteConfirm: 'Remove from favorites?',
    unfavoriteConfirmContent: 'You can add it back anytime',
    unfavoriteSuccess: 'Removed from favorites',
    // Logout
    logoutConfirm: 'Log out?',
    logoutConfirmContent: 'You will need to log in again to use full features',
    // Roles
    role: {
      user: 'User',
      admin: 'Administrator'
    }
  },

  // Admin
  admin: {
    title: 'Admin Panel',
    dashboard: 'Dashboard',
    dashboardSubtitle: 'Review users, tools and task activity in one operational overview',
    users: 'User Management',
    tools: 'Tool Management',
    tasks: 'Task Management',
    system: 'System Settings',
    backToSite: 'Back to Site',
    stats: {
      totalUsers: 'Total Users',
      totalTools: 'Total Tools',
      totalTasks: 'Total Tasks',
      activeTasks: 'Active Tasks',
      gpuUsage: 'GPU Usage',
      storageUsage: 'Storage Usage'
    },
    // Dashboard
    todayNew: 'New Today',
    activeCount: 'Active',
    runningNow: 'Running Now',
    taskTrend: 'Task Trend',
    taskCount: 'Task Count',
    successRate: 'Success Rate',
    systemStatus: 'System Status',
    cpuUsage: 'CPU Usage',
    memoryUsage: 'Memory Usage',
    diskUsage: 'Disk Usage',
    gpuMemory: 'GPU Memory',
    serviceStatus: 'Service Status',
    running: 'Running',
    stopped: 'Stopped',
    recentTasks: 'Recent Tasks',
    recentUsers: 'Recent Users',
    toolName: 'Tool Name',
    role: 'Role',
    registerTime: 'Registered',
    // User Management
    createUser: 'Create User',
    editUser: 'Edit User',
    userInfo: 'User Info',
    keyword: 'Keyword',
    searchUserPlaceholder: 'Search username or email...',
    status: 'Status',
    active: 'Active',
    disabled: 'Disabled',
    inactive: 'Inactive',
    banned: 'Banned',
    pending: 'Pending Review',
    createUserSuccess: 'User created',
    selectRole: 'Please select role',
    selectStatus: 'Please select status',
    resetPassword: 'Reset Password',
    resetPasswordConfirm: 'Reset password?',
    resetPasswordConfirmContent: 'Reset password for user {username}',
    resetPasswordSuccess: 'Password reset',
    softDeleteUser: 'Soft Delete',
    softDeleteUserConfirm: 'Soft delete this user?',
    softDeleteUserConfirmContent: 'User {username} will not be able to sign in, but related data will be kept',
    softDeleteUserSuccess: 'User soft deleted',
    hardDeleteUser: 'Hard Delete',
    hardDeleteUserConfirm: 'Permanently delete this user?',
    hardDeleteUserConfirmContent:
      'Deleting user {username} will cascade-remove their tasks, files, tools and sessions and cannot be undone',
    hardDeleteUserSuccess: 'User permanently deleted',
    banUser: 'Ban User',
    banUserConfirm: 'Ban this user?',
    banUserConfirmContent: 'User {username} will not be able to login',
    banUserSuccess: 'User banned',
    unbanUser: 'Unban User',
    unbanUserSuccess: 'User unbanned',
    deleteUserConfirm: 'Delete this user?',
    deleteUserConfirmContent: 'All data for user {username} will be deleted',
    // Tool Management
    createTool: 'Create Tool',
    editTool: 'Edit Tool',
    importToolConfig: 'Import Config',
    importToolConfigTitle: 'Import platform_tool.json',
    importToolConfigDescription:
      'Paste or load the AI-generated platform_tool.json and the system will validate it before creating the tool and version',
    importToolConfigPlaceholder: 'Paste the full platform_tool.json content',
    importToolConfigFromFile: 'Load from JSON file',
    importToolConfigPublish: 'Publish immediately after import',
    importToolConfigSuccess: 'Tool config imported successfully',
    importToolConfigRequired: 'Please paste the platform_tool.json content first',
    importToolConfigInvalid: 'platform_tool.json is not valid JSON',
    toolRegistrationTitle: 'Choose how to connect the model',
    toolRegistrationDescription: 'Pick the path that matches the model’s current setup. You can add runtime details later.',
    toolRegistrationTemplateTitle: 'Model starter template',
    toolRegistrationTemplateDescription: 'Generate AIDD capabilities, Artifact inputs, and resource settings for drug discovery.',
    toolRegistrationRemoteTitle: 'Connect a remote model service',
    toolRegistrationRemoteDescription: 'For an existing HTTP service. Read its interface definition and check connectivity.',
    toolRegistrationPackageTitle: 'Model delivery package',
    toolRegistrationPackageDescription: 'Recommended for production: register the runtime, standard Artifact contract, and verifiable versions.',
    toolRegistrationRecommended: 'Recommended',
    toolRegistrationAdvancedTitle: 'Manual advanced setup',
    toolRegistrationAdvancedDescription: 'Configure a container, Python, SSH, or compatible API executor yourself.',
    toolsSubtitle: 'Maintain the tool catalog and category assignment in one place',
    toolPackages: 'Model delivery packages',
    toolPackagesSubtitle: 'Register and validate model deliverables. Publish a package, then create a platform tool before users can run it.',
    workbenchGroups: 'Workbench Groups',
    workbenchGroupsSubtitle: 'Manage tool workbench groups, recommendations, and mappings in one place',
    toolCategories: 'Category Management',
    toolCategoriesSubtitle: 'Manage tool categories, status and display order in one place',
    createCategory: 'Create Category',
    editCategory: 'Edit Category',
    categoryName: 'Category Name',
    categorySlug: 'Category Slug',
    enterCategoryName: 'Please enter category name',
    enterCategorySlug: 'Please enter category slug',
    invalidCategorySlug: 'Category slug can only contain lowercase letters, numbers, and hyphens',
    deleteCategoryConfirm: 'Delete this category?',
    deleteCategoryConfirmContent: 'Category {name} will be permanently removed',
    searchToolPlaceholder: 'Search tool name or code...',
    categoryStructure: 'Structure Prediction',
    categoryDocking: 'Molecular Docking',
    categorySequence: 'Sequence Analysis',
    categoryVisualization: 'Visualization',
    maintenance: 'Maintenance',
    statistics: 'Statistics',
    toolCode: 'Tool Code',
    enterToolName: 'Please enter tool name',
    enterToolCode: 'Please enter tool code',
    enterDescription: 'Please enter description',
    selectCategory: 'Please select category',
    enterVersion: 'Please enter version',
    enterServiceUrl: 'Please enter service URL',
    serviceUrl: 'Service URL',
    gpuRequired: 'GPU Required',
    configParams: 'Configure Parameters',
    paramsConfigTip: 'Enter JSON Schema for tool parameters',
    paramsJsonPlaceholder: 'Enter valid JSON format parameter configuration',
    invalidJson: 'Invalid JSON format',
    deactivate: 'Deactivate',
    activate: 'Activate',
    setMaintenance: 'Set Maintenance',
    deleteToolConfirm: 'Delete this tool?',
    deleteToolConfirmContent: 'Tool {name} will be deleted, task records will be kept',
    // Task Management
    totalTasks: 'Total Tasks',
    runningTasks: 'Running',
    pendingTasks: 'Pending',
    failedTasks: 'Failed',
    remoteRecoveryAlerts: 'Recovery Alerts',
    resourceWaitTasks: 'Resource Waits',
    quotaWaitTasks: 'Quota Waits',
    workerWaitTasks: 'Worker Capacity Waits',
    gpuWaitTasks: 'GPU Waits',
    externalCapacityWaitTasks: 'Remote Capacity Waits',
    searchTaskPlaceholder: 'Search task name or ID...',
    resourceWaitCategory: 'Resource Wait Category',
    resourceWaitAll: 'All resource waits',
    resourceWaitQuota: 'Quota exhausted',
    resourceWaitWorkerCapacity: 'Worker capacity unavailable',
    resourceWaitGpu: 'GPU unavailable',
    resourceWaitScheduler: 'Scheduler busy',
    resourceWaitExternalCapacity: 'Remote service capacity unavailable',
    resourceWaitResource: 'Other resource wait',
    resourceWaitReason: 'Resource Wait Reason',
    tool: 'Tool',
    user: 'User',
    dateRange: 'Date Range',
    taskInfo: 'Task Info',
    clearCompleted: 'Clear Completed',
    clearCompletedConfirm: 'Clear completed tasks?',
    clearCompletedConfirmContent: 'All completed, failed and canceled tasks will be deleted',
    selected: '{count} selected',
    batchCancel: 'Batch Cancel',
    batchDelete: 'Batch Delete',
    batchCancelConfirm: 'Cancel selected tasks?',
    batchDeleteConfirm: 'Delete selected tasks?',
    // System Settings
    generalSettings: 'General Settings',
    taskSettings: 'Task Settings',
    storageSettings: 'Storage Settings',
    emailSettings: 'Email Settings',
    systemInfo: 'System Info',
    systemSubtitle: 'Manage runtime status, configuration snapshots, and Agent model services',
    systemOverview: 'System Overview',
    resourceWorkers: 'Resource Workers',
    resourceWorkersSubtitle: 'Inspect online Worker capabilities and dynamic lease usage',
    totalResourceWorkers: 'Online Workers',
    workerId: 'Worker ID',
    workerQueue: 'Task Queue',
    workerHealthy: 'Healthy',
    workerUnhealthy: 'Unhealthy',
    executorTypes: 'Executor Types',
    resourceTiers: 'Resource Tiers',
    resourceCpuUsage: 'CPU Used / Capacity',
    resourceMemoryUsage: 'Memory Used / Capacity',
    resourceParallelismUsage: 'Parallelism Used / Capacity',
    resourceReservationCount: 'Reservations',
    resourceExecutionCount: 'Executions',
    resourceGpuCapacity: 'GPU Capability',
    noResourceWorkers: 'No online Workers',
    resourceStatusHealthy: 'Resource scheduling healthy',
    resourceStatusDegraded: 'Some Workers unhealthy',
    resourceStatusUnavailable: 'Resource status unavailable',
    resourceStatusUnknown: 'No resource status',
    resourceQuotas: 'User and Project Quotas',
    resourceQuotasSubtitle: 'Inspect CPU, memory, parallelism usage, and rejection reasons',
    quotaEnabled: 'Quota enabled',
    quotaDisabled: 'Quota disabled',
    gpuQuotaMode: 'GPU quota mode',
    quotaScope: 'Quota Scope',
    userScope: 'User',
    projectScope: 'Project',
    quotaCpu: 'CPU Used / Limit',
    quotaMemory: 'Memory Used / Limit',
    quotaParallelism: 'Parallelism Used / Limit',
    quotaGpuRequests: 'GPU Requests',
    quotaRejections: 'Rejections',
    noQuotaScopes: 'No quota usage records',
    modelServices: 'Model Services',
    modelServicesSubtitle: 'Configure OpenAI-compatible model services used by Agent planning',
    quickPreset: 'Quick preset',
    quickPresetPlaceholder: 'Choose a provider to fill common settings',
    discoverModels: 'Discover models',
    saveBeforeDiscoveringModels: 'Save the service before discovering models',
    createModelService: 'Create Model Service',
    editModelService: 'Edit Model Service',
    providerType: 'Provider Type',
    baseUrl: 'Base URL',
    modelName: 'Model Name',
    apiKey: 'API Key',
    apiKeyPlaceholder: 'Leave empty to keep the existing API key',
    defaultService: 'Default Service',
    enabled: 'Enabled',
    timeoutSeconds: 'Timeout',
    maxTokens: 'Max Tokens',
    temperature: 'Temperature',
    runtimeSettings: 'Runtime',
    lastTest: 'Last Test',
    setDefault: 'Set Default',
    modelServiceCreated: 'Model service created',
    modelServiceUpdated: 'Model service updated',
    modelServiceDeleted: 'Model service deleted',
    defaultModelServiceUpdated: 'Default model service updated',
    confirmDeleteModelService: 'Delete this model service?',
    noApiKey: 'No API key',
    configuredApiKey: 'API key configured',
    siteSettings: 'Site Settings',
    siteName: 'Site Name',
    siteDescription: 'Site Description',
    contactEmail: 'Contact Email',
    allowRegistration: 'Allow Registration',
    maintenanceMode: 'Maintenance Mode',
    maintenanceModeDesc: 'When enabled, normal users cannot access the site',
    taskConfig: 'Task Configuration',
    maxConcurrentTasks: 'Max Concurrent Tasks',
    maxConcurrentTasksDesc: 'Maximum number of tasks running simultaneously',
    taskTimeout: 'Task Timeout',
    minutes: 'minutes',
    days: 'days',
    maxRetries: 'Max Retries',
    cleanupDays: 'Auto Cleanup Days',
    cleanupDaysDesc: 'Completed tasks older than this will be auto deleted',
    runtimeStats: 'Runtime Stats',
    configSnapshot: 'Configuration Snapshot',
    environment: 'Environment',
    debugMode: 'Debug Mode',
    hostname: 'Hostname',
    cacheBackend: 'Cache Backend',
    storageBackend: 'Storage Backend',
    taskQueue: 'Task Queue',
    cpuCount: 'CPU Cores',
    memoryTotal: 'Total Memory',
    memoryAvailable: 'Available Memory',
    diskTotal: 'Total Disk',
    diskFree: 'Free Disk',
    totalFiles: 'Total Files',
    activeConnections: 'Active Connections',
    storageConfig: 'Storage Configuration',
    storageType: 'Storage Type',
    localStorage: 'Local Storage',
    storagePath: 'Storage Path',
    endpoint: 'Endpoint',
    accessKey: 'Access Key',
    secretKey: 'Secret Key',
    bucket: 'Bucket',
    maxFileSize: 'Max File Size',
    testConnection: 'Test Connection',
    connectionSuccess: 'Connection successful',
    smtpConfig: 'SMTP Configuration',
    smtpHost: 'SMTP Host',
    smtpPort: 'SMTP Port',
    smtpUser: 'SMTP Username',
    smtpPassword: 'SMTP Password',
    senderName: 'Sender Name',
    senderEmail: 'Sender Email',
    useTLS: 'Use TLS',
    sendTestEmail: 'Send Test Email',
    testEmailSent: 'Test email sent',
    version: 'Version',
    buildTime: 'Build Time',
    pythonVersion: 'Python Version',
    nodeVersion: 'Node Version',
    os: 'Operating System',
    uptime: 'Uptime',
    database: 'Database',
    redis: 'Redis',
    gpuInfo: 'GPU Info',
    gpuName: 'GPU Name',
    gpuUtilization: 'GPU Utilization',
    gpuTemperature: 'Temperature'
  },

  // Error Pages
  error: {
    forbidden: 'Access Denied',
    notFound: 'Page Not Found',
    serverError: 'Server Error',
    backHome: 'Back to Home',
    '403': {
      title: '403',
      description: "Sorry, you don't have permission to access this page"
    },
    '404': {
      title: '404',
      description: 'Sorry, the page you visited does not exist'
    }
  },

  // Footer
  footer: {
    copyright: '© 2024 CPUModel. All rights reserved.',
    about: 'About Us',
    contact: 'Contact',
    docs: 'Documentation',
    privacy: 'Privacy Policy',
    terms: 'Terms of Service'
  }
}
