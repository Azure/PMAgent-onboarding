# AI Toolkit for Visual Studio Code (AITK-VSC) - Product and Data Overview Template

## 1. Product Overview

AI Toolkit for Visual Studio Code (AITK-VSC) provides capabilities for local and cloud model workflows, prompt/agent building, finetuning, evaluation, and integrations with GitHub Copilot. This schema document onboards AITK-VSC telemetry so PMAgent can interpret product-specific signals for metrics such as DAU/WAU/MAU, funnels, success rates, and feature usage.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
AI Toolkit for Visual Studio Code (AITK-VSC)
- **Product Nick Names**: AITK, AI Toolkit
- **Kusto Cluster**:
https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx
- **Kusto Database**:
vscode-ext-aggregate
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# AITK-VSC - Kusto Query Playbook

## Overview
- AITK-VSC is an ADX dashboard-driven analytics set that tracks AI Toolkit for VS Code usage. Queries run primarily against cluster https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx and database vscode-ext-aggregate, using the aitoolkit_vscode event fact table. Some analyses query cluster https://ddtelfiltered.centralus.kusto.windows.net/ (database VSCodeExt) using RawEventsVSCodeExt for GitHub Copilot Chat tool telemetry.
- Primary cluster: https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx
- Primary database: vscode-ext-aggregate
- Alternate source: https://ddtelfiltered.centralus.kusto.windows.net/ (database VSCodeExt) for RawEventsVSCodeExt

## Conventions & Assumptions
- Time semantics
  - Canonical Time Column: ServerTimestamp (default). Some activation/sequence queries use ClientTimestamp.
  - Frequently derive daily grain via startofday(ServerTimestamp) as eventDay.
  - Common aliasing:
    - EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
  - Typical windows:
    - Rolling windows: 28d (MAU/MEU), 7d (WAU), 1d (DAU) via manual sliding windows.
    - Cohort/retention windows: 1–8 weeks and M1–M6.
  - Binning: bin_at(eventDay, 1d, Start); range()/mv-expand to construct rolling windows.
  - Effective end time: current day is excluded with End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END)).
  - Time zone: Not specified; assume UTC. Avoid using current-day data due to known pipeline delay.
- Freshness & Completeness Gates
  - Practice: exclude current day (till yesterday) to avoid ingestion lag: End = startofday(now(-1d)).
  - Unknown ingestion SLA: Treat same-day data as incomplete; for month/week aggregates, prefer “previous full” periods.
  - Recommended gate pattern (multi-slice): compute last day where all key slices (e.g., Platforms: win32, darwin, linux) report any data; use that day as effective End for cross-slice comparability.
- Joins & Alignment
  - Frequent keys:
    - VSCodeMachineId (user/device identity)
    - VSCodeSessionId (session)
    - PromptID (agent/prompt entity)
    - eventDay (daily grain)
  - Typical join kinds: inner (e.g., all vs. new), leftouter (enrich).
  - Post-join hygiene:
    - Use project-away to drop duplicate columns; use project-rename to unify names.
    - Use coalesce() when merging similar fields across sources.
- Filters & Idioms
  - Version gating:
    - Released versions: ExtensionVersion != "" and not contains "-" and not startswith "0.0."
    - Sometimes isolate cursor versions: VSCodeVersion matches regex "^0\\.\\d+\\.\\d+$".
  - Prefix trimming for EventName into EventInfo_Name.
  - Default exclusions (context-dependent):
    - EventInfo_Name !startswith "activation_details" (exclude auto activation noise)
    - Exclude survey non-engagement: EventInfo_Name == "survey_selection" and Properties['action']=="dismiss"
    - Exclude list models noise: "chat_provider_list_models" and "-start"
  - “Success” normalization:
    - success = Properties['success']=="true"
    - Treat “Canceled”/“Operation cancelled.” as non-failure in some funnels.
  - View scoping via Properties['view-id'] (e.g., promptBuilder, modelPlayground, promptConsole).
- Cross-cluster/DB & Sharding
  - Secondary telemetry from RawEventsVSCodeExt (ddtelfiltered cluster, VSCodeExt DB).
  - Qualify cross-cluster explicitly when needed:
    - cluster("ddtelfiltered.centralus.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt
  - Sharding across regions not present; union is used to merge multiple event types before normalization.
- Table classes
  - Fact: aitoolkit_vscode and RawEventsVSCodeExt (event-level facts).
  - Snapshot/Pre-aggregated: none observed. Build aggregates at query time.
  - Counting discipline: deduplicate by VSCodeMachineId per day for activity; use min(eventDay) for first-touch “new/existing.”

Notes on query conventions across both tables:
- Time windows:
  - Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START)) for safety.
  - End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END)).
  - For rolling windows (7d, 28d), materialize a sliding window with mv-expand over a precomputed range to compute AU/engagement.
- Counting users:
  - Use VSCodeMachineId for dcount/distinct operations to approximate active users.
  - New vs existing: compute min(eventDay) per VSCodeMachineId and compare to daily eventDay.
- Event shaping:
  - Derive EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/")) for AITK events.
  - Step/event maps via datatable and join to categorize flows.
- Success/non-failure:
  - success = Properties['success'] == "true".
  - non_failure sometimes includes error == "Canceled" or "Operation cancelled." treated as non-failure.
- Model/provider attribution:
  - Use Properties['model-name'] and ['model-provider']; if provider missing, infer categories via model name suffixes (-onnx/-cpu/-gpu) or early GH lists in queries.
- Platform/arch segmentation:
  - OS labels: win32/darwin/linux; arch via Properties['common.nodearch'] (e.g., x64, arm64). Combine for os(arch) cohorts.

## Entity & Counting Rules (Core Definitions)
- Entity model
  - User/Device: VSCodeMachineId (primary identity for usage counting).
  - Session: VSCodeSessionId (used in step-sequencing within sessions).
  - Agent/Prompt: PromptID (defines agents created/used).
- Counting rules
  - Daily active basis: distinct (VSCodeMachineId, eventDay) from filtered events.
  - New vs existing: firstDay = min(eventDay) per VSCodeMachineId; daily “new” count = users whose firstDay == day; existing = all - new.
  - Rolling actives (MAU/WAU/DAU):
    - Build day-level distincts, then slide a manual window via bin_at + range + mv-expand; compute actDays per user, flag isA/isE by thresholds, then count.
  - Success/non-failure:
    - Funnels often count distinct users with success == "True"; sometimes count non-failure = success=="true" OR error in ["Canceled","Operation cancelled."].
  - Categorization:
    - Model Provider Category: ONNX/Converted (local), Ollama (local server), Cloud (else).
    - Model Lab, Finetuning, Prompt Builder, Playground features are bucketed via EventInfo_Name and Properties.

## Views (Reusable Layers)
- None defined in the source. Reuse patterns are implemented inline with let/datatable blocks (e.g., step maps, earlyGHModels).

## Query Building Blocks (Copy-paste snippets, contains snippets and description)
- Time window template
  - Description: Standard Start/End with current-day exclusion; narrow safely before expanding.
  - Query:
    ```kusto
    // Inputs: INPUT_TIME_START, INPUT_TIME_END
    let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
    let End   = iff(startofday(INPUT_TIME_END)   == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
    // Use eventDay for daily grain
    | extend eventDay = startofday(ServerTimestamp)
    | where eventDay <= End
    ```
- Rolling window MAU/MEU helper
  - Description: Build 28d sliding activity with thresholds (activeDays/engagedDays).
  - Query:
    ```kusto
    let LookbackWindow = 28d;
    let Start0 = startofday(INPUT_TIME_START - LookbackWindow);
    let End0   = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
    let activeDays = 1;
    let engagedDays = 2;
    source
    | distinct Id, eventDay // one row per identity per day
    | extend bin = bin_at(eventDay, 1d, Start0)
    | extend endRange = iff(bin + LookbackWindow > End0, End0,
                         iff(bin + LookbackWindow - 1d < Start0, Start0,
                           iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
    | extend range = range(bin, endRange, 1d)
    | mv-expand range to typeof(datetime)
    | summarize actDays = count() by Id, range
    | extend isA = iff(actDays >= activeDays, 1, 0), isE = iff(actDays >= engagedDays, 1, 0)
    | summarize AU = min(isA), EU = min(isE) by Id, range
    | summarize MAU = countif(AU > 0), MEU = countif(EU > 0) by range
    | where range >= Start0 + LookbackWindow
    ```
- Join template: daily “all” vs “new”
  - Description: Compute all active users per day and join to “firstDay” to split new vs existing.
  - Query:
    ```kusto
    let Start = ...; let End = ...;
    let daily_all =
      source
      | distinct VSCodeMachineId, eventDay
      | summarize all = count() by eventDay;
    let daily_new =
      source
      | distinct VSCodeMachineId, eventDay
      | summarize firstDay = min(eventDay) by VSCodeMachineId
      | summarize new = count() by firstDay;
    daily_all
    | join kind=inner daily_new on $left.eventDay == $right.firstDay
    | project eventDay, all, new, existing = all - new
    ```
- De-dup pattern
  - Description: Keep most recent event per key or first event per user.
  - Query:
    ```kusto
    // First day seen per user
    source
    | summarize firstDay = min(eventDay) by VSCodeMachineId
    // Latest event per user
    source
    | summarize arg_max(ServerTimestamp, *) by VSCodeMachineId
    ```
- Important filters
  - Description: Standard event noise exclusions and released version gating.
  - Query:
    ```kusto
    | where ExtensionVersion != "" and ExtensionVersion !contains "-" and ExtensionVersion !startswith "0.0."
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
    | extend surveyAction = tostring(Properties["action"])
    | where EventInfo_Name !startswith "activation_details"
    | where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss")
    | where not(EventInfo_Name in ("chat_provider_list_models", "chat_provider_list_models-start"))
    ```
- Important definitions
  - Description: Category classification used across analyses.
  - Query:
    ```kusto
    | extend Category = case(
        tostring(Properties["model-provider"]) in ("ONNX", "ONNX (Converted)"), "ONNX/Converted",
        tostring(Properties["model-provider"]) == "Ollama", "Ollama",
        "Cloud"
      )
    | extend CaseType = case(
        EventInfo_Name == "inference_model_add_my_model" and Category == "ONNX/Converted", "Catalog add local model",
        EventInfo_Name == "inference_model_load" and Category == "ONNX/Converted" and Properties["view-id"] == "modelPlayground", "Playground/Comparison",
        EventInfo_Name == "inference_model_load" and Category == "ONNX/Converted" and Properties["view-id"] == "promptBuilder", "PromptBuilder(Agent (Prompt) Builder/Bulk Run)",
        EventName contains "finetuning_" and EventInfo_Name !in ("finetuning_overview_open-start", "finetuning_overview_open"), "Finetuning",
        EventInfo_Name contains "model_lab_" and EventInfo_Name !in ("model_lab_open_workflow-start", "model_lab_open_workflow", "model_lab_open_create_workspace", "model_lab_open_create_workspace-start"), "Model Lab",
        "Others"
      )
    ```
- ID parsing/derivation
  - Description: Platform+arch string; model provider fallback and Ollama model prefix.
  - Query:
    ```kusto
    // Platform + arch
    | extend arch = tostring(Properties["common.nodearch"])
    | extend os = case(Platform == "win32", "Windows", Platform == "darwin", "MacOS", Platform == "linux", "Linux", "unknown")
    | extend Platform_Arch = strcat(Platform, "_", arch)

    // Ollama model family
    | extend ModelNamePrefix = tostring(split(tostring(Properties["model-name"]), ":")[0])

    // Provider fallback for early GH models
    let earlyGHModels = dynamic(['AI21-Jamba-1.5-Large','AI21-Jamba-1.5-Mini','Cohere-command-r',' Cohere-command-r-08-2024',
      'Cohere-command-r-plus','Cohere-command-r-plus-08-2024','Llama-3.2-11B-Vision-Instruct',
      'Llama-3.2-90B-Vision-Instruct','Meta-Llama-3.1-405B-Instruct','Meta-Llama-3.1-70B-Instruct',
      'Meta-Llama-3.1-8B-Instruct','Meta-Llama-3-70B-Instruct','Meta-Llama-3-8B-Instruct','Mistral-large'
      'Mistral-large-2407','Mistral-Nemo','Mistral-small','gpt-4o','gpt-4o-mini','o1-mini','o1-preview',
      'Phi-3-medium-128k-instruct','Phi-3-medium-4k-instruct','Phi-3-mini-128k-instruct',
      'Phi-3-mini-4k-instruct','Phi-3-small-128k-instruct','Phi-3-small-8k-instruct',
      'Phi-3-5-MoE-instruct','Phi-3.5-vision-instruct','Phi-3.5-mini-instruct']);
    | extend providerX = tostring(Properties["model-provider"])
    | extend provider = iff(providerX != "", providerX,
                        iff(tostring(Properties["model-name"]) matches regex "-(onnx|cpu|gpu)$", "ONNX",
                          iff(tostring(Properties["model-name"]) in (['earlyGHModels']), "GitHub", "")))
    ```
- Sharded union (merge event types into a workflow)
  - Description: Combine Add/Edit, Load, Run into a single daily action summary.
  - Query:
    ```kusto
    let Start=...; let End=...;
    union
    (
      source | where EventName in~ (".../inference_model_download",".../add_remote_inference_endpoint",".../inference_model_add_my_model")
      | project model_name=tostring(Properties["model-name"]), VSCodeMachineId, eventDay=startofday(ServerTimestamp), action="Add/Edit"
    ),
    (
      source | where EventName in~ (".../inference_model_load",".../inference_model_connect")
      | project model_name=tostring(Properties["model-name"]), VSCodeMachineId, eventDay=startofday(ServerTimestamp), action="Load"
    ),
    (
      source | where EventName == ".../inference_model_run"
      | project model_name=tostring(Properties["model-name"]), VSCodeMachineId, eventDay=startofday(ServerTimestamp), action="Run"
    )
    | where model_name != ""
    | distinct VSCodeMachineId, eventDay, action
    | summarize ['Add/Edit'] = countif(action=="Add/Edit"), ['Load']=countif(action=="Load"), ['Run']=countif(action=="Run") by eventDay
    ```
- Cross-cluster GitHub Copilot Chat tools
  - Description: Extract model usage for specific tool invocations.
  - Query:
    ```kusto
    let Start=...; let End=...;
    let TOOLNAME = "aitk-get_ai_model_guidance";
    cluster("ddtelfiltered.centralus.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt
    | where ServerTimestamp >= Start and ServerTimestamp <= End
    | where EventName == "github.copilot-chat/panel.request"
    | extend toolcounts = extractjson(strcat("$", TOOLNAME), tostring(Properties["toolcounts"]))
    | extend model = tostring(Properties["model"])
    | where toolcounts <> ""
    | distinct VSCodeMachineId, model
    | summarize users=count() by model
    | order by users desc
    ```

## Example Queries (with explanations)
1) Rolling MAU/MEU over 28 days (active and engaged)
- Description: Computes monthly active/engaged users using a sliding 28-day window. Filters out survey dismiss and activation noise, applies version/os filters, and excludes current day. Adjust activeDays/engagedDays or LookbackWindow to change definitions.
```kusto
let LookbackWindow = 28d; // 28day rolling
let Start = startofday(INPUT_TIME_START - LookbackWindow);
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let activeDays = 1; // user that actives at least {activeDays} in past {LookbackWindow} is "active user"
let engagedDays = 2; // user that actives at least {engagedDays} in past {LookbackWindow} is "engaged user"
aitoolkit_vscode
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
// exclude auto activation and survey-timeout-dismiss events
| extend surveyAction = tostring(Properties['action'])
| where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss") and not(EventInfo_Name == "chat_provider_list_models-start" or EventInfo_Name == "chat_provider_list_models")
| where EventInfo_Name !startswith "activation_details"
| extend eventDay = startofday(ServerTimestamp)
| distinct VSCodeMachineId, eventDay
//// start: manual slide window to filter x-day active
| extend bin = bin_at(eventDay, 1d, Start)
| extend endRange = iff(bin + LookbackWindow > End, End, 
                      iff(bin + LookbackWindow - 1d < Start, Start, 
                        iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
| extend range = range(bin, endRange, 1d)
| mv-expand range to typeof(datetime)
| where range != datetime(null)
| summarize actDays = count() by VSCodeMachineId, range
| extend isA = iff(actDays >= activeDays, 1, 0), isE = iff(actDays >= engagedDays, 1, 0)
//// end: slide window
| summarize AU = min(isA), EU = min(isE) by VSCodeMachineId, range
| summarize MAU = countif(AU > 0), MEU = countif(EU > 0) by range
| where range >= Start + LookbackWindow // exclude the first days without enough rolling data
| project range,MAU,MEU
```

2) Daily new vs existing users
- Description: Splits daily active users into “new” (first day seen) vs “existing,” using an inner join on firstDay. Adapt by changing filters (e.g., restrict to a feature-specific event).
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
(
    aitoolkit_vscode
    | where ExtensionVersion in (['INPUT_EXT_VER'])
    | where Platform in (['INPUT_OS'])
    | where ServerTimestamp >= Start
    | extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
    // exclude auto activation and survey-timeout-dismiss events
    | extend surveyAction = tostring(Properties['action'])
    | where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss") and not(EventInfo_Name == "chat_provider_list_models-start" or EventInfo_Name == "chat_provider_list_models")
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
    // exclude auto activation and survey-timeout-dismiss events
    | extend surveyAction = tostring(Properties['action'])
    | where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss") and not(EventInfo_Name == "chat_provider_list_models-start" or EventInfo_Name == "chat_provider_list_models")
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

3) Feature step funnel with success rate (Prompt Builder)
- Description: Maps a curated step list to events and computes success and funnel sizes. Treats canceled operations as non-failure. Customize step list in the datatable and the success criteria as needed.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
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
  "prompt_builder_get_code", "View Code", 8,
  "batch_run_import_dataset", "Import Dataset", 11,
  "batch_run_export_dataset", "Export Dataset", 12,
  "batch_run_generate_dataset", "Generate Row", 13,
  "batch_run_add_row", "Manual CRUD", 14,
  "batch_run_edit_row", "Manual CRUD", 14,
  "batch_run_delete_row", "Manual CRUD", 14,
  "batch_run_insert_column", "Manual CRUD", 14,
  "batch_run_remove_column", "Manual CRUD", 14,
  "batch_run_rename_column", "Manual CRUD", 14,
  "batch_run_row", "Bulk Run Row(s)", 15,
  "create_evaluation", "Add Eval", 16,
  "start_evaluation", "Run Eval", 17,
  "prompt_builder_save_version", "Save Version", 18,
  "prompt_builder_list_versions", "List Version", 19,
  "prompt_builder_compare_version", "Compare Version", 20,
  "click_toggle_fullscreen", "Expand to fullscreen", 21,
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
    | extend success = case(
        Properties['success'] == "true" 
        or Properties['error'] == "Canceled" 
        or Properties['error'] == "Operation cancelled.",
        "True", "False")
    | distinct event = EventInfo_Name, uid = VSCodeMachineId, success
)
| join kind=inner 
( eventToStep )
on $left.event == $right.event
| distinct step, uid, success, order
| summarize success_=count_distinctif(uid, success == "True"), all_=count_distinct(uid) by step, order
| extend success__ = iff(success_ == 0, all_, success_)
| order by order asc
| extend success_rate = round((todouble(success__) / all_ * 100), 2)
| project Step=step, Success=success__, All=all_, SuccessRate=success_rate
```

4) Model run success by model/provider
- Description: Groups distinct users who ran inference by model and provider, computing success and overall counts. Adjust earlyGHModels or provider fixes if needed.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let earlyGHModels = dynamic([
    'AI21-Jamba-1.5-Large','AI21-Jamba-1.5-Mini','Cohere-command-r',' Cohere-command-r-08-2024',
    'Cohere-command-r-plus','Cohere-command-r-plus-08-2024','Llama-3.2-11B-Vision-Instruct',
    'Llama-3.2-90B-Vision-Instruct','Meta-Llama-3.1-405B-Instruct','Meta-Llama-3.1-70B-Instruct',
    'Meta-Llama-3.1-8B-Instruct','Meta-Llama-3-70B-Instruct','Meta-Llama-3-8B-Instruct','Mistral-large'
    'Mistral-large-2407','Mistral-Nemo','Mistral-small','gpt-4o','gpt-4o-mini','o1-mini','o1-preview',
    'Phi-3-medium-128k-instruct','Phi-3-medium-4k-instruct','Phi-3-mini-128k-instruct',
    'Phi-3-mini-4k-instruct','Phi-3-small-128k-instruct','Phi-3-small-8k-instruct',
    'Phi-3-5-MoE-instruct','Phi-3.5-vision-instruct','Phi-3.5-mini-instruct']); // fix missing 'provider' for early releases
aitoolkit_vscode
| where EventName == "ms-windows-ai-studio.windows-ai-studio/inference_model_run"
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend eventDay = startofday(ServerTimestamp)
| where eventDay <= End
| extend model_name = tostring(Properties["model-name"])
| extend type = iff(model_name endswith "-onnx" or model_name endswith "-cpu" or model_name endswith "-gpu", "local", "remote")
| extend providerX = tostring(Properties["model-provider"])
| extend provider = iff(providerX != "", providerX, 
                        iff(type == "local", "ONNX",
                            iff(model_name in (['earlyGHModels']), "GitHub", ""))) // fix missing property
| extend success = case(Properties['success'] == "true", "True", "False")
| where model_name != ""
| distinct VSCodeMachineId, model_name, provider, success
| summarize success_=count_distinctif(VSCodeMachineId, success == "True"), all_=count_distinct(VSCodeMachineId) by model_name, provider
| order by all_ desc
```

5) Weekly retention by cohort (weeks 1–8)
- Description: Computes weekly return rates relative to cohort’s first active week. Adjust time windows and presentation thresholds as needed.
```kusto
let today=startofday(now());
let firsttime=datetime(2024-05-19);
let starttime = datetime(2024-12-22);
let endtime = startofweek(today) - 3d;
let 1week = 7d; let 2week = 14d; let 3week = 21d; let 4week = 28d;let 8week = 56d;
// active user by day
let common_query = aitoolkit_vscode
| where ExtensionVersion !contains "-" and ExtensionVersion !startswith "0.0." // released version
| where ServerTimestamp >= starttime
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
// // exclude auto activation and survey-timeout-dismiss events
| where EventInfo_Name !startswith "activation_details"
| extend surveyAction = tostring(Properties['action'])
| where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss") and not(EventInfo_Name == "chat_provider_list_models-start" or EventInfo_Name == "chat_provider_list_models")
| extend eventDay = startofday(ServerTimestamp)
| distinct MachineId = VSCodeMachineId, Time = eventDay;
let active_day = common_query
//use the first time a user is coming
| summarize ActiveDay = min(Time) by MachineId;
common_query
| where Time >= starttime
| join kind=inner active_day on MachineId
| extend w1__ = iff(Time >= ActiveDay + 1d, 1, 0)
| extend w2__ = iff(Time >= ActiveDay + 1d + 1week, 1, 0)
| extend w3__ = iff(Time >= ActiveDay + 1d + 2week, 1, 0)
| extend w4__ = iff(Time >= ActiveDay + 1d + 3week, 1, 0)
| extend m1 = iff(Time >= ActiveDay + 1d and Time < ActiveDay + 1d + 4week, 1, 0)
| extend m2 = iff(Time >= ActiveDay + 1d + 4week and Time < ActiveDay + 1d + 8week, 1, 0)
| extend w1 = iff(Time >= ActiveDay + 1d and Time < ActiveDay + 1d + 1week, 1, 0)
| extend w2 = iff(Time >= ActiveDay + 1d + 1week and Time < ActiveDay + 1d + 2week, 1, 0)
| extend w3_4 = iff(Time >= ActiveDay + 1d + 2week and Time < ActiveDay + 1d + 4week, 1, 0)
| extend w5_8 = iff(Time >= ActiveDay + 1d + 4week and Time < ActiveDay + 1d + 8week, 1, 0)
| summarize max(w1__), max(w2__), max(w3__), max(w4__),
            max(m1), max(m2),
            max(w1), max(w2), max(w3_4), max(w5_8)
            by MachineId, ActiveWeek = startofweek(ActiveDay)
| summarize w1__ = sum(max_w1__), w2__ = sum(max_w2__), w3__ = sum(max_w3__), w4__ = sum(max_w4__),
            m1 = sum(max_m1), m2 = sum(max_m2),
            w1 = sum(max_w1), w2 = sum(max_w2), w3_4 = sum(max_w3_4), w5_8 = sum(max_w5_8),
            all = count() by ActiveWeek
| where ActiveWeek < endtime
| order by ActiveWeek asc
| project Week = format_datetime(ActiveWeek, "yyyy-MM-dd"),
          Users = all,
          ['Re[>=w1]'] = iff(ActiveWeek + 1week  < today, strcat(round(w1__ * 100 / all, 2),"%"), ""),
          ['Re[>=w2]'] = iff(ActiveWeek + 2week < today, strcat(round(w2__ * 100 / all, 2),"%"), ""),
          ['Re[>=w3]'] = iff(ActiveWeek + 3week < today, strcat(round(w3__ * 100 / all, 2),"%"), ""),
          ['Re[>=w4]'] = iff(ActiveWeek + 4week < today, strcat(round(w4__ * 100 / all, 2),"%"), ""),
          ['_'] = '|',
          ['Re[Month1]'] = iff(ActiveWeek + 4week < today, strcat(round(m1 * 100 / all, 2),"%"), ""),
          ['Re[Month2]'] = iff(ActiveWeek + 8week < today, strcat(round(m2 * 100 / all, 2),"%"), ""),
          ['-'] = '|',
          ['Re[=w1]'] = iff(ActiveWeek + 1week < today, strcat(round(w1 * 100 / all, 2),"%"), ""),
          ['Re[=w2]'] = iff(ActiveWeek + 2week < today, strcat(round(w2 * 100 / all, 2),"%"), ""),
          ['Re[w3-4]'] = iff(ActiveWeek + 4week < today, strcat(round(w3_4 * 100 / all, 2),"%"), ""),
          ['Re[w5-8]'] = iff(ActiveWeek + 8week < today, strcat(round(w5_8 * 100 / all, 2),"%"), "")
```

6) WAU by feature category over 7d windows
- Description: Computes weekly active users per category (ONNX Inference, Finetuning, Model Lab) using a 7-day sliding window. Helpful for cross-feature comparisons with an effective end date gate.
```kusto
let LookbackWindow = 7d; // 28day rolling
let Start = startofday(INPUT_TIME_START - LookbackWindow);
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let activeDays = 1; // user that actives at least {activeDays} in past {LookbackWindow} is "active user"
let engagedDays = 2; // user that actives at least {engagedDays} in past {LookbackWindow} is "engaged user"
aitoolkit_vscode
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
| extend EventCategory = case(
    EventInfo_Name == "inference_model_load" and tostring(Properties["model-provider"]) in ("ONNX", "ONNX (Converted)"), "ONNX_Inference",
    EventName contains "finetuning_" and EventInfo_Name !in ("finetuning_overview_open-start", "finetuning_overview_open"), "Finetuning",
    EventInfo_Name contains "model_lab_" and EventInfo_Name !in ("model_lab_open_workflow-start", "model_lab_open_workflow", "model_lab_open_create_workspace", "model_lab_open_create_workspace-start"), "Model_Lab",
    "Other"
)
| where EventCategory != "Other"
| extend eventDay = startofday(ServerTimestamp)
| distinct VSCodeMachineId, eventDay, EventCategory
//// start: manual slide window to filter x-day active
| extend bin = bin_at(eventDay, 1d, Start)
| extend endRange = iff(bin + LookbackWindow > End, End, 
                      iff(bin + LookbackWindow - 1d < Start, Start, 
                        iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
| extend range = range(bin, endRange, 1d)
| mv-expand range to typeof(datetime)
| where range != datetime(null)
| summarize actDays = count() by VSCodeMachineId, range, EventCategory
| extend isA = iff(actDays >= activeDays, 1, 0), isE = iff(actDays >= engagedDays, 1, 0)
//// end: slide window
| summarize AU = min(isA), EU = min(isE) by VSCodeMachineId, range, EventCategory
| summarize WAU = countif(AU > 0), WEU = countif(EU > 0) by range, EventCategory
| where range >= Start + LookbackWindow // exclude the first days without enough rolling data
| project range, EventCategory, WAU
| order by range asc, EventCategory asc
```

7) Model Lab job failures by error and template
- Description: Breaks down Model Lab run_job failures by error and template, optionally deduping by machine. Produces a JSON map of counts per template per error for diagnostics. Adjust UNIQUE_MACHINE_ID to control distinct counting.
```kusto
let timeEnd = INPUT_TIME_END;
let timeStart = INPUT_TIME_START;
let uniqueMachineId = UNIQUE_MACHINE_ID;
aitoolkit_vscode
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp <= INPUT_TIME_END and ServerTimestamp >= timeStart
| where EventName == "ms-windows-ai-studio.windows-ai-studio/model_lab_run_job"
| extend Success = tobool(Properties["success"]) 
| where Success == false
| extend error = tostring(Properties["error"])
| extend ExecuteTemplate = tostring(Properties["executetemplate"])
| summarize template_count = iff(uniqueMachineId, dcount(VSCodeMachineId), count()) by error, ExecuteTemplate
| order by error, template_count desc
| extend kv_pair = strcat("\"", ExecuteTemplate, "\":", tostring(template_count))
| summarize 
    total_count = sum(template_count), 
    details = parse_json(strcat("{", strcat_array(make_list(kv_pair), ","), "}")) 
    by error
| order by total_count desc 
```

8) Cross-cluster GitHub Copilot Chat tool model usage
- Description: Counts users who invoked a specific GitHub Copilot tool (TOOLNAME) by model. Useful for tracing AI Toolkit’s Copilot integrations. Edit TOOLNAME and time window as needed.
```kusto
let Start = iff(startofday(INPUT_TIME_START) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_START));
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let TOOLNAME = "aitk-get_ai_model_guidance";
RawEventsVSCodeExt
| where ServerTimestamp >= Start and ServerTimestamp <= End
| where EventName == "github.copilot-chat/panel.request"
| extend toolcounts = extractjson(strcat("$", TOOLNAME), tostring(Properties["toolcounts"]))
| extend model = tostring(Properties["model"])
| where toolcounts <> ""
| distinct VSCodeMachineId, model
| summarize users=count() by model
| order by users desc
| project users, ['ghcp model'] = model
```

9) DAU for advanced/local scenarios (ONNX, Finetuning, Model Lab)
- Description: Counts DAU using a 1-day rolling window for scenarios beyond basic cloud runs (local ONNX, finetuning, model lab). Use this to monitor depth of usage.
```kusto
let LookbackWindow = 1d; // 28day rolling
let Start = startofday(INPUT_TIME_START - LookbackWindow);
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let activeDays = 1; // user that actives at least {activeDays} in past {LookbackWindow} is "active user"
let engagedDays = 2; // user that actives at least {engagedDays} in past {LookbackWindow} is "engaged user"
aitoolkit_vscode
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
| where (EventInfo_Name == "inference_model_load" and tostring(Properties["model-provider"]) in ("ONNX", "ONNX (Converted)")) 
or (EventName contains "finetuning_" and EventInfo_Name !in ("finetuning_overview_open-start", "finetuning_overview_open"))
or (EventInfo_Name contains "model_lab_" and EventInfo_Name !in ("model_lab_open_workflow-start", "model_lab_open_workflow", "model_lab_open_create_workspace", "model_lab_open_create_workspace-start"))
| extend eventDay = startofday(ServerTimestamp)
| distinct VSCodeMachineId, eventDay
//// start: manual slide window to filter x-day active
| extend bin = bin_at(eventDay, 1d, Start)
| extend endRange = iff(bin + LookbackWindow > End, End, 
                      iff(bin + LookbackWindow - 1d < Start, Start, 
                        iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
| extend range = range(bin, endRange, 1d)
| mv-expand range to typeof(datetime)
| where range != datetime(null)
| summarize actDays = count() by VSCodeMachineId, range
| extend isA = iff(actDays >= activeDays, 1, 0), isE = iff(actDays >= engagedDays, 1, 0)
//// end: slide window
| summarize AU = min(isA), EU = min(isE) by VSCodeMachineId, range
| summarize DAU = countif(AU > 0), DEU = countif(EU > 0) by range
| where range >= Start + LookbackWindow // exclude the first days without enough rolling data
| project range, DAU
```

10) Prompt/Agent MAU/MEU by PromptID
- Description: Uses PromptID as the entity to compute active/engaged “agents” over a 28d window. Useful for tracking agent usage depth independent of user counts.
```kusto
let LookbackWindow = 28d; // 28day rolling
let Start = startofday(INPUT_TIME_START - LookbackWindow);
let End = iff(startofday(INPUT_TIME_END) == startofday(now()), startofday(now(-1d)), startofday(INPUT_TIME_END));
let activeDays = 1; // agent that actives at least {activeDays} in past {LookbackWindow} is "active agent"
let engagedDays = 2; // agent that actives at least {engagedDays} in past {LookbackWindow} is "engaged agent"
aitoolkit_vscode
| where ExtensionVersion in (['INPUT_EXT_VER'])
| where Platform in (['INPUT_OS'])
| where ServerTimestamp >= Start
| extend PromptID = tostring(Properties["prompt-id"])
| where PromptID <> ""
| extend eventDay = startofday(ServerTimestamp)
| distinct PromptID, eventDay
//// start: manual slide window to filter x-day active
| extend bin = bin_at(eventDay, 1d, Start)
| extend endRange = iff(bin + LookbackWindow > End, End, 
                      iff(bin + LookbackWindow - 1d < Start, Start, 
                        iff(bin + LookbackWindow - 1d < bin, bin, bin + LookbackWindow - 1d)))
| extend range = range(bin, endRange, 1d)
| mv-expand range to typeof(datetime)
| where range != datetime(null)
| summarize actDays = count() by PromptID, range
| extend isA = iff(actDays >= activeDays, 1, 0), isE = iff(actDays >= engagedDays, 1, 0)
//// end: slide window
| summarize AU = min(isA), EU = min(isE) by PromptID, range
| summarize MA_AGENT = countif(AU > 0), ME_AGENT = countif(EU > 0) by range
| where range >= Start + LookbackWindow // exclude the first days without enough rolling data
| project range, MA_AGENT, ME_AGENT
```

## Reasoning Notes (only if uncertain)
- ServerTimestamp vs ClientTimestamp: Most queries use ServerTimestamp; a few use ClientTimestamp for activation sequences. We adopt ServerTimestamp as canonical and call out the exception.
- Identity choice: VSCodeMachineId is used as “user.” It may represent a device rather than a unique human. We keep VSCodeMachineId as the unit since all provided queries use it.
- “Success” semantics: Some funnels treat “Canceled/Operation cancelled.” as non-failure. We keep this where present; elsewhere, we use Properties['success']=="true" only.
- Version gating: “Released” is inferred by excluding versions containing "-" or starting with "0.0." We assume this distinguishes internal/test vs stable releases; adjust if your release process differs.
- Provider inference for early GH models: A static list earlyGHModels is used to backfill provider="GitHub" when missing. We keep the list as-is; refresh it if upstream schemas change.
- Category classification (ONNX/Converted, Ollama, Cloud): Derived from Properties["model-provider"]. If provider strings change, reclassify accordingly.
- New vs existing: “New” is based on the first day an identity appears post-filtering. If filters change (e.g., feature-limited), “new” becomes feature-specific.
- Time zone: Not documented. We assume UTC and avoid current-day data. If your ingestion is in a different TZ, adjust Start/End accordingly.
- Completeness gate: No explicit completeness checks beyond excluding today. For strict reporting, compute the latest day where all Platforms have non-zero events and gate to that day.
- PromptID as “agent”: We assume PromptID uniquely identifies an agent. If PromptID is recycled or mutable, agent counts may need additional constraints (e.g., also include CreatorId).

## Canonical Tables

### Table: cluster("kustoproxytest.azure-api.net/rentu-test-product/teamsfx").database("vscode-ext-aggregate").aitoolkit_vscode
- Priority: Normal
- What this table represents:
  - Fact/event log for the AI Toolkit for Visual Studio Code extension (AITK-VSC).
  - One row per telemetry event emitted by the extension.
  - Zero rows for a period implies no activity recorded (not deletion).
- Freshness expectations:
  - Many queries set End = startofday(now(-1d)) to account for a typical up-to-24h pipeline delay. Treat current-day data cautiously.
  - Timezone not explicitly stated; ADX timestamps are UTC by default.
- When to use / When to avoid:
  - Use when analyzing AITK-VSC usage: MAU/WAU/DAU, new vs. existing users, platform/arch splits, geo distribution.
  - Use for feature funnels and success rates: prompt builder, prompt console, model playground, bulk run, finetuning, evaluation, model lab.
  - Use to attribute actions to models/providers via Properties['model-name'], Properties['model-provider'].
  - Avoid joining to RawEventsVSCodeExt for GitHub Copilot chat; query RawEventsVSCodeExt directly for those events.
  - Avoid using current day unless you know ingestion delay is negligible.
- Similar tables & how to choose:
  - cluster("ddtelfiltered.centralus.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt: use for GitHub Copilot Chat signals (e.g., panel.request), not for AITK-VSC extension events.
- Common Filters:
  - Time window: ServerTimestamp between Start and End; End often coerced to yesterday.
  - ExtensionVersion: released versions (exclude values containing '-' or starting with '0.0.'), or in a provided allowlist (['INPUT_EXT_VER']).
  - Platform: in ['win32','darwin','linux']; arch via Properties['common.nodearch'].
  - Event family: EventName starts with "ms-windows-ai-studio.windows-ai-studio/"; derive short names with substring.
  - Exclusions used in many KPIs: EventInfo_Name !startswith "activation_details"; exclude survey_selection dismiss and model list events; use per-scenario view-id gates (e.g., promptBuilder, promptConsole).
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| EventName | string | Full event identifier. Often starts with "ms-windows-ai-studio.windows-ai-studio/...". Used to derive scenario-specific event names. |
| Attributes | dynamic | Additional attributes map; rarely used directly in provided queries. |
| ClientTimestamp | datetime | Event client time. Sometimes used for cohort baselines (e.g., activation). Prefer ServerTimestamp for windowing. |
| DataHandlingTags | string | Data handling classification tags. |
| ExtensionName | string | VS Code extension name emitting the event. |
| ExtensionVersion | string | Extension version; used to include released builds and filter by explicit versions. |
| GeoCity | string | City (GeoIP-derived). |
| GeoCountryRegionIso | string | Country/region ISO code; used for country-level aggregations. |
| Measures | dynamic | Numeric measures map; not referenced in the given queries. |
| NovaProperties | dynamic | Additional properties bag; not referenced in the given queries. |
| Platform | string | OS platform (win32, darwin, linux); used widely for segmentation. |
| PlatformVersion | string | Platform version string; not explicitly used. |
| Properties | dynamic | Main event payload bag. Keys used include: action, success, error, view-id, model-name, model-provider, prompt-id, finetuning-job-error, executetemplate, enhanced-mode, attachment flags, common.nodearch, show-deploy-on-limit, etc. |
| ServerTimestamp | datetime | Ingestion/server-side event time. Use for time windows and daily binning (eventDay). |
| Tags | dynamic | General tags map; not directly used. |
| VSCodeMachineId | string | Pseudonymous device identifier; primary user proxy for distinct counts (MAU/WAU/DAU, funnels). |
| VSCodeSessionId | string | VS Code session identifier; used to partition session-level sequences. |
| VSCodeVersion | string | VS Code version string; used to detect special distributions (e.g., "^0\\.\\d+\\.\\d+$"). |
| WorkloadTags | string | Workload classification tags; not used here. |
| LanguageServerVersion | string | Language server version; not used in provided queries. |
| SchemaVersion | string | Schema version marker. |
| Method | string | Method name/verb if present; not used in provided queries. |
| Duration | real | Duration measure; not used here. |
| SQMMachineId | string | Additional machine id; not used here. |
| DevDeviceId | string | Device id; not used here. |
| IngestionTime | datetime | ADX ingestion time; can be used to diagnose pipeline delays. |
| IsInternal | bool | Internal user flag; not used in provided queries. |
| ABExpAssignmentContext | string | A/B experiment assignment context; not used here. |
| Source | string | Source marker; not used here. |
| SKU | string | SKU marker; not used here. |
| Model | string | Model info (generic); for AITK events prefer Properties['model-name'] and ['model-provider']. |
| RequestId | string | Request correlation ID; not used here. |
| ConversationId | string | Conversation ID; not used here. |
| ResponseType | string | Response type; not used here. |
| ToolName | string | Tool name; not used directly for AITK events (GitHub Copilot tools occur in RawEventsVSCodeExt). |
| Outcome | string | Outcome label; not used here. |
| IsEntireFile | string | Entire file flag; not used here. |
| ToolCounts | string | Tool counts as string; not used here (queries use Properties['toolcounts'] in RawEventsVSCodeExt). |
| Isbyok | int | BYOK flag; not used here. |
| TimeToFirstToken | int | Latency metric; not used here. |
| TimeToComplete | int | Completion time metric; not used here. |
| TimeDelayms | int | Delay metric; not used here. |
| SurvivalRateFourgram | real | Metric; not used here. |
| TokenCount | real | Token count; not used here. |
| PromptTokenCount | real | Prompt token count; not used here. |
| NumRequests | int | Number of requests; not used here. |
| Turn | int | Turn index; not used here. |
| ResponseTokenCount | real | Response tokens; not used here. |
| TotalNewDiagnostics | int | Diagnostics count; not used here. |
| Rounds | real | Rounds metric; not used here. |
| AvgChunkSize | real | Average chunk size; not used here. |
| Command | string | Command name; not used here. |
| CopilotTrackingId | string | Copilot tracking id; not used here for AITK analysis. |
| IntentId | string | Intent id; not used here. |
| Participant | string | Participant role; not used here. |
| ToolGroupState | string | Tool group state; not used here. |
| DurationMS | long | Duration in ms; not used here. |

- Column Explain:
  - EventName: Primary discriminator for scenarios. Derive short names with substring("ms-windows-ai-studio.windows-ai-studio/").
  - ServerTimestamp: Use for Start/End filtering and daily bins (startofday(ServerTimestamp) as eventDay).
  - Properties: The core payload. Use keys:
    - 'success' (string "true"/"false") and 'error' to compute success vs. non-failure.
    - 'model-name', 'model-provider' for model/provider attribution and ONNX/Ollama/Cloud bucketing.
    - 'view-id' to scope events to specific UIs (promptBuilder, promptConsole, modelPlayground).
    - 'prompt-id' to track agents and compute agent activity/engagement.
    - 'executetemplate' for Model Lab execution templates and error drilldowns.
    - 'common.nodearch' for arch, combined with Platform for os(arch) splits.
    - 'show-deploy-on-limit' to analyze rate-limit experiences and follow-up actions.
  - VSCodeMachineId: Use dcount for user metrics, distinct for funnels and new/existing calculations.
  - VSCodeSessionId: Partition session flows and order steps within a session.
  - Platform and Properties['common.nodearch']: Build OS/arch cohorts and percentage-of-total MAU by cohort.
  - GeoCountryRegionIso: Country-level breakdowns.
  - ClientTimestamp: Occasionally used for activation-based cohorts; otherwise prefer ServerTimestamp.
  - IngestionTime: Validate freshness and troubleshoot delays.

---

### Table: cluster("ddtelfiltered.centralus.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt
- Priority: Normal
- What this table represents:
  - Fact/event log for VS Code extensions’ raw telemetry (broader scope beyond AITK-VSC).
  - Used here to analyze GitHub Copilot Chat panel requests and tool usage related to AITK guidance.
  - Zero rows for a period imply no captured events.
- Freshness expectations:
  - Not explicitly stated; mirror AITK practice of ending at yesterday for safety if combining with aitoolkit_vscode analyses.
  - Timezone unspecified; assume UTC in ADX.
- When to use / When to avoid:
  - Use to measure GitHub Copilot Chat requests filtered by EventName == "github.copilot-chat/panel.request".
  - Use Properties['toolcounts'] and Properties['model'] to attribute model usage when AITK-related tools are invoked in Copilot.
  - Avoid for AITK-VSC internal feature telemetry; use aitoolkit_vscode for that.
  - Avoid cross-cluster joins on raw identifiers; aggregate per-cluster first and join on small result sets if necessary.
- Similar tables & how to choose:
  - aitoolkit_vscode (AITK-VSC product table): choose that for AITK feature funnels and user metrics. Use RawEventsVSCodeExt only for Copilot Chat coverage of AITK tools.
- Common Filters:
  - Time window: ServerTimestamp between Start and End.
  - EventName: "github.copilot-chat/panel.request".
  - TOOLNAME filters via extracting from Properties['toolcounts'] (e.g., "aitk-get_ai_model_guidance", "aitk-get_tracing_code_gen_best_practices").
  - Distinct users: VSCodeMachineId.
  - Model attribution: Properties['model']. 
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| EventName | string | Full event name ("github.copilot-chat/panel.request" used in queries). |
| Attributes | dynamic | Additional attributes; not used directly in provided queries. |
| ClientTimestamp | datetime | Client-side event time. |
| DataHandlingTags | string | Data handling tags. |
| ExtensionName | string | Extension name emitting the event. |
| ExtensionVersion | string | Extension version. |
| GeoCity | string | City (GeoIP-derived). |
| GeoCountryRegionIso | string | Country/region (ISO code). |
| Measures | dynamic | Numeric measures map. |
| NovaProperties | dynamic | Additional properties. |
| Platform | string | OS platform. |
| PlatformVersion | string | OS/platform version. |
| Properties | dynamic | Main payload. Keys referenced: 'toolcounts' (JSON string), 'model'. |
| ServerTimestamp | datetime | Server-side event time; use for windowing. |
| Tags | dynamic | Tag bag. |
| VSCodeMachineId | string | Distinct user proxy for Copilot Chat usage. |
| VSCodeSessionId | string | Session id. |
| VSCodeVersion | string | VS Code version. |
| WorkloadTags | string | Workload tags. |
| LanguageServerVersion | string | Language server version. |
| SchemaVersion | string | Schema version marker. |
| Method | string | Method string. |
| Duration | real | Duration metric. |
| SQMMachineId | string | Additional machine id. |
| DevDeviceId | string | Device id. |
| IsInternal | bool | Internal flag. |
| ABExpAssignmentContext | string | A/B assignment context. |
| Source | string | Source marker. |
| SKU | string | SKU field. |
| Model | string | Model field (top-level); queries instead use Properties['model']. |
| RequestId | string | Request correlation id. |
| ConversationId | string | Conversation id. |
| ResponseType | string | Response type. |
| ToolName | string | Tool name (top-level); not used in given queries. |
| Outcome | string | Outcome string. |
| IsEntireFile | string | Entire file flag. |
| ToolCounts | string | Tool counts (string); queries use Properties['toolcounts']. |
| Isbyok | int | BYOK indicator. |
| TimeToFirstToken | int | Latency metric. |
| TimeToComplete | int | Completion time metric. |
| TimeDelayms | int | Delay ms. |
| SurvivalRateFourgram | real | Quality metric. |
| TokenCount | real | Token count. |
| PromptTokenCount | real | Prompt tokens. |
| NumRequests | int | Number of requests. |
| Turn | int | Turn index. |
| ResponseTokenCount | real | Response tokens. |
| TotalNewDiagnostics | int | Diagnostics count. |
| Rounds | real | Rounds metric. |
| AvgChunkSize | real | Chunk size average. |
| Command | string | Command name. |
| CopilotTrackingId | string | Copilot tracking id. |
| IntentId | string | Intent identifier. |
| Participant | string | Participant role. |
| ToolGroupState | string | Tool group state. |
| DurationMS | long | Duration in milliseconds. |

- Column Explain:
  - EventName: Filter to "github.copilot-chat/panel.request" when measuring Copilot Chat requests.
  - ServerTimestamp: Use for Start/End and daily bins; ensures consistent bucketing.
  - Properties:
    - 'toolcounts': JSON string that can be parsed to count a specific TOOLNAME usage; queries use extractjson($("<TOOLNAME>"), Properties['toolcounts']).
    - 'model': Used to attribute which Copilot model served the request.
  - VSCodeMachineId: Distinct user proxy for counting users per model/tool.
  - Platform/PlatformVersion: Available if you need OS splits; not used in the provided Copilot analyses.
