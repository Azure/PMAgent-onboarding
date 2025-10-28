# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub provide real-time messaging services enabling websockets and publish-subscribe scenarios. This schema and playbook power analytics for OKR snapshots (ARR/revenue/subscriptions/consumption), usage metrics (connections/messages), service type growth (SignalR/WebPubSub/SocketIO), feature tracking (replicas, auto-scale, Blazor Server, Aspire, samples), customer segments (external/billable), top customers, retention, QoS/Manage RP quality, runtime requests, and Visual Studio integration telemetry.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
SignalR and Web PubSub
- Product Nick Names:
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
signalrinsights.eastus2
- Kusto Database:
SignalRBI
- Access Control:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# SignalR and Web PubSub - Kusto Query Playbook

## Overview
- Product: SignalR and Web PubSub
- Summary: Power BI report blocks using Azure Data Explorer Kusto queries for SignalR and Web PubSub, covering OKR snapshots (ARR/revenue/subscriptions/consumption), usage metrics (connections/messages), service type growth (SignalR/WebPubSub/SocketIO), feature tracking (replicas, auto-scale, Blazor Server, Aspire, samples), customer segments (external/billable), top customers, retention, QoS/Manage RP quality, runtime requests, and VS integration telemetry.
- Cluster: signalrinsights.eastus2
- Database: SignalRBI

## Conventions & Assumptions

- Time semantics
  - Canonical time columns observed:
    - Date: the primary date column for most fact tables (BillingUsage_Daily, ResourceMetrics, FeatureTrack*, ConnectionMode_Daily, ManageRPQosDaily, Runtime*).
    - env_time: Operation QoS and Connectivity QoS facts (OperationQoS_Daily, ConnectivityQoS_Daily).
    - AdvancedServerTimestampUtc: Visual Studio telemetry (WebTools_Raw).
    - TIMESTAMP/TimeStamp: used in a few survey/OKR snapshot sources (DeleteSurvey*, Cached_*_Snapshot).
  - Canonical Time Column: Date
    - Normalize with project or project-rename when needed:
      ```kusto
      // Align env_time to Date
      OperationQoS_Daily
      | project Date = env_time, *
      ```
  - Typical windows and bins:
    - Day: startofday() for exact day boundary, and comparisons like Date > ago(60d).
    - Week: startofweek(Date) for grouping and time-windowing.
    - Month: startofmonth(Date) and endofmonth(Date) for EoM alignment.
    - Rolling windows: rolling 7/28-day computed against the last available date (see freshness gates).
  - Timezone: Not specified; assume UTC.
  - Date filter requirement (must-have):
    - All queries must include an explicit time predicate on the canonical time column (Date or its alias).
    - Acceptable patterns include:
      - `where Date >= ago(<N>d)` for rolling lookbacks.
      - `where Date between (StartDate .. EndDate)` for explicit ranges.
      - `Date <= EndDate` when using an anchored EndDate (last ingested day).
    - Do not rely on dashboard defaults; always include the predicate in your KQL to prevent partial-period reads.


- Freshness & Completeness Gates
  - End-of-day anchor: Per product guidance (Issue #10), do not rely on two-region sentinel gating for end time. Anchor to the last ingested day from BillingUsage_Daily:
    ```kusto
    let EndDate = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
    // Use Date <= EndDate in subsequent filters
    ```
  - Week/Month completeness: Queries often limit to complete prior week/month windows (e.g., Date < startofweek(now()) or Date < startofmonth(now())).
  - Rolling gates: For QoS rolling 7/28-day, use the last ingested env_time (top 1 by time desc) as the anchor; compute rolling windows relative to that anchor.
  - Recommendation when uncertain: Avoid using current day; prefer the last confirmed complete day or the previous full week/month.

- Joins & Alignment
  - Frequent keys:
    - SubscriptionId (from ResourceId via parse).
    - ResourceId (sometimes normalized tolower(); sometimes de-replicated by trimming “/replicas/” suffix).
    - Region, SKU, CustomerType, BillingType, SegmentName.
  - Common joins:
    - leftouter for adding dimensions (SubscriptionMappings; RPSettingLatest).
    - inner to enforce existence/quality gates (e.g., MaxConnectionCount_Daily presence; match billing and metrics on same day).
    - fullouter mainly used for overlaying goals (cached snapshots joined with datatable goals).
  - Post-join hygiene:
    - Coalesce/select canonical columns and drop duplicates:
      ```kusto
      | extend Date = iif(isempty(Date), Date1, Date)
      | project-away Date1
      ```
    - Normalize cases:
      ```kusto
      | extend ResourceId = tolower(ResourceId)
      ```
    - Column collisions (SKU vs SKU1): When joining RPSettingLatest (which also has SKU) with BillingUsage_Daily, Kusto will auto-suffix duplicate column names (e.g., ‘SKU1’ from the right-hand side). Prefer explicit projection/rename to avoid ambiguity:
      ```kusto
      // Keep RPSettingLatest SKU after join
      | project SKU = iif(isempty(SKU1), SKU, SKU1), *
      | project-away SKU1
      ```

- Filters & Idioms
  - Service discriminators:
    - SignalR: ResourceId has 'microsoft.signalrservice/signalr'
    - Web PubSub (AWPS): ResourceId has 'microsoft.signalrservice/webpubsub'
    - SocketIO: RPSettingLatest.Kind == 'SocketIO'
  - Default exclusions:
    - Exclude internal test subs: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    - Exclude non-billing units: SKU !in ('MessageCount', 'MessageCountPremium') where intent is paid units/normalized revenue.
    - Manage QoS API allowlists: exclude 'UNCATEGORY' and various non-core APIs; construct allowlists via inner join on distinct ApiName where appropriate.
  - Cohort construction:
    - Build cohorts first (e.g., AI cohort by keywords in ResourceId) and then aggregate or join to facts to align with completeness gates.

- Cross-cluster/DB & Sharding
  - Cross-cluster examples:
    - Unionizer from cluster('armprodgbl.eastus'): ARM Requests.
    - WebTools_Raw from a different cluster (ddtelinsights).
  - Use fully-qualified references when needed:
    ```kusto
    cluster('armprodgbl.eastus').database('<Db>').Unionizer('Requests', 'HttpIncomingRequests')
    ```
  - Sharded EU vs Non-EU tables:
    - union RuntimeRequestsGroups_Daily with RuntimeRequestsGroups_EU_Daily, and RuntimeTransport_Daily with RuntimeTransport_EU_Daily, normalize keys (e.g., Metrics label fix-ups) before summarize.

- Table classes
  - Fact (daily/events):
    - BillingUsage_Daily, ResourceMetrics, MaxConnectionCount_Daily, OperationQoS_Daily, ConnectivityQoS_Daily, ManageRPQosDaily, FeatureTrack*_Daily, Runtime*_Daily, ConnectionMode_Daily, ManageResourceTags, RuntimeResourceTags_Daily, WebTools_Raw.
  - Snapshot (latest state, flows, precomputed “Total”):
    - Cached_*_Snapshot (OKR ARR/Revenue/Subscriptions/Consumption, Subs/Customer totals, TopCustomers, Resource/Subscription/Customer flows).
    - Retention snapshots: SubscriptionRetentionSnapshot, CustomerRetentionSnapshot, ResourceRetentionSnapshot; and AWPS equivalents.
  - Pre-aggregated vs. facts:
    - Use snapshots for “Total” KPIs and historical slicing (pre-joined dimensions).
    - Use facts for granular analysis (joins to dims, gating, customized cohorts).

- Important Mapping
  - OKR dashboards:
    - Income/ARR: Cached_*OKREstRevenue* + daily income derivations from BillingUsage_Daily.
    - Subscriptions: Cached_*OKRSubs* with goals overlay; daily/weekly/monthly breakdowns by SKU & service type.
    - Consumption: Cached_CuOKRConsumption* with goal overlays and daily derivations.
  - Feature tracking:
    - AutoScale via FeatureTrack_AutoScale_Daily + Premium filter.
    - Replicas via ResourceId contains '/replicas/'.
    - Aspire via RPSettingLatest.Extras has 'isAspire'.
    - SocketIO via RPSettingLatest.Kind == 'SocketIO' and Extras.socketIO.serviceMode.
  - Top customers:
    - Cached_TopSubscriptions_Snapshot enriched with CustomerModel, FeatureTrack_Daily, RuntimeResourceTags_Daily, and ConnectionMode_Daily.

## Entity & Counting Rules (Core Definitions)
- Entity model
  - Resource → Subscription → Customer
    - ResourceId (unique resource identity; normalize tolower(); derive PrimaryResource by trimming '/replicas/...').
    - SubscriptionId (parse from ResourceId path).
    - Customer: CloudCustomerGuid, plus CustomerModel dimensions (TPName, P360/TPID, CloudCustomerName).

## Views (Reusable Layers)
- None explicitly defined as Kusto views/functions in the provided content, though several database functions are referenced (e.g., ResourceFlow_Weekly/Monthly, SubscriptionFlow_Weekly/Monthly, CustomerFlow_Weekly/Monthly). Treat them as reusable server-side functions, and prefer calling them directly.

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Mandatory date filter (copy-paste skeleton)
    ```kusto
    // Always constrain time; replace StartDate/EndDate or use an `ago()` window.
    let EndDate = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
    let StartDate = EndDate - 27d; // example; parameterize as needed
    <FactTable>
    | where Date between (StartDate .. EndDate)
    ```

  - “Use last ingested day (no sentinel regions)”
    ```kusto
    // Purpose: Anchor analysis to the latest ingested day without region sentinels.
    let EndDate = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
    // Use Date <= EndDate in subsequent filters
    ```
  - Complete prior week/month window
    ```kusto
    // Purpose: Avoid partial current week/month for stable aggregates.
    let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
    // Week window
    | where Date >= datetime_add('week', -9, startofweek(Current)) and Date < startofweek(Current)
    // Month window
    | where Date >= datetime_add('month', -12, startofmonth(Current)) and Date < startofmonth(Current)
    ```
  - Rolling windows anchored to last ingested time
    ```kusto
    // Purpose: Rolling 7/28-day QoS anchored at last env_time.
    let anchor = toscalar(OperationQoS_Daily | top 1 by env_time desc | project env_time);
    OperationQoS_Daily
    | where env_time > anchor - 7d
    | summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=anchor, Type='Rolling7'
    ```

- Join template
  - “Attach subscription/customer dims and enforce quality via MaxConnectionCount_Daily”
    ```kusto
    // Purpose: Build per-subscription facts with dims; require existence in metrics for quality.
    let base =
        BillingUsage_Daily
        | where Date >= ago(60d)
        | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
        | extend SubscriptionId = tostring(SubscriptionId), ResourceId = tolower(ResourceId);
    base
    | join kind=inner (
        MaxConnectionCount_Daily
        | where Date >= ago(60d)
        | summarize count() by Date, SubscriptionId
    ) on Date, SubscriptionId
    | join kind=leftouter SubscriptionMappings on SubscriptionId
    | project-away SubscriptionId1
    ```

- De-dup pattern
  - Distinct entities per window with accuracy
    ```kusto
    // Purpose: Distinct counts with precision parameter for large sets.
    | summarize ResourceCnt = dcount(ResourceId, 3), SubscriptionCnt = dcount(SubscriptionId, 3)
      by Week = startofweek(Date), CustomerType
    ```
  - Rank-and-pick latest snapshot per period
    ```kusto
    // Purpose: Choose the latest run per Month/Week.
    ChurnCustomers_Monthly
    | order by Month asc, RunDay desc
    | extend Rank = row_number(1, prev(Month) != Month)
    | where Rank == 1
    ```
  - De-replica aggregation
    ```kusto
    // Purpose: Count replicas once per primary resource.
    | extend IsReplicas = ResourceId has "/replicas/"
    | extend PrimaryResource = iif(IsReplicas, substring(ResourceId, 0, indexof(ResourceId, "/replicas/")), ResourceId)
    | summarize ResourceCount = dcountif(ResourceId, IsReplicas) + dcountif(PrimaryResource, IsReplicas)
    ```

- Important filters
  - Internal/test exclusion
    ```kusto
    // Purpose: Exclude team/internal subscriptions.
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    ```
  - Paid units only
    ```kusto
    // Purpose: Focus on non-message “paid unit” SKUs.
    | where SKU in ('Free','Standard','Premium') // or exclude MessageCount SKUs
    ```
  - Service type gating
    ```kusto
    // Purpose: Identify service families.
    | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
             IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
    ```
  - AI cohort
    ```kusto
    // Purpose: Identify AI-related resources.
    | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml'
       or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
    ```

- Important Definitions
  - Active resource: HasConnection = MaxConnectionCount > 0 on the given Date.
  - LiveRatio (resource activity):
    - Week: ActiveDays < 3 → 'Swift'; else 'Occasional'
    - Month: ActiveDays < 3 → 'Swift'; ActiveDays < 10 → 'Occasional'; else 'Dedicate'
  - New/Retained subscription (Top lists):
    - IsNew = StartDate > startofday(now(), -28/29)
    - IsRetained = EndDate >= startofday(now(), -3)

- ID parsing/derivation
  ```kusto
  // Purpose: Derive SubscriptionId from ARM ResourceId.
  | parse ResourceId with "/subscriptions/" SubscriptionId:string "/resourceGroups/" *
  ```
  ```kusto
  // Purpose: Normalize ResourceId (lowercase) and remove replica suffix for primaries.
  | extend ResourceId = tolower(ResourceId)
  | extend PrimaryResource =
      iif(ResourceId has "/replicas/", substring(ResourceId, 0, indexof(ResourceId, "/replicas/")), ResourceId)
  ```

- Sharded union
  ```kusto
  // Purpose: Merge EU and non-EU shards, normalize labels, and aggregate.
  let NonEU = RuntimeRequestsGroups_Daily
      | where Date > ago(60d) and Category != 'Transport';
  let EU = RuntimeRequestsGroups_EU_Daily
      | where Date > ago(60d) and Category != 'Transport';
  NonEU
  | union EU
  | extend Metrics = iif(Category == 'RestApiScenario' and (Metrics startswith 'v1' and Metrics !contains 'HubProxy'),
                         replace_string(Metrics, 'v1', 'v1-HubProxy'), Metrics)
  | summarize ResourceCount = dcount(ResourceId), RequestCount = sum(RequestCount) by Date, Category, Metrics
  ```

- Usage → Revenue mapping (abstracted)
  ```kusto
  // Purpose: Compute normalized revenue; use placeholders for per-unit prices.
  let PriceFree = 0.0;
  let PriceStandard = <PriceStandard>;   // e.g., 1.61
  let PricePremium = <PricePremium>;     // e.g., 2.0
  let PriceDefault = <PriceDefault>;     // fallback
  | extend Revenue = case(
        SKU == 'Free',      PriceFree * Quantity,
        SKU == 'Standard',  PriceStandard * Quantity,
        SKU == 'Premium',   PricePremium * Quantity,
                            PriceDefault * Quantity
    )
  ```

## Example Queries (with explanations)

1) OKR Income (Daily, by Service and Segment; with MaxConnection gating)
- Description: Computes daily income from BillingUsage_Daily for the last 30 days, excluding MessageCount SKUs and internal subscriptions; enforces quality by requiring matching entries in MaxConnectionCount_Daily; classifies records into SignalR vs WebPubSub and summarizes totals. Output is pivot-friendly with a Service dimension across Total/SignalR/WebPubSub.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium') and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) | project Date, Role = tolower(Role))
    on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr',
         isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
         Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', <PriceStandard>, SKU == 'Premium', <PricePremium>, <PriceDefault>) * Quantity
| summarize Income = sum(Revenue) by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind = leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU, CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1])
| union (
    raw
    | summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU = ' JOIN(OR)', CustomerType, SegmentName
    | extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
    | mv-expand kind = array Temp
    | project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1])
)
```

2) Subscription counts by SKU and service type (Daily)
- Description: Builds per-subscription indicators for service type (SignalR/WebPubSub) and SKU flags, joins to MaxConnectionCount_Daily to ensure presence, then emits multi-slice counts (OR/AND, per service family). Adapt time window or cohort as needed.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr',
         isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
         isFree = SKU == 'Free', isStandard = SKU == 'Standard', isPremium = SKU == 'Premium'
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) | summarize count() by Date, SubscriptionId) on Date, SubscriptionId
| join kind = leftouter SubscriptionMappings on SubscriptionId
| extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
| summarize isAsrs = max(isAsrs), isAwps = max(isAwps), isFree = max(isFree), isStandard = max(isStandard), isPremium = max(isPremium)
    by Date, SubscriptionId, SegmentName, UsageType;
// Example slice: Premium
raw
| where isPremium
| summarize OrJoin = dcount(SubscriptionId, 4),
          AndJoin = dcountif(SubscriptionId, isAwps and isAsrs, 4),
          Asrs = dcountif(SubscriptionId, isAsrs, 4),
          Awps = dcountif(SubscriptionId, isAwps, 4)
    by Date, SKU = 'Premium', SegmentName, UsageType
| extend Temp = pack(' JOIN(OR)', OrJoin, ' JOIN(AND)', AndJoin, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, UsageType, SegmentName, Service = tostring(Temp[0]), SubscriptionCnt = toint(Temp[1])
```

3) AI cohort subscriptions (28-day rolling, Monthly anchor)
- Description: Computes 28-day rolling counts of AI cohort subscriptions (keyword-based) anchored to the last ingested day (no sentinel regions). Produces month-aligned points and overlays goals if needed. Adapt keywords or rolling window (DoM) per cohort definition.
```kusto
let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
let DoM = 28d;
let LatestPeriod = BillingUsage_Daily
| where Date > Current - DoM and Date <= Current
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
| extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
         IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
         Month = startofday(Current)
| summarize SubscriptionCnt = dcount(SubscriptionId), SignalR = dcountif(SubscriptionId, IsSignalR, 4), WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
// Previous rolling month for comparison
let LatestPeriodBeforeLast = BillingUsage_Daily
| where Date > Current - 2*DoM and Date <= Current - DoM
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
| extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
         IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
         Month = startofday(Current) - 1h
| summarize SubscriptionCnt = dcount(SubscriptionId), SignalR = dcountif(SubscriptionId, IsSignalR, 4), WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
LatestPeriod | union LatestPeriodBeforeLast
```

4) Resource totals with “HasConnection”
- Description: Derives EndDate as the last ingested day (no sentinel regions), derives per-resource SKU/Region, joins metrics to compute HasConnection (MaxConnectionCount>0), then counts distinct resources per day by SKU/Region and connection status. Adapt service family filter as needed.
```kusto
let EndDate = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
BillingUsage_Daily
| where Date > ago(61d) and Date <= EndDate and ResourceId has 'microsoft.signalrservice/signalr'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| summarize SKU = max(SKU), Region = max(Region) by Date, ResourceId
| join kind = leftouter ResourceMetrics on Date, ResourceId
| extend HasConnection = iif(isempty(ResourceId1), false, MaxConnectionCount > 0)
| summarize Total = dcount(ResourceId) by Date, SKU, Region, HasConnection
```

5) Top subscriptions (enriched)
- Description: Starts from Cached_TopSubscriptions_Snapshot for the service family, enriches with CustomerModel, runtime tags (App Service/Proxy/StaticApps), feature signals (sticky, scale limit, multi-endpoints), and connection mode (serverless/server mode). Produces a customer-rich slice for deep dives. Adapt service, lookback, and feature joins as needed.
```kusto
let label = 'microsoft.signalrservice/signalr';
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| extend IsNew = StartDate > startofday(now(), -29), IsRetained = EndDate >= startofday(now(), -3)
| join kind = inner CustomerModel on SubscriptionId
| project SubscriptionId, Revenue, MaxConnection, Messages=MessageCount, Rate, CloudCustomerName, CustomerType, TPName, BillingType, OfferName, OfferType, P360_ID, IsRetained, IsNew,
         C360Url = strcat('https://cxp.azure.com/cxobserve/customers/ch:customer::tpid:',TPID,'/summary')
| join kind = leftouter (
    RuntimeResourceTags_Daily
    | where Date > startofday(now(), -29) and ServiceType == 'SignalR'
    | summarize IsAppService = max(IsAppService), UseProxy = max(IsProxy), IsStaticApps = max(IsStaticApps) by SubscriptionId
) on SubscriptionId
| join kind = leftouter (
    FeatureTrack_Daily
    | where Date > startofday(now(), -29) and ResourceId has '/signalr/'
    | extend SubscriptionId = tostring(split(ResourceId, '/')[2])
    | summarize ServerSticky = sumif(RequestCount, Feature == 'ServerSticky'),
                NeededScale = sumif(RequestCount, Feature == 'ConnectionCountLimitReached'),
                MultiEndpoints = sumif(RequestCount, Feature == 'MultiEndpoints') by SubscriptionId
) on SubscriptionId
| extend ServerSticky = ServerSticky > 0, NeededScale = NeededScale > 0, MultiEndpoints = MultiEndpoints > 0
| join kind = leftouter (
    ConnectionMode_Daily
    | where Date > startofday(now(), -29) and ResourceId has '/signalr/'
    | extend SubscriptionId = tostring(split(ResourceId, '/')[2])
    | summarize IsServerless = sum(ServerlessConnection) > 0, IsServerMode = sum(ProxyConnection) > 0 by SubscriptionId
) on SubscriptionId
| project-away SubscriptionId1, SubscriptionId2, SubscriptionId3
```

6) Service usage (Weekly aggregates for SignalR)
- Description: Aggregates ResourceMetrics into weekly totals for MaxConnectionCount, MessageCount, and AvgConnectionCount by CustomerType, ServiceMode, and BillingType; enriches with RPSettingLatest for service mode and SubscriptionMappings for dims. Adapt label/filters for WebPubSub/SocketIO.
```kusto
let label = 'microsoft.signalrservice/signalr';
ResourceMetrics
| where Date >= startofweek(now(), -26) and Date < startofweek(now()) and ResourceId has label
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
| extend ResourceId = iif(ResourceId has 'replicas', tolower(substring(ResourceId, 0, indexof(ResourceId, '/replicas/'))), tolower(ResourceId))
| join kind = leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
| join kind = inner SubscriptionMappings on SubscriptionId
| extend ServiceMode = iif(isempty(ServiceMode), 'Default', ServiceMode)
| summarize MaxConnectionCount = sum(MaxConnectionCount), MessageCount = sum(SumMessageCount), AvgConnectionCount = sum(AvgConnectionCount)
    by Date, CustomerType, ServiceMode, BillingType
| summarize MaxConnectionCount = max(MaxConnectionCount), MessageCount = sum(MessageCount), AvgConnectionCount = max(AvgConnectionCount)
    by Week = startofweek(Date), CustomerType, ServiceMode, BillingType
| extend dims = pack_array('MaxConnectionCount', 'MessageCount', 'AvgConnectionCount'),
         vals = pack_array(MaxConnectionCount, MessageCount, AvgConnectionCount)
| mv-expand MetricsType = dims to typeof(string), Value = vals to typeof(long)
| project Week, CustomerType, ServiceMode, BillingType, MetricsType, Value
```

7) Manage RP QoS with internal allowlist
- Description: Computes QoS for manage APIs after constructing a core-API allowlist by joining to distinct ApiName over the last 30 days and excluding non-core categories. Outputs daily QoS by Region and Overall. Adapt the allowlist logic and CustomerType for SignalR vs Web PubSub.
```kusto
let CoreApiList = toscalar(
    ManageRPQosDaily
    | where Date > ago(30d) and CustomerType in ('SignalR','') and ApiName !in ('INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription') and ApiName !contains 'acs' and ApiName !contains 'acis' and ApiName !in ('Internal-ACIS','UNCATEGORY')
    | summarize make_set(ApiName)
);
ManageRPQosDaily
| where Date > ago(43d)
| where ApiName in (CoreApiList)
| summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count), TotalRequest = sum(Count) by Date, Region
| union (
    ManageRPQosDaily
    | where Date > ago(43d) and ApiName in (CoreApiList)
    | summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count), TotalRequest = sum(Count) by Date, Region='Overall'
)
```

8) Runtime requests daily (EU/non-EU union + transport)
- Description: Unions sharded daily runtime requests (excluding 'Transport'), normalizes Metrics for RestApiScenario, and unions transport signals from RuntimeTransport tables with synthetic Category='Transport'. Summarizes ResourceCount and RequestCount by Date. Extend to additional regions as needed.
```kusto
RuntimeRequestsGroups_Daily
| where Date > ago(60d) and ResourceCount > 10 and RequestCount > 200 and Category != 'Transport'
| union (RuntimeRequestsGroups_EU_Daily | where Date > ago(60d) and ResourceCount > 10 and RequestCount > 200 and Category != 'Transport')
| extend Metrics = iif(Category == 'RestApiScenario' and (Metrics startswith 'v1' and Metrics !contains 'HubProxy'), replace_string(Metrics, 'v1', 'v1-HubProxy'), Metrics)
| union (
    RuntimeTransport_Daily
    | union RuntimeTransport_EU_Daily
    | where Date > ago(60d)
    | extend Metrics = strcat(Framework, '-', Transport)
    | summarize ResourceCount = dcount(ResourceId), RequestCount = sum(RequestCount) by Date, Category = 'Transport', Metrics
)
```

9) Retention snapshot (Monthly)
- Description: Computes monthly retention for subscriptions by crossing a generated month series with snapshot intervals [StartDate, EndDate], counting retained and total, and emitting a retention Ratio. Swap to Customer or Resource snapshots and adapt window length as needed.
```kusto
let initTime = datetime_add('year', -1, startofmonth(now()));
range x from 0 to 12 step 1
| extend RangeMonth = datetime_add('month', -1*x, startofmonth(now())), fakeKey = 1
| join kind = inner (
    SubscriptionRetentionSnapshot
    | where StartDate >= initTime
    | extend StartMonth = startofmonth(StartDate), fakeKey = 1
) on fakeKey
| extend Periods = datetime_diff('month', RangeMonth, StartMonth)
| where StartMonth <= RangeMonth and EndDate >= RangeMonth
| summarize Retain = dcount(SubscriptionId) by StartMonth, Periods
| join kind = inner (
    SubscriptionRetentionSnapshot
    | where StartDate >= initTime
    | extend StartMonth = startofmonth(StartDate)
    | distinct StartMonth, SubscriptionId, EndDate
    | summarize Total = dcount(SubscriptionId) by StartMonth
) on StartMonth
| project Month = StartMonth, Periods, Total, Retain, Ratio = 1.0*Retain/Total, Category = 'Subscription'
```

10) SocketIO Serverless resources (last 28 days, weekly by SKU)
- Description: Counts distinct SocketIO resources operating in Serverless mode over the last 28 days, grouped weekly by SKU. Note: when joining RPSettingLatest with BillingUsage_Daily, use SKU1 to refer to the RPSettingLatest SKU (or explicitly project/rename).
```kusto
// Preferred generic anchor: last ingested day
let EndDate = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
let StartDate = EndDate - 27d;
let raw = RPSettingLatest
| where ResourceId has '/Microsoft.SignalRService/WebPubSub/' and Kind == 'SocketIO'
| join kind = inner (
    BillingUsage_Daily
    | where Date between (StartDate .. EndDate)
) on ResourceId
| extend ServiceMode = extract_json('$.socketIO.serviceMode', Extras, typeof(string))
| project Week = startofweek(Date), ResourceId, SKU = iif(isempty(SKU1), SKU, SKU1), ServiceMode;
raw
| where ServiceMode =~ 'Serverless'
| summarize ServerlessCount = dcount(ResourceId) by Week, SKU
```
// Alternative fixed anchor if ingestion metadata is unavailable
```kusto
let EndDate = startofday(now(), -1);
let StartDate = EndDate - 27d;
// ... same as above
```

## Reasoning Notes (only if uncertain)
- Timestamp timezone: Not stated; adopt UTC to avoid ambiguity. Alternative: enforce a product-specific timezone if provided elsewhere.
- Revenue multipliers: Concrete values are present in queries; however, per guidance, we abstract with placeholders (<PriceStandard>, <PricePremium>, <PriceDefault>) to avoid hardcoding sensitive rates. Alternative: define via a config table/function.
- End-of-day anchoring: Per team request, use the last ingested day (top 1 by Date desc) instead of multi-region sentinel gating when setting EndDate in daily queries.
- Inner joins to MaxConnectionCount_Daily: Used to ensure activity/existence; we adopt the pattern for quality gating. Alternative: use leftouter with additional checks if MaxConnectionCount_Daily is sparse in some regions.
- AI cohort detection: Keyword-based in ResourceId; we adopt the exact keyword set. Alternative: maintain a centralized cohort list to reduce false positives.
