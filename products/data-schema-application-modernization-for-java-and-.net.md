# Application Modernization for Java and .NET - Product and Data Overview Template

## 1. Product Overview

> Draft: Application Modernization for Java and .NET provides top-level product metrics built from aggregated telemetry derived via predefined Kusto functions. Dashboards summarize user, app, and session-level KPIs (e.g., build/test/CVE success rates) across Java and .NET modernization scenarios using standardized views over Azure Data Explorer datasets.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
> Application Modernization for Java and .NET
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples might include: "AppMod", "AMA4J", "AMA4NET". Please confirm official nicknames.
- **Kusto Cluster**:
> https://appmod.westus2.kusto.windows.net/
- **Kusto Database**:
> Consolidation
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

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

Guidance and defaults:
- Time windows: default to a conservative 28-day window using Date >= startofday(ago(28d)) for aggregates to avoid partial ingestion bias.
- Cohorts: always check isnotempty(UserSource) and apply internal alias whitelist removal when working with raw events.
- Ratios: cast counts to real/double and coalesce missing series to 0 before computing success rates.
- Timezone: unknown. Use startofday and avoid current-day metrics unless ingestion completeness is verified.
