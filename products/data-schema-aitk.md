
# AI Toolkit for Visual Studio Code – Product and Data Overview [START]

Instruction: Treat every header containing [SECTION_ID: xyz] as a referenceable section. You can refer to it later using the SECTION_ID.
Example: "Refer to section [SECTION_ID: aitk-active-events] for details."

## 1. Product Overview

AI Toolkit for Visual Studio Code (a.k.a. AITK, AI Toolkit) is an extension to help developers and AI engineers to easily build AI apps through developing and testing with generative AI models locally or in the cloud. AI Toolkit supports most genAI models on the market.

AI engineers can use AI Toolkit to discover and try popular AI models easily with playground that has attachment support, run multiple prompts in batch mode, evaluate the prompts in a dataset to AI models for the popular evaluators, and fine-tune/deploy AI models.

Key features:
- Model catalog with rich generative AI models sources (GitHub, ONNX, OpenAI, Anthropic, Google, ...)
- Bring Your Own Models from remotely hosted model, or Ollama models that are running locally
- Playground for model inference or testing via chat
- Attachment support for multi-modal language models
- Batch run prompts for selected AI models
- Evaluate an AI model with a dataset for supported popular evaluators like F1 score, relevance, similarity, coherence, and more

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: AITK
- **Kusto Cluster**: `https://teamsfxaggregation.eastus.kusto.windows.net/`
- **Kusto Database**: `vscode-ext-aggregate`
- **Primary Metrics**: 

## 3. Table Schemas in Azure Data Explorer

### 3.1 Table `aitoolkit_vscode`

# aitoolkit_vscode Table Schema

| Column                  | Type     | Description |
|--------------------------|----------|-------------|
| EventName               | string   | Name of event triggered |
| Attributes              | dynamic  | Key-value attributes associated with the event |
| ClientTimestamp         | datetime | Time when the event occurred on the client device |
| DataHandlingTags        | string   | Tags describing data handling or compliance requirements |
| ExtensionName           | string   | Name of the VS Code extension generating the event |
| ExtensionVersion        | string   | Version of the VS Code extension |
| GeoCity                 | string   | City where the event originated (based on IP geo lookup) |
| GeoCountryRegionIso     | string   | Country/region code (ISO) where the event originated |
| Measures                | dynamic  | Numeric measures related to the event (e.g., counts, durations) |
| NovaProperties          | dynamic  | Additional diagnostic or internal properties |
| Platform                | string   | Client platform (e.g., Windows, macOS, Linux) |
| PlatformVersion         | string   | Version of the platform/OS |
| Properties              | dynamic  | General key-value properties of the event |
| ServerTimestamp         | datetime | Time when the event was received by the server |
| Tags                    | dynamic  | Arbitrary labels or tags associated with the event |
| VSCodeMachineId         | string   | Unique machine identifier for VS Code instance |
| VSCodeSessionId         | string   | Unique session identifier for VS Code session |
| VSCodeVersion           | string   | Version of VS Code in use |
| WorkloadTags            | string   | Tags describing workloads or features used |
| LanguageServerVersion   | string   | Version of the language server in use |
| SchemaVersion           | string   | Version of the event schema |
| Method                  | string   | Method or action performed by the client/tool |
| Duration                | real     | Duration of the operation in seconds |
| SQMMachineId            | string   | Machine identifier used for SQM/telemetry correlation |
| DevDeviceId             | string   | Developer device identifier |
| IngestionTime           | datetime | Time when the event was ingested into telemetry pipeline |
| IsInternal              | bool     | Flag indicating if the event came from internal users |
| ABExpAssignmentContext  | string   | A/B experiment assignment or variant |
| Source                  | string   | Source system/component that generated the event |
| SKU                     | string   | Product SKU identifier |
| Model                   | string   | Model name (e.g., AI model or hardware model) |
| RequestId               | string   | Unique identifier for the request |
| ConversationId          | string   | Identifier for the conversation/session context |
| ResponseType            | string   | Type of response generated (e.g., completion, error) |
| ToolName                | string   | Name of the tool or feature invoked |
| Outcome                 | string   | Result of the event/action (e.g., success, failure) |
| IsEntireFile            | string   | Indicates if the operation involved the entire file |
| ToolCounts              | string   | Counts of tools/features used in the session |
| Isbyok                  | int      | Flag for "bring your own key" (BYOK) usage (0/1) |
| TimeToFirstToken        | int      | Time in ms until the first token was received/generated |
| TimeToComplete          | int      | Time in ms until the request/response completed |
| TimeDelayms             | int      | Delay time in milliseconds before processing |
| SurvivalRateFourgram    | real     | Survival rate metric for 4-gram token predictions |
| TokenCount              | real     | Total number of tokens processed |
| PromptTokenCount        | real     | Number of prompt tokens provided in the request |
| NumRequests             | int      | Number of requests made during the session |
| Turn                    | int      | Turn number in a conversation/multi-turn session |
| ResponseTokenCount      | real     | Number of tokens in the response |
| TotalNewDiagnostics     | int      | Number of new diagnostics or issues reported |
| Rounds                  | real     | Number of conversation rounds completed |
| AvgChunkSize            | real     | Average size of processed/generated chunks |
| Command                 | string   | Command executed in VS Code |
| CopilotTrackingId       | string   | Tracking identifier for GitHub Copilot requests |


## 4. Common Analytical Scenarios

- **User**: Identified by `VSCodeMachineId`. Use count_distinct() to get exact number instead of dcount() with estimated number. 
- **Active User** (a.k.a active1d): An user is considered as active within a specific period if he/she has at least one `active event` in this period.
    - Get `active events` as section [SECTION_ID: aitk-active-events].
- **Engaged User** (a.k.a engaged2d): An user is considered as engaged within a specific period if he/she has two or more `active events` in this period.
    - Get `active events` as section [SECTION_ID: aitk-active-events].
- **Dedicated User** (a.k.a dedicated10d): An user is considered as dedicated within a specific period if he/she has ten or more `active events` in this period.
    - Get `active events` as section [SECTION_ID: aitk-active-events].
- **Monthly Active Users (MAU)**: Total number of `active users` in rolling 28 days time window.
- **Monthly Engaged Users (MEU)**: Total number of `engaged users` in rolling 28 days time window.
- **Monthly Dedicated Users (MDU)**: Total number of `dedicated users` in rolling 28 days time window.
- **Local Model**: The model provider is "ONNX" or "ONNX (Converted)".
- **User Funnel (User Journey)**: The sequenece of features (or feature categories) used within same VS Code session (`VSCodeSessionId`) order by ServerTimestamp in descending order.
- **App developer**: The active user who has events about AgentBuilder, BulkRun, Eval or FineTuning.

## 5. Common Filters and Definitions

### 5.1 Get the AITK events

The event info name is part of the EventName. Get the AITK events.  

```kusto
aitoolkit_vscode
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
```

### 5.2 Get the AITK active events [SECTION_ID: aitk-active-events]

Get active events by event name and surveyAction. 
- The AITK active event is also AITK event.
- The auto activation and survey-timeout-dismiss events are not active events.

```kusto
aitoolkit_vscode
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
| extend surveyAction = tostring(Properties['action'])
| where not(EventInfo_Name == "survey_selection" and surveyAction == "dismiss")
| where EventInfo_Name !startswith "activation_details"
```

### 5.3 Mapping between AITK events (active events) and feature (or feature category)

Rules for Mapping AITK events (active events) to AITK features or AITK user behaviors (or actions):
- Always define a mapping table between features (user behaviors) and their corresponding event names using a `datatable` in Kusto.
- Always join the event data with the mapping table using event name to associate each event with its corresponding feature (or user behavior).
- Always ignore any events not listed in the mapping table. Only analyze events that are explicitly mapped to features (or user behaviors).
- The user behavior is an interactive action between user and ATIK, and it may be completed by 1 or more events. 
- The feature is key capability of ATIK, and the user could complete several behaviors (or actions) with feature.

| Event Name of AITK | Description of the Event | Mapping between Event and Feature | Mapping between Event and User Behavior | 
| ---- | ---- | ---- | ---- | 
| activation_details | Captures initial activation or launch of AI Studio | Getting Started | Activation | 
| active_user_action | Logs user activity after activation. This is a legacy event and already replaced by activation_details. | Getting Started | Activation |  
| open_get_started_page | User opened the Get Started page | Getting Started | Open get started page | 
| tutorial_open | Opened a tutorial page | Getting Started | Open Tutorials | 
| scaffold_tutorial | Created tutorial scaffolding | Getting Started | Open Tutorials | 
| click_create_tutorial | Clicked button to create a new tutorial | Getting Started | Scaffold tutorial | 
| tutorial_open | Opened a tutorial project or lesson | Getting Started | Scaffold tutorial | 
| click_view_on_github_button | Clicked "View on GitHub" for the tutorial or sample | Getting Started | Click View on GitHub (>2025-04-03) | 
| model_catalog_open | Opened the model catalog UI | Models | Browser models | 
| open_model_card | Opened a specific model's detail card | Models | Browser models |
| open_model_license | Viewed a model's license information | Models | Browser models |
| add_remote_inference_endpoint | Added a new remote inference endpoint | Models | Add or edit model |
| edit_remote_inference_endpoint | Edited an existing remote inference endpoint | Models | Add or edit model |
| inference_model_download | Downloaded a model for local inference | Models | Add or edit model |
| inference_model_add_my_model | Uploaded a custom model to AI Studio | Models | Add or edit model |
| delete_model | Deleted a model from the workspace | Models | Add or edit model |
| inference_model_load | Loaded a model into the workspace | Models | Load or connect a model | 
| inference_model_connect | Connected a model for inference | Models | Load or connect a model | 
| inference_model_run | Ran a model inference request. The explicit event of which model is used. | Models | Run a model | 
| model_lab_open_workflow | Opened the workflow in Model-Lab | Model-Lab | Open Model-Lab | 
| model_lab_open_workflow-start | Opened the workflow (start event) | Model-Lab | Open Model-Lab | 
| model_lab_open_create_workspace | Opened workspace creation dialog | Model-Lab | Create Project | 
| model_lab_open_create_workspace-start | Triggered start of workspace creation | Model-Lab | Create Project | 
| model_lab_accept_datasets | Accepted/confirmed dataset(s) for use | Model-Lab | Open project in Model-Lab | 
| model_lab_click_run_job | Clicked "Run Job" in Model-Lab | Model-Lab | Open project in Model-Lab |
| model_lab_execute_script | Executed a script in Model-Lab | Model-Lab | Open project in Model-Lab |
| model_lab_execute_script-start | Triggered script execution (start event) | Model-Lab | Open project in Model-Lab |
| model_lab_export_history_succeed | Exported run/job history successfully | Model-Lab | Open project in Model-Lab |
| model_lab_first_enter_newproj | Entered a new project for the first time | Model-Lab | Open project in Model-Lab |
| model_lab_first_enter_newproj-start | Entered new project (start event) | Model-Lab | Open project in Model-Lab |
| model_lab_init_run_job | Initialized run job from a template | Model-Lab | Execute Template |
| model_lab_prepare_runtime | Started preparing runtime environment | Model-Lab | Execute Template  |
| model_lab_prepare_runtime-start | Preparing runtime environment (start) | Model-Lab | Execute Template  |
| model_lab_run_job | Executed a run job | Model-Lab | Execute Template |
| model_lab_run_job-start | Triggered run job (start event) | Model-Lab | Execute Template |
| finetuning_configure_project | Configured a fine-tuning project | Fine-tuning | Fine tunning configuration | 
| finetuning_generate_project | Generated the project setup for fine-tuning | Fine-tuning | Fine tunning generation | 
| finetuning_provision | Provisioned compute resources for fine-tuning | Fine-tuning | Fine tunning provision | 
| finetuning_run | Executed the fine-tuning job | Fine-tuning | Fine tunning running | 
| click_finetuning_run_job | Clicked to start LoRA fine-tuning job | Fine-tuning | LoRA Fine-tuning Create Job | 
| finetuning_run_job_created_success | LoRA fine-tuning job successfully created | Fine-tuning | LoRA Fine-tuning Create Job Result | 
| finetuning_run_job_failed | LoRA fine-tuning job failed to create | Fine-tuning | LoRA Fine-tuning Create Job Result | 
| finetuning_download_adapter_success | Successfully downloaded LoRA adapter | Fine-tuning | LoRA Fine-tuning Download Adapter | 
| playground_open | Opened the playground interface | Playground | Open playgournd | 
| click_conversation_starter | Clicked a starter prompt for a conversation | Playground | Chat in playgournd | 
| chat_create | Started a new chat session | Playground | Chat in playgournd | 
| chat_switch | Switched between existing chats | Playground | Chat in playgournd | 
| chat_rename | Renamed an existing chat | Playground | Chat in playgournd | 
| chat_delete | Deleted a chat session | Playground | Chat in playgournd | 
| open_prompt_builder | Opened the prompt builder tool | Agent Builder | Open Agent Builder |
| has_system_prompt_value_in_prompt_builder | System prompt was defined in builder | Agent Builder | Has System/User Prompt | 
| has_message_value_in_prompt_builder | User prompt was defined in builder | Agent Builder | Has System/User Prompt | 
| use_prompt_starter | Used a starter template for prompt | Agent Builder | Click Starter | 
| prompt_builder_generate_prompt | Auto-generated a prompt based on config | Agent Builder | Generate Prompt |
| mcp_select_tools | Selected MCP tools to add to agent | Agent Builder | Add Tools to Agent | 
| mcp_add | Added a new MCP agent | Agent Builder | Add new MCP |
| mcp_server_scaffold | Scaffolded a new MCP project | Agent Builder | Create MCP template |
| prompt_builder_run | Executed a prompt using the builder | Agent Builder | Run Agent Builder |
| prompt_builder_get_code | Retrieved generated code from a prompt | Agent Builder | View code in Agent Builder |
| prompt_builder_save_version | Saved a new version of a prompt | Agent Builder | Save prompt version in Agent Builder | 
| prompt_builder_list_versions | Viewed list of prompt versions | Agent Builder | List prompt version in Agent Builder | 
| prompt_builder_compare_version | Compared different versions of a prompt | Agent Builder | Compare prompt version in Agent Builder | 
| click_toggle_fullscreen | Toggled fullscreen mode in builder | Agent Builder | Expand to fullscreen in Agent Builder | 
| prompt_builder_load | Loaded a saved prompt configuration | Agent Builder | Use prompt builder |
| prompt_builder_list | Viewed a list of available prompts | Agent Builder | Use prompt builder |
| prompt_builder_select_json_format | Selected output format as JSON | Agent Builder | Use prompt builder |
| prompt_builder_create | Created a new prompt configuration | Agent Builder | Use prompt builder |
| prompt_builder_rename | Renamed an existing prompt | Agent Builder | Use prompt builder |
| prompt_builder_delete | Deleted a prompt configuration | Agent Builder | Use prompt builder |
| promptBuilderSave | Saved changes to a prompt configuration | Agent Builder | Use prompt builder |
| create_evaluation | Created a new evaluation project | Evaluation | Create evaluation |
| start_evaluation | Started running an evaluation | Evaluation | Run evaluation |
| view_evaluations | Viewed the list of completed evaluations | Evaluation | View evaluation |
| delete_evaluation_jobs | Deleted one or more evaluation jobs | Evaluation | Delete evaluation jobs |
| add_or_update_custom_evaluator | Added or updated a custom evaluator | Evaluation | Add/Update Custom Evaluator (CRUD Evaluator) |
| delete_custom_evaluators | Deleted custom evaluator(s) | Evaluation | Delete Custom Evaluator (CRUD Evaluator) |
| select_python_env | Selected a local Python environment | Evaluation | Select Local Python |
| batch_run_import_dataset | Imported a dataset for batch run | Bulk Run | Import Dataset |
| batch_run_select_dataset | Selected dataset for batch processing | Bulk Run | Select Dataset |
| batch_run_export_dataset | Exported dataset used in batch run | Bulk Run | Export Dataset |
| batch_run_row | Processed a row in batch mode | Bulk Run | Run Dataset |
| batch_run_generate_dataset | Generated a dataset for batch run | Bulk Run | Generate Dataset |
| batch_run_get_rows | Retrieved dataset rows for processing | Bulk Run | View Dataset |
| batch_run_add_row | Manually added a new row to dataset | Bulk Run | Manual CRUD for Dataset | 
| batch_run_edit_row | Manually edited an existing row | Bulk Run | Manual CRUD for Dataset | 
| batch_run_delete_row | Deleted a row from the dataset | Bulk Run | Manual CRUD for Dataset | 
| batch_run_insert_column | Inserted a new column into dataset | Bulk Run | Manual CRUD for Dataset | 
| batch_run_remove_column | Removed a column from dataset | Bulk Run | Manual CRUD for Dataset | 
| batch_run_rename_column | Renamed a column in the dataset | Bulk Run | Manual CRUD for Dataset | 
| batch_run_cancel | Canceled an ongoing batch run | Bulk Run | Cancel Running for Dataset |
| open_tracing_viewer | Open Tracing Viewer | Tracing | Tracing |
| start_tracing_collector | Start Tracing Collector | Tracing | Tracing |
| stop_tracing_collector | Stop Tracing Collector | Tracing | Tracing |
| tracing_copy_endpoint | Copy Tracing Endpoint | Tracing | Tracing |
| tracing_open_copilot_chat | Open Tracing Viewer from GitHub Copilot | Tracing | Tracing |


### 5.4 Get Event Error Reason

```kusto
aitoolkit_vscode
| extend error = tostring(Properties["error"])
```

### 5.5 Get Event Status

Get the status of the event:
- Success: The event is success. 
- Failed: The event is failed, and the error resaon is **NOT** cancel operation related reasons.
- Cancelled: The event is failed, and the error resaon is cancel operation related reasons.

```kusto
aitoolkit_vscode
| extend error = tostring(Properties["error"])
| extend isSuccess = iif(isempty(error), true, false), 
         isFailed = iif(isnotempty(error) and error != 'Canceled' and error != 'Cancelled' and error != 'Operation canceled.' and error != 'Operation cancelled.', true, false), 
         isCancelled = iif(isnotempty(error) and (error == 'Canceled' or error == 'Cancelled' or error == 'Operation canceled.' or error == 'Operation cancelled.'), true, false)
```

### 5.6 OS and Arch (Platform)

Get the OS and Arch (Platform) of User Machine

```kusto
// Build OS label: Windows/MacOS/Linux + (arch)
aitoolkit_vscode
| extend arch = tostring(Properties["common.nodearch"])
| extend os = strcat(
    iff(Platform == "win32", "Windows",
        iff(Platform == "darwin", "MacOS",
            iff(Platform == "linux", "Linux", "unknown")
        )
    ), "(", arch, ")"
)
```

### 5.7 Get the Name, Type and Provider for Models

Get the information of model:
- **Model name** (model_name): The name of model.
- **Model provider** (model_provider): The provider of the model.
- **Model type** (model_type): There are 3 major types: local, remote and custom. 
    - If the model provier is `ONNX`, `ONNX (Converted)`, or `Foundry Local`, the model type is **local**. 
    - If the model provider is `Custom`, the model type is **custom**. 
    - Otherwise, the model type is **remote**.

```kusto
// Define GitHub early-release models list. 
let earlyGHModels = dynamic([
    'AI21-Jamba-1.5-Large', 'AI21-Jamba-1.5-Mini',
    'Cohere-command-r', 'Cohere-command-r-08-2024',
    'Cohere-command-r-plus', 'Cohere-command-r-plus-08-2024',
    'Llama-3.2-11B-Vision-Instruct', 'Llama-3.2-90B-Vision-Instruct',
    'Meta-Llama-3.1-405B-Instruct', 'Meta-Llama-3.1-70B-Instruct',
    'Meta-Llama-3.1-8B-Instruct', 'Meta-Llama-3-70B-Instruct',
    'Meta-Llama-3-8B-Instruct',
    'Mistral-large', 'Mistral-large-2407', 'Mistral-Nemo', 'Mistral-small',
    'gpt-4o', 'gpt-4o-mini', 'o1-mini', 'o1-preview',
    'Phi-3-medium-128k-instruct', 'Phi-3-medium-4k-instruct',
    'Phi-3-mini-128k-instruct', 'Phi-3-mini-4k-instruct',
    'Phi-3-small-128k-instruct', 'Phi-3-small-8k-instruct',
    'Phi-3-5-MoE-instruct', 'Phi-3.5-vision-instruct', 'Phi-3.5-mini-instruct'
]);
aitoolkit_vscode
| extend model_name = tostring(Properties["model-name"])
| where isnotempty(model_name)
| extend model_provider = iff(tostring(Properties["model-provider"]) != "", 
                              tostring(Properties["model-provider"]), 
                              iff(tostring(Properties["model-name"]) endswith "-onnx" or tostring(Properties["model-name"]) endswith "-cpu" or tostring(Properties["model-name"]) endswith "-gpu", 
                                  "ONNX", 
                                  iff(model_name in (earlyGHModels), "GitHub", "")))
| extend model_type = iff(model_provider in ("ONNX", "ONNX (Converted)", "Foundry Local"), 
                         'local', 
                         iff(model_provider in ("Custom"), 'custom', 'remote'))
```

### 5.8 Get User Actions of Playgournd 

Get the user actions of playground

```kusto
// Mapping between action in playground and its display name
let actionToDisplayName = datatable(action: string, name: string)
[
  "click_image_attachments", "Click Image Attachments (> 2025/3/13)",
  "click_file_attachments_model_mode", "Click File Attachments (Model mode)",
  "click_file_attachments_enhanced_mode", "Click File Attachments (Enhanced mode)",
  "click_web_search", "Click Web Search",
  "click_aitk_enhanced", "Click AITK Enhanced",
  "click_regenerate", "Click Regenerate",
  "playground_get_code", "Click View Code",
];
aitoolkit_vscode
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
| extend viewId = tostring(Properties['view-id'])
| where EventInfo_Name != "inference_model_load" or viewId == "modelPlayground"
| extend action = case(
    EventInfo_Name == "click_file_attachments" and Properties["enhanced-mode"] == "false", "click_file_attachments_model_mode",
    EventInfo_Name == "click_file_attachments" and Properties["enhanced-mode"] == "true", "click_file_attachments_enhanced_mode",
    EventInfo_Name == "start_inference" and Properties["web-search"] == "true", "run_with_web_search",
    EventInfo_Name == "start_inference" and Properties["image-attachments"] == "true", "run_with_image",
    EventInfo_Name == "start_inference" and Properties["text-attachments"] == "true" and Properties["enhanced-mode"] == "true", "run_with_text_enhanced",
    EventInfo_Name == "start_inference" and Properties["text-attachments"] == "true" and Properties["enhanced-model"] == "false", "run_with_text",
    EventInfo_Name == "start_inference" and Properties["audio-attachments"] == "true", "run_with_audio",
    EventInfo_Name == "start_inference" and Properties["video-attachments"] == "true", "run_with_video",
    EventInfo_Name)
```

### 5.9 Get LoRA Fine-tuning Create Job Failed Reason

```kusto 
aitoolkit_vscode
| extend failed_reason = Properties['finetuning-job-error']
```

### 5.10 Get Potential Cursor Usage

Comparing with VS Code, the potential Cursor usage is identified by VSCodeVersion (e.g., official VSCode version is ~1.95 and Cursor version is ~0.42). 
- If the user asks potential cursor usage, you should always add a note that "The definition of potential Cursor usage of AITK is not finalized and guaranteed.".

```kusto
aitoolkit_vscode
| where VSCodeVersion matches regex "^0\\.\\d+\\.\\d+$" // cursor version?
```

### 5.11 Get Executed Template and Success status for Model-Lab 

```kusto 
aitoolkit_vscode
| extend Executetemplate = tostring(Properties["executetemplate"])
| where Executetemplate != ""
| extend Executetemplate = replace_regex(Executetemplate, @"(_context_ov_static|_qdq_qnn|_qdq_amd|_ov_config|_ov|_qnn_config|_vitis_ai_config|_text_qnn|_vision_qnn|_ov_config)", "")
| extend Executetemplate = replace_regex(Executetemplate, @"(vit-base-patch16-224|vit_base_patch16_224)", "google-vit")
| extend Success = tobool(Properties["success"])
```

### 5.12 Get User Journey as events by session

```kusto
aitoolkit_vscode
| extend EventInfo_Name = substring(EventName, strlen("ms-windows-ai-studio.windows-ai-studio/"))
| partition hint.strategy=shuffle by VSCodeSessionId
  (
    order by ServerTimestamp asc
    | summarize events = make_list(EventInfo_Name) by VSCodeMachineId 
  )
| extend user_journey_by_session = strcat_array(events, "->")
```

### 5.13 Exclude Events from Internal Users

```kusto
aitoolkit_vscode
| where IsInternal == false
```

## 6. Notes and Considerations

- All timestamps are in **UTC**.
- Data refresh is **daily** with ~2-hour delay.
- Always use `ServerTimestamp` to identify when AITK event happens. 
- When calculating floating-point numbers (such as rates or percentages), use the `round()` function with **2 decimal places** by default.
- Always analysis external users by default, identified by "IsInternal == false", unless the user specify to include internal users. 

# AI Toolkit for Visual Studio Code – Product and Data Overview [END]

---

