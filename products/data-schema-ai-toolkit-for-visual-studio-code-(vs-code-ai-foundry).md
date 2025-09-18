# AI Toolkit for Visual Studio Code (VS Code AI Foundry) - Product and Data Overview Template

## 1. Product Overview

AI Toolkit for Visual Studio Code (VS Code AI Foundry) is a VS Code extension that helps developers build, deploy, and operate AI models and agents within VS Code, integrating with Azure AI services. This document captures the telemetry schema and common analytical logic used to measure engagement, reliability, and feature adoption for the extension.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
  AI Toolkit for Visual Studio Code (VS Code AI Foundry extension)
- **Product Nick Names**: 
  **[TODO]Data_Engineer**: Populate nicknames/aliases such as “AI Toolkit”, “VS Code AI Foundry”, “AIFoundry VSCode”, etc.
- **Kusto Cluster**:
  https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx (proxy used by internal dashboard)
  **[TODO]Data_Engineer**: Confirm the canonical ADX cluster FQDN used for production analyses.
- **Kusto Database**:
  vscode-ext-aggregate
- **Access Control**:
  **[TODO] Data Engineer**: Specify allowed security groups/users if this data is confidential. If blank, it’s assumed accessible to general internal users for analysis.
- **Primary Metrics**: 
  - Daily Active Users (DAU): distinct VSCodeMachineId by day
  - Rolling 28d Active Users (Active1d): users active on >=1 day within prior 28 days
  - Rolling 28d Engaged Users (Engaged2d): users active on >=2 days within prior 28 days
  - Reliability (Connection Success Rate): countif(Result == 'Succeeded') / count() on selected event scope
  - Command Usage: event/user counts by EventNameShort
  - Feature Adoption: Model vs Agent flows (event mappings)
  - “Open in VS Code” adoption: event equals azure-ai-foundry.openinvscodeazure and follow-on usage
  - Month-over-month retention cohorts: M1–M6 rates from first active month
  - Rolling 28d Model/Agent actions (Deploy/Open Playground, etc.)

  **[TODO]Data_Engineer**: Validate metric names, finalize formulas and meaningful thresholds specific to your team reporting.

## 3. Table Schemas in Azure Data Explorer

### 3.1 ai_foundry_vsc (database: vscode-ext-aggregate)

| Column               | Type     | Description |
|----------------------|----------|-------------|
| EventName            | string   | Full event name emitted by the extension (often includes publisher/extension scope prefix). Used to derive EventNameShort via split(EventName, '/')[1]. |
| Attributes           | dynamic  | Additional attributes bag (if present). |
| ClientTimestamp      | datetime | Event time as reported by the client (user’s environment). Used for DAU time-binning and retention calculations. |
| DataHandlingTags     | string   | Data handling classification tags if provided by pipeline. |
| ExtensionName        | string   | The extension identifier/name emitting the event. |
| ExtensionVersion     | string   | The extension version. Useful for version/upgrade analyses. |
| GeoCity              | string   | City derived from geo-resolution (if available). |
| GeoCountryRegionIso  | string   | Country/region in ISO code (if available). |
| Measures             | dynamic  | Numeric measures bag (if provided). |
| NovaProperties       | dynamic  | Additional properties bag (if present). |
| Platform             | string   | Platform identifier (may overlap with OS contexts). |
| PlatformVersion      | string   | Platform version. |
| Properties           | dynamic  | Primary bag of event properties. Known keys used in queries: Properties['common.os'] (OS), Properties.result, Properties.errormessage. |
| ServerTimestamp      | datetime | Server-side event timestamp (ingestion/processing aligned). Some analyses use this for date truncation. |
| Tags                 | dynamic  | Arbitrary tags bag (if present). |
| VSCodeMachineId      | string   | Machine-scoped unique identifier in VS Code; used as user proxy in metrics (DAU/MAU/retention). |
| VSCodeSessionId      | string   | Session identifier for VS Code telemetry session. |
| VSCodeVersion        | string   | Installed VS Code version. |
| WorkloadTags         | string   | Workload tags if populated. |
| LanguageServerVersion| string   | Language server version (if applicable). |
| SchemaVersion        | string   | Event schema version. |
| Method               | string   | API/method name context (if provided). |
| Duration             | real     | Duration (units context depends on event; see DurationMS for ms). |
| SQMMachineId         | string   | Legacy/alternate machine identifier (if present). |
| DevDeviceId          | string   | Device identifier for development scenarios (if present). |
| IsInternal           | bool     | Indicates internal usage (true/false) when available. Useful for internal/test filtering. |
| IngestionTime        | datetime | Ingestion time into ADX. |
| ABExpAssignmentContext | string | A/B experiment assignment info (if present). |
| Source               | string   | Source label (if present). |
| SKU                  | string   | SKU label (if present). |
| Model                | string   | Model identifier in AI scenarios (if present). |
| RequestId            | string   | Request correlation identifier. |
| ConversationId       | string   | Conversation/session identifier (AI chat/agent flows). |
| ResponseType         | string   | Response type classification (if present). |
| ToolName             | string   | Tool name (AI tool invocation context). |
| Outcome              | string   | Outcome classification (e.g., success/failure) when provided. Often mirrored by Properties.result as well. |
| IsEntireFile         | string   | Whether operation involved entire file (if provided). |
| ToolCounts           | string   | Tool usage counts representation (if provided). |
| Isbyok               | int      | BYOK flag (if applicable). |
| TimeToFirstToken     | int      | Latency metric for model responses (ms). |
| TimeToComplete       | int      | Time for operation completion (ms). |
| TimeDelayms          | int      | Additional delay metric (ms). |
| SurvivalRateFourgram | real     | Quality/telemetry metric (if provided). |
| TokenCount           | real     | Total token count for AI operations. |
| PromptTokenCount     | real     | Input/prompt token count. |
| NumRequests          | int      | Number of requests aggregated per record (if aggregated). |
| Turn                 | int      | Conversation turn index (if applicable). |
| ResponseTokenCount   | real     | Output/response token count. |
| TotalNewDiagnostics  | int      | Diagnostics count emitted (if applicable). |
| Rounds               | real     | Interaction rounds (if applicable). |
| AvgChunkSize         | real     | Average chunk size metric (if applicable). |
| Command              | string   | Command name (if applicable). |
| CopilotTrackingId    | string   | Copilot correlation id (if present). |
| IntentId             | string   | Intent id classification (if present). |
| Participant          | string   | Participant role in conversation (if present). |
| ToolGroupState       | string   | Tool group state (if provided). |
| DurationMS           | long     | Duration in milliseconds where explicitly provided. |

Notes:
- Historical queries derive:
  - OS from Properties['common.os'].
  - Result from Properties.result.
  - ErrorMessage from Properties.errormessage.
  - EventNameShort via split(EventName, '/')[1].

## 4. Common Analytical Scenarios

- Command usage overview
  - Summarize count and distinct users by EventNameShort; identify top commands.
- Reliability and top errors
  - Compute Connection Success Rate using Result == 'Succeeded'.
  - Surface top ErrorMessage among failed operations, and analyze error category.
- User engagement time series
  - DAU: dcount(VSCodeMachineId) by day.
  - Rolling 28d cohorts: Active1d (>=1 day), Engaged2d (>=2 days), and optional Dedicated10d (>=10 days) across a 28-day window.
- Feature adoption: Model vs Agent
  - Map EventNameShort into Feature in {'model','agent','other'} and track Active1d/Engaged2d by Feature.
- “Open in VS Code” pathway
  - Users who triggered azure-ai-foundry.openinvscodeazure; track their daily volumes and overlap with any other events (engagement).
- Cohort retention
  - Month 0 new users; compute M1–M6 retention fractions based on first active month.
- Rolling 28d model/agent actions
  - Track counts of key Model and Agent actions (e.g., deploy, open playground) over time.

**[TODO]Data_Engineer**: Review these scenarios and add/remove items to reflect your canonical dashboards and business questions.

## 5. Common Filters and Definitions

- Time parameters
  - Standard time range parameters: _startTime and _endTime used across dashboards.
  - Typical date binning: bin(ClientTimestamp, 1d) or startofday() usage.
- OS platform filter
  - Parameter INPUT_OS with selectable values: ['win32', 'darwin', 'linux']; often applied as OS in (['INPUT_OS']) where OS = tostring(Properties['common.os']).

### 5.1 Excluding Internal/Test Resources

Example filters (confirm with your policy):
```Kusto
// Prefer a canonical internal filter if available
| where IsInternal == false
```
**[TODO]Data_Engineer**: Provide the authoritative internal/test exclusion logic (e.g., IsInternal flag, known tenant/account lists, or helper tables/functions).

### 5.2 Active/Engaged definitions (Rolling 28d)

- Active1d: user (VSCodeMachineId) appears on at least 1 distinct day within the previous 28 days.
- Engaged2d: user appears on at least 2 distinct days within the previous 28 days.
- Dedicated10d (optional): user appears on at least 10 distinct days within the previous 28 days.

Reference pattern:
```Kusto
// Build a 28d rolling window per day
let daterange = range Day from startofday(datetime(2025-03-01)) to ago(1d) step 1d
| extend DayEndDate = startofday(Day)
| extend dummy = 1;
let UserDays = ai_foundry_vsc
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
| extend OS = tostring(Properties['common.os'])
| where OS in (['INPUT_OS'])
| project VSCodeMachineId, Date=startofday(ServerTimestamp)
| distinct VSCodeMachineId, Date
| extend dummy = 1;
daterange
| join kind=inner (UserDays) on dummy
| project-away dummy, dummy1
| where Date between ((DayEndDate - 27d) .. (DayEndDate))
| summarize DaysSeenInPrev28 = count() by VSCodeMachineId, DayEndDate
| summarize
    Active1d = dcount(VSCodeMachineId),
    Engaged2d = dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 2),
    Dedicated10d = dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 10)
  by DayEndDate
```

### 5.3 Feature Mapping (Model vs Agent vs Other)

Derived from EventNameShort:

Model-related:
- 'azure-ai-foundry.commandpalette.llmdeploy'
- 'azure-ai-foundry.viewcontext.llmdeploy'
- 'model.update'
- 'model.delete'
- 'azure-ai-foundry.viewcontext.viewmodel'
- 'azure-ai-foundry.viewcontext.model.openinplayground'
- 'azure-ai-foundry.viewcontext.opencodefile'
- 'azure-ai-foundry.commandpalette.opencodefile'
- 'azure-ai-foundry.commandpalette.opencatalog'

Agent-related:
- 'azure-ai-foundry.editortitle.openagentdesigner'
- 'azure-ai-foundry.explorercontext.openagentdesigner'
- 'azure-ai-foundry.commandpalette.runagent'
- 'azure-ai-foundry.viewcontext.agent.delete'
- 'azure-ai-foundry.viewcontext.createagent'
- 'agentdesignerwebview.openyamlfile'
- 'agentdesignerwebview.openplayground'
- 'agentdesignerwebview.synctofile'
- 'agentdesignerwebview.deployagent'
- 'agentdesignerwebview.savetolocal'
- 'azure-ai-foundry.viewcontext.openagentdesigner'
- 'agentdesignerwebview.addtool'
- 'agentroottreenode.getchildren'
- 'playgroundwebview.createthread'
- 'project.sendmessage'

Example:
```Kusto
| extend EventNameShort = tostring(split(EventName, '/')[1])
| extend Feature = case(
    EventNameShort in ('azure-ai-foundry.commandpalette.llmdeploy','azure-ai-foundry.viewcontext.llmdeploy','model.update','model.delete','azure-ai-foundry.viewcontext.viewmodel','azure-ai-foundry.viewcontext.model.openinplayground','azure-ai-foundry.viewcontext.opencodefile','azure-ai-foundry.commandpalette.opencodefile','azure-ai-foundry.commandpalette.opencatalog'), 'model',
    EventNameShort in ('azure-ai-foundry.editortitle.openagentdesigner','azure-ai-foundry.explorercontext.openagentdesigner','azure-ai-foundry.commandpalette.runagent','azure-ai-foundry.viewcontext.agent.delete','azure-ai-foundry.viewcontext.createagent','agentdesignerwebview.openyamlfile','agentdesignerwebview.openplayground','agentdesignerwebview.synctofile','agentdesignerwebview.deployagent','agentdesignerwebview.savetolocal','azure-ai-foundry.viewcontext.openagentdesigner','agentdesignerwebview.addtool','agentroottreenode.getchildren','playgroundwebview.createthread','project.sendmessage'), 'agent',
    'other'
)
```

### 5.4 Product filter

Common event filters used to scope to AI Foundry extension events:
```Kusto
// Exclude extension initialization/info events
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
```
Optional stricter filter:
```Kusto
// If ExtensionName has a canonical value for AI Foundry, apply it here
// | where ExtensionName == '<publisher>.vscode-ai-foundry'
```
**[TODO]Data_Engineer**: Provide the authoritative ExtensionName or robust scoping predicate, if needed.

### 5.5 Reliability (Connection Success Rate)

Base definition:
```Kusto
// Result comes from Properties.result
| extend Result = Properties.result
| summarize ConnectionSuccessRate = round(100.0 * countif(Result == 'Succeeded') / count(), 2)
```

When focusing on non-user/host/data errors (dashboard “base_error” derivation):
```Kusto
// starting from a 'base' dataset that includes Result and ErrorMessage
| extend ErrorCategory = 'uncategorized'
| extend ErrorCategory = case(ErrorMessage == "Operation cancelled.", "user", ErrorCategory)
| where ErrorCategory !in ('host','user','data')
```
**[TODO]Data_Engineer**: Confirm final error categorization rules and whether additional parsing/mappings are required.

## 6. Notes and Considerations

- All timestamps are treated as UTC in ADX; ClientTimestamp reflects client-local time reported by the extension, while ServerTimestamp/IngestionTime reflect server-side times.
- For daily metrics and retention, be consistent: prefer ClientTimestamp or ServerTimestamp and document the choice. Current dashboards mix both; consider standardizing.
- OS is derived from Properties['common.os'] as one of ['win32', 'darwin', 'linux'].
- For performance, limit analysis windows where possible (e.g., <= 6 months for heavy distinct counts).
- Count distinct users using VSCodeMachineId unless a more stable user identifier becomes available.
- EventNameShort is obtained by split(EventName, '/')[1]; ensure this is valid for all event formats.
- Internal/test usage exclusion should be consistently applied once the policy is finalized (see Section 5.1).
- The “proxy” cluster URI is used by the internal dashboard. For automated jobs, use the canonical ADX cluster/database once confirmed.

**[TODO]Data_Engineer**:
- Confirm the canonical ADX cluster endpoint.
- Provide internal/test exclusion policy.
- Validate feature mapping lists and add any missing events.
- Finalize which timestamp (Client vs Server) governs official reporting.

## 7. Sample Queries

### 7.1 Rolling 28d Active and Engaged Users by Feature (weekly)

```Kusto
// Parameters: INPUT_OS = dynamic(['win32','darwin','linux'])
let daterange = range Week from startofweek(datetime(2025-03-01)) to startofweek(ago(7d)) step 7d
| extend WeekEndDate = startofday(endofweek(Week))
| extend dummy = 1;
// Build daily user activity with feature mapping
let UserDays = ai_foundry_vsc
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
| extend OS = tostring(Properties['common.os'])
| where OS in (['INPUT_OS'])
| project VSCodeMachineId, Date=startofday(ServerTimestamp), EventName
| distinct VSCodeMachineId, Date, EventName
| extend EventNameShort = tostring(split(EventName, '/')[1])
| extend Feature = case(
    EventNameShort in ('azure-ai-foundry.commandpalette.llmdeploy','azure-ai-foundry.viewcontext.llmdeploy','model.update','model.delete','azure-ai-foundry.viewcontext.viewmodel','azure-ai-foundry.viewcontext.model.openinplayground','azure-ai-foundry.viewcontext.opencodefile','azure-ai-foundry.commandpalette.opencodefile','azure-ai-foundry.commandpalette.opencatalog'), 'model',
    EventNameShort in ('azure-ai-foundry.editortitle.openagentdesigner','azure-ai-foundry.explorercontext.openagentdesigner','azure-ai-foundry.commandpalette.runagent','azure-ai-foundry.viewcontext.agent.delete','azure-ai-foundry.viewcontext.createagent','agentdesignerwebview.openyamlfile','agentdesignerwebview.openplayground','agentdesignerwebview.synctofile','agentdesignerwebview.deployagent','agentdesignerwebview.savetolocal','azure-ai-foundry.viewcontext.openagentdesigner','agentdesignerwebview.addtool','agentroottreenode.getchildren','playgroundwebview.createthread','project.sendmessage'), 'agent',
    'other'
)
| extend dummy = 1;
// Cross-join to build 28d windows ending each WeekEndDate
daterange
| join kind=inner (UserDays) on dummy
| project-away dummy, dummy1
| where Date between ((WeekEndDate - 27d) .. WeekEndDate)
| summarize DaysSeenInPrev28 = count() by VSCodeMachineId, WeekEndDate, Feature
| summarize
    Active1d = dcount(VSCodeMachineId),
    Engaged2d = dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 2)
  by WeekEndDate, Feature
| where WeekEndDate > datetime(2025-03-01)
| where Feature in ('model','agent')
| order by WeekEndDate asc
```

### 7.2 Reliability: Connection Success Rate (overall and by command)

```Kusto
// Parameters: _startTime, _endTime, INPUT_OS
let end_date = _endTime;
let start_date = _startTime;
let base = ai_foundry_vsc
| where ClientTimestamp between (start_date .. end_date)
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
| extend EventNameShort = tostring(split(EventName, '/')[1])
| extend Result = Properties.result
| extend ErrorMessage = Properties.errormessage
| extend OS = tostring(Properties['common.os'])
| where OS in (['INPUT_OS']);
// Overall success rate
base
| summarize ConnectionSuccessRate = round(100.0 * countif(Result == 'Succeeded') / count(), 2)
// By command success rate (ascending order highlights lowest performers)
;base
| summarize ConnectionSuccessRate = round(100.0 * countif(Result == 'Succeeded') / count(), 2) by EventNameShort
| order by ConnectionSuccessRate asc
```

### 7.3 “Open in VS Code” Adoption and Engagement

```Kusto
// Users who triggered the "Open in VS Code" action within the time range
let base = ai_foundry_vsc
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
| extend EventNameShort = tostring(split(EventName, '/')[1])
| extend OS = tostring(Properties['common.os'])
| where OS in (['INPUT_OS']);
let UsersWithOpenVSCode = base
| where EventNameShort == "azure-ai-foundry.openinvscodeazure"
| project VSCodeMachineId
| distinct VSCodeMachineId;
let UsersWithAnyOtherEvent = base
| where EventNameShort != "azure-ai-foundry.openinvscodeazure"
| project VSCodeMachineId
| distinct VSCodeMachineId;
// Users who came from “Open in VS Code” and also performed other actions (engaged)
UsersWithOpenVSCode
| join kind=inner (UsersWithAnyOtherEvent) on VSCodeMachineId
| summarize EngagedUsers = dcount(VSCodeMachineId)
// Daily trend for “Open in VS Code” unique users
;base
| where EventNameShort == "azure-ai-foundry.openinvscodeazure"
| summarize UserCount = dcount(VSCodeMachineId) by bin(ClientTimestamp, 1d)
| order by ClientTimestamp asc
```

