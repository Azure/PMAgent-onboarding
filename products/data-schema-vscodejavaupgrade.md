# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

VS Code Java Upgrade is a Visual Studio Code extension that assists users in upgrading their Java projects. It provides automated upgrade plans, migration tools, code consistency checks, CVE validations, and integrates with OpenRewrite and BuildFix for code transformation and validation.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: VS Code Java Upgrade
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**: ddtelvscode.kusto.windows.net
- **Kusto Database**: VSCodeExt
- **Primary Metrics**: 
  - Distinct active users (DevDeviceId, VSCodeMachineId)
  - Session counts (sessionId)
  - Upgrade success/failure rates
  - Token usage (LLM calls, completion/prompt tokens)
  - Error rates (by error message)
  - Distribution by build tool, Java version, migration type

**[TODO]Data_Engineer**: Please review and describe any additional key metrics used to measure product performance, usage, or customer behavior.

## 3. Table Schemas in Azure Data Explorer

### 3.1 VSCodeExt.RawEventsVSCodeExt

| Column           | Type      | Description                                              |
|------------------|-----------|----------------------------------------------------------|
| EventName        | string    | Name of the event (e.g., upgrade steps, tool calls)      |
| ExtensionName    | string    | Name of the extension (should be 'vscjava.vscode-java-upgrade') |
| ExtensionVersion | string    | Version of the extension                                 |
| DevDeviceId      | string    | Unique device identifier                                 |
| VSCodeMachineId  | string    | Unique VS Code machine identifier                        |
| VSCodeSessionId  | string    | Unique session identifier                                |
| Properties       | dynamic   | Event-specific properties (JSON object)                  |
| Measures         | dynamic   | Numeric measures (e.g., token counts)                    |
| ServerTimestamp  | datetime  | Event timestamp in UTC                                   |

**[TODO]Data_Engineer**: Please review and expand column descriptions for Properties and Measures, listing key fields used in analysis (e.g., sessionid, buildtool, sourcejavaversion, targetjavaversion, errormessage, output.message, cves, recipes, behaviorchangescount, brokenfilescount).

### 3.2 VSCodeInsights.fact_user_isinternal

| Column        | Type      | Description                                   |
|---------------|-----------|-----------------------------------------------|
| DevDeviceId   | string    | Device identifier                             |
| IsInternal    | int       | 1 if internal user, 0 if external             |

## 4. Common Analytical Scenarios

**[TODO]Data_Engineer**: Review or supplement this section with representative product usage scenarios that are often investigated.

- **Upgrade Funnel Analysis**: Track user progression through upgrade steps (generate plan, confirm plan, OpenRewrite, BuildFix, CVE validation, consistency validation, summarization).
- **Build Tool Distribution**: Analyze upgrade success rates by build tool (Maven, Gradle, etc.).
- **Migration Distribution**: Analyze upgrade success rates by source/target Java version.
- **Error Analysis**: Identify top error messages and their impact on sessions/users.
- **Token Usage Analysis**: Measure LLM token consumption per session, per step, and by caller.
- **Feature Adoption**: Count users/sessions for OpenRewrite, BuildFix, CVE validation, consistency checks.
- **Session Success Rates**: Calculate ratios of successful vs. failed upgrade sessions.

## 5. Common Filters and Definitions

**[TODO]Data_Engineer**: Review or add product specific and common known filters.

- **Time Range Filter**: 
  ```Kusto
  | where ServerTimestamp between (_startTime .. _endTime)
  ```
- **User Type Filter** (internal/external):
  ```Kusto
  | where isempty(_user_types) or IsInternal in (_user_types)
  ```
- **Extension Version Filter**:
  ```Kusto
  | where isempty(_versions) or ExtensionVersion in (_versions)
  ```
- **Product Filter**:
  ```Kusto
  | where ExtensionName == 'vscjava.vscode-java-upgrade'
  ```
- **Excluding Test/Mock Sessions**:
  ```Kusto
  | where tostring(Properties['sessionid']) != 'MOCKSESSION'
  ```
- **Error Classification**:
  - Git Validation Issues: error messages containing "Uncommitted changes", "not a git repository", etc.
  - Java Runtime Issues: error messages about JDK/Maven/Gradle problems.
  - Unsupported Project Type: error messages about unsupported build systems.
  - Plan Created/Confirmed: empty error message on confirmplan.end.

- **Upgrade Step Mapping**:
  ```Kusto
  | extend UpgradeStep = case(
      EventName has 'generateplan', 'Generate Plan',
      EventName has 'confirmplan', 'Confirm Plan',
      EventName has 'openrewrite', 'OpenRewrite',
      EventName has 'buildfix', 'BuildFix',
      EventName has 'validatecves', 'CVE Validation',
      EventName has 'validatecodebehaviorconsistency', 'Consistency Validation',
      EventName has 'summarizeupgrade', 'Summarization',
      'Other')
  ```

## 6. Notes and Considerations

**[TODO]Data_Engineer**: **Content Guidance**: Include important operational notes, data limitations, and analysis best practices specific to this product.

- All timestamps are in **UTC**.
- The latest available data is typically as of `now()` or `startofday(now())`.
- For performance, limit query ranges to **<6 months** and results to **≤20 rows**.
- For accuracy, use `dcount()` to count distinct identifiers.
- Always exclude usage from test/mock sessions (`sessionid != 'MOCKSESSION'`).
- Internal/external user classification is based on `IsInternal` from `fact_user_isinternal`.
- Some upgrade steps may not generate sessions for all users (e.g., validations may filter out sessions).

## 7. Sample Queries

### 7.1 Upgrade Funnel by Step

```Kusto
let eventOrder = dynamic([
    'vscjava.vscode-java-upgrade/generateplan.prepare',
    'vscjava.vscode-java-upgrade/generateplan.start',
    'vscjava.vscode-java-upgrade/generateplan.end',
    'vscjava.vscode-java-upgrade/confirmplan.prepare',
    'vscjava.vscode-java-upgrade/confirmplan.start',
    'vscjava.vscode-java-upgrade/confirmplan.end',
    'vscjava.vscode-java-upgrade/openrewrite.prepare',
    'vscjava.vscode-java-upgrade/openrewrite.start',
    'vscjava.vscode-java-upgrade/openrewrite.end',
    'vscjava.vscode-java-upgrade/buildfix.prepare',
    'vscjava.vscode-java-upgrade/buildfix.start',
    'vscjava.vscode-java-upgrade/buildfix.end',
    'vscjava.vscode-java-upgrade/validatecves.prepare',
    'vscjava.vscode-java-upgrade/validatecves.start',
    'vscjava.vscode-java-upgrade/validatecves.end',
    'vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.prepare',
    'vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start',
    'vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end',
    'vscjava.vscode-java-upgrade/summarizeupgrade.start',
    'vscjava.vscode-java-upgrade/summarizeupgrade.end'
]);
RawEventsVSCodeExt
| where ExtensionName == 'vscjava.vscode-java-upgrade'
| where ServerTimestamp between (_startTime .. _endTime)
| extend session = tostring(Properties['sessionid'])
| summarize sessionCount = dcount(session), userCount = dcount(VSCodeMachineId) by EventName
| extend orderIndex = array_index_of(eventOrder, EventName)
| where orderIndex >= 0
| order by orderIndex asc
| project EventName, sessionCount, userCount
```

### 7.2 Build Tool Success Rate

```Kusto
RawEventsVSCodeExt
| where EventName == 'vscjava.vscode-java-upgrade/confirmplan.end'
| extend buildTool = tostring(Properties['buildtool'])
| distinct buildTool, sessionId
| join kind=inner (
    RawEventsVSCodeExt
    | where EventName == 'vscjava.vscode-java-upgrade/confirmplan.end'
    | extend result = tostring(Properties['result'])
) on sessionId
| summarize totalSession = dcount(sessionId), succeededSession = dcountif(sessionId, result == 'Succeeded') by buildTool
| project buildTool, succeededSession, totalSession, succeedRate = round(succeededSession * 1.0 / totalSession, 4) * 100
```

### 7.3 Token Usage Per Step

```Kusto
RawEventsVSCodeExt
| where EventName has 'vscjava.vscode-java-upgrade/llmclient.sendrequest'
| extend caller = tostring(Properties['caller'])
| extend completionToken = toint(Measures['completiontoken']), promptToken = toint(Measures['prompttoken']), tokens = toint(Measures['tokens'])
| summarize percentiles(tokens, 50, 75, 90, 95), max(tokens) by caller
```

