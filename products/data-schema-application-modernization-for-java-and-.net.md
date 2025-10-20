# Application Modernization for Java and .NET - Product and Data Overview Template

## 1. Product Overview

The Application Modernization for Java and .NET product provides top-level metrics built from aggregated telemetry. Aggregations are derived from raw telemetry via pre-defined Kusto functions and daily rolling windows. This schema enables PMAgent to understand cohorting by UserSource, multi-stage funnels (assess, assessreport, buildfix, migrationplan, adoption, execute), and consistent time handling anchored to completed days.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
Application Modernization for Java and .NET
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
https://appmod.westus2.kusto.windows.net/
- **Kusto Database**:
Consolidation
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Application Modernization for Java and .NET - Kusto Query Playbook

## Overview
- Product summary: The dashboard of Application Modernization is the top level metrics for the product built on aggregated telemetries. The aggregated telemetries comes from raw telemetries by pre-defined Kusto functions.
- Main cluster: https://appmod.westus2.kusto.windows.net/
- Main database: Consolidation
- Note: Queries also reference alternate sources on https://ama4j.westus2.kusto.windows.net/ (databases consolidation and bi) for specific helper computations.

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - Date: the primary time column used for filtering and joins.
  - DataIngestTimestamp: used only in arg_max() to select the latest aggregated value per day.
- Canonical Time Column: Date
  - Alignment pattern:
    - Standardize to a single alias when mixing sources with different cases:
      - project-rename Time = Date
    - If sources use different casings for cohort (“UserSource” vs “user_source”), normalize early:
      - project-rename UserSource = user_source
- Typical windows and resolution:
  - Rolling 28 days: Date >= startofday(ago(28d))
  - Some percentile tiles use 29-day filters (e.g., startofday(ago(29d)))
  - Daily granularity via startofday(Date) in summarization
- Timezone:
  - Not specified; assume UTC. Be cautious with “today” until ingestion freshness is confirmed.

### Freshness & Completeness Gates
- Ingestion cadence is not provided. Several helper queries explicitly set an end anchor at startofday(now()) to avoid partial current-day data.
- Recommended effective end-time strategy:
  - Use end = startofday(now()) and compute windows relative to that end.
  - Prefer last fully completed day or previous complete week for reporting windows where completeness is critical.
- Multi-slice completeness gate (recommended pattern when unknown):
  - Identify latest day where ≥N sentinel cohorts (e.g., user_source slices) have non-empty data.
  - Select that day as effective end and compute rolling windows backward from it.

### Joins & Alignment
- Frequent keys:
  - Date, UserSource (sometimes lowercase user_source)
- Typical join kinds:
  - inner (to ensure both slices exist)
- Post-join hygiene:
  - Normalize column case first (project-rename).
  - Drop duplicate columns after join (project-away Count1, etc.).
  - Use coalesce() when reconciling differing cohort column names.

### Filters & Idioms
- Common predicates:
  - isnotempty(UserSource) or isnotempty(user_source) used as a default cohort gate.
  - Date >= startofday(ago(28d)) used widely for rolling windows.
- Cohort case normalization:
  - project-rename UserSource = user_source
- Allowlist/Denylist cohorts (recommended placeholders):
  - Build allowed cohorts first, then inner join to facts.
  - Maintain placeholder lists for internal/test exclusions (e.g., <TestUserSourceList>).

### Cross-cluster/DB & Sharding
- Qualification:
  - Use cluster('https://...').database('db') to target alternate sources.
- Sharded union pattern (same-schema across databases):
  - union → normalize keys/time → summarize
  - Always align Date to startofday and normalize UserSource casing before aggregates.
- Additional sources used by investigation funnels (internal dashboards):
  - ddtelvscode.kusto.windows.net/VSCodeExt (RawEventsVSCodeExt) and /VsCodeInsights (fact_user_isinternal)
  - ddtelai.kusto.windows.net/Copilot (RawEventsTraces)

### Table classes
- Pre-aggregated rolling tables:
  - Examples: users_count_28d_*, sessions_count_28d_*, unique_app_count_28d_*
  - Already computed counts (often need arg_max(DataIngestTimestamp, …) to pick latest per day).
- Pre-aggregated function outputs:
  - Get28DayRollingAggregation(language, modernizationType, name) returns (Date, UserSource, Count) style rolling aggregates.
- Helper functions (aggregated/fact-derived):
  - avg_users_per_app_helper, project_size_new_helper, project_size_helper, modules_per_project_helper, lines_of_code_java_upgrade_helper
  - These accept explicit start/end and compute metrics from raw/fact sources.

### Important Mapping
- Tile/page title to query intent (examples):
  - 'java_migrate_meu_total' → Get28DayRollingAggregation('Java', 'migrate', 'Users_MEU')
  - 'java_migrate_unique_app_28d_assessed' → unique_app_count_28d_assessed with arg_max per day
  - 'dotnet_migrate_apps_28d_AverageUsers' → ratio of Users_MAU to Apps_All by Date, UserSource
  - 'java_consolidated_lines_of_code_per_project' → cross-db union of lines_of_code helpers with percentiles

## Entity & Counting Rules (Core Definitions)
- Entity model and keys (as observed):
  - Cohort: UserSource (sometimes user_source)
  - Applications: AppId (used in dcount_AppId aggregations)
  - Users/Devices: DevDeviceId (used in dcount_DevDeviceId aggregations)
  - Projects: projectId appears in helper function outputs
- Standard grouping:
  - Date (daily) and UserSource are the primary grouping dimensions across queries.
- Business definitions (names imply intent but exact conditions are defined by functions):
  - Users_MAU/MEU: monthly/engaged users metrics produced by Get28DayRollingAggregation
  - Apps_* (e.g., All, AssessmentStarted, BuildStarted): app-level stage counts
  - Sessions_* (e.g., BuildStarted, CodeRemediationStarted): session-stage counts
  - Execute/Plan/ValidationPassed: stage-specific metrics for “migrate” and “upgrade”
- Counting do/don’t:
  - Do use arg_max(DataIngestTimestamp, <metric>) to select the latest daily aggregate when the source provides multiple rows per day.
  - Don’t mix UserSource vs user_source without normalization.
  - Do avoid current-day partial data by using startofday(now()) as end in helper functions.

## Views (Reusable Layers)


## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Standardize rolling windows, avoid partial current-day data, and anchor queries to day boundaries.
  - Snippet:
    ```kusto
    // Use UTC by default; anchor to completed days
    let endTime = startofday(now());
    let startTime = startofday(ago(28d));
    // Example: filter a pre-aggregated function output
    Get28DayRollingAggregation('Java', 'migrate', 'Users_MEU')
    | where Date >= startTime and Date < endTime
    | where isnotempty(UserSource) // normalize to use one casing
    ```

- Join template
  - Description: Combine multiple rolling aggregates by Date and UserSource; ensure cohesive cohorts.
  - Snippet:
    ```kusto
    // Normalize casing first if needed
    let A = Get28DayRollingAggregation('C#', 'migrate', 'Users_MAU')
            | project Date, UserSource, CountA = Count;
    let B = Get28DayRollingAggregation('C#', 'migrate', 'Apps_All')
            | project Date, UserSource, CountB = Count;
    A
    | join kind=inner B on Date, UserSource
    | project Date, UserSource, AvgUsersPerApp = iff(CountB == 0, 0.0, toreal(CountA) / CountB)
    ```

- De-dup pattern
  - Description: Resolve multiple daily rows in pre-aggregated tables; pick the latest ingestion slice.
  - Snippets:
    ```kusto
    // Unique app counts (latest per day)
    unique_app_count_28d_assessed
    | where isnotempty(user_source)
    | where Date >= startofday(ago(28d))
    | summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
    ```

    ```kusto
    // Sessions daily counts (latest per day)
    sessions_count_28d_assess
    | where isnotempty(user_source)
    | where Date >= startofday(ago(28d))
    | summarize arg_max(DataIngestTimestamp, count_) by user_source, day = startofday(Date)
    ```

- Important filters
  - Description: Cohort sanity, default exclusions, and normalization. Use placeholders for internal/test lists.
  - Snippet:
    ```kusto
    // Normalize cohort column and exclude internal/test cohorts via a maintained list
    let ExcludedSources = dynamic(["<TestSource1>", "<InternalSourceA>", "<BotSourceX>"]);
    Get28DayRollingAggregation('Java', 'migrate', 'Users_MAU')
    | project-rename UserSource = UserSource // or project-rename UserSource = user_source
    | where isnotempty(UserSource)
    | where UserSource !in (ExcludedSources)
    | where Date >= startofday(ago(28d))
    ```

- Important Definitions
  - Description: Use the Get28DayRollingAggregation name parameter to select metric families without redefining business logic.
  - Snippet:
    ```kusto
    // Example metric families (do not override definitions; use names as-is)
    Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_MAU')
    Get28DayRollingAggregation('Java', 'migrate', 'Apps_ValidationPassed')
    Get28DayRollingAggregation('C#', 'migrate', 'Sessions_BuildStarted')
    ```

- ID parsing/derivation
  - Description: When helper outputs include raw IDs (AppId, DevDeviceId, projectId), use them directly; parsing is not shown in provided queries.
  - Snippet:
    ```kusto
    // Placeholder: if an ID needs parsing, adapt as needed
    // Example path parse (replace with real field names as available)
    // | extend SubscriptionId = extract(@"subscriptions/([^/]+)", 1, ResourceId)
    ```

- Sharded union
  - Description: Merge same-schema helpers across databases; normalize cohorts and summarize percentiles.
  - Snippet:
    ```kusto
    let start = startofday(ago(28d));
    let end = startofday(now());
    let raw =
        union
        cluster('https://ama4j.westus2.kusto.windows.net/').database('consolidation').lines_of_code_java_upgrade_helper(start, end),
        cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').lines_of_code_helper(start, end);
    raw
    | summarize percentiles(lines, 95, 90, 75)
    | extend user_source = "total"
    | union (
        raw
        | summarize percentiles(lines, 95, 90, 75) by user_source
    )
    ```

## Example Queries (with explanations)

1) Java migrate MEU total
- Description: Retrieves 28-day rolling engaged users for Java migrate. Applies cohort presence gate and 28-day window.
```kusto
Get28DayRollingAggregation('Java', 'migrate', 'Users_MEU')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

2) Java migrate unique apps assessed (latest per day)
- Description: Selects latest daily unique app count (by AppId) for assessed state using arg_max on DataIngestTimestamp.
```kusto
unique_app_count_28d_assessed
| where isnotempty(user_source)
| where Date >= startofday(ago(28d))
| summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
```

3) .NET migrate average users per app (ratio join)
- Description: Joins Users_MAU and Apps_All by Date and UserSource, computes ratio; adapt windows by changing ago() or anchoring end times.
```kusto
Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Users_MAU")
| join kind=inner Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Apps_All") on Date, UserSource
| project Date, UserSource, Count = iff(Count1 == 0, 0.0, toreal(Count) / Count1)
| where Date >= ago(28d)
```

4) .NET migrate sessions: Assessment + Copilot sums
- Description: Sums two session event families with an inner join on Date and UserSource; useful for combined activity tracking.
```kusto
Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Sessions_AssessmentStarted")
| join kind=inner Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Sessions_CopilotConversationStarted") on Date, UserSource
| project Date, UserSource, Count = Count + Count1
| where Date >= ago(28d)
```

5) Java consolidated lines of code per project (cross-db union + percentiles)
- Description: Merges lines-of-code computations from two databases on the ama4j cluster; computes 95/90/75 percentiles overall and per user_source; anchors end at startofday(now()).
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
let raw =
union
cluster('https://ama4j.westus2.kusto.windows.net/').database('consolidation').lines_of_code_java_upgrade_helper(start, end),
cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').lines_of_code_helper(start, end);
raw
| summarize percentiles(lines, 95,90,75)
| extend user_source = "total"
| union (
    raw
    | summarize percentiles(lines, 95,90,75) by user_source
)
```

6) Java migrate sessions assessed (latest per day)
- Description: Uses arg_max(DataIngestTimestamp, count_) to pick the latest daily sessions count for assessed reports.
```kusto
sessions_count_28d_assess
| where isnotempty(user_source)
| where Date >= startofday(ago(28d))
| summarize arg_max(DataIngestTimestamp, count_) by user_source, day = startofday(Date)
```

7) Java consolidated module per project P90
- Description: Retrieves the P90 of apps/modules per project over a 29-day window; adapt window and percentile by changing name or ago().
```kusto
Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Apps_P90PerProject')
| where Date >= startofday(ago(29d))
```

8) Java upgrade MEU and MAU (cohorted)
- Description: 28-day rolling monthly/engaged users for Java upgrade cohorts; ensures cohort presence.
```kusto
Get28DayRollingAggregation('Java', 'upgrade', 'Users_MEU')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'upgrade', 'Users_MAU')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

9) Java migrate modules per project (helper + percentile)
- Description: Computes per-project module counts using a helper over an explicit start/end window; aggregates to P90 by cohort.
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
modules_per_project_helper(start, end)
| summarize percentile(ModuleCount, 90) by user_source
```

10) Java consolidated users category metrics (plan/execute/security/quality)
- Description: Uses unified “migrate/upgrade” scope across user activity families; default cohort gate and rolling window.
```kusto
Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_Plan')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_Execute')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_SecurityExecute')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_QualityExecute')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

## Internal Investigation Funnels (Power BI)
These end-to-end funnels power internal analysis dashboards. They stitch multiple cross-cluster sources and derive user_source via VsCodeInsights.fact_user_isinternal. Windows are anchored to completed days with start = startofday(ago(28d)) and end = startofday(now()). Use cautiously outside internal contexts due to dependency on internal telemetry.

11) Java Assessment user funnel
- Description: this query is used to get the user funnel of Java Assessment, to analyze the user conversion rate in the assess process
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
let users_assessment = materialize(
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').assessment_run_records_helper(start, end)
    | distinct  DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Assessment Kick off (Click button or Chat)");
let users_precheck = materialize(
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').assessment_precheck_records_helper(start, end)
    | distinct  DevDeviceId,ExtensionVersion,IsJavaProject, user_source,type = "Precheck ran");
let users_javaproject = 
    users_precheck 
    | where IsJavaProject == "true"
    | distinct  DevDeviceId,ExtensionVersion, user_source,type = "Confirmed as Java project";
let users_appcat = 
    cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/command'
    | extend data = parse_json(message)
    | extend command = tostring(data.message)
    | where command == 'analyze'
    | extend dimensions = parse_json(customDimensions)
    | extend appcatVersion = tostring(dimensions.appcatversion)
    | where appcatVersion !in ('latest', 'experimental')
    | extend status = tostring(dimensions.status)
    | where status == 'start'
    | extend callerid = tostring(dimensions.callerid)
    | where callerid has "migrate-java-to-azure"
    | project ServerTimestamp=timestamp, DevDeviceId=tostring(dimensions.devdeviceid),VSCodeSessionId = operation_ParentId
    | join kind=leftouter (
        users_assessment | distinct VSCodeSessionId,ExtensionVersion
    ) on VSCodeSessionId
    // the devdevice id in appcat cli may be consistent with the one in VSCodeExt
    // So the devdeviceid count may increase by the union. But the discrepancy is acceptable.
    | union (
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. end)
        | where EventName == 'vscjava.migrate-java-to-azure/java/migrateassistant/appcat/scan' and (Properties.result == 'success' or Properties.error !has "with exit code: 199" and Properties.error matches regex @"with exit code: \d+")
        | project DevDeviceId,VSCodeSessionId,ServerTimestamp,ExtensionVersion
    )
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(IsInternal == 1, 'internal', 'external')
    | distinct  DevDeviceId,ExtensionVersion, user_source,type = "AppCAT ran";
let users_report = 
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').assessment_success_occurrence_vscode_helper(start, end)
    | distinct  DevDeviceId,ExtensionVersion, user_source,type = "Report generated";
union users_assessment,users_precheck,users_javaproject,users_appcat,users_report
| join kind=inner (users_assessment | project DevDeviceId) on DevDeviceId
```

12) Java Upgrade user funnel
- Description: this query is used to get the user funnel of Java Upgrade, to analyze the user conversion rate in the upgrade process
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
let _isMarketplaceVersion = true;
// baseQuery root
let root = () {
    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where ServerTimestamp  between (start .. end)
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion >=1 and minorVersion >=2
    | extend isMarketplaceVersion = iff(ExtensionVersion !has "SNAPSHOT", true, false)
    | where isempty(['_isMarketplaceVersion']) or isMarketplaceVersion == ['_isMarketplaceVersion']
    | extend sessionId = tostring(Properties["sessionid"])
    | extend appId = tostring(Properties["hashedappid"])
};
// baseQuery filtered
let filtered = () {
    root
    | where isnotempty(sessionId) and sessionId != 'unknown'
    | extend model = tostring(Properties["modelid"])
    | extend targetdeps = tostring(Properties["targetdeps"])
    | summarize arg_min(ServerTimestamp,targetdeps), arg_min(ServerTimestamp, model) by sessionId
    | project model, targetdeps, infoSessionId=sessionId
    | join kind=rightouter root on $left.infoSessionId == $right.sessionId
};
// baseQuery inSession
let inSession = () {
    filtered
    | where isnotempty(sessionId) and sessionId != 'unknown'
};
// baseQuery workflow
let workflow = () {
    inSession
    | project DevDeviceId, sessionId, appId, ServerTimestamp, ExtensionVersion, EventName, majorVersion, minorVersion, Measures, Properties
    | extend planStarted=iff(EventName=="vscjava.vscode-java-upgrade/generateupgradeplanforjavaproject.start",'succeeded','')
    | extend planGenerated=iff(EventName=="vscjava.vscode-java-upgrade/confirmupgradeplanforjavaproject.start" or EventName=="vscjava.vscode-java-upgrade/generateupgradeplanforjavaproject.end", 'succeeded','')
    | extend readyExecution=iff((EventName == "vscjava.vscode-java-upgrade/confirmupgradeplanforjavaproject.end" and (majorVersion <1 or minorVersion <2)) or
     (EventName == "vscjava.vscode-java-upgrade/setupdevelopmentenvironmentforupgrade.end" and (majorVersion >=1 and minorVersion >=2)),'succeeded', '')
    // remediation
    | extend remediationStarted=iff(EventName in("vscjava.vscode-java-upgrade/upgradejavaprojectusingopenrewrite.start", "vscjava.vscode-java-upgrade/task.upgradeprojectusingagent.started", "vscjava.vscode-java-upgrade/task.upgradeprojectusingairecipes.started"), 'succeeded', '')
    | extend remediationResult=iff(EventName in("vscjava.vscode-java-upgrade/upgradejavaprojectusingopenrewrite.end", "vscjava.vscode-java-upgrade/task.upgradeprojectusingagent.completed", "vscjava.vscode-java-upgrade/task.upgradeprojectusingairecipes.completed"), iff(Properties['result']!='failed', 'succeeded', 'failed'), '')
    // build
    | extend buildStarted=iff(EventName=="vscjava.vscode-java-upgrade/buildjavaproject.start", 'succeeded', '')
    | extend builtResult=iff(EventName=="vscjava.vscode-java-upgrade/buildjavaproject.end", tostring(Properties["result"]), '')
    // cve
    | extend cveStarted=iff(EventName=="vscjava.vscode-java-upgrade/validatecvesforjava.start", 'succeeded', '')
    | extend cveResult=iff(EventName=="vscjava.vscode-java-upgrade/validatecvesforjava.end", iff((isempty(Measures["cve.high"]) and isempty(Measures["cve.critical"]) and isempty(Measures["cve.medium"])), "succeeded", "failed"), '')
    // behavior
    | extend behaviorStarted=iff(EventName=="vscjava.vscode-java-upgrade/validatebehaviorchangesforjava.start", 'succeeded','')
    | extend behaviorResult=iff(EventName=="vscjava.vscode-java-upgrade/project.state.behaviorchanges", iff((toint(Measures["numofbehaviorchangestofix"])==0), "succeeded", "failed"), '')
    // test
    | extend testStarted=iff(EventName=="vscjava.vscode-java-upgrade/runtestsforjava.start", 'succeeded', '')
    | extend testResult=iff(EventName=="vscjava.vscode-java-upgrade/runtestsforjava.end", tostring(Properties["result"]), '') 
    // summarize
    | extend summarizeStarted=iff(EventName=="vscjava.vscode-java-upgrade/summarizeupgrade.start", 'succeeded','')
    | extend summarizeResult=iff(EventName=="vscjava.vscode-java-upgrade/summarizeupgrade.end","succeeded",'')
    | project-away EventName, majorVersion, minorVersion, Measures, Properties
    | where isnotempty(planStarted) or isnotempty(planGenerated) or isnotempty(readyExecution) or isnotempty(remediationStarted) or isnotempty(remediationResult) or isnotempty(buildStarted) or isnotempty(builtResult) or isnotempty(cveStarted) or isnotempty(cveResult) or isnotempty( behaviorStarted) or isnotempty(behaviorResult) or isnotempty( testStarted) or isnotempty(testResult) or isnotempty( summarizeStarted) or isnotempty(summarizeResult)
    | summarize 
        take_any(ExtensionVersion),
        planStartTime=arg_min(iff(isnotempty(planStarted), ServerTimestamp, datetime(null)), planStarted),
        planGeneratedTime=arg_max(iff(isnotempty(planGenerated), ServerTimestamp, datetime(null)), planGenerated),
        readyExcutionTime=arg_max(iff(isnotempty(readyExecution), ServerTimestamp, datetime(null)), readyExecution),
        remediationStartTime=arg_min(iff(isnotempty(remediationStarted), ServerTimestamp, datetime(null)), remediationStarted),
        remediationEndTime=arg_max(iff(isnotempty(remediationResult), ServerTimestamp, datetime(null)), remediationResult),
        buildStartTime=arg_min(iff(isnotempty(buildStarted), ServerTimestamp, datetime(null)), buildStarted),
        buildEndTime=arg_max(iff(isnotempty(builtResult), ServerTimestamp, datetime(null)), builtResult),
        cveStartTime=arg_min(iff(isnotempty(cveStarted), ServerTimestamp, datetime(null)), cveStarted),
        cveEndTime=arg_max(iff(isnotempty(cveResult), ServerTimestamp, datetime(null)), cveResult),
        behaviorStartTime=arg_min(iff(isnotempty(behaviorStarted), ServerTimestamp, datetime(null)), behaviorStarted),
        behaviorEndTime=arg_max(iff(isnotempty(behaviorResult), ServerTimestamp, datetime(null)), behaviorResult),
        testStartTime=arg_min(iff(isnotempty(testStarted), ServerTimestamp, datetime(null)), testStarted),
        testEndTime=arg_max(iff(isnotempty(testResult), ServerTimestamp, datetime(null)), testResult),
        summarizeStartTime=arg_min(iff(isnotempty(summarizeStarted), ServerTimestamp, datetime(null)), summarizeStarted),
        summarizeEndTime=arg_max(iff(isnotempty(summarizeResult), ServerTimestamp, datetime(null)), summarizeResult)
        by sessionId, appId, DevDeviceId
};
workflow
| join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
| summarize
    planStartedDevices=dcountif(DevDeviceId, planStarted=='succeeded'),
    planStartedSessions=dcountif(sessionId, planStarted=='succeeded'),
    planStartedApps=dcountif(appId, planStarted=='succeeded'),
    planGeneratedDevices=dcountif(DevDeviceId, planGenerated=='succeeded'),
    planGeneratedSessions=dcountif(sessionId, planGenerated=='succeeded'),
    planGeneratedApps=dcountif(appId, planGenerated=='succeeded'),
    readyExecutionDevices=dcountif(DevDeviceId, readyExecution=='succeeded'),
    readyExecutionSessions=dcountif(sessionId, readyExecution=='succeeded'),
    readyExecutionApps=dcountif(appId, readyExecution=='succeeded'),
    remediationStartedDevices=dcountif(DevDeviceId, remediationStarted=='succeeded' and readyExecution =='succeeded'),
    remediationStartedSessions=dcountif(sessionId, remediationStarted=='succeeded' and readyExecution =='succeeded'),
    remediationStartedApps=dcountif(appId, remediationStarted=='succeeded' and readyExecution =='succeeded'),
    remediationSucceededDevices=dcountif(DevDeviceId, remediationResult=='succeeded' and readyExecution =='succeeded'),
    remediationSucceededSessions=dcountif(sessionId, remediationResult=='succeeded' and readyExecution =='succeeded'),
    remediationSucceededApps=dcountif(appId, remediationResult=='succeeded' and readyExecution =='succeeded'),
    buildStartedDevices=dcountif(DevDeviceId, buildStarted=='succeeded' and readyExecution =='succeeded'),
    buildStartedSessions=dcountif(sessionId, buildStarted=='succeeded' and readyExecution =='succeeded'),
    buildStartedApps=dcountif(appId, buildStarted=='succeeded' and readyExecution =='succeeded'),
    builtSucceededDevices=dcountif(DevDeviceId, builtResult == "succeeded" and readyExecution =='succeeded'),
    builtSucceededSessions=dcountif(sessionId, builtResult == "succeeded" and readyExecution =='succeeded'),
    builtSucceededApps=dcountif(appId, builtResult == "succeeded" and readyExecution =='succeeded'),
    cveStartedDevices=dcountif(DevDeviceId, cveStarted=='succeeded' and readyExecution =='succeeded'),
    cveStartedSessions=dcountif(sessionId, cveStarted=='succeeded' and readyExecution =='succeeded'),
    cveStartedApps=dcountif(appId, cveStarted=='succeeded' and readyExecution =='succeeded'),
    cveSucceededDevices=dcountif(DevDeviceId, cveResult == "succeeded" and readyExecution =='succeeded'),
    cveSucceededSessions=dcountif(sessionId, cveResult == "succeeded" and readyExecution =='succeeded'),
    cveSucceededApps=dcountif(appId, cveResult == "succeeded" and readyExecution =='succeeded'),
    behaviorStartedDevices=dcountif(DevDeviceId, behaviorStarted=='succeeded' and readyExecution =='succeeded'),
    behaviorStartedSessions=dcountif(sessionId, behaviorStarted=='succeeded' and readyExecution =='succeeded'),
    behaviorStartedApps=dcountif(appId, behaviorStarted=='succeeded' and readyExecution =='succeeded'),
    behaviorSucceededDevices=dcountif(DevDeviceId, behaviorResult == "succeeded" and readyExecution =='succeeded'),
    behaviorSucceededSessions=dcountif(sessionId, behaviorResult == "succeeded" and readyExecution =='succeeded'),
    behaviorSucceededApps=dcountif(appId, behaviorResult == "succeeded" and readyExecution =='succeeded'),
    testStartedDevices=dcountif(DevDeviceId, testResult=='succeeded' and readyExecution =='succeeded'),
    testStartedSessions=dcountif(sessionId, testResult=='succeeded' and readyExecution =='succeeded'),
    testStartedApps=dcountif(appId, testResult=='succeeded' and readyExecution =='succeeded'),
    testSucceededDevices=dcountif(DevDeviceId, testResult == "succeeded" and readyExecution =='succeeded'),
    testSucceededSessions=dcountif(sessionId, testResult == "succeeded" and readyExecution =='succeeded'),
    testSucceededApps=dcountif(appId, testResult == "succeeded" and readyExecution =='succeeded'),
    summarizeStartedDevices=dcountif(DevDeviceId, summarizeStarted =='succeeded' and readyExecution =='succeeded'),
    summarizeStartedSessions=dcountif(sessionId, summarizeStarted =='succeeded' and readyExecution =='succeeded'),
    summarizeStartedApps=dcountif(appId, summarizeStarted =='succeeded' and readyExecution =='succeeded'),
    summarizedDevices=dcountif(DevDeviceId,summarizeResult=='succeeded' and readyExecution =='succeeded'),
    summarizedSessions=dcountif(sessionId,summarizeResult=='succeeded' and readyExecution =='succeeded'),
    summarizedApps=dcountif(appId,summarizeResult=='succeeded' and readyExecution =='succeeded') by user_source
| extend data = bag_pack(
    "Trigger Java Upgrade", bag_pack("Devices", planStartedDevices, "Apps", planStartedApps, "Sessions", planStartedSessions),
    "Plan generated, wait for confirm", bag_pack("Devices", planGeneratedDevices, "Apps", planGeneratedApps, "Sessions", planGeneratedSessions),
    "Plan confirmed, ready to execute", bag_pack("Devices", readyExecutionDevices, "Apps", readyExecutionApps, "Sessions", readyExecutionSessions),
    "Code remediation started", bag_pack("Devices", remediationStartedDevices, "Apps", remediationStartedApps, "Sessions", remediationStartedSessions),
    "Code remediation completed", bag_pack("Devices", remediationSucceededDevices, "Apps", remediationSucceededApps, "Sessions", remediationSucceededSessions),
    "Build started", bag_pack("Devices", buildStartedDevices, "Apps", buildStartedApps, "Sessions", buildStartedSessions),
    "Build succeeded", bag_pack("Devices", builtSucceededDevices, "Apps", builtSucceededApps, "Sessions", builtSucceededSessions),
    "CVE check started", bag_pack("Devices", cveStartedDevices, "Apps", cveStartedApps, "Sessions", cveStartedSessions),
    "CVE check passed", bag_pack("Devices", cveSucceededDevices, "Apps", cveSucceededApps, "Sessions", cveSucceededSessions),
    "Behavior check started", bag_pack("Devices", behaviorStartedDevices, "Apps", behaviorStartedApps, "Sessions", behaviorStartedSessions),
    "Behavior check passed", bag_pack("Devices", behaviorSucceededDevices, "Apps", behaviorSucceededApps, "Sessions", behaviorSucceededSessions),
    "Unit tests started", bag_pack("Devices", testStartedDevices, "Apps", testStartedApps, "Sessions", testStartedSessions),
    "Unit tests passed", bag_pack("Devices", testSucceededDevices, "Apps", testSucceededApps, "Sessions", testSucceededSessions),
    "Summarize started", bag_pack("Devices", summarizeStartedDevices, "Apps", summarizeStartedApps, "Sessions", summarizeStartedSessions),
    "Summarize completed", bag_pack("Devices", summarizedDevices, "Apps", summarizedApps, "Sessions", summarizedSessions)
)
| mv-expand stage_data = data
| project Stage = tostring(bag_keys(stage_data)[0]), 
          Devices = toint(stage_data[tostring(bag_keys(stage_data)[0])].Devices),user_source
```

13) General migration funnel (Java, broader coverage)
- Description: As of last 28 days. This funnel covers all users involved in general migration, including those using migrate-by-prompt, containerization, and build-only approaches. As a result, may not accurately represent conversions along the classical migration path.
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
let users_migration = materialize(
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').migration_records_helper(start, end)
    | distinct DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Kick off Migration");
let users_migration_java = cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').migration_records_with_java_helper(start,end)
    | distinct DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Have Java App";
let users_tool_invoke =
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool in ('createMigrationPlan','appmod-run-task')
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | project ServerTimestamp, DevDeviceId, user_source,Properties,ExtensionVersion
        | union (
            cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
            | where timestamp  between (start .. (end - 1s))
            | where timestamp >= datetime(2025-07-31)
            | where operation_Name == "java/migrateassistant/tool/invoke"
            | extend properties = parse_json(customDimensions)
            | extend invokedToolId = tostring(properties["invokedtoolid"])
            | where invokedToolId has 'appmod-run-task'
            | extend DevDeviceId = tostring(properties.devdeviceid)
            | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
            | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
            | extend ExtensionVersion = tostring(properties.callerversion)
        )
        | distinct DevDeviceId,ExtensionVersion, user_source,type = "Tool invoked (after user's confirmation)";
let users_copilot_request = 
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. end)
    | where ExtensionName == 'GitHub.copilot-chat'
    | where EventName == "github.copilot-chat/panel.request"
    | where VSCodeSessionId in (users_migration | distinct VSCodeSessionId) or DevDeviceId in (users_migration | distinct DevDeviceId) 
    | project ServerTimestamp,EventName,VSCodeSessionId, requestId = tostring(Properties.requestid), conversationId = tostring(Properties.conversationid), DevDeviceId,Properties,toolcounts = tostring(Properties.toolcounts), Measures
    | project DevDeviceId, toolcounts,requestId, ServerTimestamp, Properties,VSCodeSessionId
    | where toolcounts has 'appmod-run-task' or toolcounts has 'createMigrationPlan'
    | join kind=leftouter (
        users_migration 
        | distinct VSCodeSessionId, ExtensionVersion
    ) on VSCodeSessionId
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
    | union (users_tool_invoke)
    | distinct DevDeviceId,ExtensionVersion, user_source,type = "Copilot request for migration plan";
let users_build = materialize(cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').build_result_records_helper(start,end));
let users_build_invoke =
    users_build
    | distinct DevDeviceId,ExtensionVersion, user_source,type = "Buildfix start";
let users_build_success =
    users_build
    | where success
    | distinct DevDeviceId,ExtensionVersion, user_source,type = "Buildfix success";
union users_migration,users_copilot_request,users_tool_invoke, users_build_invoke,users_build_success,users_migration_java
```

14) Classical migration funnel (Java-only, stricter path)
- Description: As of last 28 days. This funnel focuses on Java users using classical migration scenarios, which involves using a migration plan and ideally going through validation. Users who use migrate-by-prompt, containerization, or only perform validation may not follow this classical flow and are therefore excluded from this funnel analysis.
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
let users_migration = 
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').narrow_migration_records_helper_Java(start, end)
    | project  DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Kick off Migration with Java";
let users_tool_invoke = 
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ExtensionName has "migrate-java-to-azure" and EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool in ('createMigrationPlan','appmod-run-task')
        | project ServerTimestamp, DevDeviceId,Properties,ExtensionVersion,VSCodeSessionId
        | union (
            cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
            | where timestamp  between (start .. (end - 1s))
            | where operation_Name == "java/migrateassistant/tool/invoke"
            | extend invokedToolId = tostring(customDimensions["invokedtoolid"])
            | where invokedToolId has 'appmod-run-task'
            | extend DevDeviceId = tostring(customDimensions.devdeviceid)
            | extend ExtensionVersion = tostring(customDimensions.callerversion), VSCodeSessionId = tostring(customDimensions.callersessionid)
        )
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | mv-expand type = dynamic(["Tool invoked for Java", "Copilot request for migration plan for Java"]) to typeof(string)
        | project DevDeviceId,ExtensionVersion,VSCodeSessionId, user_source,type;
let users_copilot_request =
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. end)
    | where ExtensionName == 'GitHub.copilot-chat' and EventName == "github.copilot-chat/panel.request"
    | project ServerTimestamp,EventName,VSCodeSessionId, requestId = tostring(Properties.requestid), conversationId = tostring(Properties.conversationid), DevDeviceId,Properties,toolcounts = tostring(Properties.toolcounts), Measures
    | project DevDeviceId, toolcounts,requestId, ServerTimestamp, Properties,VSCodeSessionId
    | where toolcounts has 'appmod-run-task' or toolcounts has 'createMigrationPlan'
    | join kind=leftouter (
        users_migration 
        | distinct VSCodeSessionId, ExtensionVersion
    ) on VSCodeSessionId
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
    | project DevDeviceId,ExtensionVersion,VSCodeSessionId, user_source,type="Copilot request for migration plan for Java";
let users_build = 
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').build_result_records_with_appid_helper(start,end) 
    | project DevDeviceId,ExtensionVersion,VSCodeSessionId, user_source,success;
let users_build_invoke = 
    users_build
    | project DevDeviceId, ExtensionVersion, VSCodeSessionId, user_source, type = "Buildfix start";
let users_build_success = 
    users_build
    | where success
    | project DevDeviceId, ExtensionVersion, VSCodeSessionId, user_source, type = "Buildfix success";
union users_migration,users_copilot_request,users_tool_invoke, users_build_invoke, users_build_success
| join kind=inner (users_migration | project VSCodeSessionId) on VSCodeSessionId
```

## Reasoning Notes (only if uncertain)
- Get28DayRollingAggregation outputs:
  - Interpretation: returns pre-aggregated (Date, UserSource, Count) for a specific language, modernizationType, and named metric. Adopted because nearly all queries treat its output like a daily rolling fact with those columns.
- Timezone:
  - Unknown; adopt UTC as conservative default since queries use startofday/ago patterns without timezone hints.
- Cohort casing:
  - Both UserSource and user_source appear; adopt normalization via project-rename to avoid join/filter mismatch.
- Current-day completeness:
  - Some helpers explicitly use startofday(now()) as end; adopt practice to avoid partial current-day data.
- Table/function classes:
  - users_count_28d_* and sessions_count_28d_* appear to be pre-aggregated daily summaries requiring arg_max to choose the latest valid slice; adopt arg_max(DataIngestTimestamp, <metric>) for daily rollups.
- Cross-cluster sources:
  - The main product cluster is appmod.westus2; lines-of-code computations reference ama4j.westus2 across consolidation and bi DBs; adopt explicit qualification with cluster()/database() and union followed by normalization.

## Canonical Tables

The product’s main cluster/database is appmod.westus2.kusto.windows.net/Consolidation, but these canonical tables are sourced cross-cluster from ama4j.westus2.kusto.windows.net/bi. All are daily aggregates over rolling 28-day windows. Freshness and timezone are not documented; treat current-day data conservatively (use startofday and arg_max by day).

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').unique_app_count_28d_vscode
- Priority: Normal
- What this table represents: Daily snapshot of distinct application counts attributed to the VS Code source over a rolling 28-day window.
  - Aggregated (not raw events). Zero rows for a date imply no data ingested/attributed for that day.
- Freshness expectations: Daily materialization; queries often use Date >= startofday(ago(28d)). Ingestion timing is not included (no DataIngestTimestamp in this table).
- When to use:
  - Trend VS Code-attributed distinct app counts over the last 28 days.
  - Break down volume by user_source when comparing channels.
  - Join with other 28-day aggregates on Date for multi-metric dashboards.
- When to avoid:
  - Per-session or per-user analysis (it’s aggregate-only).
  - Interpreting Date as precise event time; use it as an aggregation bucket.
  - Mixing this VS Code-specific table with CLI/total tables without normalizing user_source.
- Similar tables & how to choose:
  - unique_app_count_28d_cli, unique_app_count_28d_total: choose based on channel scope (CLI vs VSCode vs total).
  - unique_app_count_28d_assessed/assessreport: use those for specific funnel stages.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column          | Type     | Description or meaning |
  |-----------------|----------|------------------------|
  | dcount_AppId    | long     | Distinct app IDs counted for the day over a rolling 28-day window (VS Code channel). |
  | Date            | datetime | Aggregation day bucket; use startofday filters for rolling windows. |
  | user_source     | string   | Attribution channel (e.g., 'vscode'); queries filter isnotempty(user_source). |

- Column Explain:
  - Date: primary time bucket for trending; filter with startofday(ago(28d)).
  - user_source: use in where/isnotempty and to produce per-channel breakdowns.
  - dcount_AppId: main metric to visualize distinct app volume.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').unique_app_count_28d_vscode
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize sum(dcount_AppId) by startofday(Date), user_source
  | order by startofday_Date asc
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').unique_app_count_28d_assessed
- Priority: Normal
- What this table represents: Daily snapshot of distinct apps that have entered “assessed” stage over a rolling 28-day window.
  - Aggregate; a row per day/user_source. Use DataIngestTimestamp to select the latest snapshot for the day.
- Freshness expectations: Daily; includes DataIngestTimestamp to support arg_max.
- When to use:
  - Count assessed apps by day/channel.
  - Select latest per-day value using arg_max(DataIngestTimestamp, dcount_AppId).
- When to avoid:
  - Using raw counts without arg_max when multiple ingests per day exist.
- Similar tables & how to choose:
  - unique_app_count_28d_assessreport: assessed report completion stage.
  - unique_app_count_28d_vscode/cli/total: channel-level vs stage specificity.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
  - Use arg_max by startofday(Date), user_source
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_AppId         | long     | Distinct app count in assessed stage for that day. |
  | Date                 | datetime | Aggregation day bucket. |
  | user_source          | string   | Attribution channel of assessed activity. |
  | DataIngestTimestamp  | datetime | Ingestion time; use arg_max to select latest per day. |

- Column Explain:
  - DataIngestTimestamp: critical for resolving multiple ingests per day via arg_max.
  - dcount_AppId: stage-specific app volume metric.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').unique_app_count_28d_assessed
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').unique_app_count_28d_assessreport
- Priority: Normal
- What this table represents: Daily snapshot of distinct apps reaching “assessment report” stage over a rolling 28-day window.
- Freshness expectations: Daily; supports arg_max via DataIngestTimestamp.
- When to use:
  - Track assessed report completions by day/channel.
  - Plot funnel progression from assessed to assessreport.
- When to avoid:
  - Inferring raw event timing; this is an aggregate snapshot.
- Similar tables & how to choose:
  - unique_app_count_28d_assessed: earlier stage.
  - unique_app_count_28d_vscode/total: non-stage-specific counts.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_AppId         | long     | Distinct apps with assessment reports for the day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTimestamp  | datetime | Ingestion time; choose latest via arg_max. |

- Column Explain:
  - Use arg_max(DataIngestTimestamp, dcount_AppId) to get the latest daily value.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').unique_app_count_28d_assessreport
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_assess
- Priority: Normal
- What this table represents: Daily snapshot of distinct users/devices participating in “assess” stage over a rolling 28-day window.
- Freshness expectations: Daily; includes DataIngestTimestamp.
- When to use:
  - Measure assess-stage adoption by users/devices.
  - Use arg_max per day to avoid multiple ingests.
- When to avoid:
  - Treating dcount_DevDeviceId as unique human users without validation; it’s device-based.
- Similar tables & how to choose:
  - users_count_28d_assessreport: later stage.
  - users_count_28d_migrationplan/buildfix/adoption: different activities.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct developer device IDs for the day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTimestamp  | datetime | Ingestion time; select latest via arg_max. |

- Column Explain:
  - dcount_DevDeviceId: proxy for user engagement; device-level uniqueness may overcount users with multiple devices.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_assess
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_DevDeviceId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_assessreport
- Priority: Normal
- What this table represents:
  - Distinct users/devices who completed assessment reports, per day, 28-day rolling window.
  - Distinct users/devices completing assessment reports per day, 28-day window.
- Freshness expectations: Daily; includes DataIngestTimestamp.
- When to use:
  - Later-stage user adoption tracking.
  - Funnel conversion analysis from assess to assessreport.
  - Report-completion engagement tracking and funnel conversion.
- When to avoid:
  - Assuming human-user granularity; it is device-based.
  - Inferring human-unique users from device-based counts.
- Similar tables & how to choose:
  - users_count_28d_assess for earlier stage.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct devices completing assessment reports. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTimestamp  | datetime | Ingestion time; use arg_max per day. |

- Column Explain:
  - Use arg_max on DataIngestTimestamp to ensure the latest daily value is selected.
  - dcount_DevDeviceId: distinct device count for report completion.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_assessreport
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_DevDeviceId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_migrationplan
- Priority: Normal
- What this table represents: Distinct users/devices associated with migration plan activities, daily, 28-day window.
- Freshness expectations: Daily; no DataIngestTimestamp column in schema. Use Date as canonical bucket.
- When to use:
  - Track planning-stage engagement by channel.
  - Join with buildfix/migration execution counts for funnel analytics.
- When to avoid:
  - Attempting arg_max on ingestion (timestamp not present).
- Similar tables & how to choose:
  - users_count_28d_buildfix (build activity), users_count_28d_migration (execution activity).
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct device IDs engaged in planning. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |

- Column Explain:
  - dcount_DevDeviceId: main metric; use startofday(Date) for windows.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_migrationplan
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize sum(dcount_DevDeviceId) by day = startofday(Date), user_source
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_buildfix
- Priority: Normal
- What this table represents: Distinct users/devices performing build-fix activities, daily, 28-day window.
- Freshness expectations: Daily; no ingest timestamp. Use Date bucket directly.
- When to use:
  - Track build-fix adoption over time by channel.
- When to avoid:
  - Assuming raw event granularity; this is aggregated.
- Similar tables & how to choose:
  - users_count_28d_migrationplan (planning), sessions_count_28d_buildfix (sessions rather than distinct users).
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct devices engaged in build-fix. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution (e.g., 'vscode', 'cli'). |

- Column Explain:
  - dcount_DevDeviceId: user engagement count; pair with sessions table for activity intensity.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_buildfix
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize sum(dcount_DevDeviceId) by day = startofday(Date), user_source
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').sessions_count_28d_assessreport
- Priority: Normal
- What this table represents: Total sessions for the assessment report stage per day, 28-day window.
- Freshness expectations: Daily; includes DataIngestTimestamp for snapshot disambiguation.
- When to use:
  - Quantify activity intensity (sessions) for assess report stage.
  - Combine with users_count to derive sessions-per-user ratios.
- When to avoid:
  - Using sessions as a proxy for distinct users.
- Similar tables & how to choose:
  - sessions_count_28d_assess (earlier stage), sessions_count_28d_buildfix/codeRemediation for other activities.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | count_               | long     | Session count for the stage/day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Attribution channel. |
  | DataIngestTimestamp  | datetime | Ingestion time; use arg_max for latest daily snapshot. |

- Column Explain:
  - count_: intensity metric; pair with distinct user/device counts to avoid misinterpretation.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').sessions_count_28d_assessreport
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, count_) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').sessions_count_28d_assess
- Priority: Normal
- What this table represents: Total sessions for the assess stage per day, 28-day window.
- Freshness expectations: Daily; includes two ingestion timestamp variants (DataIngestTimestamp and DataIngestTimeStamp). Prefer a coalesce to handle both.
- When to use:
  - Assess-stage session intensity trends by channel.
- When to avoid:
  - Assuming only one ingestion timestamp field—handle both cases safely.
- Similar tables & how to choose:
  - sessions_count_28d_assessreport (later stage), sessions_count_28d_buildfix/codeRemediation for other activities.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | count_               | long     | Session count for the stage/day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Attribution channel. |
  | DataIngestTimestamp  | datetime | Ingestion timestamp (variant 1). |
  | DataIngestTimeStamp  | datetime | Ingestion timestamp (variant 2, casing difference). |

- Column Explain:
  - Use coalesce(DataIngestTimestamp, DataIngestTimeStamp) in arg_max to get robust latest snapshot.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').sessions_count_28d_assess
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(coalesce(DataIngestTimestamp, DataIngestTimeStamp), count_) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_adoption
- Priority: Normal
- What this table represents: Distinct users/devices demonstrating “adoption” activity per day, 28-day window.
- Freshness expectations: Daily; includes DataIngestTime (note the name; different from DataIngestTimestamp).
- When to use:
  - Adoption-focused usage tracking in the migration funnel.
- When to avoid:
  - Assuming DataIngestTime equals event time; treat as ingestion timestamp.
- Similar tables & how to choose:
  - users_count_28d_migration/execute/buildfix when focusing on other funnel steps.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct devices exhibiting adoption behavior. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTime       | datetime | Ingestion timestamp field for daily snapshot. |

- Column Explain:
  - DataIngestTime: use in arg_max per day if multiple ingests occur.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_adoption
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTime, dcount_DevDeviceId) by user_source, day = startofday(Date)
  ```

---

## Notes and patterns for all tables above
- All tables are aggregate snapshots keyed by Date and user_source; do not treat them as raw events.
- Time handling:
  - Use Date >= startofday(ago(28d)) for 28-day window queries.
  - When tables have an ingest timestamp column, select latest daily snapshot via arg_max.
  - Timezone/freshness is undocumented; avoid using current-day partial data for critical reporting.
- Channel attribution:
  - user_source distinguishes the channel (e.g., 'vscode', 'cli'); always filter isnotempty(user_source) when needed.
- Joining and comparisons:
  - Join on Date and user_source to combine metrics (e.g., users and sessions).
  - Normalize by channel before comparing metrics across different activity tables.
- Anti-patterns:
  - Summing snapshots from different channels without user_source alignment.
  - Using device-based distinct counts as exact human user counts without caveats.
  - Ignoring ingest timestamp fields when multiple daily snapshots can exist.