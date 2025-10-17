# Application Modernization for Java and .NET - Product and Data Overview Template

## 1. Product Overview

> Draft: Application Modernization for Java and .NET provides top-level product metrics built from aggregated telemetry derived via predefined Kusto functions. Dashboards summarize user, app, and session-level KPIs (e.g., build/test/CVE success rates) across Java and .NET modernization scenarios using standardized views over Azure Data Explorer datasets.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
> Application Modernization for Java and .NET
- Product Nick Names: 
> [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples might include: "AppMod", "AMA4J", "AMA4NET". Please confirm official nicknames.
- Kusto Cluster:
> https://appmod.westus2.kusto.windows.net/
- Kusto Database:
> Consolidation
- Access Control:
> [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Application Modernization for Java and .NET - Kusto Query Playbook

## Overview
- Product: Application Modernization for Java and .NET
- Summary: The dashboard of Application Modernization is the top level metrics for the product built on aggregated telemetries. The aggregated telemetries comes from raw telemetries by pre-defined Kusto functions.
- Main cluster: https://appmod.westus2.kusto.windows.net/
- Main database: Consolidation

## Conventions & Assumptions

### Time semantics
- Observed time columns:
  - Date: canonical daily time for metrics and grouping.
  - DataIngestTimestamp: ingestion freshness indicator used to select the latest slice when multiple entries exist per day.
- Canonical Time Column: Date
  - Alias pattern (when needed): project-rename TimeCol = Date
- Typical windows:
  - Rolling 28 days: Date >= startofday(ago(28d))
  - Some percentile metrics use 29 days: Date >= startofday(ago(29d))
- Day alignment:
  - startofday(Date) used in summarize keys to ensure daily bins.
- Timezone: Unknown. Assume UTC unless explicitly stated.
- Effective end-time:
  - Several helper queries set end = startofday(now()) before summarization. Prefer using end-of-previous-day for completeness when daily ingestion can lag.

### Freshness & Completeness Gates
- Ingestion cadence: not specified.
- Completeness guardrails:
  - Prefer excluding current day using let end = startofday(now()) and filtering Date < end for daily aggregates.
  - For rolling windows, use startofday(ago(28d)) with a left bound and exclude the current day when completeness is uncertain.
  - When multiple entries exist per day, use summarize arg_max(DataIngestTimestamp, <metric>) by startofday(Date), <key> to keep the freshest slice.

### Joins & Alignment
- Frequent join keys:
  - Date, UserSource
- Typical join kinds:
  - leftouter: for rate computations where a denominator may exist without a numerator (coalesce to 0).
  - inner: for aligned ratio or combined counts where both sides must exist.
- Post-join hygiene:
  - Use coalesce() to handle missing metrics (e.g., coalesce(BuildPassedCount, 0)).
  - Use project-away to drop duplicate/unused intermediate columns after joins.
  - Use project-rename (or explicit project) to establish final output schema.

### Filters & Idioms
- Common filters:
  - isnotempty(UserSource) or isnotempty(user_source) to avoid null cohort rows.
  - Product == "appmod" in raw events.
  - Properties["vs.copilot.clientid"] == "Microsoft.AppModernization" in Copilot conversation events.
- Internal/external classification:
  - UserSource = iff(IsInternal, 'internal', 'external')
  - Explicit denylist of internal/test aliases via UserAlias !in (whitelist) in raw sources.
- Counting idioms:
  - arg_max(DataIngestTimestamp, Count) by startofday(Date), UserSource to deduplicate daily slices.
  - dcount-based fields (dcount_AppId, dcount_DevDeviceId) summarized via arg_max for daily distinct entity counts.

### Cross-cluster/DB & Sharding
- Qualifying sources:
  - cluster('ddtelvsraw.kusto.windows.net').database('VS').RawEventsVSBlessed
  - cluster('ddtelinsights.kusto.windows.net').database('DDTelInsights').Catalog_Events_IntelliCode_VSConversation
  - union examples across:
    - cluster('https://ama4j.westus2.kusto.windows.net/').database('consolidation')
    - cluster('https://ama4j.westus2.kusto.windows.net/').database('bi')
- Pattern:
  - Use union for same-schema shards/alternate sources.
  - Normalize key and time columns post-union (e.g., ensure user_source naming and bin to startofday(Date)).
  - Summarize after union to produce cohort-level aggregates.

### Table classes
- Pre-aggregated:
  - RollingAggregation: contains daily/rolling-window aggregates keyed by Language, ModernizationType, Name, LookBackWindow with Counts and DataIngestTimestamp.
- Facts (raw):
  - RawEventsVSBlessed (VS raw events): filtered to Product == "appmod"; extended fields from Properties and Measures.
  - Catalog_Events_IntelliCode_VSConversation (DDTelInsights events): filtered to clientId "Microsoft.AppModernization".
- Functions/Helpers (pre-built logic):
  - Helpers like avg_users_per_app_helper, project_size_helper/new_helper, modules_per_project_helper, lines_of_code_helper, modules_per_project_java_upgrade_helper; return derived metrics over specified time ranges.

### Important Mapping
- Tile/page titles imply mapping between business KPI tiles and the Get28DayRollingAggregation Name dimension. Examples:
  - 'java_migrate_mau_total' → Get28DayRollingAggregation('Java', 'migrate', 'Users_MAU')
  - 'java_consolidated_sessions_count_28d_buildfix' → Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Sessions_BuildStarted')
  - 'dotnet_migrate_apps_28d_BuildPassed' → Get28DayRollingAggregation('C#', 'migrate', 'Apps_BuildPassed')
  - 'java_consolidated_module_per_project_p90' → Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Apps_P90PerProject')

## Entity & Counting Rules (Core Definitions)
- Entity tiers and keys observed:
  - User (UserAlias, DevDeviceId, derived UserSource = internal/external)
  - App/Project (AppId, projectId)
  - Session (task/session-level counts like Sessions_BuildStarted, Sessions_CvePassed)
- Grouping levels:
  - Daily by startofday(Date) and UserSource for cohort splits (internal/external, total).
  - Some helpers return per-project metrics; use projectId and user_source for distribution analysis.
- Business definitions present in queries:
  - BuildSuccessRate: BuildPassedCount / BuildStartedCount (0 if denominator is 0); also computed as percentages.
  - CveFreeRate: CvePassedCount / CveStartedCount (0 if denominator is 0); includes not-passed count as CveStartedCount - CvePassedCount.
  - TestPassRate: TestsPassedCount / TestsStartedCount (0 if denominator is 0).
- Do/Don’t (counting):
  - Do: deduplicate daily slices via arg_max(DataIngestTimestamp, <metric>) before aggregating.
  - Don’t: include current-day partial data unless you’ve gated with end = startofday(now()).
  - Do: join on Date and UserSource for aligned ratios; coalesce missing numerators to 0.
  - Don’t: divide by 0; guard with case() or iff().

## Views (Reusable Layers)

- Get28DayRollingAggregation
  - Purpose: Standard access layer for RollingAggregation for a 28-day lookback, returning daily counts by UserSource.
  - Inputs: RollingAggregation table; filtered by Language, ModernizationType, Name, LookBackWindow == "28d".
  - Dependent queries: Most KPI tiles for Java and C# rely on this view.

```kusto
Get28DayRollingAggregation(language:string, modernizationType:string, name:string)
{
    RollingAggregation
    | where Language == language
        and ModernizationType == modernizationType
        and Name == name
        and LookBackWindow == "28d"
    | summarize arg_max(DataIngestTimestamp, Count) by UserSource, startofday(Date)
    | project Date, UserSource, Count
}
```

- RawEventsVSBlessed
  - Purpose: Raw VS events for Product == "appmod" excluding an explicit internal alias whitelist; derives properties and internal/external labeling.
  - Inputs: cluster('ddtelvsraw.kusto.windows.net').database('VS').RawEventsVSBlessed.

```kusto
RawEventsVSBlessed()
{
    let whitelist = dynamic(["kuzhong","timong",
        // Zhishou's team
        "zhiszhan","xuycao","xiading","menxiao","xiada","dixue","zhiyongli","edburns","juniwang","jinghzhu","yiliu6","haital","rujche","sonwan","fangjimmy","v-ruitang","yili7","haiche","jiangma","ninpan","wepa","kaiqianyang","qiaolei","v-shilichen","feilonghuang","guitarsheng","v-muyaofeng","haochuang","yuwzho","ruodanxie","junbchen","jiahzhu","chenshi","linglingye","zhiyuanliang","emilyzhu","caiqing","zhujiayi","jinjiez","yuwe","v-ruitang","v-shilichen","v-muyaofeng",
        // Catherine's team
        "yungez","lianw","wenhaozhang","zlhe","fenzho","haozhan","honc","yueli6","xiaofanzhou","wchi","qianwens","chentony",
        // Jeff's team
        "jeffya","jessiehuang","jaeyonglee","xinyizhang","yulinshi","xinrzhu","yiqiu","zhshang","kevinguo","yangtony","seal","hangwan","taoxu","ellieyuan","jialuogan"
    ]);
    cluster('ddtelvsraw.kusto.windows.net').database('VS').RawEventsVSBlessed
    | where Product == "appmod" and UserAlias !in (whitelist)
    | extend UserSource = iff(IsInternal, 'internal', 'external'),
             Status = tostring(Properties["status"]),
             ErrorCode = tostring(Properties["errorcode"]),
             ExtensionVersion = tostring(Properties["extensionversion"]),
             HashedAppSolutionId = tostring(Properties["hashedappsolutionid"]),
             Duration = Measures["duration"]
}
```

- Catalog_Events_IntelliCode_VSConversation
  - Purpose: Raw catalog events filtered to Microsoft.AppModernization Copilot client; excludes internal alias whitelist; derives UserSource.
  - Inputs: cluster('ddtelinsights.kusto.windows.net').database('DDTelInsights').Catalog_Events_IntelliCode_VSConversation.

```kusto
Catalog_Events_IntelliCode_VSConversation()
{
    let whitelist = dynamic(["kuzhong","timong",
        // Zhishou's team
        "zhiszhan","xuycao","xiading","menxiao","xiada","dixue","zhiyongli","edburns","juniwang","jinghzhu","yiliu6","haital","rujche","sonwan","fangjimmy","v-ruitang","yili7","haiche","jiangma","ninpan","wepa","kaiqianyang","qiaolei","v-shilichen","feilonghuang","guitarsheng","v-muyaofeng","haochuang","yuwzho","ruodanxie","junbchen","jiahzhu","chenshi","linglingye","zhiyuanliang","emilyzhu","caiqing","zhujiayi","jinjiez","yuwe","v-ruitang","v-shilichen","v-muyaofeng",
        // Catherine's team
        "yungez","lianw","wenhaozhang","zlhe","fenzho","haozhan","honc","yueli6","xiaofanzhou","wchi","qianwens","chentony",
        // Jeff's team
        "jeffya","jessiehuang","jaeyonglee","xinyizhang","yulinshi","xinrzhu","yiqiu","zhshang","kevinguo","yangtony","seal","hangwan","taoxu","ellieyuan","jialuogan"
    ]);
    cluster('ddtelinsights.kusto.windows.net').database('DDTelInsights').Catalog_Events_IntelliCode_VSConversation
    | where Properties["vs.copilot.clientid"] == "Microsoft.AppModernization" and UserAlias !in (whitelist)
    | extend UserSource = iff(IsInternal, 'internal', 'external')
}
```

- GetBuildSuccessRate
  - Purpose: Computes daily build success rate by UserSource using BuildStarted and BuildPassed aggregates.
  - Depends on: Get28DayRollingAggregation (Apps_BuildStarted, Apps_BuildPassed).

```kusto
GetBuildSuccessRate(language:string, modernizationType:string)
{
    let buildStartedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Apps_BuildStarted")
        | project Date, UserSource, BuildStartedCount = Count);
    let buildPassedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Apps_BuildPassed")
        | project Date, UserSource, BuildPassedCount = Count);
    buildStartedOverTime
    | join kind=leftouter buildPassedOverTime on Date, UserSource
    | extend BuildPassedCount = coalesce(BuildPassedCount, 0)
    | extend SuccessRate = case(BuildStartedCount == 0, 0.0, todouble(BuildPassedCount) / todouble(BuildStartedCount))
    | extend SuccessRatePercent = round(SuccessRate * 100, 2)
    | project Date, language, modernizationType, UserSource, BuildStartedCount, BuildPassedCount, SuccessRate, SuccessRatePercent
}
```

- GetCveFreeRate
  - Purpose: Computes CVE pass rate (CvePassed / CveStarted) with guardrails and not-passed count.

```kusto
GetCveFreeRate(language:string, modernizationType:string)
{
    let CveStartedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Sessions_CveStarted")
        | project Date, UserSource, CveStartedCount = Count);
    let CvePassedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Sessions_CvePassed")
        | project Date, UserSource, CvePassedCount = Count);
    CveStartedOverTime
    | join kind=leftouter CvePassedOverTime on Date, UserSource
    | extend CvePassedCount = coalesce(CvePassedCount, 0)
    | extend SuccessRate = case(CveStartedCount == 0, 0.0, todouble(CvePassedCount) / todouble(CveStartedCount))
    | extend SuccessRatePercent = round(SuccessRate * 100, 2)
    | project Date, language, modernizationType, UserSource, CveStartedCount, CvePassedCount,
              CveNotPassedCount = CveStartedCount - CvePassedCount, SuccessRate, SuccessRatePercent
}
```

- GetTestPassRate
  - Purpose: Computes session test pass rate (TestsPassed / TestsStarted) with guardrails.

```kusto
GetTestPassRate(language:string, modernizationType:string)
{
    let testsStartedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Sessions_TestRunsStarted")
        | project Date, UserSource, TestsStartedCount = Count);
    let testsPassedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Sessions_TestRunsPassed")
        | project Date, UserSource, TestsPassedCount = Count);
    testsStartedOverTime
    | join kind=leftouter testsPassedOverTime on Date, UserSource
    | extend TestsPassedCount = coalesce(TestsPassedCount, 0)
    | extend SuccessRate = case(TestsStartedCount == 0, 0.0, todouble(TestsPassedCount) / todouble(TestsStartedCount))
    | extend SuccessRatePercent = round(SuccessRate * 100, 2)
    | project Date, language, modernizationType, UserSource, TestsStartedCount, TestsPassedCount, SuccessRate, SuccessRatePercent
}
```

### Helper Functions (Reusable Layers from internal engineering)

The following helper functions aggregate raw telemetry from Copilot (ddtelai) and VSCode (ddtelvscode) sources into reusable datasets for MAU/MEU, unique apps/projects, assessment/migration events, and remediation outcomes. They consistently:
- Accept start:datetime and end:datetime parameters.
- Use time predicates: between (start .. (end - 1s)) and daily binning via bin(..., 1d).
- Normalize cohort via user_source using VSCodeInsights.fact_user_isinternal or customDimensions.internal flags.
- Deduplicate by correlationId or VSCodeSessionId where applicable.

```kusto
// MAU of AppCAT CLI
mau_cli_users_helper(start:datetime, end:datetime)
{
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where timestamp >= datetime(2025-05-20)
    | where operation_Name == 'java/appcat/command'
    | extend message = parse_json(message)
    | extend user_source = iff(tobool(message.internal), 'internal', 'external')
    | extend dimensions = parse_json(customDimensions)
    | extend callerId = tostring(dimensions.callerid)
    | where callerId == 'appcat'
    | extend DevDeviceId = tostring(dimensions.devdeviceid)
    | distinct DevDeviceId, user_source, Date=bin(timestamp, 1d);
}
```

```kusto
// MAU of VSCode extension for Application Modernization
mau_vscode_users_helper(start:datetime, end:datetime)
{
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. (end - 1s))
    | where ServerTimestamp >= datetime(2025-05-20)
    | where ExtensionName has "migrate-java-to-azure"
    | where EventName !has 'migrate-java-to-azure/info'
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
    | project DevDeviceId, user_source, Date=bin(ServerTimestamp, 1d)
    | union (
    cluster('ddtelvscode.kusto.windows.net').database('VSCode').table('RawEventsVSCode')
    | where ServerUploadTimestamp between (startofday(start) .. startofday(end) -1s)
    | where EventName == "monacoworkbench/activateplugin"
    | where Properties.id == 'vscjava.migrate-java-to-azure'
    | where Properties.reason !in ('onStartupFinished') and Properties.reason !has 'pom.xml' and Properties.reason !has 'onLanguage:java'
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
    | project DevDeviceId, user_source, Date=bin(ServerUploadTimestamp, 1d)
    )
    // MCP telemetry
    | union (
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where timestamp >= datetime(2025-07-31)
    | where operation_Name startswith 'java/migrateassistant'
    | extend dimensions = parse_json(customDimensions)
    | extend user_source = iff(tobool(dimensions.internal), 'internal', 'external')
    | extend DevDeviceId = tostring(dimensions.devdeviceid)
    | project DevDeviceId, user_source, Date=bin(timestamp, 1d)
    )
    | distinct DevDeviceId,user_source,Date;
}
```

```kusto
// MEU of AppCAT CLI
meu_cli_users_helper(start:datetime, end:datetime)
{
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where operation_Name == 'java/appcat/command'
    | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
    | extend callerId = tostring(customDimensions.callerid)
    | where callerId == 'appcat'
    | extend DevDeviceId = tostring(customDimensions.devdeviceid)
    | extend Date = bin(timestamp, 1d)
    | summarize dcount(Date) by DevDeviceId, user_source
    | where dcount_Date >=2
    | project DevDeviceId, user_source, dcount_Date
}
```

```kusto
// MEU of VSCode extension for Application Modernization
meu_vscode_users_helper(start:datetime, end:datetime)
{
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. (end - 1s))
    | where ServerTimestamp >= datetime(2025-05-20)
    | where ExtensionName has "migrate-java-to-azure"
    | where EventName !has 'migrate-java-to-azure/info'
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
    | project DevDeviceId, user_source, Date=bin(ServerTimestamp,1d)
    | union (
    cluster('ddtelvscode.kusto.windows.net').database('VSCode').table('RawEventsVSCode')
    | where ServerUploadTimestamp between (startofday(start) .. startofday(end) -1s)
    | where EventName == "monacoworkbench/activateplugin"
    | where Properties.id == 'vscjava.migrate-java-to-azure'
    | where Properties.reason !in ('onStartupFinished') and Properties.reason !has 'pom.xml' and Properties.reason !has 'onLanguage:java'
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
    | project DevDeviceId, user_source, Date=bin(ServerUploadTimestamp,1d)
    )
    // MCP telemetry
    | union (
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where timestamp >= datetime(2025-07-31)
    | where operation_Name startswith 'java/migrateassistant'
    | extend dimensions = parse_json(customDimensions)
    | extend user_source = iff(tobool(dimensions.internal), 'internal', 'external')
    | extend DevDeviceId = tostring(dimensions.devdeviceid)
    | project DevDeviceId, user_source, Date=bin(timestamp,1d)
    )
    | summarize dcount(Date) by DevDeviceId, user_source
    | where dcount_Date >=2
    | project DevDeviceId, user_source, dcount_Date
}
```

```kusto
// Unique Java module (app) count from VSCode extension for Application Modernization
unique_app_vscode_records_helper(start:datetime, end:datetime)
{
    let migrationAppIds = cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | extend p = parse_json(Properties)
        | extend AppId = tostring(p['hashedappid'])
        | where isnotempty(AppId)
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | project Date=bin(ServerTimestamp,1d), AppId, user_source,DevDeviceId;
    let MCPmigrationAppIds = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name startswith 'java/migrateassistant'
        | extend dimensions = parse_json(customDimensions)
        | extend AppId = tostring(dimensions.hashedappid)
        | where isnotempty(AppId)
        | extend user_source = iff(tobool(dimensions.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), AppId, user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
    let appcatInVScodeAppIds = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-05-20)
        | where operation_Name == 'java/appcat/project'
        | extend dimensions = parse_json(customDimensions)
        | extend callerId = tostring(dimensions.callerid)
        | where callerId has "vscjava.migrate-java-to-azure"
        | extend AppId = tostring(dimensions.project_identity)
        | where isnotempty(AppId)
        | extend data = parse_json(message)
        | extend user_source=iff(tobool(data.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), AppId,user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
        union migrationAppIds,MCPmigrationAppIds, appcatInVScodeAppIds
}
```

```kusto
// Unique Java module (app) count from AppCAT CLI
unique_app_cli_records_helper(start:datetime, end:datetime)
{
    cluster('ddtelai').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where timestamp >= datetime(2025-05-20)
    | where operation_Name == 'java/appcat/project'
    | extend dimensions = parse_json(customDimensions)
    | extend appcatVersion = tostring(dimensions.appcatversion)
    | where appcatVersion != 'latest'
    | extend callerId = tostring(dimensions.callerid)
    | where callerId == 'appcat'
    | extend AppId = tostring(dimensions.project_identity)
    | where isnotempty(AppId)
    | extend data = parse_json(message)
    | extend user_source=iff(tobool(data.internal), 'internal', 'external')
    | project Date=bin(timestamp,1d), AppId,user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
}
```

```kusto
// Assessment run records used to count assessment users (VSCode + MCP)
assessment_run_records_helper(start:datetime, end:datetime)
{
    let assessment_run_data = 
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp  between (start .. (end - 1s))
    | where ServerTimestamp >= datetime(2025-05-20)
    | where ExtensionName has "migrate-java-to-azure"
    | where EventName has "java/migrateassistant/command"
    | extend command = tostring(Properties.command) 
    | where command in ('migrate.java.assessment')
    | project DevDeviceId, ServerTimestamp, ExtensionVersion
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(IsInternal == 1, 'internal', 'external')
    | project DevDeviceId, ServerTimestamp, user_source, ExtensionVersion
    // union users who trigger assessment by copilot chat
    | union (
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool == 'assessApplication'
        | project DevDeviceId, ServerTimestamp, ExtensionVersion
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(IsInternal == 1, 'internal', 'external')
        | project DevDeviceId, ServerTimestamp, user_source, ExtensionVersion
    )
    // union users in MCP mode
    | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-29)
        | where operation_Name has "java/migrateassistant/appcat/"
        | extend message = parse_json(message)
        | extend user_source = iff(tobool(message.internal), 'internal', 'external')
        | extend dimensions = parse_json(customDimensions)
        | extend DevDeviceId = tostring(dimensions.devdeviceid), ServerTimestamp= timestamp
        | project DevDeviceId, ServerTimestamp, user_source
    );
    assessment_run_data
    | project DevDeviceId, ServerTimestamp, user_source, ExtensionVersion
}
```

```kusto
// Code accept events in VSCode Copilot panel
code_accept_records_helper(start:datetime, end:datetime)
{
    let users = materialize (
        cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').migration_plan_records_helper(start,end)
        | distinct DevDeviceId
    );
    let CopilotchatRawEvents =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. end)
        | where ExtensionName == 'GitHub.copilot-chat'
        | where DevDeviceId in (users);
    let ConversationDetails = materialize(
        CopilotchatRawEvents
        | where EventName == "github.copilot-chat/toolcalldetails"
        | where Properties has "createMigrationPlan" or (Properties has 'appmod-run-task' and ServerTimestamp >= datetime(2025-07-31))
        | project conversationId = tostring(Properties.conversationid), Properties.toolcounts, DevDeviceId
        | distinct conversationId, DevDeviceId
    );
    let PanelRequests = 
        CopilotchatRawEvents
        | where EventName == "github.copilot-chat/panel.request"
        | project requestId = tostring(Properties.requestid), conversationId = tostring(Properties.conversationid), DevDeviceId;
    let PanelFeedback = 
        CopilotchatRawEvents
        | where EventName == "github.copilot-chat/panel.edit.feedback"
        | project outcome = tostring(Properties.outcome), requestId = tostring(Properties.requestid), hasRemainingEdits = tobool(Properties.hasremainingedits), DevDeviceId;
    // Join conversation details with panel requests
    let ConversationWithRequests = materialize(
        ConversationDetails
        | join kind=leftouter PanelRequests on conversationId, DevDeviceId
        | distinct requestId, DevDeviceId
    );
    // Join with panel feedback
    let FeedbackWithRequests = materialize(
        ConversationWithRequests
        | join kind=leftouter PanelFeedback on requestId
    );
    // Join with fact_user_isinternal table
    FeedbackWithRequests
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(IsInternal == 1, 'internal', 'external')
    | distinct requestId, outcome, hasRemainingEdits, user_source, DevDeviceId
    | extend outcome = iif(isempty(outcome), 'Implicit accepted', iif(hasRemainingEdits, 'partially accepted', outcome))
    | project DevDeviceId, requestId, outcome, user_source, hasRemainingEdits
}
```

```kusto
// Migration (code remediation) records used to count migration users
migration_records_helper(start:datetime, end:datetime)
{
    let users_java_project =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-08-10)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "java/migrateassistant/projectsize"
        | extend AppId = tostring(Properties['hashedappid'])
        | distinct DevDeviceId;
    let command_event = 
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "java/migrateassistant/command"
        | where tostring(Properties.command) in ('migrate.java.formula.run', 'java.migrateassistant.handleMigrate')
        | extend migrateaction=tostring(Properties.migrateaction), migrateby = tostring(Properties.migrateby)
        | where migrateaction == 'migrate' and migrateby != "upgrade"
        | extend source = tostring(Properties.source)
        | extend source = iff(isempty(source), 'unknown', source)
        | project source, ServerTimestamp,VSCodeSessionId, DevDeviceId,Properties, ExtensionVersion
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | extend  isJava = iff(parse_version(ExtensionVersion) >= parse_version("1.3.0"), DevDeviceId in (users_java_project), true)
        | where isJava == true
        | project source, ServerTimestamp,VSCodeSessionId, DevDeviceId, user_source,Properties,ExtensionVersion;
    let command_event_sessionIds =
        command_event 
        | distinct VSCodeSessionId;
    let vscodetool_sole_event =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool has 'createMigrationPlan'
        | project Properties, ServerTimestamp,VSCodeSessionId, DevDeviceId
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | where VSCodeSessionId !in (command_event_sessionIds)
        | project source="copilotChat", ServerTimestamp,VSCodeSessionId, DevDeviceId, user_source,Properties;
    let mcp_sole_event =
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp  between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name == "java/migrateassistant/tool/invoke"
        | extend properties = parse_json(customDimensions)
        | extend invokedToolId = tostring(properties["invokedtoolid"])
        | where invokedToolId has 'appmod-run-task'
        | extend DevDeviceId = tostring(properties.devdeviceid)
        | extend user_source  = iff(tobool(properties.internal), 'internal', 'external')
        | project properties, ServerTimestamp=timestamp, DevDeviceId,user_source, callersessionid=tostring(properties.callersessionid),operation_ParentId, correlationId = tostring(properties.correlationid)
        | extend VSCodeSessionId = iff(isnotempty(callersessionid), callersessionid, operation_ParentId)
        | where VSCodeSessionId !in (command_event_sessionIds) 
        | project source="copilotChat", ServerTimestamp,VSCodeSessionId, DevDeviceId, user_source,Properties=properties;
    union command_event, vscodetool_sole_event, mcp_sole_event
}
```

```kusto
// Unique apps assessed
unique_app_assess_records_helper(start:datetime, end:datetime)
{
    let assessAppIds = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-05-20)
        | where operation_Name == 'java/appcat/project'
        | extend dimensions = parse_json(customDimensions)
        | extend callerId = tostring(dimensions.callerid)
        | where callerId has "vscjava.migrate-java-to-azure" or callerId == "appcat"
        | extend AppId = tostring(dimensions.project_identity)
        | extend appcatVersion = tostring(dimensions.appcatversion)
        | where appcatVersion != 'latest'
        | where isnotempty(AppId)
        | extend data = parse_json(message)
        | extend user_source=iff(tobool(data.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), AppId,user_source;
    assessAppIds
}
```

```kusto
// Unique apps with code remediation
unique_app_code_remediation_records_helper(start:datetime, end:datetime)
{
    let latest_query = migration_records_with_appid_helper(start,end) | project Date=bin(ServerTimestamp,1d), AppId, user_source;
        // before 2025-8-26, we only have below data, we can deprecate below query on 2025-09-23
    let migrationAppIds_toDeprecate = cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure" and EventName has "java/migrateassistant/formula/apply"
        | extend p = parse_json(Properties)
        | extend AppId = tostring(p['hashedappid'])
        | where isnotempty(AppId)
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | project Date=bin(ServerTimestamp,1d), AppId, user_source;
    let MCPmigrationAppIds_toDeprecate = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name startswith 'java/migrateassistant/formula/apply' or operation_Name startswith "java/migrateassistant/kb/applied"
        | extend dimensions = parse_json(customDimensions)
        | extend AppId = tostring(dimensions.hashedappid)
        | where isnotempty(AppId)
        | extend user_source = iff(tobool(dimensions.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), AppId, user_source;
        union latest_query,migrationAppIds_toDeprecate,MCPmigrationAppIds_toDeprecate
}
```

```kusto
// Unique apps with generated assessment reports
unique_app_assessmentreport_records_helper(start:datetime, end:datetime)
{
    let validAppTable = 
    cluster('ddtelai').database('Copilot').RawEventsTraces
    | where timestamp between (start .. end)
    | where operation_Name == "java/appcat/project"
    | extend AppId = tostring(customDimensions.project_identity)
    | where isnotempty(AppId)
    | extend DevDeviceId=tostring(customDimensions.devdeviceid)
    | project operation_Id,AppId, Date=bin(timestamp,1d),DevDeviceId,customDimensions;
    let reportTable = 
        cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. end)
        | where operation_Name == 'java/appcat/report'
        | distinct operation_Id;
    validAppTable
    | extend callerid = tostring(customDimensions.callerid)
    | where callerid == 'appcat' or callerid has "migrate-java-to-azure"
    | where operation_Id in (reportTable)
    | extend appcatVersion = tostring(customDimensions.appcatversion)
    | where appcatVersion != 'latest'
    | project AppId, DevDeviceId,Date
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(IsInternal == 1, 'internal', 'external')
    | project user_source, AppId,DevDeviceId,Date
}
```

```kusto
// Assessment run records from both CLI and VSCode, used to count users
assessment_run_records_cli_vscode_helper(start:datetime, end:datetime)
{
    let appcat_cli_occurences = 
    cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/command'
    | extend data = parse_json(message)
    | extend command = tostring(data.message)
    | where command == 'analyze'
    | extend dimensions = parse_json(customDimensions)
    | extend appcatVersion = tostring(dimensions.appcatversion)
    | where appcatVersion != 'latest'
    | extend status = tostring(dimensions.status)
    | where status == 'start'
    | extend callerid = tostring(dimensions.callerid)
    | where callerid == 'appcat'
    | project ServerTimestamp=timestamp, DevDeviceId=tostring(dimensions.devdeviceid)
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(IsInternal == 1, 'internal', 'external')
    | project ServerTimestamp, DevDeviceId, user_source;
    let assessment_run_data = 
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp  between (start .. (end - 1s))
    | where ServerTimestamp >= datetime(2025-05-20)
    | where ExtensionName has "migrate-java-to-azure"
    | where EventName has "java/migrateassistant/command"
    | extend command = tostring(Properties.command) 
    | where command in ('migrate.java.assessment')
    | project DevDeviceId, ServerTimestamp, ExtensionVersion
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(IsInternal == 1, 'internal', 'external')
    | project DevDeviceId, ServerTimestamp, user_source, ExtensionVersion
    // union users who trigger assessment by copilot chat
    | union (
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool == 'assessApplication'
        | project DevDeviceId, ServerTimestamp, ExtensionVersion
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(IsInternal == 1, 'internal', 'external')
        | project DevDeviceId, ServerTimestamp, user_source, ExtensionVersion
    )
    // union users in MCP mode
    | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-29)
        | where operation_Name has "java/migrateassistant/appcat/"
        | extend message = parse_json(message)
        | extend user_source = iff(tobool(message.internal), 'internal', 'external')
        | extend dimensions = parse_json(customDimensions)
        | extend DevDeviceId = tostring(dimensions.devdeviceid), ServerTimestamp= timestamp
        | project DevDeviceId, ServerTimestamp, user_source
    );
    union assessment_run_data,appcat_cli_occurences
    | project DevDeviceId, ServerTimestamp, user_source, ExtensionVersion
}
```

```kusto
// Migration plan records for tracking migration plan generation activity
migration_plan_records_helper(start:datetime, end:datetime)
{
    let agent_event =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool == 'createMigrationPlan'
        | extend AppId = tostring(Properties['hashedappid'])
        | project Properties, ServerTimestamp,VSCodeSessionId, DevDeviceId,AppId
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | project ServerTimestamp, DevDeviceId, user_source,AppId,Properties;
    let mcp_event =
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp  between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name == "java/migrateassistant/tool/invoke"
        | extend properties = parse_json(customDimensions)
        | extend invokedToolId = tostring(properties["invokedtoolid"])
        | where invokedToolId == 'appmod-run-task'
        | extend DevDeviceId = tostring(properties.devdeviceid)
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(tobool(IsInternal), 'internal', 'external')
        | extend AppId = tostring(properties.hashedappid)
        | project Properties=properties, ServerTimestamp=timestamp, DevDeviceId,user_source, AppId;
    union agent_event,mcp_event
}
```

```kusto
// Start assessment occurrences (CLI + VSCode)
start_assessment_occurrence_cli_vscode_helper(start:datetime, end:datetime)
{
    let appcat_cli_occurences = 
        cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
        | where timestamp between (start .. end)
        | where operation_Name == 'java/appcat/command'
        | extend data = parse_json(message)
        | extend command = tostring(data.message)
        | where command == 'analyze'
        | extend dimensions = parse_json(customDimensions)
        | extend appcatVersion = tostring(dimensions.appcatversion)
        | where appcatVersion != 'latest'
        | extend status = tostring(dimensions.status)
        | where status == 'start'
        | extend callerid = tostring(dimensions.callerid)
        | where callerid == 'appcat'
        | extend user_source=iff(tobool(customDimensions.internal), 'internal', 'external')
        | project ServerTimestamp=timestamp, DevDeviceId=tostring(dimensions.devdeviceid), user_source;
    let vscode_occurences = 
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp  between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "java/migrateassistant/command"
        | extend command = tostring(Properties.command) 
        | where command in ('migrate.java.assessment')
        | project DevDeviceId, ServerTimestamp, ExtensionVersion
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(IsInternal == 1, 'internal', 'external')
        | project DevDeviceId, ServerTimestamp,user_source;
    union appcat_cli_occurences, vscode_occurences;
}
```

```kusto
// Successful assessment completions (CLI + VSCode) used to count occurrences
assessment_success_occurrence_cli_vscode_helper(start:datetime, end:datetime)
{
        let validAppTable = 
        cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. end)
        | where operation_Name == "java/appcat/project"
        | extend AppId = tostring(customDimensions.project_identity)
        | where isnotempty(AppId)
        | extend DevDeviceId=tostring(customDimensions.devdeviceid)
        | distinct  operation_Id;
        cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
        | where timestamp between (start .. end)
        | where operation_Name == 'java/appcat/report'
        | extend appcatVersion = tostring(customDimensions.appcatversion)
        | where appcatVersion != 'latest'
        | extend user_source=iff(tobool(customDimensions.internal), 'internal', 'external')
        | where operation_Id in (validAppTable)
        | extend callerid = tostring(customDimensions.callerid)
        | where callerid == 'appcat' or callerid has "migrate-java-to-azure"
        | distinct DevDeviceId=tostring(customDimensions.devdeviceid), user_source, operation_Id
}
```

```kusto
// Build fix output records (VSCode + MCP); latest per correlationId
buildfix_output_records_helper(start:datetime, end:datetime)
{
    let rawData = materialize (
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "javamigrationcopilot/buildfix/output"
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(tobool(IsInternal1), 'internal', 'external')
        | extend success = iff(tostring(Properties.result) == "SUCCEEDED", true, false)
        | extend timestamp = ServerTimestamp, mode = 'non-mcp'
        | extend moduleId = tostring(Properties.hashedappid)
        // MCP telemetry
        | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp > datetime(2025-07-01)
        | where operation_Name == "java/migrateassistant/buildFix/output"
        | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
        | extend success = iff(tostring(customDimensions.result)=="success", true, false)
        | extend DevDeviceId = tostring(customDimensions.devdeviceid), mode = 'mcp'
        | extend correlationId = tostring(customDimensions.correlationid)
        | extend moduleId = tostring(customDimensions.hashedappid)
        )
        | project timestamp, DevDeviceId,correlationId,moduleId, user_source, success,mode
    );
    rawData
    | where isnotempty(correlationId)
    | summarize arg_max(timestamp,*) by correlationId
    | union (
        rawData
        | where isempty( correlationId)
    )
}
```

```kusto
// Validate: CVE fix output (MCP)
cvefix_records_helper(start:datetime, end:datetime)
{
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp > datetime(2025-07-01) and timestamp between (start .. (end - 1s))
    | where operation_Name == "java/migrateassistant/cveFix/output"
    | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
    | extend success = iff(tostring(customDimensions.result)=="success", true, false)
    | extend DevDeviceId = tostring(customDimensions.devdeviceid)
    | distinct  DevDeviceId, success,user_source,timestamp 
}
```

```kusto
// Validate: unit test fix output (MCP)
utfix_records_helper(start:datetime, end:datetime)
{
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp > datetime(2025-07-01) and timestamp between (start .. (end - 1s))
    | where operation_Name == "java/migrateassistant/testFix/output"
    | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
    | extend success = iff(tostring(customDimensions.result)=="success", true, false)
    | extend DevDeviceId = tostring(customDimensions.devdeviceid)
    | distinct  DevDeviceId, success,user_source,timestamp 
}
```

```kusto
// Adoption users (union of success/accept signals)
adoption_user_helper(start:datetime, end:datetime)
{
    // assessment report generated
    let assessmentReportUsers = assessment_success_occurrence_cli_vscode_helper(start,end);
    // build fix succeeded
    let buildfixSuccessUsers = buildfix_output_records_helper(start,end) | where success;
    // code proposal not rejected
    let codeAcceptUsers = code_accept_records_helper(start, end) | where outcome != 'rejected';
    // UT passed
    let utPassedUsers = utfix_records_helper(start,end) | where success;
    // cve check passed
    let cvefixPassedUsers = cvefix_records_helper(start,end) | where success;
    // consistency check passed
    let consistencyPassedUsers = consistencycheck_records_helper(start,end) | where success;
    union assessmentReportUsers, buildfixSuccessUsers,codeAcceptUsers,utPassedUsers,cvefixPassedUsers,consistencyPassedUsers
    | project DevDeviceId,user_source
}
```

```kusto
// Assessment success (VSCode only)
assessment_success_occurrence_vscode_helper(start:datetime, end:datetime)
{
        let validAppTable = 
        cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. end)
        | where operation_Name == "java/appcat/project"
        | extend AppId = tostring(customDimensions.project_identity)
        | where isnotempty(AppId)
        | extend callerid = tostring(customDimensions.callerid)
        | where callerid has "vscjava.migrate-java-to-azure"
        | extend DevDeviceId=tostring(customDimensions.devdeviceid)
        | distinct  operation_Id;
        cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
        | where timestamp between (start .. end)
        | where operation_Name == 'java/appcat/report'
        | extend appcatVersion = tostring(customDimensions.appcatversion)
        | where appcatVersion != 'latest'
        | extend callerid = tostring(customDimensions.callerid)
        | where callerid has "vscjava.migrate-java-to-azure"
        | extend user_source=iff(tobool(customDimensions.internal), 'internal', 'external')
        | where operation_Id in (validAppTable)
        | distinct DevDeviceId=tostring(customDimensions.devdeviceid), user_source, operation_Id
}
```

```kusto
// Validate: consistency check results (MCP)
consistencycheck_records_helper(start:datetime, end:datetime)
{
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp > datetime(2025-07-01) and timestamp between (start .. (end - 1s))
    | where operation_Name == "java/migrateassistant/consistency/output"
    | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
    | extend result = parse_json(tostring(customDimensions.result))
    | extend success = iff(result.critical == 0 and result.major == 0, true, false)
    | extend DevDeviceId = tostring(customDimensions.devdeviceid)
    | distinct  DevDeviceId, success,user_source,timestamp 
}
```

```kusto
// Unique app: average developers per app
avg_users_per_app_helper(start:datetime, end:datetime)
{
    union unique_app_vscode_records_helper(start,end), unique_app_cli_records_helper(start,end)
    | summarize DistinctDevelopers = dcount(DevDeviceId) by AppId
    | summarize AvgDevelopersPerApp = avg(DistinctDevelopers), MaxDevelopersPerApp = max(DistinctDevelopers)
}
```

```kusto
// Project size (legacy mapping)
project_size_helper(start:datetime, end:datetime)
{
    cluster('ddtelai').database('Copilot').RawEventsTraces
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/project'
    | extend dimensions = parse_json(customDimensions)
    | extend val = tolong(dimensions.project_scale)
    | where isnotempty( val)
    | extend ProjectSize = case (
        val > 100000,
        "Extra Large (>100K lines)",
        val > 15000 and val <= 100000,
        "Large (15K-100K lines)",
        val > 5000 and val <= 15000,
        "Medium (5K-15K lines)",
        val > 200 and val <= 5000,
        "Small (200-5K lines)",
        val <=200,
        "Tiny (<=200 lines)",
        "unknown"
    )
    | summarize ["Project count"]=count() by ProjectSize
}
```

```kusto
// Project size (new mapping; joins to hashed project id)
project_size_new_helper(start:datetime, end:datetime)
{
    cluster('ddtelai').database('Copilot').RawEventsTraces
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/project'
    | extend val = tolong(customDimensions.project_scale)
    | extend callerId = tostring(customDimensions.callerid)
    | where callerId has "vscjava.migrate-java-to-azure" or callerId == "appcat"
    | where isnotempty( val)
    | project val, operation_Id
    | join kind=inner  (
        cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. end)
        | where operation_Name == 'java/appcat/project'
        | extend val = tolong(customDimensions.project_scale),  project_id = tostring(customDimensions.hashed_project_id)
        | where isnotempty( project_id)
        | project project_id,operation_Id,val, timestamp
    ) on operation_Id
    | project-away operation_Id1
    | extend ProjectSize = case (
            val > 100000,
            "Extra Large (>100K lines)",
            val > 15000 and val <= 100000,
            "Large (15K-100K lines)",
            val > 5000 and val <= 15000,
            "Medium (5K-15K lines)",
            val > 200 and val <= 5000,
            "Small (200-5K lines)",
            val <=200,
            "Tiny (<=200 lines)",
            "unknown"
        )
    | distinct ProjectSize, project_id
}
```

```kusto
// Buildfix start (VSCode + MCP)
start_buildfix_users_helper(start:datetime, end:datetime)
{
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. (end - 1s))
    | where ServerTimestamp >= datetime(2025-05-20)
    | where ExtensionName has "migrate-java-to-azure"
    | where EventName has "javamigrationcopilot/buildfix"
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(tobool(IsInternal1), 'internal', 'external')
    | extend timestamp = ServerTimestamp
    // MCP telemetry
    | union (
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where timestamp > datetime(2025-07-01)
    | where operation_Name has "java/migrateassistant/buildfix"
    | extend dimensions = parse_json(customDimensions)
    | extend DevDeviceId = tostring(customDimensions.devdeviceid)
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(tobool(IsInternal1), 'internal', 'external')
    )
    | distinct timestamp,DevDeviceId, user_source,type = "Buildfix start"
}
```

```kusto
// Modules per project (VSCode + Copilot)
modules_per_project_helper(start:datetime, end:datetime)
{
    let modulesInfo = materialize (
        cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
        | where operation_Name has "java/migrateassistant" or operation_Name has "java/appcat"
        | where timestamp between (start .. end)
        | extend projectId = tostring(customDimensions.hashedprojectid), moduleId = tostring(customDimensions.hashedappid)
        | where isnotempty(projectId) and isnotempty(moduleId)
        | project DevDeviceId = tostring(customDimensions.devdeviceid), moduleId,projectId
        | union (
            cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
            | where ServerTimestamp between (start .. (end - 1s))
            | where ServerTimestamp >= datetime(2025-08-10)
            | where ExtensionName has "migrate-java-to-azure"
            | where EventName has "java/migrateassistant/projectsize"
            | extend projectId = tostring(Properties.hashedprojectid), moduleId = tostring(Properties.hashedappid), correlationId = tostring(Properties['correlationid'])
            | where isnotempty(projectId) and isnotempty(moduleId)
            | project DevDeviceId, moduleId,projectId
        )
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | project-away  DevDeviceId1
    );
    modulesInfo    
    | summarize  ModuleCount = dcount(moduleId) by projectId,user_source
    | union (
        modulesInfo
        | summarize  ModuleCount = dcount(moduleId) by projectId
        | extend user_source = "total"
    )
}
```

```kusto
// Build success (VSCode + MCP) with dedup by correlationId
build_success_records_helper(start:datetime, end:datetime)
{
    let rawData = materialize (
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "javamigrationcopilot/buildfix/output"
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(tobool(IsInternal1), 'internal', 'external')
        | extend success = iff(tostring(Properties.result) == "SUCCEEDED", true, false)
        | extend timestamp = ServerTimestamp, mode = 'non-mcp'
        | extend result = tostring(Properties.result)
        // MCP telemetry, buildfix output
        | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp > datetime(2025-07-01)
        | where operation_Name == "java/migrateassistant/buildFix/output"
        | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
        | extend result = tostring(customDimensions.result)
        | extend success = iff(tostring(customDimensions.result) has "success", true, false)
        | extend DevDeviceId = tostring(customDimensions.devdeviceid), mode = 'mcp'
        | extend correlationId = tostring(customDimensions.correlationid)
        )
        // MCP telemetry, build events
        | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp > datetime(2025-07-01)
        | where operation_Name == "java/migrateassistant/buildFix/build"
        | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
        | extend result = tostring(customDimensions.result)
        | extend success = iff(tostring(customDimensions.result) has "success", true, false)
        | extend DevDeviceId = tostring(customDimensions.devdeviceid), mode = 'mcp'
        | extend correlationId = tostring(customDimensions.correlationid)
        )
        | project timestamp, DevDeviceId,correlationId, user_source, success,mode,result
    );
    rawData
    | where isnotempty(correlationId)
    | summarize arg_max(timestamp,*) by correlationId
    | union (
        rawData
        | where isempty( correlationId)
    )
}
```

```kusto
// Migration events with AppId (joins VSCode + MCP)
migration_records_with_appid_helper(start:datetime, end:datetime)
{
    let java_project_info =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-08-10)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "java/migrateassistant/projectsize"
        | extend AppId = tostring(Properties['hashedappid']), correlationId = tostring(Properties['correlationid'])
        | distinct DevDeviceId,AppId,correlationId;
    let command_event = 
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "java/migrateassistant/command"
        | where tostring(Properties.command) in ('migrate.java.formula.run', 'java.migrateassistant.handleMigrate')
        | extend migrateaction=tostring(Properties.migrateaction), migrateby = tostring(Properties.migrateby)
        | where migrateaction == 'migrate' and migrateby != "upgrade"
        | extend source = tostring(Properties.source)
        | extend source = iff(isempty(source), 'unknown', source)
        | project source, ServerTimestamp,VSCodeSessionId, DevDeviceId,Properties, ExtensionVersion, correlationId = tostring(Properties['correlationid'])
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | extend  isJava = iff(parse_version(ExtensionVersion) >= parse_version("1.3.0"), DevDeviceId in (java_project_info | project DevDeviceId), true)
        | where isJava == true
        | join kind=leftouter (java_project_info) on correlationId
        | project source, ServerTimestamp,VSCodeSessionId, DevDeviceId, user_source,AppId,Properties,ExtensionVersion;
    let command_event_sessionIds =
        command_event 
        | distinct VSCodeSessionId;
    let agent_sole_event =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool has 'createMigrationPlan'
        | extend AppId = tostring(Properties['hashedappid'])
        | project Properties, ServerTimestamp,VSCodeSessionId, DevDeviceId,AppId
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | where VSCodeSessionId !in (command_event_sessionIds)
        | project source="copilotChat", ServerTimestamp,VSCodeSessionId, DevDeviceId, user_source,AppId,Properties;
    let mcp_sole_event =
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp  between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name == "java/migrateassistant/task/run"
        | extend DevDeviceId = tostring(customDimensions.devdeviceid)
        | project customDimensions, ServerTimestamp=timestamp, DevDeviceId, callersessionid=tostring(customDimensions.callersessionid),operation_ParentId, AppId = tostring(customDimensions.hashedappid)
        | extend VSCodeSessionId = iff(isnotempty(callersessionid), callersessionid, operation_ParentId)
        | where VSCodeSessionId !in (command_event_sessionIds) 
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | project source="copilotChat", ServerTimestamp,VSCodeSessionId, DevDeviceId,AppId, user_source,Properties=customDimensions;
    union command_event, agent_sole_event, mcp_sole_event
}
```

```kusto
// Build results with AppId (VSCode + MCP)
build_result_records_with_appid_helper(start:datetime, end:datetime)
{
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "javamigrationcopilot/buildfix/output"
        | extend success = iff(tostring(Properties.result) == "SUCCEEDED", true, false)
        | extend timestamp = ServerTimestamp, mode = 'non-mcp'
        | extend result = tostring(Properties.result)
        // MCP telemetry, buildfix output
        | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp > datetime(2025-07-01)
        | where operation_Name == "java/migrateassistant/buildFix/output"
        | extend result = tostring(customDimensions.result)
        | extend success = iff(tostring(customDimensions.result) has "success", true, false)
        | extend DevDeviceId = tostring(customDimensions.devdeviceid), mode = 'mcp'
        | extend correlationId = tostring(customDimensions.correlationid)
        | extend AppId = tostring(customDimensions.hashedappid),VSCodeSessionId = tostring(customDimensions.callersessionid)
        )
        // MCP telemetry, build events
        | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp > datetime(2025-07-01)
        | where operation_Name == "java/migrateassistant/buildFix/build"
        | extend result = tostring(customDimensions.result)
        | extend success = iff(tostring(customDimensions.result) has "success", true, false)
        | extend DevDeviceId = tostring(customDimensions.devdeviceid), mode = 'mcp'
        | extend correlationId = tostring(customDimensions.correlationid)
        | extend AppId = tostring(customDimensions.hashedappid),VSCodeSessionId = tostring(customDimensions.callersessionid)
        )
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(tobool(IsInternal1), 'internal', 'external')
        | project timestamp, DevDeviceId,correlationId,AppId, user_source, success,mode,result, VSCodeSessionId
}
```

```kusto
// CVE fix results with AppId (MCP)
cvefix_result_records_with_appid_helper(start:datetime, end:datetime)
{
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp > datetime(2025-07-01) and timestamp between (start .. (end - 1s))
    | where operation_Name == "java/migrateassistant/cveFix/output"
    | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
    | extend success = iff(tostring(customDimensions.result)=="success", true, false)
    | extend DevDeviceId = tostring(customDimensions.devdeviceid)
    | extend correlationId = tostring(customDimensions.correlationid)
    | extend AppId = tostring(customDimensions.hashedappid)
    | project DevDeviceId, success,user_source,timestamp,AppId,correlationId, VSCodeSessionId = tostring(customDimensions.callersessionid)
}
```

```kusto
// Unit test fix results with AppId (MCP)
utfix_result_records_with_appid_helper(start:datetime, end:datetime)
{
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp > datetime(2025-07-01) and timestamp between (start .. (end - 1s))
    | where operation_Name == "java/migrateassistant/testFix/output"
    | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
    | extend success = iff(tostring(customDimensions.result)=="success", true, false)
    | extend DevDeviceId = tostring(customDimensions.devdeviceid)
    | extend AppId = tostring(customDimensions.hashedappid)
    | extend correlationId = tostring(customDimensions.correlationid)
    | project DevDeviceId, success,user_source,timestamp,AppId,correlationId,VSCodeSessionId = tostring(customDimensions.callersessionid)
    | union (
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp > datetime(2025-07-01)
        | where operation_Name == "java/migrateassistant/testFix/test"
        | extend result = tostring(customDimensions.result)
        | extend success = iff(tostring(customDimensions.result) has "success", true, false)
        | extend DevDeviceId = tostring(customDimensions.devdeviceid), mode = 'mcp'
        | extend correlationId = tostring(customDimensions.correlationid)
        | extend AppId = tostring(customDimensions.hashedappid)
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source = iff(IsInternal == 1, 'internal', 'external')
        | project DevDeviceId, success,user_source,timestamp,AppId,correlationId,VSCodeSessionId = tostring(customDimensions.callersessionid)
        )
}
```

```kusto
// Unique projects from CLI
unique_project_cli_records_helper(start:datetime, end:datetime)
{
    cluster('ddtelai').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where timestamp >= datetime(2025-05-20)
    | where operation_Name == 'java/appcat/project'
    | extend dimensions = parse_json(customDimensions)
    | extend appcatVersion = tostring(dimensions.appcatversion)
    | where appcatVersion != 'latest'
    | extend callerId = tostring(dimensions.callerid)
    | where callerId == 'appcat'
    | extend projectId = tostring(dimensions.hashed_project_id)
    | where isnotempty(projectId)
    | extend data = parse_json(message)
    | extend user_source=iff(tobool(data.internal), 'internal', 'external')
    | project Date=bin(timestamp,1d), projectId,user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
}
```

```kusto
// Unique projects from VSCode
unique_project_vscode_records_helper(start:datetime, end:datetime)
{
    let migrationProjectIds = cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | extend projectId = tostring(Properties['hashedprojectid'])
        | where isnotempty(projectId)
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | project Date=bin(ServerTimestamp,1d), projectId, user_source,DevDeviceId;
    let MCPmigrationProjectIds = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name startswith 'java/migrateassistant'
        | extend projectId = tostring(customDimensions.hashedprojectid)
        | where isnotempty(projectId)
        | extend user_source = iff(tobool(customDimensions.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), projectId, user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
    let appcatInVScodeProjectIds = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-05-20)
        | where operation_Name == 'java/appcat/project'
        | extend callerId = tostring(customDimensions.callerid)
        | where callerId has "vscjava.migrate-java-to-azure"
        | extend projectId = tostring(customDimensions.hashed_project_id)
        | where isnotempty(projectId)
        | extend data = parse_json(message)
        | extend user_source=iff(tobool(data.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), projectId,user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
        union migrationProjectIds,MCPmigrationProjectIds, appcatInVScodeProjectIds
}
```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Use a bounded window with an effective end time to avoid current-day partials; daily bin via startofday.
```kusto
// Rolling 28-day window, excluding current day
let start = startofday(ago(28d));
let end   = startofday(now());          // effective end excludes today
source_table
| where Date >= start and Date < end
| summarize arg_max(DataIngestTimestamp, Count) by startofday(Date), UserSource
```

- Join template (rates and alignment)
  - Description: Align daily cohorts by Date and UserSource; use leftouter for denominators with missing numerators; coalesce after join.
```kusto
let A = Get28DayRollingAggregation(language="Java", modernizationType="migrate", name="Sessions_BuildStarted")
        | project Date, UserSource, DenomCount = Count;
let B = Get28DayRollingAggregation(language="Java", modernizationType="migrate", name="Sessions_BuildPassed")
        | project Date, UserSource, NumerCount = Count;
A
| join kind=leftouter B on Date, UserSource
| extend NumerCount = coalesce(NumerCount, 0)
| extend Rate = case(DenomCount == 0, 0.0, todouble(NumerCount) / todouble(DenomCount))
| project Date, UserSource, DenomCount, NumerCount, Rate
```

- De-dup pattern
  - Description: Keep the freshest daily slice per cohort using DataIngestTimestamp. Works for any metric column.
```kusto
RollingAggregation
| where Language == "C#" and ModernizationType == "migrate" and Name == "Users_MAU" and LookBackWindow == "28d"
| summarize arg_max(DataIngestTimestamp, Count) by UserSource, startofday(Date)
| project Date, UserSource, Count
```
```
// Distinct counts per day with dedup
some_helper_function()
| where isnotempty(user_source)
| where Date >= startofday(ago(28d))
| summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, startofday(Date)
```

- Important filters
  - Description: Standardized exclusion of internal/test cohorts, product scoping, and client ID filters.
```kusto
// Product scoping and internal/test exclusion for raw VS events
cluster('ddtelvsraw.kusto.windows.net').database('VS').RawEventsVSBlessed
| where Product == "appmod" and UserAlias !in (<InternalAliasWhitelist>)
| extend UserSource = iff(IsInternal, 'internal', 'external')

// Copilot conversation scoping
cluster('ddtelinsights.kusto.windows.net').database('DDTelInsights').Catalog_Events_IntelliCode_VSConversation
| where Properties["vs.copilot.clientid"] == "Microsoft.AppModernization"
| where UserAlias !in (<InternalAliasWhitelist>)
| extend UserSource = iff(IsInternal, 'internal', 'external')

// Cohort sanity
| where isnotempty(UserSource)
```

- Important definitions
  - Description: Build/Test/CVE rates as ratios of “passed” to “started”; guard against zero denominators; produce percent when needed.
```kusto
// Generic rate template
let denom = ... | project Date, UserSource, D = Count;
let numer = ... | project Date, UserSource, N = Count;
denom
| join kind=leftouter numer on Date, UserSource
| extend N = coalesce(N, 0)
| extend Rate = case(D == 0, 0.0, todouble(N) / todouble(D))
| extend RatePercent = round(Rate * 100, 2)
```

- ID parsing/derivation
  - Description: Extract keys from dynamic property bags; unify internal/external flag.
```kusto
source
| extend UserSource = iff(IsInternal, 'internal', 'external')
| extend Status           = tostring(Properties["status"])
| extend ErrorCode        = tostring(Properties["errorcode"])
| extend ExtensionVersion = tostring(Properties["extensionversion"])
| extend HashedAppId      = tostring(Properties["hashedappsolutionid"])
| extend DurationMs       = Measures["duration"]
```

- Sharded union
  - Description: Combine same-schema outputs across clusters; compute distribution percentiles; include total and cohort splits.
```kusto
let start = startofday(ago(28d));
let end   = startofday(now());
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

1) Get28DayRollingAggregation (standardized rolling aggregate layer)
- Description: Fetches daily counts for a given language, modernization type, and metric name from the RollingAggregation table, restricted to a 28-day lookback window and deduplicated per day via DataIngestTimestamp. Adapt by changing language/modernizationType/name.
```kusto
Get28DayRollingAggregation(language:string, modernizationType:string, name:string)
{
    RollingAggregation
    | where Language == language
        and ModernizationType == modernizationType
        and Name == name
        and LookBackWindow == "28d"
    | summarize arg_max(DataIngestTimestamp, Count) by UserSource, startofday(Date)
    | project Date, UserSource, Count
}
```

2) RawEventsVSBlessed (raw telemetry with default exclusions)
- Description: Pulls raw VS events for the Application Modernization product, excluding a curated internal alias whitelist and deriving standard properties. Adapt by modifying whitelist and property extraction.
```kusto
RawEventsVSBlessed()
{
    let whitelist = dynamic(["kuzhong","timong",
        "zhiszhan","xuycao","xiading","menxiao","xiada","dixue","zhiyongli","edburns","juniwang","jinghzhu","yiliu6","haital","rujche","sonwan","fangjimmy","v-ruitang","yili7","haiche","jiangma","ninpan","wepa","kaiqianyang","qiaolei","v-shilichen","feilonghuang","guitarsheng","v-muyaofeng","haochuang","yuwzho","ruodanxie","junbchen","jiahzhu","chenshi","linglingye","zhiyuanliang","emilyzhu","caiqing","zhujiayi","jinjiez","yuwe","v-ruitang","v-shilichen","v-muyaofeng",
        "yungez","lianw","wenhaozhang","zlhe","fenzho","haozhan","honc","yueli6","xiaofanzhou","wchi","qianwens","chentony",
        "jeffya","jessiehuang","jaeyonglee","xinyizhang","yulinshi","xinrzhu","yiqiu","zhshang","kevinguo","yangtony","seal","hangwan","taoxu","ellieyuan","jialuogan"
    ]);
    cluster('ddtelvsraw.kusto.windows.net').database('VS').RawEventsVSBlessed
    | where Product == "appmod" and UserAlias !in (whitelist)
    | extend UserSource = iff(IsInternal, 'internal', 'external'),
             Status = tostring(Properties["status"]),
             ErrorCode = tostring(Properties["errorcode"]),
             ExtensionVersion = tostring(Properties["extensionversion"]),
             HashedAppSolutionId = tostring(Properties["hashedappsolutionid"]),
             Duration = Measures["duration"]
}
```

3) Catalog_Events_IntelliCode_VSConversation (Copilot conversation filter)
- Description: Filters catalog events to Microsoft.AppModernization client, excludes internal alias whitelist, and sets UserSource. Adapt by changing client ID or extending additional properties.
```kusto
Catalog_Events_IntelliCode_VSConversation()
{
    let whitelist = dynamic(["kuzhong","timong",
        "zhiszhan","xuycao","xiading","menxiao","xiada","dixue","zhiyongli","edburns","juniwang","jinghzhu","yiliu6","haital","rujche","sonwan","fangjimmy","v-ruitang","yili7","haiche","jiangma","ninpan","wepa","kaiqianyang","qiaolei","v-shilichen","feilonghuang","guitarsheng","v-muyaofeng","haochuang","yuwzho","ruodanxie","junbchen","jiahzhu","chenshi","linglingye","zhiyuanliang","emilyzhu","caiqing","zhujiayi","jinjiez","yuwe","v-ruitang","v-shilichen","v-muyaofeng",
        "yungez","lianw","wenhaozhang","zlhe","fenzho","haozhan","honc","yueli6","xiaofanzhou","wchi","qianwens","chentony",
        "jeffya","jessiehuang","jaeyonglee","xinyizhang","yulinshi","xinrzhu","yiqiu","zhshang","kevinguo","yangtony","seal","hangwan","taoxu","ellieyuan","jialuogan"
    ]);
    cluster('ddtelinsights.kusto.windows.net').database('DDTelInsights').Catalog_Events_IntelliCode_VSConversation
    | where Properties["vs.copilot.clientid"] == "Microsoft.AppModernization" and UserAlias !in (whitelist)
    | extend UserSource = iff(IsInternal, 'internal', 'external')
}
```

4) dotnet_migrate_apps_28d_AverageUsers (ratio of users per app)
- Description: Computes average users per app by joining Users_MAU and Apps_All for C# migrate, dividing users by apps per day and cohort. Adapt by changing language, modernization type, or time window.
```kusto
Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Users_MAU")
| join kind=inner Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Apps_All") on Date, UserSource
| project Date, UserSource, Count = iff(Count1 == 0, 0.0, toreal(Count) / Count1)
| where Date >= ago(28d)
```

5) java_migrate_sessions_count_28d_assessreport (distinct session count with dedup)
- Description: Uses a helper that outputs count_ and user_source, filters to last 28 days, and deduplicates daily slices by arg_max(DataIngestTimestamp). Adapt by replacing the helper with other 28d functions.
```kusto
sessions_count_28d_assessreport
| where isnotempty(user_source)
| where Date >= startofday(ago(28d))
| summarize arg_max(DataIngestTimestamp, count_) by user_source, startofday(Date)
```

6) GetBuildSuccessRate (success rate computation)
- Description: Computes build success rate within a 28-day lookback using leftouter join and coalesce to handle missing numerator. Adapt by changing language and modernizationType.
```kusto
GetBuildSuccessRate(language:string, modernizationType:string)
{
    let buildStartedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Apps_BuildStarted")
        | project Date, UserSource, BuildStartedCount = Count);
    let buildPassedOverTime =
        materialize(Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Apps_BuildPassed")
        | project Date, UserSource, BuildPassedCount = Count);
    buildStartedOverTime
    | join kind=leftouter buildPassedOverTime on Date, UserSource
    | extend BuildPassedCount = coalesce(BuildPassedCount, 0)
    | extend SuccessRate = case(BuildStartedCount == 0, 0.0, todouble(BuildPassedCount) / todouble(BuildStartedCount))
    | extend SuccessRatePercent = round(SuccessRate * 100, 2)
    | project Date, language, modernizationType, UserSource, BuildStartedCount, BuildPassedCount, SuccessRate, SuccessRatePercent
}
```

7) java_consolidated_lines_of_code_per_project (cross-cluster union + percentiles)
- Description: Combines two sources across the ama4j cluster to compute p95/p90/p75 distributions of lines per project, emitting both total and cohort split. Adapt by changing helper functions or percentiles.
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

8) java_consolidated_sessions_count_28d_buildfix (sessions build started)
- Description: Uses the standardized Get28DayRollingAggregation view for Java migrate/upgrade sessions build starts, filters to rolling 28 days and non-empty UserSource. Adapt by switching Name to other session-level metrics.
```kusto
Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Sessions_BuildStarted')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

9) java_consolidated_module_per_project_p90 (distribution p90)
- Description: Pulls p90 per-project module counts for Java consolidated (migrate/upgrade) using RollingAggregation view over a 29-day window. Adapt by switching to p75/p95 or migrate/upgrade specific views.
```kusto
Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Apps_P90PerProject')
| where Date >= startofday(ago(29d))
```

## Additional Conventions for Raw Telemetry Sources
- Time columns by source:
  - Copilot (ddtelai.Copilot.RawEventsTraces): timestamp
  - VSCodeExt.RawEventsVSCodeExt: ServerTimestamp
  - VSCode.RawEventsVSCode: ServerUploadTimestamp
- Parameterized windowing pattern: between (start .. (end - 1s)) with 1d binning via bin(..., 1d)
- Internal vs external:
  - Prefer VSCodeInsights.fact_user_isinternal for VSCode-derived DevDeviceId; the join can expose IsInternal or IsInternal1 depending on dataset.
  - For Copilot traces, use customDimensions.internal or message.internal
- MCP vs non-MCP signals:
  - Use correlationId to deduplicate multiple outputs for the same operation (e.g., buildFix/build vs buildFix/output)
  - VSCodeSessionId vs callersessionid/operation_ParentId are used to align events across sources
- Cutover/backfill start dates (per engineering sources): 2025-05-20 (initial VSCode/AppCAT), 2025-07-29/2025-07-31 (MCP telemetry), 2025-08-10 (projectsize events)

## Reasoning Notes (only if uncertain)
- Timezone: Not specified; adopted UTC for safety. If data is in a regional time zone, align startofday() accordingly.
- Ingestion freshness: DataIngestTimestamp usage implies multi-slice per day. We assume arg_max is the canonical dedup for daily metrics to avoid stale slices.
- MEU/MAU meaning: Names appear (Users_MAU, Users_MEU) but exact business definitions are not stated. We treat them as distinct user metrics and do not apply any transformations beyond filtering and dedup.
- Internal/external cohorts: Both denylist and IsInternal exist. We adopt UserSource = iff(IsInternal, 'internal', 'external') and additionally exclude whitelist in raw event views.
- Helpers: Several helper functions (avg_users_per_app_helper, project_size_helper, modules_per_project_helper) are referenced without bodies. We assume they return pre-aligned data with Date and user_source fields suitable for summarization; avoid inferring their internal schemas beyond visible usage.
- Effective end day: Some helper queries set end = startofday(now()). We adopt excluding current day as a conservative completeness guard unless explicitly proven otherwise.
- Sharded union normalization: We assume consistent columns across helpers when union-ing; when mismatches occur, normalize column names and types before summarize.

## Canonical Tables

Below are the canonical tables referenced by this product’s queries. Where possible, schema details are retrieved via the adx-mcp-server get_table_schema tool. If schema retrieval fails, columns are inferred from actual query usage and clearly called out as inferred.

### Table: RollingAggregation (appmod.westus2.kusto.windows.net/Consolidation)
- Priority: Normal
- What this table represents:
  - Aggregated metrics (fact table) computed from raw telemetry via predefined Kusto functions.
  - Rows represent daily snapshots of specific metric “Name” values grouped by UserSource; zero rows generally indicate no activity recorded for that metric/day.
- Freshness expectations:
  - Unknown. Queries consistently use startofday and arg_max(DataIngestTimestamp), implying daily snapshots and freshness tied to ingestion time. Avoid relying on current-day partial data without checking ingestion completeness.
- When to use:
  - Tracking 28-day rolling counts for Users, Apps, Sessions (e.g., Users_MAU/MEU, Apps_BuildStarted/Passed, Sessions_*).
  - Comparing success rates (build/test/CVE) across UserSource by joining different metric “Name” series.
  - Consolidated metrics across Java/.NET and migrate/upgrade modalities using Get28DayRollingAggregation.
- When to avoid:
  - Event-level analyses (status, error codes, durations, extension versions) — use raw event tables.
  - Sub-day or near-real-time detail; this is daily aggregated data.
  - If you need per-entity identifiers (AppId, DevDeviceId, projectId), use helper functions/views built on raw.
- Similar tables & how to choose:
  - RawEventsVSBlessed: use for detailed Visual Studio event telemetry and property-level fields.
  - Catalog_Events_IntelliCode_VSConversation: use for Copilot/IntelliCode conversation-level events and client attributes.
  - Decision rule: Use RollingAggregation for metric counts/time series; use raw tables to drill into per-event context.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(UserSource)
  - Language in ('Java', 'C#')
  - ModernizationType in ('migrate', 'upgrade', 'migrate/upgrade')
  - Name startswith one of ('Users_', 'Apps_', 'Sessions_')
  - LookBackWindow == '28d'
- Table columns:
  - Schema access note: get_table_schema failed (SEM0100: Failed to resolve table or column expression named 'RollingAggregation'). Columns below are inferred from query usage and may be incomplete.
  
  | Column              | Type      | Description or meaning |
  |---------------------|-----------|------------------------|
  | Language            | string    | Programming language dimension (e.g., Java, C#). Used for segmenting metrics. |
  | ModernizationType   | string    | Scenario dimension (migrate, upgrade, migrate/upgrade). |
  | Name                | string    | Metric identifier (e.g., Users_MAU, Apps_BuildStarted, Sessions_CvePassed). Drives the metric series. |
  | LookBackWindow      | string    | Rolling window marker (e.g., '28d'). |
  | Date                | datetime  | Metric date (daily granularity). Queries use startofday(Date). |
  | UserSource          | string    | 'internal' or 'external' cohort; used for segmentation and joins. |
  | Count               | long      | Aggregated count for the metric on the given Date/UserSource. Used in joins and success rate calculations. |
  | DataIngestTimestamp | datetime  | Ingestion marker used in arg_max to select the latest snapshot per day. |
- Column Explain:
  - Language and ModernizationType: always filter by these to pick the correct metric family for Java vs .NET and migrate vs upgrade scenarios.
  - Name: choose the right metric series (Users_*, Apps_*, Sessions_*). Examples: Apps_BuildStarted, Users_MAU, Sessions_CvePassed.
  - Date: use startofday and restrict to a conservative window (e.g., last 28 days) to avoid partial ingestion issues.
  - UserSource: segment internal vs external; most dashboards require isnotempty(UserSource) and often join on Date, UserSource.
  - Count: the core value for charting and rate computations; coalesce to 0 when joining with missing counterpart series; cast to double/toreal for ratios.

---

### Table: cluster('ddtelvsraw.kusto.windows.net').database('VS').RawEventsVSBlessed
- Priority: Normal
- What this table represents:
  - Raw Visual Studio event telemetry for the “appmod” product, including user alias and internal/external classification.
  - Event-level facts; zero rows imply no events captured for filters applied.
- Freshness expectations:
  - Unknown. This is raw telemetry; ingestion can be near-real-time or batch. Be cautious with same-day analyses.
- When to use:
  - Filtering out internal test aliases (whitelisting) and focusing on external users.
  - Extracting event-level attributes like status, errorcode, extensionversion, durations from Properties/Measures.
  - Building funnels or detailed diagnostics that require per-event context.
- When to avoid:
  - High-level aggregate KPIs over time — prefer RollingAggregation or views that materialize aggregates.
  - Cross-tenant joins without proper ingestion windows and alias filtering.
- Similar tables & how to choose:
  - RollingAggregation: for daily aggregated counts.
  - Catalog_Events_IntelliCode_VSConversation: for Copilot conversation events; choose this when investigating Copilot client interactions.
- Common Filters:
  - Product == "appmod"
  - UserAlias !in whitelist (internal aliases list)
  - Derived UserSource = iff(IsInternal, 'internal', 'external')
  - Often extended fields extracted: Status, ErrorCode, ExtensionVersion, HashedAppSolutionId, Duration
- Table columns:
  - Schema access note: get_table_schema failed due to remote access denied (SEM0056). Columns below are inferred from query usage and may be incomplete.
  
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | Product        | string   | Product tag; filtered to "appmod". |
  | UserAlias      | string   | User identifier (UPN alias); used for whitelist-based filtering of internal users. |
  | IsInternal     | bool     | Marks internal telemetry; used to derive UserSource. |
  | Properties     | dynamic  | Bag of event attributes (e.g., ["status"], ["errorcode"], ["extensionversion"], ["hashedappsolutionid"]). |
  | Measures       | dynamic  | Numeric measures (e.g., ["duration"]). |
  | Timestamp      | datetime | Event time (typical in raw telemetry; not explicitly referenced but commonly present). |
- Column Explain:
  - Product and UserAlias: mandatory filters to restrict to appmod and exclude internal aliases.
  - IsInternal and derived UserSource: cohort segmentation for internal vs external analyses.
  - Properties/Measures: source for event-level fields (status/error/duration/version/app solution id) used in troubleshooting or experience mapping.
  - Timestamp: use with appropriate time windows if building event timelines (if available).

---

### Table: cluster('ddtelinsights.kusto.windows.net').database('DDTelInsights').Catalog_Events_IntelliCode_VSConversation
- Priority: Normal
- What this table represents:
  - Raw IntelliCode/Copilot conversation event telemetry in Visual Studio.
  - Event-level facts filtered to clientid == "Microsoft.AppModernization".
- Freshness expectations:
  - Unknown. As raw telemetry, ingestion cadence may vary; avoid current-day reliance without validation.
- When to use:
  - Identifying and segmenting conversation events specific to AppModernization client.
  - Deriving internal/external cohorts via IsInternal.
  - Correlating Copilot usage with modernization flows.
- When to avoid:
  - Aggregate KPI computation (counts over 28 days) — prefer RollingAggregation or views.
  - Non-Copilot/IntelliCode event analysis — use other raw event sources.
- Similar tables & how to choose:
  - RawEventsVSBlessed: broader raw event set; use when needing appmod product events not specific to Copilot client.
  - RollingAggregation: use for consolidated metrics over time.
- Common Filters:
  - Properties["vs.copilot.clientid"] == "Microsoft.AppModernization"
  - UserAlias !in whitelist (internal alias removal)
  - Derived UserSource = iff(IsInternal, 'internal', 'external')
- Table columns:
  - Schema access note: get_table_schema failed due to remote access denied (SEM0056). Columns below are inferred from query usage and may be incomplete.
  
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | Properties     | dynamic  | Event attributes; filtered on ["vs.copilot.clientid"]. |
  | UserAlias      | string   | User identifier; used to exclude internal aliases. |
  | IsInternal     | bool     | Marks internal telemetry; used to derive UserSource. |
  | Timestamp      | datetime | Event time (typical in raw telemetry; not explicitly referenced but commonly present). |
- Column Explain:
  - Properties["vs.copilot.clientid"]: primary filter to isolate AppModernization Copilot conversations.
  - UserAlias and IsInternal: used to create internal/external segmentation for adoption metrics.
  - Timestamp: use with appropriate time window constraints for event timelines (if present).

---

### Table: cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
- Priority: High
- What this table represents:
  - Copilot/agent telemetry events across AppMod scenarios (AppCAT, migrateassistant, buildFix/testFix/cveFix, consistency checks).
- Common time column: timestamp
- Common Filters:
  - operation_Name startswith/equals patterns for java/migrateassistant/* and java/appcat/*
  - Cutover time gates: >= 2025-07-29/2025-07-31 for MCP features
- Useful fields (inferred):
  - customDimensions (dynamic): contains internal, devdeviceid, callersessionid, correlationid, hashedappid, hashedprojectid, project_identity, appcatversion, etc.
  - message (string JSON): may contain { internal: bool, ... }
  - DevDeviceId (derived): tostring(customDimensions.devdeviceid)

---

### Table: cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
- Priority: High
- What this table represents:
  - VSCode extension telemetry for migrate-java-to-azure, including command invocations, tool calls, project sizing, and buildfix outputs.
- Common time column: ServerTimestamp
- Common Filters:
  - ExtensionName has "migrate-java-to-azure"
  - EventName has prefixes: java/migrateassistant/*, javamigrationcopilot/*
  - Join to VSCodeInsights.fact_user_isinternal on DevDeviceId
- Useful fields (inferred):
  - Properties (dynamic): e.g., command, migrateaction, migrateby, source, invokedtoolid, hashedappid, hashedprojectid, correlationid
  - DevDeviceId (string)
  - VSCodeSessionId (string)

---

### Table: cluster('ddtelvscode.kusto.windows.net').database('VSCode').RawEventsVSCode
- Priority: Normal
- What this table represents:
  - Core VSCode client telemetry used to detect extension activation (monacoworkbench/activateplugin) for migrate-java-to-azure.
- Common time column: ServerUploadTimestamp
- Common Filters:
  - EventName == "monacoworkbench/activateplugin" and Properties.id == 'vscjava.migrate-java-to-azure'
  - Properties.reason excludes startup or language-triggered activations

---

### Table: cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal
- Priority: High
- What this table represents:
  - Internal/external lookup for DevDeviceId. Exposes IsInternal/IsInternal1 (bool) in joins.
- When to use:
  - Always join for VSCode-derived DevDeviceId when computing cohort splits.

---

Guidance and defaults:
- Time windows: default to a conservative 28-day window using Date >= startofday(ago(28d)) for aggregates to avoid partial ingestion bias.
- Cohorts: always check isnotempty(UserSource) and apply internal alias whitelist removal when working with raw events.
- Ratios: cast counts to real/double and coalesce missing series to 0 before computing success rates.
- Timezone: unknown. Use startofday and avoid current-day metrics unless ingestion completeness is verified.
