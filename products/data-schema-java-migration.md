# GitHub Copilot app modernization for Java – Product and Data Overview

## 1. Product Overview

GitHub Copilot app modernization for Java (a.k.a. Java migration) aims to help you migrate your Java applications to Azure with confidence and efficiency, covering assessment, code remediation and validation, powered by the intelligence of GitHub Copilot.

- App modernization for Java evaluates the readiness of your application for migration to Azure, with an interactive experience on VS Code, powered by AppCAT for Java.
- App modernization for Java recommends target Azure services for the resource dependencies of your application, for each category of assessed issues.
- To accelerate code changes for common modernization issues, you may apply Microsoft formulas (code change patterns) that represent best practices from experts.
- To imitate past changes on other applications, you may pick some git commits and/or the working tree diff, save them as a custom formula, then apply it just like a Microsoft formula.
- After applying formulas, app modernization for Java will automatically find and fix compilation errors introduced by the code changes.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: Java Migration
- **Kusto Cluster**: `https://ddtelvscode.kusto.windows.net/`
- **Kusto Database**: `VSCodeExt`
- **Primary Metrics**: 

## 3. Table Schemas in Azure Data Explorer

### 3.1 Table `RawEventsVSCodeExt`

| Column Name           | Data Type    | Description                                   |
|-----------------------|-------------|-----------------------------------------------|
| EventName             | string      | Name of the event triggered                   |
| Attributes            | dynamic     | Event attributes                              |
| ClientTimestamp       | datetime    | Event timestamp at client                     |
| DataHandlingTags      | string      | Data handling tags                            |
| ExtensionName         | string      | Extension name                                |
| ExtensionVersion      | string      | Extension version                             |
| GeoCity               | string      | Client geo city                               |
| GeoCountryRegionIso   | string      | Client country ISO code                       |
| Measures              | dynamic     | Measures or indicators                        |
| NovaProperties        | dynamic     | Additional properties                         |
| Platform              | string      | Platform name                                 |
| PlatformVersion       | string      | Platform version                              |
| Properties            | dynamic     | Extra event properties                        |
| ServerTimestamp       | datetime    | Timestamp at server ingest                    |
| Tags                  | dynamic     | Tag metadata                                  |
| VSCodeMachineId       | string      | VSCode installation id                        |
| VSCodeSessionId       | string      | VSCode session id                             |
| VSCodeVersion         | string      | Version of VSCode                             |
| WorkloadTags          | string      | Associated workloads                          |
| LanguageServerVersion | string      | Version of language server                    |
| SchemaVersion         | string      | Schema version                                |
| Method                | string      | Action or method invoked                      |
| Duration              | real        | Duration (seconds)                            |
| SQMMachineId          | string      | SQM/MachineId                                 |
| DevDeviceId           | string      | Developer device id                           |
| IsInternal            | bool        | Internal usage flag                           |

## 4. Common Analytical Scenarios

In our model, users first run an assessment, and then perform migration operations based on the results. Each migration corresponds to a scenario, and a single assessment may result in multiple scenarios. For a given migration—or scenario—multiple formulas may be executed, followed by build fixes. Finally, the user is prompted to confirm whether to accept the changes.


- **User**: Identified by DevDeviceId
- **Active User**: Users with at least 1 java migration event
- **Engaged User**: Users with at least 1 java migration event
- **Installation**: The VSC extension installation is defined by Action in fact_activity_daily_ext

```kusto
fact_activity_daily_ext
| where Action in ('Install')
```

- **Migrate Action, Formula, Command and Prompt**: Java migration key contexts 

```kusto
RawEventsVSCodeExt
| extend migrateaction=tostring(Properties.migrateaction), formula=tostring(Properties.formula), command=tostring(Properties.command), prompt=tostring(Properties.prompt),appid=tostring(Properties.hashedappid)
```

- **AppID**: 

```kusto 
RawEventsVSCodeExt
| extend AppId = tostring(Properties.hashedappid)
```

- **Command**:
```kusto
RawEventsVSCodeExt
| extend command=tostring(Properties.command)
```
Each command represents a user-triggered event during their migration workflow. These commands are essential for tracing user actions and diagnosing issues accurately. Below is a comprehensive list of supported commands, along with their descriptions.

| **Command**                                     | **Description**                                                        |
| ----------------------------------------------- | ---------------------------------------------------------------------- |
| `migrate.java.assessment`                       | Triggers the initial assessment of the project.                   |
| `migrate.java.formula.create`                   | Creates a new custom formula based on current changes.              |
| `migrate.java.openScanSummaryCategoryDetails`   | Opens the details of a specific scan summary category from the assessment results.                 |
| `migrate.java.assessment.solutionReport`        | Create the solution report from the assessment results.                 |
| `migrate.java.formula.importFromLocal`          | Imports an existing formula file from the local file system.           |
| `migrate.java.assessment.refresh`               | Refreshes the assessment results.                                      |
| `migrate.java.formula.run`                      | Run formulas against a scenerio to handle migration from sidebar                  |
| `migrate.java.openSolutionMigrateView`          | Opens the solution report.              |
| `migrate.java.saveChangeAsFormula`              | Saves the current code changes as a reusable custom formula.                  |
| `migrate.java.formula.edit`                     | Edits an existing formula.                                             |
| `migrate.java.assessment.summaryReport`         | Create the summary report of the assessment.                            |
| `migrate.java.openScanSummary`                  | Opens the overall scan summary view.                                   |
| `java.migrateassistant.handleMigrate`           | Run formulas against a scenerio to handle migration from assessment view.                         |
| `migrate.java.openIssueSolution`                | Opens the proposed solutions for a specific issue.                     |
| `migrate.java.formula.refresh`                  | Refreshes the list or content of formulas.                             |
| `migrate.java.assessment.summaryReport.delete`  | Deletes the generated assessment summary report.                       |
| `migrate.java.generateDiscoveryReport`          | Generates a discovery report listing all dependencies and tech stacks. |
| `migrate.java.formula.deleteAll`                | Deletes all existing custom formulas.                                         |
| `migrate.java.formula.exportAll`                | Exports all formulas to local files.                                   |
| `migrate.java.saveChangeFromGroup`              | Saves grouped changes as a formula or for review.                      |
| `migrate.java.rejectChange`                     | Rejects a proposed change during review.                               |
| `migrate.java.refreshApplyFormulaView`          | Refreshes the view for applying a formula.                             |
| `migrate.java.resource.documentation`           | Opens related documentation for the identified issue.                  |
| `migrate.java.formula.export`                   | Exports a specific formula.                                            |
| `migrate.java.applyFormula`                     | Applies a selected formula to the project code.                        |
| `migrate.java.addSelectedFiles`                 | Adds selected files to be included in the migration.                   |
| `migrate.java.assessment.solutionReport.delete` | Deletes the solution report generated from the assessment.             |
| `migrate.java.saveChangeFromResources`          | Saves selected resource-level changes.                                 |
| `migrate.java.formula.delete`                   | Deletes a single formula.                                              |
| `migrate.java.refreshApplyFormulaReport`        | Refreshes the report after applying a formula.                         |
| `migrate.java.searchFormulaFiles`               | Searches for formula files in the workspace.                           |
| `migrate.java.generate`                         | Triggers code generation based on selected formula or rules.           |
| `migrate.java.saveChangeFromCommit`             | Saves code changes grouped by commit.                                  |
| `migrate.java.closeApplyFormulaReport`          | Closes the formula application report view.                            |


- **Mapping between App ID and Sample**

```kusto 
let appIdGroupMap = datatable(AppId:string, Sample:string)
[
    "87fed29caa8fb634f6b56b3cbc236f3fc16d5beb034979e358bd9c838d92fb0c", "com.microsoft.migration (asset-manager)",
    "324480b15b4c36f765c1c461443197d1e2b23f91115f22edb700e40d90da8586", "com.microsoft.migration (asset-manager)",
    "b2db5d1f438ff5b82e09a714e9cae19f82eae882ca4097724c2848ef50f299e6", "org.airsonic.player (airsonic)",
    "5f916b75f2f039574d1d507ba6d0b7198d67cdf5056f0dd8290e2831628f6e8e", "org.airsonic.player (airsonic)",
    "435f612e930b646d6627d6d9b621a0e6c5ae7591e0d75455e7c7187ce8e11446", "org.airsonic.player (airsonic)",
    "967a5ddd2b0b11a2b910a59f476daed7a75128836ad85bb574240612ab9598aa", "org.airsonic.player (airsonic)",
    "8dfd1f9c9d6729775dd858cf29476c62c21eaec9721375d6d43cee2bc455ad81", "org.airsonic.player (airsonic)",
    "808655d72a0bbbf7c98f7a501959497b27f43dc54c07caf9b63b1991c007e1c0", "org.airsonic.player (airsonic)",
    "52c67183c1ba3f0ef40a25c11d75033ea073ab68d8204bb373ad041f69a7974a", "com.microsoft.sqlserver (mi-sql-public-demo)",
    "f0df20177ccc81aa28f5cab74fe95aeebaf99f7b0cf0db3f135a2b3bfcc9752a", "com.example (rabbitmq-sender)"
];
```

## 5. Common Filters and Definitions

### 5.1 Events about Java migration product 

Filter the events about Java migration product (VSC ext) 

```kusto
RawEventsVSCodeExt
| where ExtensionName contains "migrate-java-to-azure"
| where EventName !contains 'migrate-java-to-azure/info'
```

### 5.3 External User

Filter the external users by joining with fact_user_isinternal table on DevDeviceId

```kusto
RawEventsVSCodeExt
| join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
| where IsInternal == false  
```

### 5.4 External Release date

Filter the external releases by ClientTimestamp or ActivityDay in different tables 

```kusto 
RawEventsVSCodeExt
| where ClientTimestamp >= datetime(2025-05-20)
```

Or


```kusto
fact_activity_daily_ext
| where ActivityDay >= datetime(2025-05-20)
```

### 5.5 Assessment runs

Filter the commands about assessment

```kusto 
RawEventsVSCodeExt
| where EventName contains "java/migrateassistant/command"
| where tostring(Properties.command) in ('migrate.java.assessment')
```

### 5.6 LLM Call

Filter LLM Call events 

```kusto 
RawEventsVSCodeExt
| where (EventName contains "java/migrateassistant/llmcall"
       or EventName contains "javaMigrationCopilot/llmcall")
```

### 5.7 GitHub Copilot-Chat panel & tool-call

Filter the tool call of Java migrate in GitHub Copilot Chat 

```kusto 
RawEventsVSCodeExt
| where ExtensionName == 'GitHub.copilot-chat'
| where EventName == "github.copilot-chat/panel.request"
| where EventName == "github.copilot-chat/toolcalldetails"
```

### 5.8 Scenarios run 

Filter the scenarios command event 

```kusto
RawEventsVSCodeExt
| where EventName contains "java/migrateassistant/command"
| where tostring(Properties.command) in ('migrate.java.formula.run', 'java.migrateassistant.handleMigrate')
```

### 5.9 Formula run

Filter Formula run 

```kusto
RawEventsVSCodeExt
| where EventName contains "java/migrateassistant/command"
| where tostring(Properties.command) in ('java/migrateassistant/formula/apply')
```

### 5.10 Build-fix event

Filter build-fix event 

```kusto
RawEventsVSCodeExt
| where EventName contains "javamigrationcopilot/buildfix/output"
```

Filter success build-fix event
```
RawEventsVSCodeExt
| where EventName contains "javamigrationcopilot/buildfix/output"
| where tostring(Properties.result) == "SUCCEEDED"
```

### 5.12 Assessment funnel commands

```kusto 
RawEventsVSCodeExt
| where tostring(Properties.command) in (
    'migrate.java.assessment',
    'migrate.java.assessment.solutionReport',
    'migrate.java.assessment.summaryReport',
    'migrate.java.openSolutionMigrateView')
```

### 5.13 Sample App IDs that may need to be distinguished from those used by real users

```kusto 
let excludedAppIds = dynamic([
    "87fed29caa8fb634f6b56b3cbc236f3fc16d5beb034979e358bd9c838d92fb0c",
    "324480b15b4c36f765c1c461443197d1e2b23f91115f22edb700e40d90da8586",
    "b2db5d1f438ff5b82e09a714e9cae19f82eae882ca4097724c2848ef50f299e6",
    "5f916b75f2f039574d1d507ba6d0b7198d67cdf5056f0dd8290e2831628f6e8e",
    "435f612e930b646d6627d6d9b621a0e6c5ae7591e0d75455e7c7187ce8e11446",
    "967a5ddd2b0b11a2b910a59f476daed7a75128836ad85bb574240612ab9598aa",
    "8dfd1f9c9d6729775dd858cf29476c62c21eaec9721375d6d43cee2bc455ad81",
    "808655d72a0bbbf7c98f7a501959497b27f43dc54c07caf9b63b1991c007e1c0",
    "52c67183c1ba3f0ef40a25c11d75033ea073ab68d8204bb373ad041f69a7974a",
    "f0df20177ccc81aa28f5cab74fe95aeebaf99f7b0cf0db3f135a2b3bfcc9752a"
]);
```

### 5.14 Code accept rate
```kusto
RawEventsVSCodeExt
| where ExtensionName == 'GitHub.copilot-chat'
| where Properties contains "modernization_planner"
| where EventName == "github.copilot-chat/toolcalldetails"
| project conversationId=tostring(Properties.conversationid), Properties.toolcounts, VSCodeMachineId, DevDeviceId
| distinct conversationId, VSCodeMachineId, DevDeviceId
| join kind=leftouter (
RawEventsVSCodeExt
| where ExtensionName == 'GitHub.copilot-chat'
| where EventName == "github.copilot-chat/panel.request"
    | extend conversationId=tostring(Properties.conversationid)
| project requestId = tostring(Properties.requestid), conversationId, VSCodeMachineId, DevDeviceId
) on conversationId, VSCodeMachineId, DevDeviceId
| project requestId
| distinct requestId
| join kind=leftouter (
RawEventsVSCodeExt
| where ExtensionName == 'GitHub.copilot-chat'
| where EventName == "github.copilot-chat/panel.edit.feedback"
| project outcome = tostring(Properties.outcome), requestId = tostring(Properties.requestid), hasRemainingEdits=tobool(Properties.hasremainingedits), DevDeviceId
) on requestId
| join kind=leftouter database('VsCodeInsights').fact_user_isinternal on DevDeviceId
| distinct requestId, outcome, hasRemainingEdits
| extend outcome=iif(isempty(outcome), 'Implicit accepted', iif(hasRemainingEdits, 'partially accepted', outcome))
| summarize count() by outcome
```

## 6. Notes and Considerations

- All timestamps are in **UTC**.
- The latest available data is typically as of `startofday(now())`.
- Always exclude usage from internal releases to focus on external customer behavior.
