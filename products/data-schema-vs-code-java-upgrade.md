# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

VS Code Java Upgrade is a Visual Studio Code extension (ExtensionName: "vscjava.vscode-java-upgrade") that guides developers through upgrading Java dependencies and project configurations. The telemetry-driven analytics in this schema define how to scope product events, derive session identity, compute funnel stages and outcomes (Succeeded, BuildFixFailed, OpenResultFailed, Incomplete), and analyze token usage, errors, and dependency updates across the upgrade flow.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product: VS Code Java Upgrade
- Product Nick Names:
  - [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product (e.g., "Java Upgrade", "VSCode Java Upgrade") to help PMAgent recognize the product in conversations.
- Kusto Cluster:
  - https://ddtelvscode.kusto.windows.net/
- Kusto Database:
  - VSCodeExt (primary)
  - Note: Also reads from database VSCodeInsights for user internal/external classification.
- Access Control:
  - [TODO] Data Engineer: If this product’s data has high confidentiality concerns, specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

1. Overview
- Product: VS Code Java Upgrade. Kusto dashboard JSON defining pages, tiles, parameters, base queries (raw, result, updatedependencies, compileFailedSessions), and multiple analytical queries for VS Code Java Upgrade.
- Cluster: https://ddtelvscode.kusto.windows.net/
- Database: VSCodeExt (primary). Also reads from database VSCodeInsights for user internal/external classification.

2. Conventions & Assumptions
- Time semantics
  - Observed timestamp columns:
    - ServerTimestamp (canonical). Used in base/view filters for time windowing.
    - startTime is derived in the result view as an alias for ServerTimestamp at session start.
  - Canonical Time Column: ServerTimestamp
    - Alias pattern: project-rename StartTime=ServerTimestamp when needed.
  - Windows seen: Parameterized ['_startTime'] .. ['_endTime'] on ServerTimestamp.
  - Common bin(): Not explicitly used in examples; recommend bin(ServerTimestamp, 1d) for daily cuts.
  - Timezone: Not specified. Assume UTC. Be cautious with “today”—prefer complete prior day/week windows for accurate aggregates.

- Freshness & Completeness Gates
  - Ingestion cadence: Unknown.
  - Current-day completeness: Unknown. Treat current day as potentially incomplete.
  - Recommended gate:
    - Use an effective end time as the last fully ingested day.
    - Multi-slice gate pattern (example below) to ensure N key slices (e.g., regions/shards; here not sharded) are present before counting.
  - Prefer using the previous full day/week for trend charts.

- Joins & Alignment
  - Frequent keys:
    - DevDeviceId (used to join to VSCodeInsights.fact_user_isinternal).
    - sessionId (upgrade session-level id from Properties["sessionid"]).
    - VSCodeMachineId and VSCodeSessionId appear in counting; VSCodeSessionId is broader VS Code session, sessionId is upgrade tool flow.
  - Typical join kinds:
    - inner: to attach IsInternal by DevDeviceId in the raw view.
    - leftouter: to attach optional outcomes/stages (e.g., buildFixResult, OpenRewrite results).
    - leftantisemi: to identify cohorts excluding a failure reason.
  - Post-join hygiene:
    - After multiple joins, duplicate columns appear (e.g., sessionId1, sessionId2). Normalize with project-rename and project-away.
    - Use coalesce() to select the first non-empty of alternative columns.

- Filters & Idioms
  - Scope to the extension: ExtensionName == "vscjava.vscode-java-upgrade".
  - Exclude mock data: tostring(Properties["sessionid"]) != "MOCKSESSION".
  - Version gating: majorVersion = toint(split(ExtensionVersion, ".", 0)[0]); minorVersion = toint(split(ExtensionVersion, ".", 1)[0]); keep where majorVersion > 0 or minorVersion >= 10.
  - User cohort: join to IsInternal and optionally filter IsInternal in ['_user_types'] (treat pre-code-complete as internal).
  - Event filters: EventName == "<stage>" or EventName has "<prefix>" are common.
  - Error filters: error messages often sourced from Properties["errormessage"] or Properties["output.message"].
  - Empty checks: isnotempty(sessionId) or count missing sessions by where isempty(sessionId) or sessionId == "".

- Cross-cluster/DB & Sharding
  - Cross-database on the same cluster:
    - Read facts from database("VSCodeExt").RawEventsVSCodeExt.
    - Read user classification from database("VSCodeInsights").fact_user_isinternal.
  - Use explicit database() qualification to avoid name collisions.
  - Sharding/regions: Not observed. If later introduced with same schema, use union pattern and normalize keys/time before summarize.

- Table classes
  - Fact (events): VSCodeExt.RawEventsVSCodeExt
    - High-volume, event-level telemetry holding EventName, Measures, Properties, ServerTimestamp, VSCodeMachineId, VSCodeSessionId, DevDeviceId, ExtensionVersion.
  - Dimension/Snapshot: VSCodeInsights.fact_user_isinternal
    - User internal/external attribute keyed by DevDeviceId. Treat as latest snapshot unless otherwise documented.
  - No pre-aggregated KPI tables observed; aggregations are done on the fly with summarize.

3. Entity & Counting Rules (Core Definitions)
- Entity model
  - Device: DevDeviceId (join to IsInternal).
  - Machine: VSCodeMachineId (used in funnels).
  - VS Code Session: VSCodeSessionId (IDE session).
  - Upgrade Flow Session: sessionId = tostring(Properties["sessionid"]) (per-upgrade flow; primary grain for funnels/outcomes).
  - Version: ExtensionVersion; also derived majorVersion/minorVersion.

- Counting Do/Don’t
  - Do:
    - Count sessions by dcount(sessionId) when measuring funnel progression or outcomes.
    - Count unique users by dcount(VSCodeMachineId) when user-level reach is needed.
    - Guard against missing sessionId in early “generateplan” stages; treat these as special (noSessionEvents).
    - Use leftouter joins to attach optional results; classify “Incomplete” when no downstream completion exists.
  - Don’t:
    - Mix user and session counts in the same denominator without clear intent.
    - Include MOCKSESSION or empty sessionId in stage metrics unless explicitly assessing data quality.

- Business definitions (from views)
  - result classification (view: result)
    - For each sessionId that has confirmplan.end:
      - BuildFix result: if buildfix.end Properties["result"] == "true" then Succeeded else BuildFixFailed.
      - Otherwise, if openrewrite.end Properties["result"] == "failed" then OpenResultFailed.
      - Otherwise Incomplete.
    - Note: “Succeeded” here means buildfix.end result true; openrewrite success alone isn’t final success.

4. Views (Reusable Layers)
- raw
  - Purpose: Base events dataset with product scoping, time windowing, version gating, internal-user tagging, and parameterized filters.
  - Inputs: VSCodeExt.RawEventsVSCodeExt; VSCodeInsights.fact_user_isinternal (join on DevDeviceId).
  - Output: Events with derived major/minor version, sessionId, and IsInternal filter applied.
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

- result
  - Purpose: Session-level outcome classification (Succeeded, BuildFixFailed, OpenResultFailed, Incomplete).
  - Inputs: raw view.
  - Outputs: One row per sessionId with result and version info.
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

- updatedependencies
  - Purpose: Extract per-session dependency upgrade pairs from planstarted events.
  - Inputs: raw view.
  - Outputs: One row per dependency with source/target versions and session.
  - Query:
    ```kusto
    raw
    | where EventName == "vscjava.vscode-java-upgrade/javaupgrade.planstarted"
    | extend dependencies = parse_json(tostring(Properties["updateddependencies"])), session = tostring(Properties["sessionid"])
    | project dependencies, session
    | mv-expand dependencies
    | project dependency = tostring(dependencies["source"]["id"]), source=tostring(dependencies["source"]["version"]), target=tostring(dependencies["target"]["version"]), session;
    ```

- compileFailedSessions
  - Purpose: Identify sessions failing at task 1 while excluding OpenRewrite failures.
  - Inputs: raw view.
  - Outputs: Cohort (sessionId) likely needing compile-first troubleshooting.
  - Query:
    ```kusto
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

5. Query Building Blocks (Copy-paste snippets, contains snippets and description)
- Time window template
  - Use this to scope to a safe, complete window with UTC defaults and an effective end time.
  - ```kusto
    // Parameters (update in dashboard or let bindings)
    let _startTime: datetime = datetime(2025-01-01);
    let _endTime_raw: datetime = now(); // possibly incomplete
    // Effective end time: fallback to midnight UTC of previous day
    let _effectiveEndTime: datetime = startofday(now() - 1d);
    let _endTime: datetime = iff(_endTime_raw > _effectiveEndTime, _effectiveEndTime, _endTime_raw);

    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where ServerTimestamp between (_startTime .. _endTime)
    ```

- Join templates
  - Attach internal/external user classification (inner join on DevDeviceId).
  - ```kusto
    // Pre-align keys
    let base = database("VSCodeExt").RawEventsVSCodeExt
      | where ExtensionName == "vscjava.vscode-java-upgrade";
    base
    | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
    | project-away DevDeviceId1
    ```
  - Session-level outcome attach (leftouter on sessionId).
  - ```kusto
    // Build result by session
    let buildFix = raw
    | where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
    | extend buildResult = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")
    | project sessionId, buildResult;
    raw
    | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
    | project sessionId
    | join kind=leftouter buildFix on sessionId
    | extend FinalResult = coalesce(buildResult, "Incomplete")
    ```
  - Exclusion cohort via leftantisemi (denylist).
  - ```kusto
    let deny = raw | where Properties["errormessage"] has "Failed to run OpenRewrite" | distinct sessionId;
    let cohort = raw | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end" | distinct sessionId;
    cohort
    | join kind=leftantisemi deny on sessionId
    ```

- De-dup pattern
  - Latest record per key (use when picking latest event/state per session).
  - ```kusto
    // If events exist across time and you need latest per session
    raw
    | summarize arg_max(ServerTimestamp, *) by sessionId
    ```
  - Unique counts and cohorts:
  - ```kusto
    raw | summarize sessions=dcount(sessionId), users=dcount(VSCodeMachineId)
    ```

- Important filters
  - Product scope and quality:
  - ```kusto
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where tostring(Properties["sessionid"]) != "MOCKSESSION"
    | extend sessionId = tostring(Properties["sessionid"])
    ```
  - Version gating:
  - ```kusto
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion > 0 or minorVersion >= 10
    ```
  - Enforce non-empty session in mid/late stages:
  - ```kusto
    | where isnotempty(sessionId)
    ```

- Important Definitions
  - Upgrade result (session-level):
    - Succeeded: buildfix.end with Properties["result"] == "true".
    - BuildFixFailed: buildfix.end with Properties["result"] != "true".
    - OpenResultFailed: openrewrite.end with Properties["result"] == "failed".
    - Incomplete: no qualifying downstream result after confirmplan.end.

- ID parsing/derivation
  - Parse hierarchical task id "X.Y" into numeric parts:
  - ```kusto
    | extend taskId = tostring(Properties["taskid"])
    | extend task = toint(split(taskId, ".")[0]), subTask = toint(split(taskId, ".")[1])
    ```
  - Extract and expand JSON arrays from Properties:
  - ```kusto
    | extend deps = parse_json(tostring(Properties["updateddependencies"]))
    | mv-expand dep = deps
    | project sourceId = tostring(dep["source"]["id"]),
              sourceVer = tostring(dep["source"]["version"]),
              targetVer = tostring(dep["target"]["version"])
    ```
  - Parse OpenRewrite recipes:
  - ```kusto
    | project recipes = tostring(Properties["recipes"])
    | extend recipeJson = parse_json(recipes)
    | mv-expand recipe = recipeJson
    | project recipeId = tostring(recipe.id), recipeName = recipe.name
    ```

- Sharded union (template)
  - Not observed in current sources. If regional shards appear with same schema:
  - ```kusto
    union withsource=TableName
      cluster("...").database("VSCodeExt").RawEventsVSCodeExt // region A
      , cluster("...").database("VSCodeExtEU").RawEventsVSCodeExt // region B
    | extend ServerTimestamp = todatetime(ServerTimestamp) // normalize time
    | extend sessionId = tostring(Properties["sessionid"]) // normalize key
    | summarize sessions=dcount(sessionId) by bin(ServerTimestamp, 1d)
    ```

6. Example Queries (with explanations)
- Funnel coverage across stages (ordered)
  - Description: Computes session and user reach per stage across key EventNames, normalizes ordering, and handles stages without sessionId (noSessionEvents). Adapt by changing stage list or time window via the raw view parameters.
  - ```kusto
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

- Success rate by build tool
  - Description: For sessions that reached confirmplan.end, extend build tool and join outcomes from result view. Calculates session-level success counts and rates by buildTool. Adapt by changing grouping or adding user-level rates.
  - ```kusto
    raw 
    | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
    | extend buildTool = tostring(Properties["buildtool"])
    | distinct buildTool, sessionId
    | join result on sessionId
    | summarize totalSession = dcount(sessionId), succeededSession = dcountif(sessionId, result  == "Succeeded"),
      totalUser = dcount(VSCodeMachineId), succeededUser = dcountif(VSCodeMachineId, result  == "Succeeded") by buildTool
    | project buildTool, succeededSession, totalSession, ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100 
    ```

- Success rate by source/target Java versions
  - Description: Buckets sessions by source/target Java versions from confirmplan.end and computes success rates via result view. Adapt by changing version parsing or adding minor version grouping.
  - ```kusto
    raw 
    | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
    | extend sourceVersion = toint(Properties["sourcejavaversion"]), targetVersion = toint(Properties["targetjavaversion"])
    | distinct sourceVersion, targetVersion, sessionId
    | join result on sessionId
    | summarize totalSession = dcount(sessionId), succeededSession = dcountif(sessionId, result  == "Succeeded"),
      totalUser = dcount(VSCodeMachineId), succeededUser = dcountif(VSCodeMachineId, result  == "Succeeded") by sourceVersion, targetVersion
    | project sourceVersion, targetVersion, succeededSession, totalSession, ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100 
    ```

- OpenRewrite stage completion status (pie)
  - Description: Tracks session-level progression from prepare→start→end and outcome for OpenRewrite. Use to visualize drop-offs and failures. Adapt by swapping EventName for other stages.
  - ```kusto
    let prepare = raw
    | where EventName == "vscjava.vscode-java-upgrade/openrewrite.prepare"
    | distinct sessionId;
    let start = raw
    | where EventName == "vscjava.vscode-java-upgrade/openrewrite.start"
    | distinct sessionId;
    let end = raw
    | where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
    | distinct sessionId, result = tostring(Properties["result"]);
    prepare
    | join kind=leftouter start on sessionId
    | join kind=leftouter end on sessionId
    | extend result = case(isempty(sessionId1), "Not Start", isempty(sessionId2), "Not Complete/Error", result)
    | summarize dcount(sessionId) by result
    | render piechart
    ```

- Error taxonomy across generateplan/confirmplan
  - Description: Categorizes error messages for generateplan* and confirmplan.* stages into friendly buckets and visualizes distribution. Useful for top failure reasons. Adapt by editing the case() conditions.
  - ```kusto
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
        or error has "Failed to run command: \"mvnw\"" or error has "Failed to run command: \"mvn\"", "Java Runtime Issues (JDK/Maven/Gradle)",
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

- End-to-end stage funnel with ratios
  - Description: Builds a concise funnel from plan creation to summarization, computing per-stage Sessions and Ratio against plan-confirmed baseline. Adapt by toggling which stages are “started” vs “succeeded”.
  - ```kusto
    let createPlan = raw
    | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
    | summarize dcount(sessionId)
    | project Stage = "Plan Confirmed/Created", Sessions = dcount_sessionId, order = 0;
    let openrewrite = raw
    | where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "succeed"
    | summarize dcount(sessionId)
    | project Stage = "OpenRewrite Succeeded", Sessions = dcount_sessionId, order = 2;
    let buildFix_started = raw
    | where EventName == "vscjava.vscode-java-upgrade/buildfix.start"
    | summarize dcount(sessionId)
    | project Stage = "Build Fix Started", Sessions = dcount_sessionId, order = 3;
    let cve_started = raw
    | where EventName == "vscjava.vscode-java-upgrade/validatecves.start"
    | distinct sessionId, cves = tostring(Properties["cves"])
    | summarize dcount(sessionId)
    | project Stage = "CVE Validation Started/Build project Succeeded", Sessions = dcount_sessionId, order = 5;
    let consistency_started = raw
    | where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start"
    | summarize dcount(sessionId)
    | project Stage = "Consistency Validation Started", Sessions = dcount_sessionId, order = 7;
    let summarize_started = raw
    | where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.start"
    | summarize dcount(sessionId)
    | project Stage = "Summarizing started", Sessions = dcount_sessionId, order = 9;
    let summarize_ended = raw
    | where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.end"
    | summarize dcount(sessionId)
    | project Stage = "Summarizing ended", Sessions = dcount_sessionId, order = 10;
    let data = createPlan
    | union openrewrite
    | union buildFix_started
    | union cve_started
    | union consistency_started
    | union summarize_started
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

- LLM token usage by session outcome and overall
  - Description: Summarizes tokens/toolCalls per session for llmclient.sendrequest, then joins to result to compare token usage by outcome. Also computes overall distribution. Adapt to add cost mapping via token price multipliers.
  - ```kusto
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

- Dependency upgrade extraction
  - Description: Expands the dependency upgrade plan per session to analyze which libraries/versions are updated. Adapt by grouping by dependency and computing success rate by joining to result.
  - ```kusto
    raw
    | where EventName == "vscjava.vscode-java-upgrade/javaupgrade.planstarted"
    | extend dependencies = parse_json(tostring(Properties["updateddependencies"])), session = tostring(Properties["sessionid"])
    | project dependencies, session
    | mv-expand dependencies
    | project dependency = tostring(dependencies["source"]["id"]),
              source=tostring(dependencies["source"]["version"]),
              target=tostring(dependencies["target"]["version"]),
              session
    ```

- CompileFailedSessions cohort excluding OpenRewrite failures
  - Description: Forms a cohort of sessions whose max task is 1 (and has a subTask), excluding those failing due to OpenRewrite. Use for targeted debuggability. Adapt by changing the max task threshold.
  - ```kusto
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
    | join kind=leftantisemi openrewriteFailed on sessionId
    ```

7. Reasoning Notes (only if uncertain)
- Timezone and latency are not specified; we assume UTC and that current day may be incomplete. We recommend gating to the previous full day to avoid ingestion skew.
- VSCodeInsights.fact_user_isinternal appears as a snapshot/dimension keyed by DevDeviceId; we assume its values are “current” for the analysis window, though it could be slowly changing. If temporal user-type is required, a time-aware join would be needed (not shown).
- sessionId is derived from Properties["sessionid"]. Early “generateplan.*” events may lack sessionId; we treat them separately (noSessionEvents) and avoid dividing by session counts for those stages.
- “Succeeded” is defined strictly by buildfix.end Properties["result"] == "true”. If buildfix is not attempted but OpenRewrite succeeds, classification remains “Incomplete” by design. Adjust if product definition changes.
- Counts of “users” sometimes use VSCodeMachineId and sometimes DevDeviceId. We assume VSCodeMachineId is the correct grouping for “user reach” in this product. If uniqueness across reinstalls is desired, validate key choice.
- The extension version gating rule (major > 0 or minor >= 10) is domain-specific. We carry it forward as a default filter; remove/adjust for version-agnostic analysis.
- Error taxonomy uses case() with message text. These categories are heuristics and may need updates as messages evolve or localize.
- No sharded/regional sources are present in examples. If future shards are added, adopt a union and normalize keys/time prior to summarize.

8. Canonical Tables

Below are the canonical tables used by VS Code Java Upgrade analytics, ordered by priority. All guidance is inferred from the provided queries and views (raw, result, updatedependencies, compileFailedSessions) and the database schemas.

---

### Table name: VSCodeExt.RawEventsVSCodeExt (cluster: https://ddtelvscode.kusto.windows.net/)
- Priority: Normal
- What this table represents:
  - Event fact table with one row per telemetry event raised by VS Code extensions.
  - Contains event-level attributes (EventName, Properties, Measures) and identities (VSCodeMachineId, VSCodeSessionId, DevDeviceId).
  - Zero rows for a filter window imply no activity, not deletion.
- Freshness expectations:
  - Not specified; treat ingestion delay and timezone as unknown. Be cautious when querying current-day data—prefer a wider window and verify late arrivals.
- When to use:
  - Analyze VS Code Java Upgrade extension usage and funnel progression across stages (generateplan, confirmplan, openrewrite, buildfix, validatecves, validatecodebehaviorconsistency, summarizeupgrade).
  - Calculate per-session success/failure states by deriving “sessionId” from Properties["sessionid"] and by inspecting Properties/Measures fields.
  - Error taxonomy and top errors by stage using Properties["errormessage"] and output messages.
  - LLM usage and token metrics using Measures fields (e.g., tokencount, prompttoken).
  - Identify user and session deduplicated counts across events, versions, and stages.
- When to avoid:
  - Scanning without a ServerTimestamp time filter—high data volume.
  - Omitting ExtensionName == "vscjava.vscode-java-upgrade" when doing Java Upgrade analysis—will mix unrelated events.
  - Relying on VSCodeSessionId when the logic requires the upgrade pipeline session (use Properties["sessionid"] as sessionId).
  - Using dynamic fields (Properties/Measures) without casting to appropriate types; parsing errors will skew results.
- Similar tables & how to choose:
  - No alternatives documented in the input. Use curated views "raw" and "result" for reusable logic (filters, joins, and session/result derivation).
- Common Filters:
  - Time: ServerTimestamp between ['_startTime'] .. ['_endTime'].
  - Extension: ExtensionName == "vscjava.vscode-java-upgrade".
  - Version: major/minor derived from ExtensionVersion; often majorVersion > 0 or minorVersion >= 10, and optionally restrict to a versions list ['_versions'].
  - User type: join to VSCodeInsights.fact_user_isinternal via DevDeviceId; filter by IsInternal (parameter ['_user_types']).
  - Stage: EventName exact matches or has-prefix for stage families (e.g., ".../confirmplan.*", ".../openrewrite.*").
  - Session: sessionId = tostring(Properties["sessionid"]).
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| EventName | string | Logical name of the event; used to segment upgrade stages (e.g., vscjava.vscode-java-upgrade/confirmplan.end). |
| Attributes | dynamic | Additional attributes; rarely used in provided queries. |
| ClientTimestamp | datetime | Client-side timestamp when the event occurred. |
| DataHandlingTags | string | Data handling classification; not used in queries shown. |
| ExtensionName | string | VS Code extension identifier (e.g., vscjava.vscode-java-upgrade). Primary filter for this product. |
| ExtensionVersion | string | Extension version; split into major/minor for version gating and analysis. |
| GeoCity | string | City geo hint; not used in provided queries. |
| GeoCountryRegionIso | string | Country/region ISO code; not used in provided queries. |
| Measures | dynamic | Numeric metrics bag; token counts and numeric KPIs read from here. |
| NovaProperties | dynamic | Additional properties; not used in provided queries. |
| Platform | string | OS/platform; not used in provided queries. |
| PlatformVersion | string | OS/platform version; not used in provided queries. |
| Properties | dynamic | String/bag properties; source of sessionid, errormessage, caller, taskid, etc. |
| ServerTimestamp | datetime | Ingestion/server timestamp; primary time filter. |
| Tags | dynamic | Tag bag; not used in provided queries. |
| VSCodeMachineId | string | Pseudonymous machine/user identity; used for user-level deduplication. |
| VSCodeSessionId | string | VS Code session id; different from Java Upgrade pipeline session. |
| VSCodeVersion | string | VS Code app version; not used in provided queries. |
| WorkloadTags | string | Workload tags; not used in provided queries. |
| LanguageServerVersion | string | Language server version; not used in provided queries. |
| SchemaVersion | string | Event schema version; not used in provided queries. |
| Method | string | Method or action; not used in provided queries. |
| Duration | real | Event duration; not used directly in shown queries. |
| SQMMachineId | string | Alternate machine id; not used in provided queries. |
| DevDeviceId | string | Device/user id used to join to user metadata (IsInternal). |
| IsInternal | bool | Whether event is internal; can be present on this table; also enforced via external join. |
| ABExpAssignmentContext | string | A/B experiment context; not used in provided queries. |
| Source | string | Source identifier; not used in provided queries. |
| SKU | string | SKU string; not used in provided queries. |
| Model | string | Model identifier (LLM or other); informs LLM-related events. |
| RequestId | string | Request id; useful for request/response correlation. |
| ConversationId | string | Conversation id (chat flows); used in Copilot chat correlation queries. |
| ResponseType | string | Response type; not used in provided queries. |
| ToolName | string | Tool name invoked within chat/LLM operations. |
| Outcome | string | Operation outcome; not used directly in shown queries. |
| IsEntireFile | string | Indicates file scope; not used in provided queries. |
| ToolCounts | string | Serialized tool counts; used to detect “javaupgrade” tool in chat requests. |
| Isbyok | int | BYOK flag (int); not used in provided queries. |
| TimeToFirstToken | int | LLM latency metric; not used directly in shown queries. |
| TimeToComplete | int | LLM completion time; not used directly in shown queries. |
| TimeDelayms | int | Delay metric in ms; not used directly in shown queries. |
| SurvivalRateFourgram | real | Text metric; not used directly in shown queries. |
| TokenCount | real | Total tokens; used in token cost/usage analysis (sometimes also via Measures). |
| PromptTokenCount | real | Prompt tokens; used in token cost/usage analysis (sometimes via Measures). |
| NumRequests | int | Number of requests; not directly used in shown queries. |
| Turn | int | Conversation turn index; not used in provided queries. |
| ResponseTokenCount | real | Response tokens; used in LLM usage analysis. |
| TotalNewDiagnostics | int | Diagnostics count; not used in provided queries. |
| Rounds | real | Conversation or iteration rounds; not used in provided queries. |
| AvgChunkSize | real | Average chunk size; not used in provided queries. |
| Command | string | Command name; not used in provided queries. |
| CopilotTrackingId | string | Tracking id for Copilot; not used in provided queries. |
| IntentId | string | Intent identifier; not used in provided queries. |
| Participant | string | Participant role; not used in provided queries. |
| ToolGroupState | string | Tool group state; not used in provided queries. |
| DurationMS | long | Duration in ms; alternative to Duration. |
- Column Explain:
  - ServerTimestamp: Always add time filters to constrain scan size.
  - ExtensionName: Mandatory filter to keep analysis scoped to Java Upgrade.
  - ExtensionVersion: Split into major/minor to gate versions (e.g., minor >= 10).
  - Properties (dynamic): Source of key fields used across queries:
    - Properties["sessionid"] -> sessionId (upgrade-session identity).
    - Properties["errormessage"] for error taxonomies.
    - Properties["taskid"] to parse task/subtask.
    - Properties["caller"], ["recipes"], ["updateddependencies"], etc.
  - Measures (dynamic): Numeric metrics used for token counts and validation metrics:
    - Measures["tokencount"], ["prompttoken"], ["completiontoken"], ["behaviorchangescount"], ["brokenfilescount"].
  - VSCodeMachineId: Use for user-level dedup (dcount) and success rates by user.
  - DevDeviceId: Join key to VSCodeInsights.fact_user_isinternal.
  - EventName: Primary stage segmentation and funnel logic (start/prepare/end).

---

### Table name: VSCodeInsights.fact_user_isinternal (cluster: https://ddtelvscode.kusto.windows.net/)
- Priority: Normal
- What this table represents:
  - Small dimension table mapping DevDeviceId to an internal-user flag.
  - Zero rows for a join key imply the user’s internal status is unknown.
- Freshness expectations:
  - Not specified; treat as unknown. If used for slicing by internal/external, consider late updates impacting recent windows.
- When to use:
  - Filter or pivot metrics by user type (internal vs external).
  - Join with RawEventsVSCodeExt on DevDeviceId to annotate events with IsInternal.
- When to avoid:
  - Using without joining on DevDeviceId; other ids (VSCodeMachineId) are not keyed here.
  - Assuming IsInternal is boolean in all contexts; schema may expose numeric types—coerce as needed.
- Similar tables & how to choose:
  - No alternatives documented in the input.
- Common Filters:
  - Typically used via an inner join; downstream filters like IsInternal in ['_user_types'] are applied post-join.
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| DevDeviceId | string | Join key to RawEventsVSCodeExt.DevDeviceId. |
| IsInternal | long | Internal user flag (0/1). Cast to bool or compare explicitly when filtering. |
- Column Explain:
  - DevDeviceId: Use for deterministic joins with RawEventsVSCodeExt.
  - IsInternal: Used to segment metrics (e.g., where IsInternal in ['_user_types']). If stored as long, map 1->true, 0->false.

---

Guidance and patterns observed from queries and views:
- Session handling:
  - The upgrade pipeline session is not VSCodeSessionId; it is derived from Properties["sessionid"] as sessionId in the raw view. Use this for stage funnels and per-session results.
- Version gating:
  - majorVersion/minorVersion derived from ExtensionVersion; typical filter: majorVersion > 0 or minorVersion >= 10; optional multi-select filter ['_versions'].
- User type:
  - Join with VSCodeInsights.fact_user_isinternal on DevDeviceId. Apply IsInternal filters via a parameter ['_user_types'] or treat all pre-GA users as internal if applicable.
- Stage modeling:
  - Identify events by EventName suffixes: generateplan.*, confirmplan.*, openrewrite.*, buildfix.*, validatecves.*, validatecodebehaviorconsistency.*, summarizeupgrade.*.
  - Classify results from openrewrite and buildfix using Properties["result"] and from validation stages using Measures/Properties fields.
- LLM usage:
  - Requests: EventName has "llmclient.sendrequest"; derive caller, tokens from Measures (completiontoken, prompttoken, tokens), aggregate per session and caller.
  - Copilot chat correlation: Use RawEventsVSCodeExt for panel.request/response.success, correlating by VSCodeSessionId and conversation/request ids; filter ToolCounts to conversations using "javaupgrade".
- Error taxonomy:
  - Parse Properties["errormessage"] and bucket with a case() into categories (Git Validation Issues, Business/Enterprise plan requirement, Invalid Spring Boot Target Version, Java Runtime Issues, Unsupported project type, Failed to transform configuration markdown, Others).
- Performance and safety defaults:
  - Always filter by ServerTimestamp and ExtensionName.
  - Start with shorter time windows and top N when exploring token distributions or error lists; scale up after validating results.
  - Cast from dynamic safely: toint(), tostring(), parse_json(), mv-expand as needed, and guard with isnotempty()/isempty().