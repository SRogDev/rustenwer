# Graph Report — rustenwer  (2026-10-06)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 2703 nodes · 7738 edges · 80 communities (70 shown, 10 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 714 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 77
- Community 78

## God Nodes (most connected - your core abstractions)
1. `ApiUser` - 116 edges
2. `ProjectRepository` - 112 edges
3. `WorkerManager` - 81 edges
4. `isApiOfflineError()` - 81 edges
5. `IntelligenceSpec` - 74 edges
6. `request()` - 72 edges
7. `TrainingStrategy` - 43 edges
8. `lucide-react` - 40 edges
9. `EvaluationManager` - 39 edges
10. `EvaluationRun` - 38 edges

## Surprising Connections (you probably didn't know these)
- `test_architecture_component_kind_values()` --uses--> `ArchitectureComponentKind`  [INFERRED]
  api/tests/test_phase4_intelligence.py → shared/domain.py
- `test_allowed_transitions_cover_all_states()` --uses--> `JobStatus`  [INFERRED]
  api/tests/test_services.py → shared/domain.py
- `bundle_size_bytes()` --uses--> `ModelVersion`  [INFERRED]
  api/app/evaluation/subjects.py → shared/domain.py
- `evaluate_model_version_rows()` --uses--> `ModelVersion`  [INFERRED]
  api/app/evaluation/subjects.py → shared/domain.py
- `load_classifier_bundle()` --uses--> `ModelVersion`  [INFERRED]
  api/app/evaluation/subjects.py → shared/domain.py

## Import Cycles
- 3-file cycle: `api/app/training/__init__.py -> api/app/training/router.py -> api/app/training/worker.py -> api/app/training/__init__.py`
- 3-file cycle: `api/app/evaluation/__init__.py -> api/app/evaluation/router.py -> api/app/evaluation/compare.py -> api/app/evaluation/__init__.py`
- 3-file cycle: `api/app/evaluation/__init__.py -> api/app/evaluation/router.py -> api/app/evaluation/runner.py -> api/app/evaluation/__init__.py`

## Communities (80 total, 10 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (47): _changed_fields(), create_model(), create_model_version(), get_model_lineage(), _get_model_or_404(), get_model_version(), _get_project_or_404(), InMemoryModelRepository (+39 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (40): StubLLM, append_note(), spec_from_dict(), dataset_node(), evaluation_node(), _recommendation(), route_after_baselines(), specification_node() (+32 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (19): create_dataset(), create_version(), DatasetCreate, DatasetRepository, get_dataset(), _get_dataset_or_404(), get_dataset_repository(), _get_project_or_404() (+11 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (16): accuracy(), brier_score(), cost_per_1k_usd(), expected_calibration_error(), latency_p50_ms(), latency_p99_ms(), per_class_accuracy(), EvaluationManager (+8 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (24): ArtifactCorruptedError, ArtifactNotFoundError, ArtifactStore, LocalArtifactStore, _sha256(), _utc_now(), EventSink, _install_signal_handlers() (+16 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (34): _baseline_predictors(), predict(), bundle_size_bytes(), evaluate_baseline_rows(), evaluate_baseline_subject(), evaluate_model_version_rows(), evaluate_subject_rows(), InvalidSubjectError (+26 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (35): _iso(), _iter_checkpoint_files(), latest_checkpoint(), list_checkpoints(), load_checkpoint(), save_checkpoint(), _torch(), attempt_dirs() (+27 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (13): BenchmarkRegistry, InMemoryBenchmarkRepository, ring_benchmark(), _ring_test_rows(), termination_benchmark(), _utc_now(), _comparison_subject(), TestBenchmarks (+5 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (19): get_current_user(), _stub_user(), demo_termination(), TerminationDemoResult, _utc_now(), EvaluationRepository, EvaluationRunRequest, get_evaluation() (+11 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (43): test_health_returns_ok(), _create_deployment(), _create_model(), _create_spec(), test_create_and_list_models(), test_demo_termination_seeds_and_evaluates(), test_demo_termination_unknown_project_404(), test_deployment_cancel_from_anywhere() (+35 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (24): create_project(), delete_project(), _get_or_404(), get_project(), InMemoryProjectRepository, list_projects(), ProjectCreate, ProjectUpdate (+16 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (7): AdapterValidationError, rate_for(), get_training_job_repository(), get_worker_manager(), _LiveAttempt, _utc_now(), WorkerManager

### Community 12 - "Community 12"
Cohesion: 0.07
Nodes (29): get_settings(), BenchmarkRepository, BenchmarkCreate, cancel_evaluation_run(), compare_subjects(), CompareRequest, create_benchmark(), EvaluationRunCreate (+21 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (29): ProjectRepository, cancel_run(), _control(), create_job(), enqueue_run(), EnqueueRunRequest, get_job(), _get_job_or_404() (+21 more)

### Community 14 - "Community 14"
Cohesion: 0.07
Nodes (49): CheckpointInfo, UsageKind, UsageScope, Action, RunControlButtons(), handleEnqueue(), parseHyperparameters(), runAction() (+41 more)

### Community 15 - "Community 15"
Cohesion: 0.07
Nodes (20): _get_project_or_404(), InMemoryUsageRepository, record_usage_event(), usage_rollups(), usage_summary(), UsageEventCreate, UsageRepository, _utc_now() (+12 more)

### Community 16 - "Community 16"
Cohesion: 0.07
Nodes (32): _spec(), test_allowed_transitions_cover_all_states(), test_detect_leakage_flags_label_copy(), test_detect_leakage_ignores_unique_identifiers(), test_detect_leakage_no_label_column(), test_diagnose_learning_signal_beats_deterministic_pattern(), test_diagnose_no_ml_conclusion(), test_diagnose_rationale_answers_ten_questions() (+24 more)

### Community 17 - "Community 17"
Cohesion: 0.09
Nodes (45): METHOD_CATEGORIES, MethodCategory, MethodRank, MethodRecommendation, MethodValidationStatus, MethodVeto, ResearchFinding, TrainingMethod (+37 more)

### Community 18 - "Community 18"
Cohesion: 0.08
Nodes (16): create_deployment(), DeploymentCreate, DeploymentRepository, DeploymentUpdate, get_deployment(), _get_deployment_or_404(), get_deployment_repository(), get_intelligence_repository_hook() (+8 more)

### Community 19 - "Community 19"
Cohesion: 0.08
Nodes (23): _architecture_summary(), _components_for(), create_intelligence(), create_intelligence_version(), diff_intelligence_versions(), get_intelligence(), _get_intelligence_or_404(), get_intelligence_repository() (+15 more)

### Community 20 - "Community 20"
Cohesion: 0.09
Nodes (43): Dataset, DatasetReport, DatasetVersion, Evaluation, DatasetsPage(), dynamic, metadata, dynamic (+35 more)

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (5): ComputeProvider, DigitalOceanComputeProvider, ExecutionHandle, LocalComputeProvider, ProviderCredentialsError

### Community 22 - "Community 22"
Cohesion: 0.07
Nodes (16): get_provider(), SchemaValidationError, _get_deployment_or_404(), get_intelligence_repository_hook(), get_model_repository_hook(), get_usage_repository_hook(), infer_deployment(), _utc_now() (+8 more)

### Community 23 - "Community 23"
Cohesion: 0.09
Nodes (10): _accuracy_of(), _build_mlp(), CostEstimate, _count_params(), DistillationAdapter, LoRAAdapter, _synthetic_blobs(), _TeacherMLP (+2 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (20): _check(), main(), _create_dataset(), _create_version(), _rows_payload(), test_create_and_list_datasets(), test_create_version_computes_report(), test_create_version_empty_rows_422() (+12 more)

### Community 25 - "Community 25"
Cohesion: 0.09
Nodes (14): build_comparison_report(), _fmt(), subject_label(), _utc_now(), _verdict_note(), assemble_quality_vector(), beats_bar(), is_better_per_priorities() (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.05
Nodes (37): @biomejs/biome, react-dom, tailwindcss, @tailwindcss/postcss, @types/node, @types/react, @types/react-dom, typescript (+29 more)

### Community 27 - "Community 27"
Cohesion: 0.10
Nodes (31): next, Intelligence, IntelligenceSpec, IntelligenceVersion, IntelligenceVersionDiff, dynamic, metadata, NewDeploymentPage() (+23 more)

### Community 28 - "Community 28"
Cohesion: 0.07
Nodes (34): AdapterRegistration, ApiUser, ARCHITECTURE_KINDS, ArchitectureComponentKind, ArtifactRecord, BaselineMetrics, BaselineReport, CandidateLifecycle (+26 more)

### Community 29 - "Community 29"
Cohesion: 0.09
Nodes (33): TrainingRun, dynamic, EmptyState(), formatBytes(), formatDateTime(), formatScalar(), formatUsd(), JobDetailPage() (+25 more)

### Community 30 - "Community 30"
Cohesion: 0.13
Nodes (18): _column_value(), ComponentExecutionError, _exec_baseline(), _exec_deterministic_rule(), _exec_model_version(), _exec_post_processor(), _exec_threshold(), _execute_component() (+10 more)

### Community 31 - "Community 31"
Cohesion: 0.11
Nodes (11): FileJobQueue, JobQueue, QueuedItem, _ids(), test_claim_fifo_order(), test_enqueue_claim_roundtrip(), test_enqueue_same_run_id_replaces(), test_pending_lists_without_removing() (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.08
Nodes (5): InMemoryTrainingJobRepository, _utc_now(), test_sse_stream_emits_data_lines_and_done(), TrainingJob, TrainingRun

### Community 33 - "Community 33"
Cohesion: 0.06
Nodes (34): noAriaUnsupportedElements, useValidAriaValues, noUnusedImports, noUnusedVariables, css, parser, files, ignoreUnknown (+26 more)

### Community 34 - "Community 34"
Cohesion: 0.09
Nodes (4): DuplicateVersionError, InMemoryIntelligenceRepository, Intelligence, IntelligenceVersion

### Community 35 - "Community 35"
Cohesion: 0.13
Nodes (4): AdapterContext, _prepare_blobs(), _TorchSupervisedAdapter, TrainingMethodAdapter

### Community 36 - "Community 36"
Cohesion: 0.16
Nodes (17): Settings, _create_job(), exec_client(), _strategy_json(), test_enqueue_409_digitalocean_without_token(), test_enqueue_409_no_training_needed(), test_enqueue_409_qlora_on_local(), test_enqueue_409_unknown_method() (+9 more)

### Community 37 - "Community 37"
Cohesion: 0.12
Nodes (14): approve_spec(), create_spec(), diagnose(), _get_project_or_404(), get_spec(), _get_spec_or_404(), get_spec_repository(), list_specs() (+6 more)

### Community 38 - "Community 38"
Cohesion: 0.16
Nodes (23): _baseline_report(), _diagnosis(), _methods_by_slug(), _spec(), test_citations_reference_ranked_methods(), test_contrastive_allowed_with_allow_generic(), test_contrastive_recommended_for_ranking(), test_contrastive_vetoed_for_pure_classification() (+15 more)

### Community 39 - "Community 39"
Cohesion: 0.17
Nodes (13): _eval_app(), _make_mlp_bundle(), _make_project(), _manager(), _record_usage(), _on_finish(), _register_model_version(), _stub_user() (+5 more)

### Community 40 - "Community 40"
Cohesion: 0.15
Nodes (21): react, ComparisonReport, ComparisonSubjectResult, SubjectKind, ComparePanel(), handleCompare(), formatQv(), QUALITY_ROWS (+13 more)

### Community 41 - "Community 41"
Cohesion: 0.11
Nodes (27): JobStatus, UsageRollups, UsageSummary, CostRollupsSection(), dynamic, EmptyState(), formatDateTime(), formatPercent() (+19 more)

### Community 42 - "Community 42"
Cohesion: 0.13
Nodes (11): ArchitectureValidationError, _component_key(), diff_architectures(), _model_repository_get_version(), summarize_architecture(), validate_architecture(), _validate_component(), _arch_of() (+3 more)

### Community 43 - "Community 43"
Cohesion: 0.11
Nodes (27): ModelVersion, BenchmarkDetailPage(), dynamic, formatDateTime(), formatScalar(), metadata, withOffline(), dynamic (+19 more)

### Community 44 - "Community 44"
Cohesion: 0.19
Nodes (19): job_repo(), _make_job(), manager(), _now(), _strategy(), test_brutal_kill_marks_run_failed(), test_cancel_writes_graceful_checkpoint(), test_e2e_local_training_completes_with_artifacts() (+11 more)

### Community 45 - "Community 45"
Cohesion: 0.24
Nodes (20): auth_headers(), _deploy(), _project(), _repos(), _spec(), _termination_version(), test_deploy_model_version_auto_creates_intelligence(), test_deploy_requires_exactly_one_target() (+12 more)

### Community 46 - "Community 46"
Cohesion: 0.20
Nodes (19): ClassifierAdapter, _ctx(), _metric_epochs(), _strategy(), test_classifier_estimate_is_sane(), test_classifier_evaluate_and_export(), test_classifier_prepare_is_deterministic(), test_classifier_prepare_materializes_dataset() (+11 more)

### Community 47 - "Community 47"
Cohesion: 0.13
Nodes (24): EvaluationRun, EvaluationStatus, QualityVector, dynamic, EvaluationRunPage(), metadata, withOffline(), COST_DIMENSIONS (+16 more)

### Community 48 - "Community 48"
Cohesion: 0.11
Nodes (14): MethodRank, MethodVeto, TrainingMethod, _has_labeled_signal(), _method(), _score_method(), _spec_latency_budget_ms(), _spec_text() (+6 more)

### Community 49 - "Community 49"
Cohesion: 0.13
Nodes (22): ArchitectureComponent, Deployment, DeploymentStatus, IntelligenceArchitecture, DeploymentDetailPage(), dynamic, metadata, ArchitectureComponentCard() (+14 more)

### Community 50 - "Community 50"
Cohesion: 0.14
Nodes (22): Benchmark, Model, dynamic, metadata, RegistryPage(), withOffline(), BenchmarkCreateForm(), handleSubmit() (+14 more)

### Community 51 - "Community 51"
Cohesion: 0.12
Nodes (7): ExternalAPIProvider, HostedInferenceProvider, InferenceProviderBase, LocalGPUProvider, list_providers(), InferenceProvider, ProviderInfo

### Community 52 - "Community 52"
Cohesion: 0.13
Nodes (7): get_research_repository(), InMemoryResearchRepository, ResearchFindingRepository, test_research_finding_schema_rejects_missing_fields(), test_research_repository_protocol(), test_research_seed_findings(), ResearchFinding

### Community 53 - "Community 53"
Cohesion: 0.28
Nodes (17): _create_spec(), _spec_payload(), test_approve_from_draft_and_diagnosed(), test_approve_twice_409(), test_create_spec_auto_detect_falls_back_to_decision(), test_create_spec_returns_draft(), test_create_spec_unknown_project_404(), test_create_spec_without_primitive_auto_detects() (+9 more)

### Community 54 - "Community 54"
Cohesion: 0.16
Nodes (16): lucide-react, Home(), ROADMAP, dynamic, metadata, ProjectsPage(), NewProjectForm(), handleSubmit() (+8 more)

### Community 55 - "Community 55"
Cohesion: 0.13
Nodes (8): get_method(), get_method_catalog(), list_methods(), list_research(), recommend(), RecommendRequest, MethodCategory, MethodRecommendation

### Community 56 - "Community 56"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 57 - "Community 57"
Cohesion: 0.20
Nodes (11): _fake_diagnose_spec(), _fake_propose_strategy(), _fake_run_baselines(), _fake_termination_dataset_rows(), _fake_termination_spec_fields(), _fake_validate_dataset_version(), install_service_doubles(), _ml_necessary() (+3 more)

### Community 58 - "Community 58"
Cohesion: 0.14
Nodes (3): InMemorySpecRepository, test_spec_detail_other_org_404(), IntelligenceSpec

### Community 59 - "Community 59"
Cohesion: 0.18
Nodes (11): auth_headers(), client(), dataset_repository(), deployment_repository(), evaluation_repository(), model_repository(), project_id(), repository() (+3 more)

### Community 60 - "Community 60"
Cohesion: 0.14
Nodes (6): configure_logging(), get_logger(), create_app(), lifespan(), test_methods_endpoints(), test_research_endpoint()

### Community 61 - "Community 61"
Cohesion: 0.12
Nodes (3): TestCancelEndpoint, TestRouter, _wait_for_run()

### Community 62 - "Community 62"
Cohesion: 0.17
Nodes (7): test_detect_environment_shape(), BaselineReport, detect_environment(), strategy_defaults_for(), propose_strategy(), _recommend(), _row_count()

### Community 63 - "Community 63"
Cohesion: 0.18
Nodes (5): assert_registered(), RegistryInconsistencyError, test_registry_every_validated_local_method_has_adapter(), test_seed_taxonomy_complete(), MethodValidationStatus

### Community 64 - "Community 64"
Cohesion: 0.19
Nodes (3): AdapterEnvironmentError, QLoRAAdapter, test_qlora_provider_support()

### Community 66 - "Community 66"
Cohesion: 0.15
Nodes (9): get_adapter(), TrainContext, test_get_adapter_none_raises(), test_get_adapter_unknown_method_raises(), _strategy_for(), test_contrastive_learns(), test_distillation_and_contrastive_validate_rejects_wrong_method(), test_distillation_learns_and_beats_scratch() (+1 more)

### Community 67 - "Community 67"
Cohesion: 0.26
Nodes (12): INTELLIGENCE_PRIMITIVES, IntelligencePrimitive, dynamic, NewSpecPage(), goTo(), handleCreate(), validateStep(), parseJsonObject() (+4 more)

### Community 68 - "Community 68"
Cohesion: 0.27
Nodes (5): IntelligencePrimitive, detect_primitive(), diagnose_spec(), _guess_primitive(), _matches_any()

### Community 69 - "Community 69"
Cohesion: 0.27
Nodes (10): MetricSeries, RunMetrics, formatValue(), LossChart(), PAD, RunMetricsPanel(), fetchMetrics(), STAT_KEYS (+2 more)

### Community 70 - "Community 70"
Cohesion: 0.27
Nodes (7): body, display, metadata, RootLayout(), SiteFooter(), BrandMark(), SiteHeader()

## Knowledge Gaps
- **163 isolated node(s):** `Action`, `CompareBenchmarkInput`, `CreateBenchmarkInput`, `CreateDatasetVersionInput`, `CreateDeploymentInput` (+158 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 898 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `WorkerManager` connect `Community 11` to `Community 32`, `Community 4`, `Community 36`, `Community 6`, `Community 44`, `Community 13`, `Community 15`, `Community 21`, `Community 23`, `Community 31`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 97 inferred relationships involving `ApiUser` (e.g. with `get_current_user()` and `create_dataset()`) actually correct?**
  _`ApiUser` has 97 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Action`, `CompareBenchmarkInput`, `CreateBenchmarkInput` to the rest of the system?**
  _163 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05194805194805195 - nodes in this community are weakly interconnected._
- **Why does `ApiUser` connect `Community 13` to `Community 0`, `Community 2`, `Community 37`, `Community 39`, `Community 8`, `Community 7`, `Community 10`, `Community 12`, `Community 15`, `Community 18`, `Community 51`, `Community 19`, `Community 22`, `Community 55`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 86 inferred relationships involving `ProjectRepository` (e.g. with `create_dataset()` and `create_version()`) actually correct?**
  _`ProjectRepository` has 86 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05570611261668172 - nodes in this community are weakly interconnected._