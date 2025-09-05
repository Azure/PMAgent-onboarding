# GitHub Copilot app modernization - upgrade for Java – Product and Data Overview

## 1. Product Overview

GitHub Copilot app modernization - upgrade for Java (a.k.a. Java Upgrade) helps you upgrade your Java applications. It's an extension for Visual Studio Code which can help:

- Analyze your project, assess your dependencies and propose an upgrade plan
- Execute the plan to transform your project
- Automatically fix issues during the progress
- Report all details including commits, logs and output
- Show a summary including file changes, updated dependencies and commits in the working branch when update is finished
- Generate unit test cases separately from the upgrade process.

This product is large language tool used by GitHub Copilot in VSC. 

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: Java Upgrade
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

- **User**: Identified by VSCodeMachineId
- **Session**: Use following kusto to get session identifier

```kusto 
| extend session = tostring(Properties["sessionid"])
```

- **Build Tool**: It is extracted from the Properties["buildtool"] property when the event is confirmplan.end.

```kusto 
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend buildTool = tostring(Properties["buildtool"])
```

- **Source version and Target version**: Pull from Properties["sourcejavaversion"] and Properties["targetjavaversion"] (cast to int).

```kusto
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend sourceVersion = toint(Properties["sourcejavaversion"]),
         targetVersion = toint(Properties["targetjavaversion"])
```

- **Token Counts**: Uses Measures["completiontoken"], Measures["prompttoken"], and Measures["tokens"] per session and “caller” (which typically corresponds to a tool or extension

```kusto
| extend caller = tostring(Properties["caller"])
| extend completionToken = toint(Measures["completiontoken"]),
         promptToken     = toint(Measures["prompttoken"]),
         tokens          = toint(Measures["tokens"])
```

- **Event Result**: Each event of Java Upgrade may have several stages (e.g. prepare, start, end.) The result for each event is from Properties["result"]


## 5. Common Filters and Definitions

### 5.1 Events about Java Upgrade product 

Filter the events about Java Upgrade product (VSC ext) 

```kusto
| where EventName startswith "vscjava.vscode-java-upgrade"
```

### 5.2 Funnel of Java Upgrade 

The funnel of java Upgrade is defined by the events for this product and they are in following workflow ideally. Eeah sub event name is formatted as 'sub_event_name.stage'.

- vscjava.vscode-java-upgrade/generateplan.prepare
- vscjava.vscode-java-upgrade/generateplan.start
- vscjava.vscode-java-upgrade/generateplan.end
- vscjava.vscode-java-upgrade/conformplan.start
- vscjava.vscode-java-upgrade/conformplan.end
- vscjava.vscode-java-upgrade/openwrite.prepare
- vscjava.vscode-java-upgrade/openwrite.start
- vscjava.vscode-java-upgrade/openwrite.end
- vscjava.vscode-java-upgrade/buildproject.prepare
- vscjava.vscode-java-upgrade/buildproject.start
- vscjava.vscode-java-upgrade/buildproject.end
- vscjava.vscode-java-upgrade/buildfix.prepare
- vscjava.vscode-java-upgrade/buildfix.start
- vscjava.vscode-java-upgrade/buildfix.end
- vscjava.vscode-java-upgrade/validatecves.start
- vscjava.vscode-java-upgrade/validatecves.end
- vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.prepare
- vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start
- vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end
- vscjava.vscode-java-upgrade/summarizechanges.prepare
- vscjava.vscode-java-upgrade/summarizechanges.start
- vscjava.vscode-java-upgrade/summarizechanges.end

### 5.3 Error Message

Filter by Properties["eventtype"] == "error" and non‐empty

```kusto
| extend eventType = tostring(Properties["eventtype"])
| where eventType == "error"
| extend errorMessage = tostring(Properties["errormessage"])
| where isnotempty(errorMessage)
```

### 5.4 Release Version

Filter the new published releases by version 

```kusto
| extend
    majorVersion = toint(split(ExtensionVersion, ".", 0)),  
    minorVersion = toint(split(ExtensionVersion, ".", 1))   
| where majorVersion > 0 or minorVersion >= 10
```

### 5.5 External User

Filter the external users by joining with fact_user_isinternal table on DevDeviceId

```kusto
| join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
| where IsInternal == false  
```

## 6. Notes and Considerations

- All timestamps are in **UTC**.
- The latest available data is typically as of `startofday(now())`.
- Always exclude usage from internal testing releases to focus on external customer behavior.
