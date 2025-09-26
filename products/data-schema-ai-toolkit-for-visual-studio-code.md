# AI Toolkit for Visual Studio Code - Product and Data Overview Template

## 1. Product Overview

AI Toolkit for Visual Studio Code provides AI workflows inside VS Code, including model browsing, playground, agent builder, evaluation, finetuning, and model lab. This schema draft is based on telemetry queries and conventions used across the product’s dashboards.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
AI Toolkit for Visual Studio Code
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx
- **Kusto Database**:
vscode-ext-aggregate
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# AI Toolkit for Visual Studio Code - Kusto Query Playbook

## Overview
- Product: AI Toolkit for Visual Studio Code
- Summary: Use the OS, Versions and Time Range filter(s). Default filters: All OS, All versions and Last 30 days. On each dashboard tile, click "... → View query" to see the full query. To run queries yourself, connect to cluster 'kustoproxytest.azure-api.net/rentu-test-product/teamsfx', database 'vscode-ext-aggregate', and use the 'aitoolkit_vscode' table.
- Main cluster: https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx
- Main database: vscode-ext-aggregate
- Note: Ignore pages marked as WIP or Legacy: "Tracing (WIP)", "(WIP)", "Bulk Run (Legacy)". If seeing "Unknown" connection error, follow the provided doc to configure connection settings.

## Conventions & Assumptions

### Time semantics
- Canonical time columns observed:
  - ServerTimestamp: primary event timestamp for most queries (DAU/MAU, funnels, usage).
  - ClientTimestamp: used in the 28-day funnel path queries for session-level sequencing.
- Aliases and normalization:
  - eventDay = startofday(ServerTimestamp) commonly used for daily aggregates.
  - EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/")) normalizes event names by removing the common prefix.
- Typical windows and binning:
  - Rolling windows: 28d for MAU/MEU; 7d for WAU; 1d for DAU.
  - Daily binning via startofday() and manual sliding windows implemented with bin_at(), range(), and mv-expand.
- Timezone: Not specified; treat timestamps as UTC by default.
- Effective end time:
  - Many queries set End to startofday(now(-1d)) to avoid incomplete current-day data due to pipeline delay.
  - Exclude early slices without full rolling coverage: where range >= Start + LookbackWindow.

### Freshness & Completeness Gates
- Ingestion cadence: Unknown; queries consistently gate End to yesterday.
- Recommended practices:
  - Avoid using current day; use an effective end time of startofday(now(-1d)).
  - For rolling windows, drop the first LookbackWindow period from output to ensure completeness.
  - If multi-slice completeness is needed (regions/OS/versions), compute the last day where ≥N sentinel slices (e.g., platforms) have non-zero counts before selecting End.

### Joins & Alignment
- Frequent keys:
  - VSCodeMachineId: unique machine identifier; primary user proxy for counts and distinct computations.
  - VSCodeSessionId: session-level sequencing in funnels.
  - PromptID: agent identifier in Agent Builder.
- Typical join kinds:
  - inner joins to map events to steps (via datatable event→step).
  - inner joins on eventDay vs firstDay for new user derivation.
  - leftouter joins for top-N grouping and "Others".
- Post-join hygiene:
  - After joins that create duplicate column names, use project-rename or explicit project() to disambiguate (e.g., Country vs Others).
  - Drop unused columns with project-away or limit via project to reduce payload.

### Filters & Idioms
- Default exclusions frequently applied:
  - EventInfo_Name !startswith "activation_details".
  - Exclude survey-timeout dismiss: not(EventInfo_Name == "survey_selection" and Properties['action'] == "dismiss").
  - Exclude model listing noise: not(EventInfo_Name in ("chat_provider_list_models-start", "chat_provider_list_models")).
- Released versions filter:
  - ExtensionVersion != "" and ExtensionVersion !contains "-" and ExtensionVersion !startswith "0.0." to exclude test vsix and prereleases.
- Platform handling:
  - Platform in ['win32','darwin','linux'] and arch from Properties["common.nodearch"] to form Platform_Arch.
- Success/non-failure semantics:
  - success = Properties['success'] == "true".
  - non_failure = success or Properties['error'] in ("Canceled","Operation cancelled.").

### Cross-cluster/DB & Sharding
- Primary source: aitoolkit_vscode in vscode-ext-aggregate (teamsfx proxy cluster).
- Secondary cross-cluster source: RawEventsVSCodeExt on ddtelfiltered.centralus cluster, used for GHCP "panel.request" events due to access limits.
- Qualification:
  - Use cluster("<url>") and database("<db>") if running cross-cluster; provided queries reference table names directly within known connections.
- Sharded unions:
  - Same-schema action unions are constructed via union() across event subsets before normalization and summarization.

### Table classes
- Fact tables: aitoolkit_vscode, RawEventsVSCodeExt (event facts).
- Snapshots/pre-aggregated: None observed; all metrics derived directly from facts with summarize.

### Important Mapping
- Funnels rely on explicit datatable mappings of EventName→Action/Step, reused across:
  - Overall funnel (activation → open/get started → browse model → open playground → add/edit/run ...).
  - Agent Builder actions and evaluation steps.
  - Tutorials actions (including legacy/renamed events).
- Model provider classification:
  - ONNX and "ONNX (Converted)" treated as local models.
  - "Ollama" separated; otherwise classified as "Cloud".
- Early GitHub models:
  - A placeholder list (earlyGHModels) used to backfill missing 'model-provider' property to "GitHub" for early releases.

### Acceptance Checklist
- Identified timestamp columns (ServerTimestamp, ClientTimestamp), typical windows (28d/7d/1d), bin usage (startofday, bin_at/range), timezone unknown → use UTC.
- Documented freshness strategy: End = startofday(now(-1d)); exclude initial LookbackWindow days for rolling completeness.
- Produced entity model and counting rules; clarified snapshot vs daily facts and rolling semantics.
- Called out unions across related actions; cross-cluster usage for GHCP and provided a union pattern for same-schema event families.
- Included default exclusions (activation_details, survey dismiss, model list noise) and version filters with placeholders.
- Provided ID parsing/derivation snippets (EventInfo_Name substring, ModelNamePrefix split; provider backfill).
- Example queries are copy-paste-ready with parameters and explanations; more than six included.
- No fabricated fields/values; placeholders used where specifics (e.g., earlyGHModels list, version arrays) lack full details.

## Entity & Counting Rules (Core Definitions)
- Entity model:
  - Machine → Session → Action
    - VSCodeMachineId: proxy for a unique user across days.
    - VSCodeSessionId: scope for funnel sequence ordering.
    - PromptID: identifies agents in Agent Builder.
- Counting levels:
  - Daily: distinct VSCodeMachineId per eventDay for DAU; with min(eventDay) to derive new users.
  - Rolling: countif across sliding windows for MAU/MEU/WAU.
  - Model/provider breakdowns: distinct users per model/provider; counts per model/provider.
- Business definitions:
  - Active user: at least 1 active day within LookbackWindow.
  - Engaged user: at least 2 active days within LookbackWindow.
  - Non-failure: success or cancellation semantics used as "success" for rate computation in some funnels.
  - Active agent: PromptID has open/run/update events; distinct PromptID per day; rolling definitions for monthly active/engaged agents.

## Views (Reusable Layers)
- No database views provided. Reusable layers are implemented via let blocks and datatable mappings within queries:
  - stepEvents/eventToStep datatable: maps raw events to semantic steps used across funnels (Overall, Agent Builder, Evaluation, Tutorials).
  - provider classification logic: converts Properties["model-provider"] and model-name heuristics into provider categories ("ONNX/Converted", "Ollama", "Cloud").
  - success/non-failure derivation: standardizes Properties['success'] and certain error states.

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Standard Start/End gate with previous-day end to avoid ingestion lag; daily normalization via eventDay.
  - Query:
    ```kusto
    // Use UTC; gate current day to avoid pipeline delay
    let Start = iff(startofday(INPUT_TIME_START) == startofday(now()),
                    startofday(now(-1d)),
                    startofday(INPUT_TIME_START));
    let End   = iff(startofday(INPUT_TIME_END) == startofday(now()),
                    startofday(now(-1d)),
                    startofday(INPUT_TIME_END));
    // Daily bin
    | extend eventDay = startofday(ServerTimestamp)
    | where eventDay <= End and ServerTimestamp >= Start
    ```

- Rolling MAU/MEU sliding window
  - Description: Manual sliding window for active/engaged definitions; excludes first LookbackWindow period lacking full data.
  - Query:
    ```kusto
    let LookbackWindow = 28d;
    let Start = startofday(INPUT_TIME_START - LookbackWindow);
    let End   = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
    let activeDays  = 1;
    let engagedDays = 2;

    // Distinct user-day activity pre-filtered
    | extend eventDay = startofday(ServerTimestamp)
    | distinct VSCodeMachineId, eventDay
    // Sliding window indices
    | extend bin      = bin_at(eventDay, 1d, Start)
    | extend endRange = iff(bin + LookbackWindow > End, End,
                        iff(bin + LookbackWindow - 1d < Start, Start,
                        iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
    | extend range = range(bin, endRange, 1d)
    | mv-expand range to typeof(datetime)
    | where range != datetime(null)
    | summarize actDays = count() by VSCodeMachineId, range
    | extend isA = iff(actDays >= activeDays, 1, 0),
             isE = iff(actDays >= engagedDays, 1, 0)
    | summarize AU = min(isA), EU = min(isE) by VSCodeMachineId, range
    | summarize MAU = countif(AU > 0), MEU = countif(EU > 0) by range
    | where range >= Start + LookbackWindow
    ```

- DAU: new vs. existing cohort
  - Description: Count all active users per day and derive "new" by earliest eventDay; join to compute existing.
  - Query:
    ```kusto
    // All users per day
    let allDaily =
      aitoolkit_vscode
      | <filters>
      | extend eventDay = startofday(ServerTimestamp)
      | distinct VSCodeMachineId, eventDay
      | summarize all = count() by eventDay;

    // First activity day per user → new users per day
    let firstDaily =
      aitoolkit_vscode
      | <same filters>
      | extend eventDay = startofday(ServerTimestamp)
      | distinct VSCodeMachineId, eventDay
      | summarize firstDay = min(eventDay) by VSCodeMachineId
      | summarize new = count() by firstDay;

    allDaily
    | join kind=inner firstDaily on $left.eventDay == $right.firstDay
    | project eventDay, all, new, existing = all - new
    ```

- Success/non-failure gating
  - Description: Normalize Properties['success'] and treat certain error values as non-failure to compute success_rate.
  - Query:
    ```kusto
    | extend success = case(Properties['success'] == "true", "True", "False")
    | extend non_failure = case(
        Properties['success'] == "true" or
        Properties['error'] == "Canceled" or
        Properties['error'] == "Operation cancelled.", "True", "False")
    | summarize success_ = count_distinctif(VSCodeMachineId, non_failure == "True"),
                all_     = count_distinct(VSCodeMachineId) by step
    | extend success_rate = round((todouble(success_) / all_) * 100, 2)
    ```

- Important filters (defaults/exclusions)
  - Description: Common noise exclusions to stabilize metrics.
  - Query:
    ```kusto
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
    | where EventInfo_Name !startswith "activation_details"
    | extend surveyAction = tostring(Properties['action'])
    | where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss")
    | where not(EventInfo_Name in ("chat_provider_list_models-start", "chat_provider_list_models"))
    // Released versions only
    | where ExtensionVersion != "" and ExtensionVersion !contains "-" and ExtensionVersion !startswith "0.0."
    ```

- Provider classification and early model backfill
  - Description: Standardize provider category and backfill early GitHub models with missing provider.
  - Query:
    ```kusto
    let earlyGHModels = dynamic([
      // Placeholder list used to backfill missing GitHub provider in early releases
      "Meta-Llama-3-8B-Instruct", "gpt-4o", "Phi-3.5-mini-instruct" /* ... */
    ]);
    | extend model_name = tostring(Properties["model-name"])
    | extend providerX  = tostring(Properties["model-provider"])
    | extend provider   = iff(providerX != "", providerX,
                         iff(model_name endswith "-onnx" or model_name endswith "-cpu" or model_name endswith "-gpu", "ONNX",
                         iff(model_name in (earlyGHModels), "GitHub", "")))
    | extend Category   = case(
        provider in ("ONNX", "ONNX (Converted)"), "ONNX/Converted",
        provider == "Ollama", "Ollama",
        "Cloud")
    ```

- ID parsing/derivation
  - Description: Normalize event names and derive prefixes from model names.
  - Query:
    ```kusto
    // EventInfo_Name
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))

    // ModelNamePrefix for Ollama models (e.g., "llama3:latest" → "llama3")
    | extend ModelNamePrefix = tostring(split(tostring(Properties["model-name"]), ":")[0])
    ```

- Top-N with “Others”
  - Description: Top-20 countries with an “Others” bucket.
  - Query:
    ```kusto
    let counts = aitoolkit_vscode
      | <filters>
      | distinct VSCodeMachineId, GeoCountryRegionIso
      | summarize count() by GeoCountryRegionIso;
    let top20 = counts | top 20 by count_;
    counts
    | join kind=leftouter top20 on GeoCountryRegionIso
    | extend Country = iff(GeoCountryRegionIso1 != "", GeoCountryRegionIso1, "Others")
    | summarize Count = sum(count_) by Country
    ```

- Sharded union (merge related actions)
  - Description: Combine multiple related event sources into a unified action series.
  - Query:
    ```kusto
    union
    (
      aitoolkit_vscode
      | where EventName in (".../inference_model_download", ".../add_remote_inference_endpoint", ".../inference_model_add_my_model")
      | project model_name = tostring(Properties["model-name"]), VSCodeMachineId, eventDay = startofday(ServerTimestamp), action = "Add/Edit"
    ),
    (
      aitoolkit_vscode
      | where EventName in (".../inference_model_load", ".../inference_model_connect")
      | project model_name = tostring(Properties["model-name"]), VSCodeMachineId, eventDay = startofday(ServerTimestamp), action = "Load"
    ),
    (
      aitoolkit_vscode
      | where EventName == ".../inference_model_run"
      | project model_name = tostring(Properties["model-name"]), VSCodeMachineId, eventDay = startofday(ServerTimestamp), action = "Run"
    )
    | where model_name != ""
    | distinct VSCodeMachineId, eventDay, action
    | summarize ["Add/Edit"] = countif(action == "Add/Edit"),
                ["Load"]     = countif(action == "Load"),
                ["Run"]      = countif(action == "Run") by eventDay
    ```

## Example Queries (with explanations)

1) MAU/MEU (28 days rolling) - Overall
- Intent: Measure monthly active and engaged users across all meaningful events with rolling completeness. Filters OS and extension version. Excludes activation-details and survey dismiss/list events. Uses sliding window and gates current day.
- How to adapt: Change LookbackWindow, activeDays/engagedDays, or filters; keep the End gate.
```kusto
let LookbackWindow = 28d;
let Start = startofday(INPUT_TIME_START - LookbackWindow);
let End   = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let activeDays  = 1;
let engagedDays = 2;
aitoolkit_vscode
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
| extend surveyAction = tostring(Properties['action'])
| where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss")
      and not(EventInfo_Name in ("chat_provider_list_models-start","chat_provider_list_models"))
| where EventInfo_Name !startswith "activation_details"
| extend eventDay = startofday(ServerTimestamp)
| distinct VSCodeMachineId, eventDay
| extend bin = bin_at(eventDay, 1d, Start)
| extend endRange = iff(bin + LookbackWindow > End, End,
                        iff(bin + LookbackWindow - 1d < Start, Start,
                        iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
| extend range = range(bin, endRange, 1d)
| mv-expand range to typeof(datetime)
| where range != datetime(null)
| summarize actDays = count() by VSCodeMachineId, range
| extend isA = iff(actDays >= activeDays, 1, 0), isE = iff(actDays >= engagedDays, 1, 0)
| summarize AU = min(isA), EU = min(isE) by VSCodeMachineId, range
| summarize MAU = countif(AU > 0), MEU = countif(EU > 0) by range
| where range >= Start + LookbackWindow
| project range, MAU, MEU
```

2) Daily Active User (new vs existing) - Overall
- Intent: Count daily active users and split into new vs. existing by earliest activity day. Applies exclusions; gates End to yesterday.
- How to adapt: Replace the event filter or source table; adjust time window; keep the join pattern for cohorting.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End   = iff(startofday(INPUT_TIME_END)   == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));

(
    aitoolkit_vscode
    | where ExtensionVersion in (['INPUT_EXT_VER'])
    | where Platform in (['INPUT_OS'])
    | where ServerTimestamp >= Start
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
    | extend surveyAction = tostring(Properties['action'])
    | where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss")
          and not(EventInfo_Name in ("chat_provider_list_models-start","chat_provider_list_models"))
    | where EventInfo_Name !startswith "activation_details"
    | extend eventDay = startofday(ServerTimestamp)
    | where eventDay <= End
    | distinct VSCodeMachineId, eventDay
    | summarize all = count() by eventDay
)
| join kind=inner
(
    aitoolkit_vscode
    | where ExtensionVersion in (['INPUT_EXT_VER'])
    | where Platform in (['INPUT_OS'])
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
    | extend surveyAction = tostring(Properties['action'])
    | where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss")
          and not(EventInfo_Name in ("chat_provider_list_models-start","chat_provider_list_models"))
    | where EventInfo_Name !startswith "activation_details"
    | extend eventDay = startofday(ServerTimestamp)
    | where eventDay <= End
    | distinct VSCodeMachineId, eventDay
    | summarize firstDay = min(eventDay) by VSCodeMachineId
    | summarize new = count() by firstDay
)
on $left.eventDay == $right.firstDay
| project eventDay, all, new, existing = all - new
```

3) Funnel (and success rate) - Overall
- Intent: Compute distinct users per funnel step mapped from raw events and a non-failure success rate. Uses a stepEvents mapping; success includes cancellations.
- How to adapt: Modify stepEvents mapping or success logic; keep distinct counts by VSCodeMachineId.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End   = iff(startofday(INPUT_TIME_END)   == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let stepEvents = datatable(step: string, events: dynamic)
[
    "activation", dynamic(["activation_details"]),
    "open get started", dynamic(["open_get_started_page"]),
    "browse model", dynamic(["model_catalog_open","open_model_card","open_model_license"]),
    "open playground", dynamic(["playground_open"]),
    "add/edit my model", dynamic(["add_remote_inference_endpoint","edit_remote_inference_endpoint","delete_model","inference_model_download","inference_model_add_my_model"]),
    "chat in playground", dynamic(["click_conversation_starter","inference_model_run","chat_create","chat_switch","chat_rename","chat_delete"]),
    "agent builder", dynamic(["prompt_builder_list","prompt_builder_create","prompt_builder_rename","prompt_builder_delete","promptBuilderSave","prompt_builder_run","prompt_builder_get_code","prompt_builder_generate_prompt","prompt_builder_select_json_format"]),
    "create evaluation", dynamic(["create_evaluation"]),
    "start evaluation", dynamic(["start_evaluation"]),
    "view evaluation", dynamic(["view_evaluations"]),
    "finetuning", dynamic(["finetuning_configure_project","finetuning_generate_project","finetuning_provision","finetuning_run"]),
];
let eventToStep = stepEvents | mv-expand events | project step, event = tostring(events);
(
    aitoolkit_vscode
    | where ExtensionVersion in (['INPUT_EXT_VER'])
    | where Platform in (['INPUT_OS'])
    | where ServerTimestamp >= Start
    | extend eventDay = startofday(ServerTimestamp)
    | where eventDay <= End
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
    | extend success = case(Properties['success'] == "true", "True", "False")
    | extend non_failure = case(
        Properties['success'] == "true"
        or Properties['error'] == "Canceled"
        or Properties['error'] == "Operation cancelled.", "True", "False")
    | distinct event = EventInfo_Name, uid = VSCodeMachineId, success, non_failure
)
| join kind=inner (eventToStep) on $left.event == $right.event
| distinct step, uid, success, non_failure
| summarize success_ = count_distinctif(uid, non_failure == "True"),
            all_     = count_distinct(uid) by step
| order by all_ desc
| extend success_rate = round((todouble(success_) / all_) * 100, 2)
| project Step=step, Success=success_, All=all_, SuccessRate=success_rate
```

4) Model run by user - Model page
- Intent: Count distinct users running inference by model and provider; backfill provider for early models and local model heuristics. Shows success vs all.
- How to adapt: Limit to specific providers or models; adjust time window.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End   = iff(startofday(INPUT_TIME_END)   == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let earlyGHModels = dynamic([/* placeholder model list for backfill */]);
aitoolkit_vscode
| where EventName == "ms-windows-ai-studio.windows-ai-studio/inference_model_run"
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend eventDay = startofday(ServerTimestamp)
| where eventDay <= End
| extend model_name = tostring(Properties["model-name"])
| extend type       = iff(model_name endswith "-onnx" or model_name endswith "-cpu" or model_name endswith "-gpu", "local", "remote")
| extend providerX  = tostring(Properties["model-provider"])
| extend provider   = iff(providerX != "", providerX,
                        iff(type == "local", "ONNX",
                        iff(model_name in (earlyGHModels), "GitHub", "")))
| extend success = case(Properties['success'] == "true", "True", "False")
| where model_name != ""
| distinct VSCodeMachineId, model_name, provider, success
| summarize success_ = count_distinctif(VSCodeMachineId, success == "True"),
            all_     = count_distinct(VSCodeMachineId) by model_name, provider
| order by all_ desc
```

5) Active user by Country (top 20 + Others) - Overall
- Intent: Distinct users per GeoCountryRegionIso with a top-20 display and an “Others” bucket.
- How to adapt: Change top N; add platform/version filters.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End   = iff(startofday(INPUT_TIME_END)   == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let countByCountry =
  aitoolkit_vscode
  | where ExtensionVersion in (['INPUT_EXT_VER'])
  | where Platform in (['INPUT_OS'])
  | where ServerTimestamp >= Start
  | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
  | where EventInfo_Name !startswith "activation_details"
  | extend surveyAction = tostring(Properties['action'])
  | where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss")
        and not(EventInfo_Name in ("chat_provider_list_models-start","chat_provider_list_models"))
  | extend eventDay = startofday(ServerTimestamp)
  | where eventDay <= End
  | distinct VSCodeMachineId, GeoCountryRegionIso
  | summarize count() by GeoCountryRegionIso;
let top20 = countByCountry | top 20 by count_;
countByCountry
| join kind=leftouter top20 on GeoCountryRegionIso
| extend Country = iff(GeoCountryRegionIso1 != "", GeoCountryRegionIso1, "Others")
| summarize Count = sum(count_) by Country
```

6) Agent Builder User Actions with Success Rates
- Intent: Track key Agent Builder steps with order, distinct users, and success rates (non-failure). Filters event source by view-id for specific steps.
- How to adapt: Add/remove steps; adjust success definition or ordering; keep distinct user counting.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End   = iff(startofday(INPUT_TIME_END)   == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let eventToStep = datatable(event: string, step: string, order: int)
[
  "open_prompt_builder", "Open", 1,
  "inference_model_load", "Has Model", 2,
  "has_system_prompt_value_in_prompt_builder", "Has System/User Prompt", 3,
  "has_message_value_in_prompt_builder", "Has System/User Prompt", 3,
  "use_prompt_starter", "Click Starter", 4,
  "prompt_builder_generate_prompt", "Generate Prompt", 5,
  "mcp_select_tools", "Add Tools to Agent", 6,
  "mcp_add", "Add new MCP", 9,
  "mcp_server_scaffold", "Create MCP template", 10,
  "prompt_builder_run", "Run", 7,
  "prompt_builder_get_code", "View Code", 8
];
(
    aitoolkit_vscode
    | where ExtensionVersion in (['INPUT_EXT_VER'])
    | where Platform in (['INPUT_OS'])
    | where ServerTimestamp >= Start
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
    | extend eventDay = startofday(ServerTimestamp)
    | where eventDay <= End
    | extend viewId = tostring(Properties['view-id'])
    | where (EventInfo_Name != "inference_model_load" and EventInfo_Name != "create_evaluation" and EventInfo_Name != "start_evaluation") or viewId == "promptBuilder"
    | extend success = case(Properties['success'] == "true"
                            or Properties['error'] == "Canceled"
                            or Properties['error'] == "Operation cancelled.", "True", "False")
    | distinct event = EventInfo_Name, uid = VSCodeMachineId, success
)
| join kind=inner (eventToStep) on $left.event == $right.event
| distinct step, uid, success, order
| summarize success_ = count_distinctif(uid, success == "True"), all_ = count_distinct(uid) by step, order
| extend success__ = iff(success_ == 0, all_, success_)  // if no explicit success, treat as all
| order by order asc
| extend success_rate = round((todouble(success__) / all_) * 100, 2)
| project Step=step, Success=success__, All=all_, SuccessRate=success_rate
```

7) Local Model DAU and Provider Mix
- Intent: Track daily active users interacting with local models (ONNX/Converted, Finetuning, Model Lab) using a 1-day window; separate provider categories for mix analysis.
- How to adapt: Replace categories or add Ollama; adjust LookbackWindow.
```kusto
let LookbackWindow = 1d;
let Start = startofday(INPUT_TIME_START - LookbackWindow);
let End   = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let activeDays  = 1;
let engagedDays = 2;
aitoolkit_vscode
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
| where (EventInfo_Name == "inference_model_load" and tostring(Properties["model-provider"]) in ("ONNX","ONNX (Converted)"))
   or (EventName contains "finetuning_" and EventInfo_Name !in ("finetuning_overview_open-start","finetuning_overview_open"))
   or (EventInfo_Name contains "model_lab_" and EventInfo_Name !in ("model_lab_open_workflow-start","model_lab_open_workflow","model_lab_open_create_workspace","model_lab_open_create_workspace-start"))
| extend eventDay = startofday(ServerTimestamp)
| distinct VSCodeMachineId, eventDay
| extend bin = bin_at(eventDay, 1d, Start)
| extend endRange = iff(bin + LookbackWindow > End, End,
                        iff(bin + LookbackWindow - 1d < Start, Start,
                        iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
| extend range = range(bin, endRange, 1d)
| mv-expand range to typeof(datetime)
| where range != datetime(null)
| summarize actDays = count() by VSCodeMachineId, range
| extend isA = iff(actDays >= activeDays, 1, 0), isE = iff(actDays >= engagedDays, 1, 0)
| summarize AU = min(isA), EU = min(isE) by VSCodeMachineId, range
| summarize DAU = countif(AU > 0) by range
| where range >= Start + LookbackWindow
| project range, DAU
```

8) GHCP Model Tool Usage by Users (AITK models)
- Intent: Count distinct users calling AITK model guidance via GHCP; filter by extension version and platform; daily series.
- How to adapt: Change tool name, time range, or filters; keep distinct-by-day pattern.
```kusto
let INPUT_TIME_START = datetime(2025-08-23T04:15:00Z);
let INPUT_TIME_END   = datetime(2025-09-22T04:15:00Z);
let INPUT_EXT_VER    = dynamic([...versions...]);
let INPUT_OS         = dynamic(['win32','darwin','linux']);
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End   = iff(startofday(INPUT_TIME_END)   == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));

aitoolkit_vscode
| where EventName == "ms-windows-ai-studio.windows-ai-studio/chat_provider_chat"
| where ExtensionVersion in (INPUT_EXT_VER)
| where Platform in (INPUT_OS)
| where ServerTimestamp >= Start
| extend eventDay = startofday(ServerTimestamp)
| where eventDay <= End
| distinct VSCodeMachineId, eventDay
| summarize count() by eventDay
```

## Reasoning Notes (only if uncertain)
- Timestamps are assumed to be UTC due to lack of timezone info; End is gated to yesterday in most queries. Alternative: if local time needed, apply convert_to_timezone()—not present here.
- Success and non-failure definitions vary slightly by page; we adopt the pattern where cancellations are counted as non-failure because this appears consistently in funnel queries; alternative is stricter success-only.
- Provider backfill for early GitHub models relies on a placeholder list; we keep it as-is with a comment rather than inventing a universal rule.
- The "released version" filter excludes hyphenated versions and "0.0.*"; could miss certain beta releases; we follow the dashboard’s convention to match tiles.
- The "Cursor" VSCodeVersion regex ("^0\.d+\.d+$") aims to detect a special variant; we treat it as-is; alternative would be explicit version list cohorts.

## Canonical Tables

### Table name: kustoproxytest.azure-api.net/rentu-test-product/teamsfx.vscode-ext-aggregate.aitoolkit_vscode
- Priority: Normal
- What this table represents: Fact-style telemetry events emitted by the “AI Toolkit for Visual Studio Code” extension. Each row is a single event with client and server timestamps, event name, platform and version context, and a dynamic Properties bag holding event-specific fields (e.g., action, model-name, model-provider, success, error, view-id, prompt-id, common.nodearch). Zero rows in a time window generally indicate no activity captured (not deletion).
- Freshness expectations: Queries consistently set End to startofday(now(-1d)) to avoid pipeline delay. Timezone is unknown. Avoid using current-day data; prefer “till yesterday” for stable counts.
- When to use:
  - Active user metrics: DAU/WAU/MAU/MEU via distinct VSCodeMachineId and rolling windows.
  - Funnels and feature adoption: Map EventName → steps via datatable; compute success/non-failure rates.
  - Model usage and locality: Group by Properties['model-name'] and Properties['model-provider'] (e.g., ONNX/Ollama/Cloud).
  - Agent Builder and Evaluation flows: Filter by Properties['view-id'] (“promptBuilder”), PromptID for agent activity, evaluator CRUD.
  - Error analytics: Use Properties['error'] and event scoping to top-N error reasons.
- When to avoid:
  - Using current day (End=now) due to delay; prefer End=startofday(now(-1d)).
  - Counting actions without excluding auto-activation and survey dismiss: remove “activation_details”, “survey_selection” with action==dismiss; exclude “chat_provider_list_models(-start)”.
  - Relying on ClientTimestamp for lag-sensitive KPIs; prefer ServerTimestamp for time windows.
  - Treating early releases as complete: provider may be missing; queries patch provider for early GitHub models.
- Similar tables & how to choose:
  - RawEventsVSCodeExt (ddtelfiltered.centralus) contains GitHub Copilot Chat telemetry used for GHCP tool calls; it is marked partial/internal/non-US in usage notes. Use aitoolkit_vscode for AITK extension telemetry. Use RawEventsVSCodeExt only for GHCP tool-call breakdowns where explicitly needed.
- Common Filters:
  - Time: ServerTimestamp between Start and End; End is typically startofday(now(-1d)).
  - Version/OS: ExtensionVersion in dynamic list; Platform in ['win32','darwin','linux'].
  - Event scoping: substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/")) → EventInfo_Name; exclude “activation_details”, “survey_selection” (dismiss), and model list events; view-id constraints for Prompt Builder vs Playground.
  - Properties-based: model-name, model-provider, success (string “true”/“false”; often treated as boolean or non-failure), error strings, view-id, common.nodearch, prompt-id.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | EventName | string | Fully-qualified event name. Commonly trimmed to EventInfo_Name by removing the “ms-windows-ai-studio.windows-ai-studio/” prefix. Used to scope features (e.g., inference_model_run, prompt_builder_run). |
  | Attributes | dynamic | Additional event attributes (seldom used in provided queries). |
  | ClientTimestamp | datetime | Client-side timestamp when event was emitted. Prefer ServerTimestamp for pipeline-stable windows. |
  | DataHandlingTags | string | Data handling/privacy tags associated with the event. |
  | ExtensionName | string | VS Code extension identifier/name emitting the telemetry. |
  | ExtensionVersion | string | Extension version (e.g., “0.20.0”, “0.10.9”). Frequently filtered to distinguish release vs test builds. |
  | GeoCity | string | City inferred from geo IP. Rarely used; country is preferred. |
  | GeoCountryRegionIso | string | ISO country/region (used for geo breakdowns and top-20 analyses). |
  | Measures | dynamic | Numeric measures payload; not directly referenced in provided queries. |
  | NovaProperties | dynamic | Additional properties bag; not referenced in provided queries. |
  | Platform | string | OS id: “win32”, “darwin”, “linux”. Used for platform counts and MAU percent by OS. |
  | PlatformVersion | string | OS version string. |
  | Properties | dynamic | Primary event-specific bag: keys include 'action', 'model-name', 'model-provider', 'success', 'error', 'view-id', 'prompt-id', 'common.nodearch', 'executetemplate', etc. Extensively used for feature logic and grouping. |
  | ServerTimestamp | datetime | Server-side event time used for stable time filters (Start/End). Preferred over ClientTimestamp. |
  | Tags | dynamic | Arbitrary tags for the event; not directly used in provided queries. |
  | VSCodeMachineId | string | Pseudonymous machine identifier. Used for distinct counts (e.g., DAU/MAU, success by user). |
  | VSCodeSessionId | string | VS Code session identifier; used for per-session sequencing/funnel calculations. |
  | VSCodeVersion | string | VS Code version (e.g., “1.93.0”) or “0.x.x” pattern to flag cursor scenarios. |
  | WorkloadTags | string | Workload-specific tags; not referenced in provided queries. |
  | LanguageServerVersion | string | LSP version; not referenced in provided queries. |
  | SchemaVersion | string | Telemetry schema version string. |
  | Method | string | Method name/verb; not referenced in provided queries. |
  | Duration | real | Event duration (seconds) where applicable; not directly used. |
  | SQMMachineId | string | Alternate machine id used by SQM; not referenced in provided queries. |
  | DevDeviceId | string | Developer device id; not referenced in provided queries. |
  | IngestionTime | datetime | ADX ingestion time; useful for pipeline/debug but not for product KPIs. |
  | IsInternal | bool | Internal user flag (1/true indicates internal). Use to segment internal/external if required. |
  | ABExpAssignmentContext | string | A/B experiment assignment details. |
  | Source | string | Event source tag; not referenced in provided queries. |
  | SKU | string | SKU label; not referenced in provided queries. |
  | Model | string | Model label for some events; model context typically comes from Properties['model-name']. |
  | RequestId | string | Request identifier; join/debug. |
  | ConversationId | string | Chat conversation id; join/debug. |
  | ResponseType | string | Response type for chat/inference; not widely used. |
  | ToolName | string | Tool name in tool-invocation contexts; primary usage is via Properties['toolcounts'] rather than this column. |
  | Outcome | string | Outcome descriptor; success/failure is typically using Properties['success']. |
  | IsEntireFile | string | Flag indicating full-file context; not referenced in provided queries. |
  | ToolCounts | string | Stringified tool-counts summary. Queries for GHCP use Properties['toolcounts'] (lowercase) not this column. |
  | Isbyok | int | BYOK flag; not referenced in provided queries. |
  | TimeToFirstToken | int | Latency to first token (ms); performance analytics. |
  | TimeToComplete | int | Time to completion (ms); performance analytics. |
  | TimeDelayms | int | Delay in ms; performance analytics. |
  | SurvivalRateFourgram | real | Metric for content preservation; not used in provided queries. |
  | TokenCount | real | Total tokens; performance/cost proxy. |
  | PromptTokenCount | real | Prompt tokens; performance/cost proxy. |
  | NumRequests | int | Number of requests in a session; not used in provided queries. |
  | Turn | int | Conversation turn index; not used in provided queries. |
  | ResponseTokenCount | real | Tokens in response; performance/cost proxy. |
  | TotalNewDiagnostics | int | New diagnostics generated; not used in provided queries. |
  | Rounds | real | Rounds metric; not used in provided queries. |
  | AvgChunkSize | real | Average chunk size; not used in provided queries. |
  | Command | string | Command string; not used in provided queries. |
  | CopilotTrackingId | string | Tracking id for Copilot; join/debug. |
  | IntentId | string | Intent identifier; not used in provided queries. |
  | Participant | string | Participant role; not used in provided queries. |
  | ToolGroupState | string | Tool group state; not used in provided queries. |
  | DurationMS | long | Duration in milliseconds; performance analytics. |
- Column Explain:
  - ServerTimestamp: Use for Start/End filtering and daily/rolling windows; reduces impact of pipeline lag.
  - EventName and EventInfo_Name: Derive EventInfo_Name via substring. Use to scope features (e.g., “playground_open”, “prompt_builder_run”, “inference_model_load/run”, “finetuning_*”, “model_lab_*”, “evaluation” events).
  - Properties: Central for feature logic and grouping. Frequent keys:
    - 'action' (e.g., "dismiss" for survey),
    - 'model-name'/'model-provider' (e.g., ONNX, Ollama, Cloud providers),
    - 'success' (string “true”/“false”; often treated as boolean or non-failure),
    - 'error' (error codes/messages and finetuning-job-error),
    - 'view-id' (e.g., “promptBuilder”, “modelPlayground”),
    - 'common.nodearch' (arch used in platform+arch splits),
    - 'prompt-id' (agent identity for agent activity counts),
    - 'executetemplate' (Model-Lab templates).
  - VSCodeMachineId and VSCodeSessionId: Machine-level distinct for DAU/MAU; session-level sequencing for funnels.
  - ExtensionVersion and Platform: Primary segmentation filters; many dashboards use curated version lists and all 3 OS values.
  - GeoCountryRegionIso: For country breakdowns and top-20 aggregation.
  - VSCodeVersion: Used to isolate “cursor” scenarios via regex "^0\.\d+\.\d+$".
  - Error fields: Use Properties['error'] to build error tables/top-N; use “non_failure” logic to include cancellations.

---

### Table name: ddtelfiltered.centralus.kusto.windows.net.<database unknown>.RawEventsVSCodeExt
- Priority: Normal
- What this table represents: Fact-style telemetry for GitHub Copilot Chat in VS Code used to analyze “panel.request” tool invocations and model breakdowns. Queries in the product use it only for partial/internal/non-US coverage of GHCP tool calls.
- Freshness expectations: Unknown (cross-tenant internal dataset). Use caution with current-day windows; prefer End=startofday(now(-1d)) as in examples.
- When to use:
  - GHCP tool usage breakdowns: Count distinct users by model for specific tool calls (e.g., aitk-get_ai_model_guidance, aitk-get_tracing_code_gen_best_practices).
  - Validate model distribution for GHCP panel.request events in the specified period.
- When to avoid:
  - Assuming full global coverage: Notes explicitly say it is partial/internal/non-US.
  - Mixing with AITK extension events: Use aitoolkit_vscode for AITK feature telemetry.
  - Relying on columns beyond Properties and standard identifiers without schema validation.
- Similar tables & how to choose:
  - Use aitoolkit_vscode for AITK feature telemetry (Agent Builder, Playground, Finetuning, Model-Lab).
  - Use RawEventsVSCodeExt only for GHCP “panel.request” tool-count analyses where the internal dataset is required.
- Common Filters:
  - Time: ServerTimestamp between Start and End (End typically startofday(now(-1d))).
  - EventName == "github.copilot-chat/panel.request".
  - Properties['toolcounts'] contains the specific tool key; Properties['model'] for grouping.
  - Distinct by VSCodeMachineId for user counts.
- Table columns:
  - Note: Schema retrieval failed via tool call for this cross-cluster table (“Failed to resolve table or column expression named 'RawEventsVSCodeExt'”). The following columns are inferred from queries and may be incomplete.
  
  | Column | Type | Description or meaning |
  |---|---|---|
  | EventName | string | Expected to contain “github.copilot-chat/panel.request” for GHCP requests. |
  | ServerTimestamp | datetime | Server-side event time used in Start/End filtering. |
  | VSCodeMachineId | string | Machine identifier used for distinct user counts. |
  | Properties | dynamic | Contains 'toolcounts' (JSON keyed by tool name) and 'model' (model id/name from GHCP). |
- Column Explain:
  - Properties['toolcounts']: Extract per-tool invocation counts; queries check presence of the specific tool key to filter users for that tool.
  - Properties['model']: Used to group and rank model usage by distinct users.
  - VSCodeMachineId: Basis for “users” metric as a distinct count.
  - EventName/ServerTimestamp: Scope to panel.request and time-bound the query.

---

Notes and cautions across tables:
- Time handling: Use Start/End with End=startofday(now(-1d)) to avoid pipeline delay. Timezone is unspecified; keep day-level aggregations aligned with startofday().
- Provider normalization: Early releases may lack 'model-provider'; queries patch provider (e.g., infer ONNX for local models, GitHub for early GH models). Mirror that logic when necessary.
- Success vs non-failure: Many dashboards treat cancellations as non-failure; define success carefully based on Properties['success'] and known cancellation markers.
- Rolling windows: For AU/EU metrics, manually compute rolling windows via bin_at() and range(); exclude early days without enough rolling data.
- New vs existing: Compute firstDay per entity (VSCodeMachineId or PromptID) to split “new” vs “existing” counts.