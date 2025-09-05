# Azure AI Foundry for Visual Studio Code – Product and Data Overview

## 1. Product Overview

With the Azure AI Foundry for Visual Studio Code extension (a.k.a. AI Foundry extension) you can easily deploy Large Language Models, develop AI applications, develop with Agents, and more with Azure AI Foundry from the Visual Studio Code interface.

With Azure AI Foundry, you can:

- Deploy language models from Microsoft, OpenAI, Meta, DeepSeek, and more using the model catalog
- Test deployed models in a model playground
- Start building with deployed models by right-clicking on the model to get the sample code
- Create, deploy, and test agents with Azure AI Agent Service

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: AI Foundry extension
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

- **User**: Identified by VSCodeMachineId. Use count_distinct() to get exact number instead of dcount() with estimated number. 
- **Active User (active1d)**:  A user is considered as active within a specific period if he fires at least one event of AI Foundry VSC extension during that time.
    - **Always apply the [Filter for events of active users](#53-filter-for-events-of-active-users)** before counting.
- **Engaged User (engaged2d)**: An active user is considered as engaged within a specific period if he fires event of AI Foundry VSC extension for at least 2 distinct days during that time.
    - **Always apply the [Filter for events of active users](#53-filter-for-events-of-active-users)** before counting.
- **Dedicated User (dedicated10d)**: An active user is considered deidicated within a specific period if he fires event of AI Foundry VSC extension for at least 10 distinct days during that time.
    - **Always apply the [Filter for events of active users](#53-filter-for-events-of-active-users)** before counting.
- **Monthly Active Users (MAU)**: Total number of active users in rolling 28 days.
- **Monthly Engaged Users (MEU)**: Total number of engaged users in rolling 28 days.
- **User Active Date (New User Date)**: Identified by first appearance date of a specific active user. 
- **New User**: A user is considered as new user for a specific period if his active date is during that time. 
- **Existing User**: A user is considered as existing user for a specific period if his active date is before during that time. 
- **Retention Week N for New Users of Week W**: measures the percentage of users who first became active during the week starting on Week W (their "activation week") and who were also active during the N-th week following their activation week.
    - **New users of Week W**: Users whose very first recorded activity falls within the calendar week starting on Week W.
    - **Retention Week N**: The period starting exactly N weeks after the start of the activation week and lasting one week.
- **JTBD**: It is the short name of 'jobs to be done'. A JTBD is a job user could completed in AI Foundry VSC extension.
- **User Funnel (User Journey)**: The sequenece of JTBDs completed within same VS Code session (VSCodeSessionId) order by ClientTimestamp in descending order.
- **Command**: The event of AI Foundry VSC extension is also called as 'Command'. 

## 5. Common Filters and Definitions

### 5.1 Time range: Rolling 28 days

When calculating metrics over a rolling 28-day window, follow this logic to define the start and end dates:

1. **If the user asks for the latest rolling 28 days** (no specific end date mentioned), use **start of yesterday** as the end of the window to avoid incomplete telemetry.

    ```kusto
    let endDate = startofday(now(), -1);
    let startDate = endDate - 27d;
    RawEventsVSCodeExt
    | where ClientTimestamp between (startDate .. endDate)
    ```
2. **If the user provides a specific end date (e.g. July 10, 2025)**, use start of that day as the end of the window.

    ```kusto
    let endDate = startofday(datetime(2025-07-10));
    let startDate = endDate - 27d;
    RawEventsVSCodeExt
    | where ClientTimestamp between (startDate .. endDate)

### 5.2 Get the event name

Get the event name for AI Foundry VSC extension.

```kusto
RawEventsVSCodeExt
| extend EventNameShort = tostring(split(EventName, '/')[1])
```

Rules for Mapping Events
- Always define a mapping table using a `datatable` in Kusto.
- Always join the event with the mapping table using event name to associate each event with its corresponding feature or JTBD. Ensure that all features or JTBDs are retained in the final output, even if no events are mapped to them.
- Always ignore any events not listed in the mapping table. Only analyze events that are explicitly mapped to features or JTBD.

| EventNameShort | Description | Feature | JTBD (Jobs-to-be-Done) |
|---|---|---|---|
| azure-ai-foundry.commandpalette.llmdeploy | Deploy a large language model via the command palette | model | Deploy a model |
| azure-ai-foundry.viewcontext.llmdeploy | Deploy a model from the right-click view context | model | Deploy a model |
| model.update | Update the configuration or definition of a model | model | |
| model.delete | Delete a model from the workspace or registry | model | |
| azure-ai-foundry.viewcontext.viewmodel | View details of a model from the view context | model | |
| azure-ai-foundry.viewcontext.model.openinplayground | Open a model in the interactive Playground for testing | model | Open Playground - Model |
| azure-ai-foundry.viewcontext.opencodefile | Open a model-related code file from the view context | model | Open Code file - Model |
| azure-ai-foundry.commandpalette.opencodefile | Open a model-related code file via the command palette | model | Open Code file - Model |
| azure-ai-foundry.commandpalette.opencatalog | Open the model or agent catalog from the command palette | model | |
| azure-ai-foundry.editortitle.openagentdesigner | Open Agent Designer from the editor title bar | agent | |
| azure-ai-foundry.explorercontext.openagentdesigner | Open Agent Designer from the explorer's right-click context menu | agent | |
| azure-ai-foundry.commandpalette.runagent | Run an agent via the command palette | agent | |
| azure-ai-foundry.viewcontext.agent.delete | Delete an agent from the right-click context menu | agent | |
| azure-ai-foundry.viewcontext.createagent | Create a new agent from the right-click context menu | agent | |
| agentdesignerwebview.openyamlfile | Open the YAML configuration file in Agent Designer | agent | |
| agentdesignerwebview.openplayground | Open the Playground interface for an agent | agent | Open Playground - Agent |
| agentdesignerwebview.synctofile | Sync the agent definition to a local file | agent | |
| agentdesignerwebview.deployagent | Deploy the configured agent | agent | Deploy an agent |
| agentdesignerwebview.savetolocal | Save the agent configuration locally | agent | |
| azure-ai-foundry.viewcontext.openagentdesigner | Open Agent Designer from the view context menu | agent | |
| agentdesignerwebview.addtool | Add a tool to the agent within Agent Designer | agent | |
| agentroottreenode.getchildren | Retrieve child nodes of the agent tree view | agent | |
| playgroundwebview.createthread | Create a new conversation thread in Playground | agent | |
| project.sendmessage | Send a message to the agent within a project or Playground | agent | |
| playgroundwebview.initialize | Initialize the Playground interface | other | Open Playground - Agent |
| azure-ai-foundry.commandpalette.setdefault | Set the current project as default via the command palette | other | Choose a project |
| azure-ai-foundry.commandpalette.createproject | Create a new project via the command palette | other | Choose a project |
| azure-ai-foundry.viewcontext.openinfoundryview | Open the project in AI Foundry view | other | Choose a project |
| azure-ai-foundry.viewcontext.switchdefaultproject | Switch the default project from the view context | other | Choose a project |


### 5.3 Filter for events of active users

Find out the active users' events.
- **Use this filter ONLY when calculating user-level metrics for active users, like MAU, MEU, active user, engaged user, dedicated user, etc.** 
- **Do NOT use this filter for feature usage, funnel analysis, or event-based analysis for any user, unless explicitly instructed.**

```kusto
RawEventsVSCodeExt
| where ExtensionName == 'TeamsDevApp.vscode-ai-foundry'
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
```

### 5.4 External User

Filter the external users by joining with fact_user_isinternal table on DevDeviceId

```kusto
RawEventsVSCodeExt
| join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
| where IsInternal == false  
```

### 5.5 Get OS

Get the OS. 

```kusto
RawEventsVSCodeExt
| extend OS = tostring(Properties['common.os'])
```

### 5.6 Get Event Result, Error Message, Error Category

Get the result, error message, error category of an event. 
- When analyzing the error, ALWASY using this filter to focus on target error categories.

```kusto
RawEventsVSCodeExt
| extend Result = Properties.result // The result will be 'Succeeded' if the event is completed successfully.
| extend ErrorMessage = Properties.errormessage
| extend ErrorCategory='uncategorized'
| extend ErrorCategory=case(ErrorMessage == "Operation cancelled.", "user", ErrorCategory)
| where ErrorCategory !in ('host','user', 'data')
```

### 5.7 Filter of User from "Open in VS Code" 

```kusto
RawEventsVSCodeExt
| extend EventNameShort = tostring(split(EventName, '/')[1])
| where EventNameShort == "azure-ai-foundry.openinvscodeazure"
```

### 5.8 Get the deployment type

There are 2 types of deployment for AI Foundry VSC extension: Model Deployment and Agent Deployment.

```kusto
RawEventsVSCodeExt
| extend DeploymentType = case(  
    EventNameShort in ('azure-ai-foundry.commandpalette.llmdeploy','azure-ai-foundry.viewcontext.llmdeploy'), "ModelDeployment",
    EventNameShort in ('agentdesignerwebview.deployagent'), "AgentDeployment",
    "other"
  )
```

## 6. Notes and Considerations

- All timestamps are in **UTC**.
- Data refresh is **daily** with ~2-hour delay.
- Always ONLY analyze external users' data.
