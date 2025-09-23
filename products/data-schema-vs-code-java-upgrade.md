# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

VS Code Java Upgrade is a Visual Studio Code extension that assists developers in upgrading Java projects. This schema and playbook capture telemetry for the Java upgrade workflow to enable PMAgent to analyze session outcomes, funnel conversion, error taxonomies, and LLM token usage related to the upgrade process.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: VS Code Java Upgrade
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
https://ddtelvscode.kusto.windows.net/
- **Kusto Database**:
VSCodeExt
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# VS Code Java Upgrade - Kusto Query Playbook

## **Overview**
- Product: VS Code Java Upgrade
- Summary: VS Code Java Upgrade
- Main cluster: https://ddtelvscode.kusto.windows.net/
- Main database: VSCodeExt
- Note: Queries also read cross-database from VSCodeInsights (same cluster), notably fact_user_isinternal.

## **Conventions & Assumptions**

- Time semantics
  - Observed timestamp columns: ServerTimestamp (canonical), startTime (derived = ServerTimestamp in the result view).
  - Canonical Time Column: ServerTimestamp
    - Alias pattern: project-rename or extend, e.g., startTime = ServerTimestamp; downstream queries should consistently reference one canonical time column.
  - Typical windowing: parameterized ['_startTime'] .. ['_endTime'] in the raw view.
  - Common binning: not explicitly used in provided queries (mostly snapshot/funnel/dcount). If needed, default to bin(ServerTimestamp, 1d).
  - Timezone: unspecified; assume UTC by default.
  - Recommendation: current day may be incomplete (unknown ingestion lag); prefer using an effective end time that excludes the current partial day for reporting unless real-time is required.

- Freshness & Completeness Gates
  - Ingestion cadence: unknown.
  - Current-day completeness: unknown; avoid same-day reporting for stable KPIs.
  - Suggested gate pattern:
    - Use a prior full period (e.g., last full day/week).
    - Multi-slice gate: require all expected event stages to emit at least 1 record for the latest slice; otherwise fall back to the previous slice.

- Joins & Alignment
  - Frequent keys:
    - DevDeviceId (join to user internality in fact_user_isinternal).
    - VSCodeMachineId (user/device-level counts).
    - VSCodeSessionId (VS Code session).
    - sessionId (upgrade flow session from Properties["sessionid"]).
  - Typical join kinds:
    - inner (to apply user internality from fact_user_isinternal).
    - leftouter (to attach outcomes or failure states).
    - leftantisemi (to exclude known failure cohorts).
  - Post-join hygiene:
    - Use project-rename or extend to standardize columns (e.g., session vs sessionId).
    - Remove duplicate columns and temporary fields with project-away.
    - Use coalesce() when merging alternate keys if needed.

- Filters & Idioms
  - Event scope: ExtensionName == "vscjava.vscode-java-upgrade" is the base filter (in raw view).
  - Exclude mock data: tostring(Properties["sessionid"]) != "MOCKSESSION".
  - Version gating: majorVersion = toint(split(ExtensionVersion, ".", 0)[0]); minorVersion = toint(split(ExtensionVersion, ".", 1)[0]); keep where majorVersion > 0 or minorVersion >= 10.
  - User cohort: join to fact_user_isinternal; filter IsInternal via dropdown ['_user_types'] when provided.
  - String filters: has, contains on Properties["errormessage"] and other Properties/Measures fields; be mindful of case sensitivity as per Kusto defaults.

- Cross-cluster/DB & Sharding
  - Cross-database (same cluster) qualification:
    - database("VSCodeExt").RawEventsVSCodeExt
    - database("VSCodeInsights").fact_user_isinternal
  - No regional shards or union patterns are present in the input. If you introduce shards, use union → normalize time/keys → summarize.

- Table classes
  - Fact (events): RawEventsVSCodeExt (primary source of all Java upgrade telemetry).
  - Snapshot/Dimension: fact_user_isinternal (used to flag internal users; joined by DevDeviceId).
  - Pre-aggregated: none in the provided content.

## **Entity & Counting Rules (Core Definitions)**

- Entity model
  - Device/user: DevDeviceId, VSCodeMachineId (used for dcount at user/device level).
  - Session:
    - VSCodeSessionId: VS Code session context (broader).
    - sessionId: the Java upgrade flow session (from Properties["sessionid"]); primary unit for funnels/outcomes.
  - Version:
    - ExtensionVersion → majorVersion, minorVersion (derived via split).

- Counting Do/Don’t
  - Use dcount(sessionId) for flow-level KPIs and stage conversion.
  - Use dcount(DevDeviceId) or dcount(VSCodeMachineId) for user/device breadth; pick one consistently per KPI.
  - Snapshot vs. events:
    - Use event facts (RawEventsVSCodeExt) for stage counts and error bucketing.
    - Use joined snapshot (fact_user_isinternal) only for cohorting, not counting the snapshot rows.

## **Views (Reusable Layers)**

- raw
  - Purpose: Canonical filtered event stream for the Java Upgrade extension with time, version, and internality controls.
  - Inputs: VSCodeExt.RawEventsVSCodeExt joined with VSCodeInsights.fact_user_isinternal.
  - Output: Stream with standardized sessionId, version fields, and filtered cohorts.
  - Query:
    ```kusto
    let base = database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where tostring(Properties["sessionid"]) != "MOCKSESSION"
    | where ServerTimestamp  between (['_startTime'] .. ['_endTime']) // Time range filtering
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion > 0 or minorVersion >=10
    | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId;
    base
    | where isempty(['_versions']) or ExtensionVersion in (['_versions']) // Multiple selection filtering
    // regrad all users before code complete as internal users
    | where isempty( ['_user_types']) or IsInternal in ( ['_user_types'])
    | extend sessionId = tostring(Properties["sessionid"])
    ```
  - Dependents: All queries; this is the base for counts, funnels, and metrics.

- result
  - Purpose: Session-level end-state classification (Succeeded, BuildFixFailed, OpenResultFailed, Incomplete) per upgrade flow.
  - Inputs: raw events for confirmplan.end (start of flow), openrewrite.end (failure detection), buildfix.end (success/failure).
  - Output: One row per session with result and version context.
  - Query:
    ```kusto
    let all = raw
    | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
    | distinct VSCodeMachineId, startTime = ServerTimestamp, sessionId, majorVersion, minorVersion;
    let openRewriteFailedResults = raw
    | where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "failed"
    | distinct VSCodeMachineId, sessionId, majorVersion, minorVersion
    | project sessionId, orResult = "OpenResultFailed";
    let buildFixResult = raw
    | where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
    | extend buildResult = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")
    | distinct VSCodeMachineId, sessionId, majorVersion, minorVersion, buildResult
    | project sessionId, buildResult;
    all
    | join kind=leftouter openRewriteFailedResults on sessionId
    | join kind=leftouter buildFixResult on sessionId
    | extend result = case(isnotempty( buildResult), buildResult, isnotempty(orResult), orResult, "Incomplete")
    | project VSCodeMachineId, startTime, sessionId, result, majorVersion, minorVersion, version = strcat(majorVersion, ".", minorVersion);
    ```
  - Dependents: Success-rate breakdowns, token usage by outcome, version-level distributions.

- updatedependencies
  - Purpose: Extract and flatten planned dependency updates from planstarted events.
  - Inputs: raw
  - Output: One row per dependency with source/target versions and session.
  - Query:
    ```kusto
    // Please enter your KQL query (Example):
    // <table name>
    // | where <datetime column> between (['_startTime'] .. ['_endTime']) // Time range filtering
    // | where isempty(['_versions']) or <column name> in (['_versions']) // Multiple selection filtering
    // | take 100
    raw
    | where EventName == "vscjava.vscode-java-upgrade/javaupgrade.planstarted"
    | extend dependencies = parse_json(tostring(Properties["updateddependencies"])), session = tostring(Properties["sessionid"])
    | project dependencies, session
    | mv-expand dependencies
    | project dependency = tostring(dependencies["source"]["id"]), source=tostring(dependencies["source"]["version"]), target=tostring(dependencies["target"]["version"]), session;
    ```
  - Dependents: Ad-hoc analyses of planned upgrades per dependency.

- compileFailedSessions
  - Purpose: Identify sessions that stalled early without OpenRewrite “Failed to run OpenRewrite” signature (task-level filter).
  - Inputs: raw
  - Output: Cohort of sessionIds.
  - Query:
    ```kusto
    // Please enter your KQL query (Example):
    // <table name>
    // | where <datetime column> between (['_startTime'] .. ['_endTime']) // Time range filtering
    // | where isempty(['_user_types']) or <column name> == ['_user_types'] // Single selection filtering
    // | where isempty(['_versions']) or <column name> in (['_versions']) // Multiple selection filtering
    // | take 100
    let openrewriteFailed = raw
    | extend outputMessage = tostring(Properties["output.message"])
    | extend sessionid = tostring(Properties["sessionid"])
    | where outputMessage has "Failed to run OpenRewrite"
    | distinct sessionId;
    let failedTask1 = raw
    | extend taskId = tostring(Properties["taskid"])
    | extend task = toint(split(taskId, ".")[0]) , subTask = toint(split(taskId, ".")[1])
    | where isnotempty(subTask)
    | summarize max(task) by sessionId
    | where max_task == 1
    | distinct sessionId;
    failedTask1
    | join kind=leftantisemi openrewriteFailed on sessionId;
    ```
  - Dependents: Triage and early-stage failure detection.

## **Query Building Blocks (Copy-paste snippets, contains snippets and description)**

- Time window template
  - Description: Consistent time filter over ServerTimestamp; supports dashboards with ['_startTime']/['_endTime'] parameters. Consider excluding current day if freshness is unknown.
  - Snippet:
    ```kusto
    // Time window with effective end time gate (optional)
    let startTime = datetime(<YYYY-MM-DD>);
    let endTime = datetime(<YYYY-MM-DD>); // consider now(-1d) to avoid partial day if freshness is unknown
    database("VSCodeExt").RawEventsVSCodeExt
    | where ServerTimestamp between (startTime .. endTime)
    ```

- Base cohort with internality and version gating
  - Description: Standard filter + join to internality; derive sessionId and versions.
  - Snippet:
    ```kusto
    let base = database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where tostring(Properties["sessionid"]) != "MOCKSESSION"
    | where ServerTimestamp between (['_startTime'] .. ['_endTime'])
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
             minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion > 0 or minorVersion >= 10
    | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId;
    base
    | where isempty(['_versions']) or ExtensionVersion in (['_versions'])
    | where isempty(['_user_types']) or IsInternal in (['_user_types'])
    | extend sessionId = tostring(Properties["sessionid"])
    ```

- Join template (attach outcomes to sessions)
  - Description: Leftouter joins to attach failure/success outcomes while retaining all planned sessions.
  - Snippet:
    ```kusto
    let planned = raw | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end" | distinct sessionId;
    let openrewrite = raw | where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
                          | project sessionId, orResult = tostring(Properties["result"]);
    let buildfix = raw | where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
                       | project sessionId, bfResult = tostring(Properties["result"]);
    planned
    | join kind=leftouter openrewrite on sessionId
    | join kind=leftouter buildfix on sessionId
    | extend finalResult = case(bfResult == "true", "Succeeded",
                                orResult == "failed", "OpenResultFailed",
                                "Incomplete")
    | project-away orResult, bfResult
    ```

- De-dup pattern
  - Description: Choose latest event per session or device.
  - Snippet:
    ```kusto
    raw
    | summarize arg_max(ServerTimestamp, *) by sessionId
    ```

- Important filters and error bucketing
  - Description: Standardized bucketing of error messages for generateplan/confirm stages.
  - Snippet:
    ```kusto
    raw
    | where EventName has "vscjava.vscode-java-upgrade/generateplan"
      or EventName startswith "vscjava.vscode-java-upgrade/confirmplan"
    | extend error = tostring(Properties["errormessage"])
    | where isnotempty(error)
    | extend Message = case(
        error has "Uncommitted changes" or error has "not a git repository" or error has "Failed to get git status", "Git Validation Issues",
        error has "is only available for GitHub Copilot \"Business\" and \"Enterprise\" plans", "Require Business and Enterprise plans",
        error has "Spring Boot dependency not found" or error has "Invalid Spring Boot version to upgrade", "Invalid Spring Boot Target Version",
        error has "Please provide a path to an existing JDK" or error has "Maven path is required" or error has "Invalid Maven path"
          or error has "is not a valid JDK installation path" or error has "Gradle wrapper not found", "Java Runtime Issues (JDK/Maven/Gradle)",
        error has "Failed to convert markdown to JSON", "Failed to transform configuration markdown",
        "Others"
      )
    | summarize Count = count(), Users = dcount(DevDeviceId) by Message
    | order by Count desc
    ```

- Important definitions (upgrade session outcome)
  - Description: Session outcome classification used across dashboards.
  - Snippet:
    ```kusto
    // "Succeeded" if buildfix.end result == "true"
    // "OpenResultFailed" if openrewrite.end result == "failed" and no success afterwards
    // otherwise "Incomplete"
    let result = ... // use the 'result' view provided in this playbook
    ```

- ID parsing / derivation
  - Description: Parse versions and dependency arrays.
  - Snippet:
    ```kusto
    // ExtensionVersion → major/minor
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
             minorVersion = toint(split(ExtensionVersion, ".", 1)[0])

    // Dependencies from planstarted
    | extend dependencies = parse_json(tostring(Properties["updateddependencies"]))
    | mv-expand dependencies
    | project dependency = tostring(dependencies["source"]["id"]),
              source=tostring(dependencies["source"]["version"]),
              target=tostring(dependencies["target"]["version"])
    ```

- Sharded union template
  - Description: Not present in inputs; if later sharded by region or environment, normalize before summarize.
  - Snippet:
    ```kusto
    union withsource=TableName
      database("VSCodeExt").RawEventsVSCodeExt, database("VSCodeExtEU").RawEventsVSCodeExt
    | project ServerTimestamp, DevDeviceId, VSCodeSessionId, Properties, Measures
    | summarize count() by bin(ServerTimestamp, 1d), TableName
    ```

## **Example Queries (with explanations)**

1) Event stage coverage and percentages across sessions/users
- Description: Computes session/user coverage per event in the end-to-end flow. Uses a fixed event order, excludes “no session” events from session percentage, and orders output for a funnel-like view. Adapt by changing time window in the raw view and by adding/removing events.
```kusto
let eventOrder = dynamic([
    "vscjava.vscode-java-upgrade/generateplan.prepare",
    "vscjava.vscode-java-upgrade/generateplan.start",
    "vscjava.vscode-java-upgrade/generateplan.end",
    "vscjava.vscode-java-upgrade/confirmplan.prepare",
    "vscjava.vscode-java-upgrade/confirmplan.start",
    "vscjava.vscode-java-upgrade/confirmplan.end",
    "vscjava.vscode-java-upgrade/openrewrite.prepare",
    "vscjava.vscode-java-upgrade/openrewrite.start",
    "vscjava.vscode-java-upgrade/openrewrite.end",
    "vscjava.vscode-java-upgrade/buildfix.prepare",
    "vscjava.vscode-java-upgrade/buildfix.start",
    "vscjava.vscode-java-upgrade/buildfix.end",
    "vscjava.vscode-java-upgrade/validatecves.prepare",
    "vscjava.vscode-java-upgrade/validatecves.start",
    "vscjava.vscode-java-upgrade/validatecves.end",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.prepare",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end",
    "vscjava.vscode-java-upgrade/summarizechanges.start",
    "vscjava.vscode-java-upgrade/summarizechanges.prepare",
    "vscjava.vscode-java-upgrade/summarizechanges.end"
]);
let noSessionEvents = dynamic(["vscjava.vscode-java-upgrade/generateplan.start", "vscjava.vscode-java-upgrade/generateplan.prepare", "vscjava.vscode-java-upgrade/generateplan.end"]);
let operations = raw
| extend session = tostring(Properties["sessionid"]) 
| where EventName in (
    "vscjava.vscode-java-upgrade/validatecves.start",
    "vscjava.vscode-java-upgrade/validatecves.prepare",
    "vscjava.vscode-java-upgrade/validatecves.end",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.prepare",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end",
    "vscjava.vscode-java-upgrade/summarizechanges.start",
    "vscjava.vscode-java-upgrade/summarizechanges.prepare",
    "vscjava.vscode-java-upgrade/summarizechanges.end",
    "vscjava.vscode-java-upgrade/openrewrite.start",
    "vscjava.vscode-java-upgrade/openrewrite.prepare",
    "vscjava.vscode-java-upgrade/openrewrite.end",
    "vscjava.vscode-java-upgrade/generateplan.start",
    "vscjava.vscode-java-upgrade/generateplan.prepare",
    "vscjava.vscode-java-upgrade/generateplan.end",
    "vscjava.vscode-java-upgrade/confirmplan.start",
    "vscjava.vscode-java-upgrade/confirmplan.prepare",
    "vscjava.vscode-java-upgrade/confirmplan.end",
    "vscjava.vscode-java-upgrade/buildproject.start",
    "vscjava.vscode-java-upgrade/buildproject.prepare",
    "vscjava.vscode-java-upgrade/buildproject.end",
    "vscjava.vscode-java-upgrade/buildfix.start",
    "vscjava.vscode-java-upgrade/buildfix.prepare",
    "vscjava.vscode-java-upgrade/buildfix.end"
);
let totalUser = toscalar(operations | summarize dcount(VSCodeMachineId));
let totalSession = toscalar(operations | summarize dcount(session));
operations
| summarize sessionCount = dcount(session), userCount = dcount(VSCodeMachineId) by EventName
| extend orderIndex = array_index_of(eventOrder, EventName)
| project EventName,
    sessionPercentage = iff(EventName in (noSessionEvents), 100.0, round(todouble(sessionCount) / totalSession * 100.0, 2)), 
    sessionCount,
    userPercentage = round(todouble(userCount) / totalUser * 100.0, 2), 
    userCount,
    orderIndex
| where orderIndex >= 0
| order by orderIndex asc
| project EventName, 
    sessionCount = iff(EventName in (noSessionEvents), "N/A", tostring(sessionCount)), 
    sessionPercentage = iff(EventName in (noSessionEvents), "N/A", strcat(sessionPercentage, "%")), 
    userCount, 
    userPercentage = strcat(userPercentage, "%")
```

2) Success rate by build tool
- Description: For sessions reaching confirmplan.end, attribute build tool and join to result view to compute succeed rate at session and user level. Adapt by changing the time window in raw and restricting to specific tools.
```kusto
raw 
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend buildTool = tostring(Properties["buildtool"]) 
| distinct buildTool, sessionId
| join result on sessionId
| summarize totalSession = dcount(sessionId), succeededSession = dcountif(sessionId, result  == "Succeeded"),
totalUser = dcount(VSCodeMachineId), succeededUser = dcountif(VSCodeMachineId, result  == "Succeeded") by buildTool
| project buildTool, succeededSession, totalSession, ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100 
```

3) Success rate by source/target Java versions
- Description: Groups sessions by source/target versions (from confirmplan.end) and computes success metrics using result. Adapt by filtering specific version paths.
```kusto
raw 
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend sourceVersion = toint(Properties["sourcejavaversion"]), targetVersion = toint(Properties["targetjavaversion"]) 
| distinct sourceVersion, targetVersion, sessionId
| join result on sessionId
| summarize totalSession = dcount(sessionId), succeededSession = dcountif(sessionId, result  == "Succeeded"),
totalUser = dcount(VSCodeMachineId), succeededUser = dcountif(VSCodeMachineId, result  == "Succeeded") by sourceVersion, targetVersion
| project sourceVersion, targetVersion, succeededSession, totalSession, ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100 
```

4) OpenRewrite recipe success ratio
- Description: Parses recipes from openrewrite.end, computes per-recipe success ratio. Adapt to filter particular recipes or sessions.
```kusto
let succeeded = raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
| where Properties["result"] == "succeed"
| distinct sessionId;
raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
| project sessionId, recipes = tostring(Properties["recipes"])
| extend recipeJson = parse_json(recipes)
| mv-expand recipe = recipeJson
| project 
    sessionId,
    recipeId = tostring(recipe.id),
    recipeName = recipe.name,
    recipeDescription = recipe.description,
    recipeTarget = recipe.target,
    recipeDependencies = recipe.dependencyGroups
| join kind=leftouter succeeded on sessionId
| summarize total = dcount(sessionId), succeeded = dcount(sessionId1) by recipeId
| extend succeededRatio = succeeded * 1.0 / total
```

5) Error bucketing for plan creation/confirmation
- Description: Buckets error messages into categories for generateplan/confirmplan phases, unions and renders distribution. Adapt categories as needed.
```kusto
let generatePlanErrors = raw
| where EventName has "vscjava.vscode-java-upgrade/generateplan"
| extend error = tostring(Properties["errormessage"])
| where isnotempty(error)
| extend Message = case(
    error has "Uncommitted changes" or error has " please commit, stash or discard them first" or error has "not a git repository" 
    or error has "Failed to get git status", "Git Validation Issues",
    error has "is only available for GitHub Copilot \"Business\" and \"Enterprise\" plans", "Require Business and Enterprise plans",
    error has "Spring Boot dependency not found" or error has "Invalid Spring Boot version to upgrade", "Invalid Spring Boot Target Version",
    error has "Please provide a path to an existing JDK" or error has "Maven path is required"
    or error has "is not a valid JDK installation path" or error has "Gradle wrapper not found", "Java Runtime Issues (JDK/Maven/Gradle)",
    error has "Unsupported project type. Please choose a valid maven or gradle project", "Unsupported project type",
    "Others"
)
| where isnotempty(Message)
| summarize Count = count(), User = dcount(DevDeviceId) by Message
| order by Count desc;
let confirmErrors = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.failed" or EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend error = tostring(Properties["errormessage"])
| extend Message = case(
    isempty(error), "Plan Created",
    error has "Uncommitted changes" or error has " please commit, stash or discard them first" or error has "not a git repository" 
    or error has "Failed to get git status", "Git Validation Issues",
    error has "Spring Boot dependency not found" or error has "Invalid Spring Boot version to upgrade", "Invalid Spring Boot Target Version",
    error has "Please provide a path to an existing JDK" or error has "Maven path is required" or error has "Invalid Maven path"
    or error has "is not a valid JDK installation path" or error has "Gradle wrapper not found" or error has "There is no JDK information in the upgrade options."
    or error has "Failed to run command: \"mvnw\" or error has "Failed to run command: \"mvn\"", "Java Runtime Issues (JDK/Maven/Gradle)",
    error has "Failed to convert markdown to JSON,", "Failed to transform configuration markdown",
    "Others"
)
| summarize Count = dcount(sessionId), User = dcount(DevDeviceId) by Message
| order by Count desc;
generatePlanErrors
| union confirmErrors
| summarize Count = sum(Count) by Message
| render piechart 
```

6) Funnel conversion ratios across main stages
- Description: Produces a stage funnel (Plan Created → OpenRewrite Succeeded → Build Fix Succeeded → CVE Validation Passed → Consistency Validation Passed → Summarizing ended), computes ratio versus Plan Created. Adapt by toggling “started” stages or using alternative funnel variant.
```kusto
let createPlan = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| summarize dcount(sessionId)
| project Stage = "Plan Created", Sessions = dcount_sessionId, order = 0;
let openrewrite = raw
| where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "succeed"
| summarize dcount(sessionId)
| project Stage = "OpenRewrite Succeeded", Sessions = dcount_sessionId, order = 1;
let buildFix = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"and Properties["result"] == "true"
| summarize dcount(sessionId)
| project Stage = "Build Fix Succeeded", Sessions = dcount_sessionId, order = 2;
let cve = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecves.end"
| distinct sessionId, cves = tostring(Properties["cves"])
| summarize dcountif(sessionId, isempty( cves))
| project Stage = "CVE Validation Passed", Sessions = dcountif_sessionId, order = 3;
let consistency = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end"
| distinct sessionId, behaviorChangesCount = toint(Measures["behaviorchangescount"]), brokenFilesCount = toint(Measures["brokenfilescount"])
| summarize dcountif(sessionId, behaviorChangesCount ==0 and brokenFilesCount  == 0)
| project Stage = "Consistency Validation Passed", Sessions = dcountif_sessionId, order = 4;
let summarize_ended = raw
| where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.end"
| summarize dcount(sessionId)
| project Stage = "Summarizing ended", Sessions = dcount_sessionId, order = 5;
let data = createPlan
| union openrewrite
| union buildFix
| union cve
| union consistency
| union summarize_ended;
let totalSessions = toscalar(
    createPlan
    | summarize max(Sessions)
);
data
| extend Ratio = Sessions * 100.0 / totalSessions
| order by order asc
| project Stage, Sessions, Ratio
```

7) LLM request token distribution by session outcome and overall
- Description: Aggregates tokens/toolCalls per session from llmclient.sendrequest, computes summary stats overall and by result (join to result view). Adapt to analyze by caller or other cohorts.
```kusto
let results = raw
| where EventName == "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend caller = tostring(Properties["caller"])
| extend completionToken = toint(Measures["completiontoken"]),prompToken = toint(Measures["prompttoken"]), tokens = toint(Measures["tokens"]) 
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| join result on sessionId
| summarize 
    sessions = count(),
    average = avg(tokens),
    median = percentile(tokens, 50),
    p75 = percentile(tokens, 75),
    p90 = percentile(tokens, 90),
    p95 = percentile(tokens, 95),
    maximum = max(tokens) by result;
raw
| where EventName has "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend caller = tostring(Properties["caller"])
| extend completionToken = toint(Measures["completiontoken"]),prompToken = toint(Measures["prompttoken"]), tokens = toint(Measures["tokens"]) 
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| summarize 
    sessions = count(),
    average = avg(tokens),
    median = percentile(tokens, 50),
    p75 = percentile(tokens, 75),
    p90 = percentile(tokens, 90),
    p95 = percentile(tokens, 95),
    maximum = max(tokens)| extend result = "Overall"
| project result, sessions, average, median, p75, p90, p95, maximum
| union results
```

8) Copilot Chat usage for Java Upgrade conversations
- Description: Ties Java Upgrade sessions to Copilot Chat panel.request events, counts tool calls and filters to conversations where javaupgrade tool was used. Outputs session-level distribution statistics. Adapt time window and include token joins if needed.
```kusto
let javaUpgradeSessions = raw
| distinct VSCodeSessionId;
database('VSCodeExt').RawEventsVSCodeExt
| where EventName == "github.copilot-chat/panel.request"
| where VSCodeSessionId in (javaUpgradeSessions)
| extend conversationid = tostring(Properties["conversationid"]), requestid = tostring(Properties["requestid"]), tools = tostring(Properties["toolcounts"]) 
| summarize toolCalls = dcount(requestid), isJavaConversation = dcountif(requestid, tools has "javaupgrade") by conversationid
| where isJavaConversation > 0
| summarize 
    sessions = count(),
    average = avg(toolCalls),
    median = percentile(toolCalls, 50),
    p75 = percentile(toolCalls, 75),
    p90 = percentile(toolCalls, 90),
    p95 = percentile(toolCalls, 95),
    maximum = max(toolCalls)
```

9) Validate code behavior consistency pass count
- Description: Counts sessions where behavior/broken file counts are zero at the end stage. Use for a KPI of “consistency validation passed”.
```kusto
raw
| where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end"
| distinct sessionId, behaviorChangesCount = toint(Measures["behaviorchangescount"]), brokenFilesCount = toint(Measures["brokenfilescount"]) 
| summarize dcountif(sessionId, behaviorChangesCount ==0 and brokenFilesCount  == 0)
```

10) GeneratePlan and ConfirmPlan errors (raw listing)
- Description: Lists raw error messages by event and counts. Useful for detailed triage. Adapt by scoping to specific time/version.
```kusto
raw
| where EventName has "vscjava.vscode-java-upgrade/generateplan"
| extend error = tostring(Properties["errormessage"])
| where isnotempty( error)
| summarize Count = count(), User = dcount(DevDeviceId) by error, EventName
| order by Count desc
```

## **Reasoning Notes (only if uncertain)**
- Timezone is not specified; we assume UTC for consistency. If your dashboards expect local time, adjust bin() and between() accordingly.
- Freshness/ingestion delay is unknown; for stable KPIs, prefer excluding the current day via an effective end time gate.
- sessionId (Properties["sessionid"]) represents the Java upgrade flow, while VSCodeSessionId is broader VS Code context; do not mix them when computing funnels.
- DevDeviceId vs. VSCodeMachineId both appear as user/device identifiers; ensure consistency per KPI. Internal cohorting uses DevDeviceId.
- The “Succeeded” definition hinges on buildfix.end Properties["result"] == "true"; if other success signals exist (e.g., post-validate stages), extend the result view carefully.
- Error bucketing lists are heuristic; update message patterns as products evolve.
- Some queries render cards/piecharts; if running outside dashboards, remove render statements or adapt visuals as needed.
- The product reads from VSCodeExt (events) and VSCodeInsights (internal users) databases; ensure appropriate permissions for cross-database joins.

## **Canonical Tables**

### Table name: cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
- Priority: Normal
- What this table represents: High-volume event telemetry (fact/event stream) emitted by VS Code extensions. Each row is a single event with common columns and extension-specific details in dynamic JSON bags (Properties, Measures). Zero rows for a time window typically imply no activity captured for the selected filters.
- Freshness expectations: Near-real-time ingestion is typical for RawEvents, but exact latency is unknown. Be cautious when querying “today” or the most recent hour; consider backfilling or widening the time window to validate counts.
- When to use / When to avoid:
  - Use when analyzing Java Upgrade workflow stages via EventName (e.g., generateplan/confirmplan/openrewrite/buildfix/validate*), including funnels and drop-offs.
  - Use for error taxonomy by parsing Properties["errormessage"] and other Properties payload keys (e.g., output.message, result, recipes, cves).
  - Use to compute LLM token usage (Measures[*token*]) and request volumes for vscjava.vscode-java-upgrade/llmclient.sendrequest.
  - Use to correlate VSCodeSessionId/VSCodeMachineId/DevDeviceId for unique users, sessions, and device-based joins to user attributes.
  - Avoid unbounded scans; always filter by ServerTimestamp and ExtensionName or EventName prefixes. Avoid mixing multiple features without explicit EventName filters.
  - Avoid assuming a native sessionId column; derive it from Properties["sessionid"].
- Similar tables & how to choose:
  - The same RawEventsVSCodeExt table also holds GitHub Copilot Chat events (EventName like "github.copilot-chat/*"). Choose by filtering EventName and/or ExtensionName; do not union other tables unless required.
- Common Filters:
  - Time: ServerTimestamp between your dashboard parameters (e.g., ['_startTime'] .. ['_endTime']).
  - Feature scoping: ExtensionName == "vscjava.vscode-java-upgrade" and EventName prefix/suffix matching for specific steps.
  - Session derivation and exclusion: sessionId = tostring(Properties["sessionid"]); exclude MOCKSESSION.
  - Version gating: parse ExtensionVersion into major/minor; filter major > 0 or minor >= 10; optionally filter ExtensionVersion in ['_versions'].
  - User cohort: join to VSCodeInsights.fact_user_isinternal on DevDeviceId; then filter IsInternal in ['_user_types'] if needed.
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| EventName | string | Logical name of the emitted event (used for stage/workflow filtering). |
| Attributes | dynamic | Additional event attributes (opaque; seldom used here). |
| ClientTimestamp | datetime | Event time on client. May differ from ServerTimestamp. |
| DataHandlingTags | string | Data handling classification tags. |
| ExtensionName | string | VS Code extension emitting the event (e.g., "vscjava.vscode-java-upgrade"). |
| ExtensionVersion | string | Extension version string (parsed into major/minor in queries). |
| GeoCity | string | Client geo city (if available). |
| GeoCountryRegionIso | string | Client country/region ISO code. |
| Measures | dynamic | Numeric metrics (e.g., tokencount, completiontoken, prompttoken, behaviorchangescount). |
| NovaProperties | dynamic | Additional properties (not used in shown queries). |
| Platform | string | OS/platform (e.g., win32, darwin). |
| PlatformVersion | string | Platform version. |
| Properties | dynamic | JSON bag of event fields (sessionid, errormessage, output.message, result, recipes, cves, caller, taskid, buildtool, sourcejavaversion, targetjavaversion, etc.). |
| ServerTimestamp | datetime | Ingestion/processing timestamp used for time filtering. |
| Tags | dynamic | Tag bag if present. |
| VSCodeMachineId | string | Machine identifier for user/device-level aggregation. |
| VSCodeSessionId | string | VS Code session identifier (also used to correlate to Copilot Chat). |
| VSCodeVersion | string | VS Code client version. |
| WorkloadTags | string | Workload classification tags. |
| LanguageServerVersion | string | Language server version (if applicable). |
| SchemaVersion | string | Event schema version. |
| Method | string | Method or action label (seldom used here). |
| Duration | real | Event duration metric (if applicable). |
| SQMMachineId | string | SQM/telemetry machine id (if populated). |
| DevDeviceId | string | Device id used for joining to user attributes (e.g., IsInternal). |
| IsInternal | bool | Internal user flag (may be populated in some data paths). Prefer the join with fact_user_isinternal. |
| ABExpAssignmentContext | string | A/B experiment assignment info. |
| Source | string | Source label of event (if used). |
| SKU | string | SKU information (if populated). |
| Model | string | LLM/model name where applicable (Copilot). |
| RequestId | string | Request id (especially for chat/LLM events). |
| ConversationId | string | Conversation id (chat flows). |
| ResponseType | string | Type of response (Copilot/chat). |
| ToolName | string | Tool identifier (Copilot/chat tool). |
| Outcome | string | Outcome label (success/failure/etc.). |
| IsEntireFile | string | Whether the request covered entire file (if used). |
| ToolCounts | string | Tool usage counts (as string-encoded summary). |
| Isbyok | int | BYOK flag (if present). |
| TimeToFirstToken | int | Latency to first token (ms). |
| TimeToComplete | int | Time to complete (ms). |
| TimeDelayms | int | Additional delay metric (ms). |
| SurvivalRateFourgram | real | Quality metric (if used). |
| TokenCount | real | Total token count for an event (Copilot/chat). |
| PromptTokenCount | real | Prompt tokens count. |
| NumRequests | int | Number of requests in a batch (if applicable). |
| Turn | int | Conversation turn number (chat). |
| ResponseTokenCount | real | Response tokens count. |
| TotalNewDiagnostics | int | Diagnostics metric. |
| Rounds | real | Rounds metric (batched requests). |
| AvgChunkSize | real | Average chunk size metric. |
| Command | string | Command identifier invoked. |
| CopilotTrackingId | string | Copilot tracking id. |
| IntentId | string | Intent id for chat. |
| Participant | string | Participant role (user/assistant/etc.). |
| ToolGroupState | string | State of tool group (chat). |
| DurationMS | long | Duration metric in milliseconds. |

- Column Explain:
  - ServerTimestamp: Primary filter for time windows. Use between (['_startTime'] .. ['_endTime']).
  - ExtensionName: Scope to "vscjava.vscode-java-upgrade" for Java upgrade feature analysis.
  - EventName: Drive funnels and stage counts (e.g., ".../confirmplan.end", ".../openrewrite.*", ".../buildfix.*", ".../validatecves.*", ".../validatecodebehaviorconsistency.*", ".../llmclient.sendrequest").
  - Properties (dynamic):
    - sessionid: Derive sessionId = tostring(Properties["sessionid"]) for session-level analysis.
    - errormessage, output.message: Build error taxonomies and failure detection.
    - result: Detect success/failure (e.g., "true"/"failed"/"succeed") for openrewrite/buildfix.
    - recipes, cves: Expand/parse to compute recipe success and CVE outcomes.
    - caller, taskid, buildtool, sourcejavaversion, targetjavaversion: Segment success rates and flows.
  - Measures (dynamic):
    - tokencount, completiontoken, prompttoken: Token usage per request; aggregate percentiles by caller or session.
    - behaviorchangescount, brokenfilescount: Used to classify "consistency validation passed".
  - DevDeviceId, VSCodeMachineId, VSCodeSessionId: Distinct counts for user/session metrics; DevDeviceId is the join key to internal/external user mapping.

---

### Table name: cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal
- Priority: Normal
- What this table represents: User/device attribute mapping used to classify internal vs external users. Acts like a dimension/snapshot keyed by DevDeviceId with a boolean IsInternal flag. Zero rows after a join typically indicate no matching device id (e.g., new or unknown device).
- Freshness expectations: Exact refresh cadence is unknown. Treat it as a slowly-changing dimension; if you see unexpected drops after a join, validate time windows and the join key population in your source events.
- When to use / When to avoid:
  - Use to filter cohorts by internal/external after joining from RawEventsVSCodeExt on DevDeviceId.
  - Use when dashboards offer a ['_user_types'] filter to include or exclude internal users.
  - Avoid scanning this table standalone; it is primarily for enrichment via joins.
  - Avoid joining on fields other than DevDeviceId unless you’ve validated alternative keys exist.
- Similar tables & how to choose: None identified in the provided queries. If multiple user-attribute tables exist, prefer the one keyed by DevDeviceId used by VS Code events.
- Common Filters:
  - Join: ... | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
  - User type filtering post-join: where isempty(['_user_types']) or IsInternal in (['_user_types'])
- Table columns:
  - Full schema could not be retrieved from this environment. Known columns from usage:
  
| Column | Type | Description or meaning |
|---|---|---|
| DevDeviceId | string | Device identifier used as the join key from RawEventsVSCodeExt. |
| IsInternal | bool | Flag indicating whether the device/user is internal. |

- Column Explain:
  - DevDeviceId: Join key from RawEventsVSCodeExt; ensures user-level enrichment.
  - IsInternal: Used to segment metrics (e.g., treat early adopters as internal; filter via dashboard parameter ['_user_types']).
