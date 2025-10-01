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

- Freshness & Completeness Gates
  - End-of-day completeness: Many queries derive an EndDate by requiring at least two sentinel regions (e.g., australiaeast and westeurope) to report, ensuring last-day completeness before inclusion.
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
  - Standard grouping levels:
    - Day/Week/Month windows via startof{day|week|month} on Date.
    - Dimensions: Region, SKU, ServiceMode/Kind, CustomerType, BillingType, SegmentName.

- Counting rules and definitions
  - Active resource:
    - HasConnection: MaxConnectionCount > 0 on the same Date.
    - LiveRatio:
      - Week: ActiveDays < 3 → 'Swift'; else 'Occasional'
      - Month: ActiveDays < 3 → 'Swift'; ActiveDays < 10 → 'Occasional'; else 'Dedicate'
  - Subscription/Customer distinct counts use dcount with accuracy 3 or 4.
  - Retention:
    - New/Retained Top subscriptions: IsNew if StartDate > startofday(now(), -28/29), IsRetained if EndDate >= startofday(now(), -3).
  - AI cohort:
    - ResourceId contains any of: 'gpt', 'ai', 'ml', 'cognitive', 'openai', 'chatgpt'.

## Views (Reusable Layers)
- None explicitly defined as Kusto views/functions in the provided content, though several database functions are referenced (e.g., ResourceFlow_Weekly/Monthly, SubscriptionFlow_Weekly/Monthly, CustomerFlow_Weekly/Monthly). Treat them as reusable server-side functions, and prefer calling them directly.

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - “Use last complete day across sentinel regions”
    ```kusto
    // Purpose: Anchor analysis to the latest complete day where both sentinel regions reported.
    let Sentinels = dynamic(['australiaeast','westeurope']);
    let EndDate =
        toscalar(
            BillingUsage_Daily
            | where Date > ago(10d) and Region in (Sentinels)
            | summarize Regions = dcount(Region) by Date
            | where Regions >= array_length(Sentinels)
            | top 1 by Date desc
            | project Date
        );
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
- Description: Computes 28-day rolling counts of AI cohort subscriptions (keyword-based) anchored to the last complete day using separate sentinel region anchors for EU vs Non-EU. Produces month-aligned points and overlays goals if needed. Adapt keywords or rolling window (DoM) per cohort definition.
```kusto
let NonEU = BillingUsage_Daily | where Region == 'australiaeast' | top 1 by Date desc | project Date;
let EU    = BillingUsage_Daily | where Region == 'westeurope'   | top 1 by Date desc | project Date;
let Current = toscalar(NonEU | union EU | top 1 by Date asc);
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

4) Resource totals with completeness gate and “HasConnection”
- Description: Ensures complete last day via sentinel regions, derives per-resource SKU/Region, joins metrics to compute HasConnection (MaxConnectionCount>0), then counts distinct resources per day by SKU/Region and connection status. Adapt sentinel regions or service family filter.
```kusto
let EndDate = toscalar(
    BillingUsage_Daily
    | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
    | summarize counter = dcount(Region) by Date
    | where counter >= 2
    | top 1 by Date desc
    | project Date
);
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

## Reasoning Notes (only if uncertain)
- Timestamp timezone: Not stated; adopt UTC to avoid ambiguity. Alternative: enforce a product-specific timezone if provided elsewhere.
- Revenue multipliers: Concrete values are present in queries; however, per guidance, we abstract with placeholders (<PriceStandard>, <PricePremium>, <PriceDefault>) to avoid hardcoding sensitive rates. Alternative: define via a config table/function.
- Completeness gates: Two sentinel regions are used (australiaeast, westeurope) as a proxy for completeness; we assume they’re sufficient sentinels. Alternative: expand to more regions or use a system ingest health signal.
- Inner joins to MaxConnectionCount_Daily: Used to ensure activity/existence; we adopt the pattern for quality gating. Alternative: use leftouter with additional checks if MaxConnectionCount_Daily is sparse in some regions.
- AI cohort detection: Keyword-based in ResourceId; we adopt the exact keyword set. Alternative: maintain a centralized cohort list to reduce false positives.
- Replica handling: Counting replicas and primaries by trimming “/replicas/”; adopt that for premium-only scenarios. Alternative: compute at SKU-agnostic level as needed.
- Distinct counting precision: dcount uses precision 3 or 4 in queries; we keep these defaults. Alternative: use exact summarize by ... | distinct ... when scale permits.
- SocketIO service mode detection: Extras JSON extraction for serviceMode; we assume schema stability. Alternative: guard with try_cast/extract_json() fallback defaults.

## Canonical Tables

Canonical Tables for SignalR and Web PubSub (signalrinsights.eastus2.SignalRBI)

Notes and defaults
- Timezone and refresh delay: unknown. Be careful with current-day data; prefer using startofday/startofweek/startofmonth and lag by at least 1 day when building KPIs.
- Common filters across queries:
  - Time window: Date >= ago(30d) for daily; startofweek(now(), -N) for weekly; startofmonth(now(), -N) for monthly.
  - Service scoping: ResourceId has 'microsoft.signalrservice/signalr' for SignalR; ResourceId contains '/webpubsub/' for Web PubSub; use cluster-agnostic contains if needed.
  - Exclude internal team subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) or SignalRTeamInternalSubscriptionIds.
  - SKU scoping: SKU in ('Free','Standard','Premium'); explicitly exclude message SKUs where noted ('MessageCount','MessageCountPremium').
  - Join keys: Date and ResourceId for usage/metrics joins; SubscriptionId for customer segmentation joins.
- Similar tables & sharding: many metrics have Weekly/Monthly "Snapshot" counterparts; choose the snapshot partition aligned to your visualization granularity (daily vs weekly vs monthly) and join SubscriptionMappings for segmentation.

High Priority Tables

### Table name: Cached_ZnOKRARR_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: OKR ARR snapshot by month for SignalR and Web PubSub. Zero rows imply no snapshot for a month; do not infer deletion.
- Freshness expectations: Monthly snapshot; queries join datatable growth goals and project TimeStamp. Use startofmonth windowing; avoid same-day reads.
- When to use / When to avoid:
  - Use for ARR goal overlays and OKR tracking on monthly axes.
  - Use as a base for fullouter joins with datatable goals to fill goal lines.
  - Avoid per-day revenue; switch to BillingUsage_Daily-derived revenue.
- Similar tables & how to choose: Cached_DtOKRARR_Snapshot (Dt) for broader month ranges; stay consistent with your goal series source.
- Common Filters: TimeStamp >= startofmonth(now(), -35) for rolling 35 months.
- Table columns:

| Column    | Type     | Description or meaning |
|-----------|----------|------------------------|
| TimeStamp | datetime | Month bucket of ARR snapshot |
| SignalR   | real     | ARR value (SignalR) |
| WebPubSub | real     | ARR value (Web PubSub) |

- Column Explain:
  - TimeStamp: align to end-of-month for charting; use startofday(endofmonth(Date)) in joins.
  - SignalR/WebPubSub: aggregate ARR; used in fullouter joins against goal series.

### Table name: BillingUsage_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Daily billing usage records per resource. The core fact table for quantity and revenue calculations; zero rows for a day imply no billable activity.
- Freshness expectations: Daily ingestion; most queries use the last 30–60 days and exclude team subscriptions.
- When to use / When to avoid:
  - Use to compute revenue: sum(case(SKU) * Quantity) with normalized unit prices (<UnitPriceStandard>, <UnitPricePremium>).
  - Use to classify service type via ResourceId contains '/signalr/' or '/webpubsub/'.
  - Avoid using for message-level telemetry; use ResourceMetrics for message counts.
- Similar tables & how to choose: Cached_* snapshots for weekly/monthly aggregates; use BillingUsage_Daily for derivations and precise daily joins.
- Common Filters: Date >= ago(30–60d); SKU in ('Free','Standard','Premium'); SubscriptionId !in SignalRTeamInternalSubscriptionIds.
- Table columns:

| Column         | Type     | Description or meaning |
|----------------|----------|------------------------|
| Date           | datetime | Usage date (daily granularity) |
| Region         | string   | Azure region of the resource |
| SubscriptionId | string   | Azure subscription GUID |
| ResourceId     | string   | ARM resource ID; includes provider path |
| SKU            | string   | Plan tier ('Free','Standard','Premium', or message SKUs) |
| Quantity       | real     | Billable units for the day |

- Column Explain:
  - SKU: drives revenue mapping; exclude message SKUs where computing subscription counts or normalized revenue.
  - ResourceId: filter by provider path to distinguish SignalR vs Web PubSub; extract SubscriptionId via split for some queries.

### Table name: MaxConnectionCount_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Daily max concurrent connections per resource/role. Fact table to validate “active” resources or subscriptions.
- Freshness expectations: Daily metrics; joins typically within 60 days for activity validation.
- When to use / When to avoid:
  - Use to ensure a resource has connections (MaxConnectionCount > 0) when counting active subs/resources.
  - Use for weekly aggregation of MaxConnectionCount trends.
  - Avoid customer segmentation; join SubscriptionMappings instead.
- Similar tables & how to choose: ResourceMetrics also carries connection counts; pick MaxConnectionCount_Daily for role-focused daily maxima; ResourceMetrics for broader aggregates.
- Common Filters: Date >= ago(60d); join on Date and Role/resource key.
- Table columns:

| Column            | Type     | Description |
|-------------------|----------|-------------|
| Date              | datetime | Metric date |
| Role              | string   | Resource role or derived role identifier |
| SubscriptionId    | string   | Azure subscription GUID |
| CustomerType      | string   | Customer segment (Internal/External etc.) |
| Region            | string   | Azure region |
| MaxConnectionCount| long     | Max concurrent connections observed |

- Column Explain:
  - MaxConnectionCount: used to classify HasConnection true/false; often aggregated to weekly maxima.
  - Role/Resource join: ensure consistent lower-casing to avoid mismatches.

### Table name: SubscriptionMappings (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Subscription-to-customer and offer mapping used for segmentation (CustomerType, SegmentName, OfferType/Name, BillingType).
- Freshness expectations: Snapshot-like; used widely in leftouter joins; unknown refresh cadence.
- When to use / When to avoid:
  - Use to add CustomerType and SegmentName to BillingUsage_Daily or ResourceMetrics.
  - Use to exclude Internal subscriptions.
  - Avoid using alone for counts; always join with a fact table to avoid duplicate counting.
- Similar tables & how to choose: CustomerModel provides customer-level metrics; use SubscriptionMappings for subscription segmentation.
- Common Filters: Join on SubscriptionId; sometimes pack UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType).
- Table columns:

| Column            | Type   | Description |
|-------------------|--------|-------------|
| P360_ID           | string | Customer360 ID |
| CloudCustomerGuid | string | Cloud customer GUID |
| SubscriptionId    | string | Subscription GUID (join key) |
| CustomerType      | string | Segment (e.g., Internal, External) |
| CustomerName      | string | Display name |
| SegmentName       | string | Marketing/segment label |
| OfferType         | string | Offer type |
| OfferName         | string | Offer name |
| BillingType       | string | Billing category (PayG, EA, Internal) |
| WorkloadType      | string | Workload classification |
| S500              | string | Additional segment code |

- Column Explain:
  - SubscriptionId: primary join key to usage/metrics.
  - CustomerType/BillingType/SegmentName: drive slicing in OKR/overview queries.

### Table name: Cached_ZnOKREstRevenueWeekly_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Weekly revenue snapshot by SKU/segment/service for OKR “Zn” series.
- Freshness expectations: Weekly partitions; use startofweek and “last good week” windows.
- When to use / When to avoid:
  - Use to trend weekly income; overlay goals if needed.
  - Avoid day-level revenue detail; compute from BillingUsage_Daily.
- Similar tables & how to choose: Monthly counterpart (Cached_ZnOKREstRevenueMonthly_Snapshot) for monthly charts.
- Common Filters: Week window; SKU, CustomerType, SegmentName, Service.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Week         | datetime | Week bucket |
| SKU          | string   | Tier name |
| CustomerType | string   | Segment |
| SegmentName  | string   | Segment label |
| Service      | string   | 'SignalR' or 'WebPubSub' |
| Income       | real     | Revenue amount |

- Column Explain:
  - Week: align to startofweek(Date).
  - Service: derived category to split service-level revenue.

### Table name: Cached_ZnOKREstRevenueMonthly_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Monthly revenue snapshot by SKU/segment/service.
- Freshness expectations: Monthly partitions; use endofmonth for alignment.
- When to use / When to avoid:
  - Use for monthly OKR revenue visualizations.
  - Avoid mixing with weekly snapshot in one chart; choose one granularity.
- Common Filters: Month window; same dimensions as weekly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Month        | datetime | Month bucket |
| SKU          | string   | Tier name |
| CustomerType | string   | Segment |
| SegmentName  | string   | Segment label |
| Service      | string   | 'SignalR' or 'WebPubSub' |
| Income       | real     | Revenue amount |

- Column Explain:
  - Month: startofmonth used in joins and pivots.
  - Income: pre-aggregated revenue to speed OKR visuals.

### Table name: Cached_ZnOKRSubs_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: OKR subscription counts snapshot by month for service types.
- Freshness expectations: Monthly snapshots; used with growth goals.
- When to use / When to avoid:
  - Use to track total subs by service compared to goals.
  - Avoid resource-level details; use subscriptions/retention snapshots if individual tracking is needed.
- Common Filters: TimeStamp >= startofmonth(now(), -35).
- Table columns:

| Column    | Type     | Description |
|-----------|----------|-------------|
| TimeStamp | datetime | Month bucket |
| SignalR   | long     | Subscription count (SignalR) |
| WebPubSub | long     | Subscription count (Web PubSub) |

- Column Explain:
  - Counts used with dcount(SubscriptionId, precision) in other tables for validation.

### Table name: Cached_CuOKRConsumption_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: OKR consumption snapshot (scaled quantities) by month per service.
- Freshness expectations: Monthly snapshots; unknown refresh cadence.
- When to use / When to avoid:
  - Use for monthly consumption goals visualization.
  - Avoid raw usage; compute directly from BillingUsage_Daily for precise daily sums.
- Table columns:

| Column     | Type   | Description |
|------------|--------|-------------|
| TimeStamp  | datetime | Month bucket |
| Consumption| real   | Total consumption (scaled) |
| SignalR    | real   | Service-specific portion |
| WebPubSub  | real   | Service-specific portion |

- Column Explain:
  - Consumption often scaled by * 24 in daily derivations.

### Table name: Cached_CuOKRConsumptionWeekly_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Weekly consumption snapshot by SKU/segment/service.
- Freshness expectations: Weekly partitions; see above.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Week         | datetime | Week bucket |
| SKU          | string   | Tier |
| CustomerType | string   | Segment |
| SegmentName  | string   | Segment label |
| Service      | string   | 'SignalR'/'WebPubSub' |
| Consumption  | real     | Quantity consumed |

- Column Explain:
  - Align with startofweek for consistent comparisons.

### Table name: Cached_CuOKRConsumptionMonthly_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Monthly consumption snapshot by SKU/segment/service.
- Freshness expectations: Monthly partitions.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Month        | datetime | Month bucket |
| SKU          | string   | Tier |
| CustomerType | string   | Segment |
| SegmentName  | string   | Segment label |
| Service      | string   | Service |
| Consumption  | real     | Quantity consumed |

- Column Explain:
  - Use when monthly granularity is needed for OKR consumption.

### Table name: ResourceMetrics (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Daily resource telemetry aggregates (messages, connections, errors, operations).
- Freshness expectations: Daily metrics; commonly aggregated to weekly/monthly.
- When to use / When to avoid:
  - Use to compute MessageCount, MaxConnectionCount, AvgConnectionCount across Date, ResourceId.
  - Use to validate HasConnection and ActiveDays in resource total views.
  - Avoid revenue computation here; use BillingUsage_Daily.
- Similar tables & how to choose: ConnectionMode_Daily for connection types (serverless/proxy).
- Common Filters: Date >= ago(61d); ResourceId provider label; parse to extract SubscriptionId.
- Table columns:

| Column             | Type    | Description |
|--------------------|---------|-------------|
| Date               | datetime| Metric date |
| Region             | string  | Azure region |
| ResourceId         | string  | ARM resource ID |
| SumMessageCount    | real    | Total messages |
| MaxConnectionCount | real    | Max connections |
| AvgConnectionCount | real    | Average connections |
| SumSystemErrors    | real    | System errors |
| SumTotalOperations | real    | Operations count |

- Column Explain:
  - MaxConnectionCount/AvgConnectionCount: used to classify live/occasional/dedicated resources.

### Table name: RPSettingLatest (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Latest ARM/RP settings snapshot per resource, including SKU/Kind and many booleans and Extras JSON.
- Freshness expectations: Snapshot; used to derive features (Aspire flag, SocketIO mode).
- When to use / When to avoid:
  - Use to flag features (Serverless, Private Endpoint, LiveTrace, Resource log).
  - Use to detect Aspire (Extras has 'isAspire') and ServiceMode for SocketIO.
  - Avoid using for direct counts; join to usage for context.
- Common Filters: ResourceId has '/Microsoft.SignalRService/SignalR/' or '/WebPubSub/'. Join to BillingUsage_Daily for time buckets.
- Table columns:

| Column                    | Type     | Description |
|---------------------------|----------|-------------|
| ResourceId                | string   | ARM resource ID |
| Region                    | string   | Region |
| SKU                       | string   | Tier |
| Kind                      | string   | Product kind (SignalR/WebPubSub/SocketIO) |
| State                     | string   | Resource state |
| ServiceMode               | string   | Serverless/Default/etc. |
| IsUpstreamSet             | bool     | Upstream configured |
| IsEventHandlerSet         | bool     | Event handler configured |
| EnableTlsClientCert       | bool     | TLS client cert enabled |
| IsPrivateEndpointSet      | bool     | Private Endpoint set |
| EnablePublicNetworkAccess | bool     | PNA enabled |
| DisableLocalAuth          | bool     | Local auth disabled |
| DisableAadAuth            | bool     | AAD auth disabled |
| IsServerlessTimeoutSet    | bool     | Serverless timeout configured |
| AllowAnonymousConnect     | bool     | Anonymous connect allowed |
| EnableRegionEndpoint      | bool     | Region endpoint enabled |
| ResourceStopped           | bool     | Resource stopped |
| EnableLiveTrace           | bool     | Live trace enabled |
| EnableResourceLog         | bool     | Resource log enabled |
| LastUpdated               | datetime | Last update time |
| Extras                    | string   | JSON extras (e.g., isAspire, socketIO settings) |

- Column Explain:
  - Extras: extract_json(...) to derive feature flags (e.g., $.socketIO.serviceMode).

### Table name: BillingNormalizedRevenue (from BillingUsage_Daily derived) (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Derived monthly revenue normalized from BillingUsage_Daily; not a physical table in the product database.
- Accessibility: Not accessible as a table (Failed to resolve table). Compute on-the-fly:
  - Extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', <UnitPriceStandard>, SKU == 'Premium', <UnitPricePremium>, 1.0) * Quantity
  - Summarize by DateKey = startofmonth(Date), SKU, CustomerType, BillingType
- When to use / When to avoid:
  - Use in visuals expecting normalized revenue by month.
  - Avoid assuming persistence; recompute from BillingUsage_Daily.

### Table name: Cached_SubsTotalWeekly_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Weekly subscription totals snapshot with flags for connectivity and live ratio.
- Freshness expectations: Weekly snapshots; used in totals by Region, SKU, CustomerType.
- When to use / When to avoid:
  - Use for SubscriptionCnt aggregates by dimensions.
  - Avoid daily counts; use daily retention or BillingUsage_Daily+MaxConnectionCount joins.
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Week          | datetime | Week bucket |
| ServiceType   | string   | 'SignalR'/'WebPubSub' |
| SubscriptionId| string   | Subscription |
| Region        | string   | Region |
| SKU           | string   | Tier |
| HasConnection | bool     | True if connected activity observed |
| LiveRatio     | string   | Swift/Occasional/Dedicate classification |

- Column Explain:
  - LiveRatio: derived from ActiveDays thresholds in resource total queries.

### Table name: Cached_SubsTotalMonthly_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Monthly subscription totals snapshot.
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Month         | datetime | Month bucket |
| ServiceType   | string   | Service |
| SubscriptionId| string   | Subscription |
| Region        | string   | Region |
| SKU           | string   | Tier |
| HasConnection | bool     | Connectivity flag |
| LiveRatio     | string   | Activity category |

- Column Explain:
  - Combine with SubscriptionMappings for segmentation.

### Table name: FeatureTrackV2_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Daily feature-level request counts per resource; used to track feature adoption and ping categories.
- Freshness expectations: Daily; often projected to startofday(Date) and aggregated weekly.
- When to use / When to avoid:
  - Use to quantify feature usage (Feature, Category) with RequestCount.
  - Avoid revenue inference; join BillingUsage_Daily for SKU context.
- Table columns:

| Column         | Type     | Description |
|----------------|----------|-------------|
| Date           | datetime | Event date |
| Feature        | string   | Feature name (e.g., BlazorServerSide) |
| Category       | string   | Feature category (may be trimmed via replace) |
| ResourceId     | string   | ARM resource |
| SubscriptionId | string   | Subscription |
| Properties     | string   | Raw telemetry properties (often dropped) |
| RequestCount   | long     | Count of feature requests |

- Column Explain:
  - Feature/Category: used to compute feature-specific weekly trends.

### Table name: FeatureTrackV2_EU_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: EU shard of FeatureTrackV2_Daily; same schema.
- Table columns: same as FeatureTrackV2_Daily.
- When to use / When to avoid:
  - Use via union with FeatureTrackV2_Daily for global coverage.
  - Avoid counting duplicates without defining Date/ResourceId groupings.

### Table name: FeatureTrack_AutoScale_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: AutoScale-related request counts; used to compute percent of resources in Premium using autoscale.
- Freshness expectations: Daily; aggregated to weekly counts.
- Table columns:

| Column         | Type     | Description |
|----------------|----------|-------------|
| Date           | datetime | Event date |
| Region         | string   | Region |
| ResourceId     | string   | Resource |
| SubscriptionId | string   | Subscription |
| RequestCount   | long     | Requests tied to autoscale signals |

- Column Explain:
  - Combine with BillingUsage_Daily filtered to SKU == 'Premium' to compute PercentInPremium.

### Table name: FeatureTrack_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Daily feature telemetry (original version) used for flags like ServerSticky/MultiEndpoints.
- Table columns:

| Column         | Type     | Description |
|----------------|----------|-------------|
| Date           | datetime | Event date |
| Feature        | string   | Feature name |
| ResourceId     | string   | Resource |
| SubscriptionId | string   | Subscription |
| RequestCount   | long     | Request count |

- Column Explain:
  - Feature: names mapped in queries to boolean flags for top subscriptions.

### Table name: CustomerModel (signalrinsights.eastus2.SignalRBI)
- Priority: High
- Accessibility: Not accessible (Access denied to cross-customer cluster). Columns unknown via tool.
- What this table represents: Customer-level enrichment (names, rate, message/connection summaries). Used in “TopSubscriptions” enrichment.
- Guidance:
  - Join Cached_TopSubscriptions_Snapshot to CustomerModel by SubscriptionId when available in the product environment; if not, use SubscriptionMappings and resource aggregates as fallback.

### Table name: RPSettingLatest (WebPubSub/Aspire subset) (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Same as RPSettingLatest; used with Extras has 'isAspire' to identify Aspire usage for Web PubSub resources.
- Common Filters: ResourceId has '/Microsoft.SignalRService/WebPubSub/', Extras has 'isAspire'.

### Table name: Cached_Awps_TopCustomersWoW_v2_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Web PubSub weekly-over-week top customers snapshot with current vs prior values and ranks.
- Table columns:

| Column                     | Type     | Description |
|----------------------------|----------|-------------|
| P360_ID                    | string   | Customer ID |
| P360_CustomerDisplayName   | string   | Customer name |
| SKU                        | string   | Tier |
| CustomerType               | string   | Segment |
| BillingType                | string   | Billing category |
| Category                   | string   | Metric category |
| CurrentValue               | real     | Current metric value |
| P360Url                    | string   | CX observe URL |
| LastDay                    | datetime | Last sample day |
| UsageType                  | string   | Usage classification |
| CurrentValue1              | real     | Secondary current value |
| PrevValue                  | real     | Previous value |
| W3Value                    | real     | 3-week value |
| DeltaValue                 | real     | Change vs prior |
| Rank                       | long     | Current rank |
| W1Rank                     | long     | 1-week rank |
| W3Rank                     | long     | 3-week rank |

- Column Explain:
  - Category/CurrentValue: used for trend and ranking visuals.

### Table name: Cached_Asrs_TopCustomersWoW_v2_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: SignalR counterpart of top customers WoW snapshot.
- Table columns: same as Awps counterpart.
- Column Explain: same usage but for SignalR.

### Table name: Cached_TopSubscriptions_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: High
- What this table represents: Top subscription snapshot including revenue, messages, connections, date range and flags.
- Freshness expectations: Windowed over last ~29 days; used in trends and profile pages.
- Table columns:

| Column          | Type     | Description |
|-----------------|----------|-------------|
| SubscriptionId  | string   | Subscription |
| Revenue         | real     | Revenue computed |
| MaxConnection   | long     | Max connections |
| MessageCount    | long     | Messages |
| StartDate       | datetime | Start of window |
| EndDate         | datetime | End of window |
| TopRevenue      | real     | Top revenue value |
| TopConnection   | long     | Top connection value |
| TopMessageCount | long     | Top message value |
| Rate            | real     | Composite rate/value |
| Service         | string   | 'SignalR'/'WebPubSub' |

- Column Explain:
  - Trend joins expand into categories ('PaidUnits','Revenue','Messages','Connections','Resources') for per-day trend lines.

Normal Priority Tables

### Table name: OKRv2021 (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Historical OKR values by category and date; used in pivot visuals.
- Freshness expectations: Static historical dataset; unknown refresh.
- Common Filters: Date >= datetime(20200701).
- Table columns:

| Column  | Type     | Description |
|---------|----------|-------------|
| Date    | datetime | Observation date |
| Category| string   | Metric category (e.g., ARR/Revenue/etc.) |
| Value   | real     | Numeric value |

- Column Explain:
  - Used in evaluate pivot(Category, sum(Value)) to produce wide KPI sets.

### Table name: ManageResourceTags (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: RP manage requests with tags; used to analyze API method mix (RequestName/Tags) and counts.
- Freshness expectations: Daily/manage events; often aggregated by Date.
- Common Filters: Date > ago(30d); ResourceId !contains 'Microsoft.Authorization'; exclude RequestName == 'Other'.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Request date |
| SubscriptionId| string  | Subscription |
| ResourceId   | string   | Resource |
| RequestName  | string   | API name |
| Tags         | string   | Method tags/parameters |
| Count        | long     | Count of requests |

- Column Explain:
  - RequestName/Tags: used to compute OperationCount and summarize ResourceCnt/SubscriptionCnt.

### Table name: ConnectionMode_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Daily connection mode counts (serverless vs proxy).
- Freshness expectations: Daily; aggregated by Date/ServiceMode.
- Common Filters: Date > ago(60d); ResourceId has 'microsoft.signalrservice/signalr'.
- Table columns:

| Column             | Type     | Description |
|--------------------|----------|-------------|
| Date               | datetime | Day |
| ResourceId         | string   | Resource |
| ServerlessConnection| long    | Serverless connections count |
| ProxyConnection    | long     | Proxy connections count |
| ServiceMode        | string   | Mode label |

- Column Explain:
  - Used to derive IsServerless/IsServerMode booleans per Subscription in “TopSubscriptions” enrichment.

### Table name: KPIv2019 (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: KPI counts (subscriptions/resources) by date.
- Table columns:

| Column           | Type     | Description |
|------------------|----------|-------------|
| Date             | datetime | Day |
| SubscriptionCount| long     | Count of subscriptions |
| ResourceCount    | long     | Count of resources |

- Column Explain:
  - Used as a simple KPI time series.

### Table name: ChurnCustomers_Monthly (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Monthly churn stats per service type.
- Common Filters: where ServiceType == 'SignalR' or 'WebPubSub'.
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Month         | datetime | Month |
| ServiceType   | string   | Service |
| Total         | long     | Total customers |
| Churn         | long     | Churned customers |
| Standard      | long     | Standard-tier customers |
| StandardChurn | long     | Churn among Standard |
| RunDay        | datetime | Snapshot instantiation day |

- Column Explain:
  - StandardChurnRate = 1.0*StandardChurn/Standard; OverallChurnRate = 1.0*Churn/Total.

### Table name: ConvertCustomer_Weekly (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Weekly conversion flows (Free to Standard/Premium; Standard to Premium).
- Table columns:

| Column           | Type     | Description |
|------------------|----------|-------------|
| Week             | datetime | Week |
| ServiceType      | string   | Service |
| FreeToStandard   | long     | Conversions |
| TotalCustomers   | long     | Total customers |
| StandardCustomers| long     | Standard customers |
| RunDay           | datetime | Snapshot day |
| FreeToPaid       | long     | Alias to FreeToStandard when present |
| StandardToPremium| long     | Conversions |
| FreeToPremium    | long     | Conversions |
| PremiumCustomers | long     | Premium customers |

- Column Explain:
  - Week-level ordering with Rank ensures latest snapshot per week.

### Table name: DeleteSurvey (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- Accessibility: Not accessible via tool; likely a survey log including TIMESTAMP, Deployment, resourceId, reason, feedback.
- Usage: Simple projection of key fields for reporting deletion feedback.

### Table name: SubscriptionRetentionSnapshot (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Subscription retention intervals with StartDate/EndDate for cohort analysis.
- Table columns:

| Column         | Type     | Description |
|----------------|----------|-------------|
| SubscriptionId | string   | Subscription |
| StartDate      | datetime | Cohort start |
| EndDate        | datetime | Cohort end |

- Column Explain:
  - Used to compute Retain/Total and Retention ratios across monthly/weekly cohorts.

### Table name: CustomerRetentionSnapshot (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Customer retention intervals (C360_ID).
- Table columns:

| Column  | Type     | Description |
|---------|----------|-------------|
| C360_ID | string   | Customer ID |
| StartDate| datetime| Cohort start |
| EndDate | datetime | Cohort end |

- Column Explain:
  - Compute Retain/Total per Periods dimension.

### Table name: ResourceRetentionSnapshot (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Resource retention intervals.
- Table columns:

| Column     | Type     | Description |
|------------|----------|-------------|
| ResourceId | string   | ARM resource |
| StartDate  | datetime | Cohort start |
| EndDate    | datetime | Cohort end |

- Column Explain:
  - Used similarly to subscription/customer retention charts.

### Table name: Cached_ResourceFlow_Snapshot (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Resource flow classification snapshots by service and partition (Week/Month).
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Category      | string   | Flow category |
| Region        | string   | Region |
| SKU           | string   | Tier |
| HasConnection | bool     | Has observed connections |
| LiveRatio     | string   | Swift/Occasional/Dedicate |
| ResourceCnt   | long     | Resource count |
| Date          | datetime | Partition date |
| ServiceType   | string   | Service |
| Partition     | string   | 'Week'/'Month' |

- Column Explain:
  - Week/Month partition controls the aliasing of Date into Week/Month in queries.

### Table name: RuntimeResourceTags_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: Daily resource tags summary flags (IsAppService, IsProxy, IsStaticApps, IsSample, success/failure).
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Date          | datetime | Date |
| ResourceId    | string   | Resource |
| SubscriptionId| string   | Subscription |
| ServiceType   | string   | Service |
| IsAppService  | bool     | Using App Service |
| IsStaticApps  | bool     | Using Static Web Apps |
| IsSample      | bool     | Sample resource |
| IsProxy       | bool     | Using proxy |
| HasFailure    | bool     | Failure tag observed |
| HasSuccess    | bool     | Success tag observed |
| Extra         | string   | Extra info |

- Column Explain:
  - Used to enrich top subscriptions with AppService/Proxy/StaticApps flags.

### Table name: FeedbackSurvey (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- Accessibility: Not accessible via tool in this environment. Queries project TimeStamp, CESValue, CVAValue, Comments. Likely customer feedback telemetry.

### Table name: OKRv2021_AWPS (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: OKR values for Web PubSub, used with SocketIO merges and pivot.
- Table columns:

| Column  | Type     | Description |
|---------|----------|-------------|
| Date    | datetime | Date |
| Category| string   | OKR category |
| Value   | real     | Numeric value |

- Column Explain:
  - Union with OKRv2021_SocketIO extends SocketIO categories.

### Table name: OKRv2021_SocketIO (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: SocketIO-specific OKR categories/values.
- Table columns: same as OKRv2021_AWPS.

### Table name: KPI_AWPS (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this table represents: AWPS KPI counts for subscriptions/resources.
- Table columns:

| Column           | Type     | Description |
|------------------|----------|-------------|
| Date             | datetime | Date |
| SubscriptionCount| long     | Count of subscriptions |
| ResourceCount    | long     | Count of resources |

- Column Explain:
  - Used similar to KPIv2019 but scoped to AWPS.

### Table name: DeleteSurveyWebPubSub (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- Accessibility: Not accessible via tool. Queries project TIMESTAMP, Deployment, resourceId, reason, feedback for Web PubSub deletions.

### Table name: ResourceFlow_Weekly (function) (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this represents: A database function returning weekly resource flow; not a static table.
- Accessibility: Function; schema not retrievable via getschema. Use as invoked: ResourceFlow_Weekly(startDate, endDate, <serviceTypeId>).

### Table name: ResourceFlow_Monthly (function) (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- Similar to weekly; monthly resource flow function.

### Table name: AwpsRetention_SubscriptionSnapshot (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- What this represents: Web PubSub subscription retention intervals.
- Table columns:

| Column         | Type     | Description |
|----------------|----------|-------------|
| SubscriptionId | string   | Subscription |
| StartDate      | datetime | Cohort start |
| EndDate        | datetime | Cohort end |

### Table name: AwpsRetention_CustomerSnapshot (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- Table columns:

| Column  | Type     | Description |
|---------|----------|-------------|
| C360_ID | string   | Customer |
| StartDate| datetime| Cohort start |
| EndDate | datetime | Cohort end |

### Table name: AwpsRetention_ResourceSnapshot (signalrinsights.eastus2.SignalRBI)
- Priority: Normal
- Table columns:

| Column     | Type     | Description |
|------------|----------|-------------|
| ResourceId | string   | Resource |
| StartDate  | datetime | Cohort start |
| EndDate    | datetime | Cohort end |

Low Priority Tables

### Table name: OperationQoS_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- What this table represents: Daily operational QoS windows (uptime/time) per role/location.
- Freshness expectations: Daily; used for rolling 7/28 day QoS calculations.
- Common Filters: env_time > ago(10–60d); resourceId has 'microsoft.signalrservice/signalr' or contains 'webpubsub'.
- Table columns:

| Column               | Type     | Description |
|----------------------|----------|-------------|
| env_name             | string   | Environment name |
| env_time             | datetime | Observation time |
| resourceId           | string   | Resource identifier |
| env_cloud_role       | string   | Cloud role |
| env_cloud_roleInstance| string  | Role instance |
| env_cloud_environment| string   | Environment |
| env_cloud_location   | string   | Region/location |
| env_cloud_deploymentUnit| string| Deployment unit |
| totalUpTimeSec       | long     | Up-time seconds |
| totalTimeSec         | long     | Total time seconds |

- Column Explain:
  - Use iif(sum(totalTimeSec)==0,1.0, sum(UpTime)/sum(TotalTime)) to compute Qos.

### Table name: ConnectivityQoS_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- What this table represents: Daily connectivity QoS windows.
- Table columns: same schema as OperationQoS_Daily.
- Column Explain:
  - Use 0.995 SLA threshold in SlaAttainment.

### Table name: ManageRPQosDaily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- What this table represents: RP API QoS events (status counts).
- Common Filters: ApiName !in ('UNCATEGORY', various invalid); CustomerType filters to 'SignalR'/'WebPubSub'.
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Date          | datetime | Day |
| ApiName       | string   | RP Operation |
| SubscriptionId| string   | Subscription |
| CustomerType  | string   | Service group |
| Region        | string   | Region |
| Result        | string   | Status category |
| Count         | long     | Count of events |

- Column Explain:
  - QoS = sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count) or Result=='Success' for Web PubSub views.

### Table name: RuntimeRequestsGroups_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- What this table represents: Daily grouped runtime request metrics by category and metrics label.
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Date          | datetime | Day |
| Category      | string   | Group (RestApiScenario, etc.) |
| Metrics       | string   | Scenario/metric name |
| ResourceCount | long     | Unique resources |
| RequestCount  | long     | Total requests |

### Table name: RuntimeRequestsGroups_EU_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- Same schema as RuntimeRequestsGroups_Daily; EU shard.

### Table name: RuntimeTransport_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- What this table represents: Transport usage (Framework-Transport) counts.
- Table columns:

| Column         | Type     | Description |
|----------------|----------|-------------|
| Date           | datetime | Day |
| Feature        | string   | Feature label |
| Transport      | string   | Transport type (WebSockets/LongPolling/etc.) |
| Framework      | string   | Client framework |
| ResourceId     | string   | Resource |
| SubscriptionId | string   | Subscription |
| RequestCount   | long     | Total requests |

### Table name: RuntimeTransport_EU_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- Same schema; EU shard.

### Table name: Unionizer (armprodgbl.eastus)
- Priority: Low
- Accessibility: Cross-cluster function returning ARM request telemetry (Requests/HttpIncomingRequests). Not accessible from the current product environment for schema.
- Guidance: Use as shown in queries to detect PUT/DELETE on EventGrid filters and produce Date, ResourceId, subscriptionId, action, Location.

### Table name: WebTools_Raw (ddtelinsights)
- Priority: Low
- Accessibility: Cross-cluster dataset not accessible in this environment. Queries use VS telemetry fields like AdvancedServerTimestampUtc, EventName, Measures, Properties, MacAddressHash, ActiveProjectId, ExeVersion.
- Guidance: Use per examples to compute dev/project counts and ratios; avoid hardcoding structure without access.

### Table name: AwpsRuntimeRequestsGroups_Daily (signalrinsights.eastus2.SignalRBI)
- Priority: Low
- What this table represents: Web PubSub runtime grouped requests (AWPS).
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Date          | datetime | Day |
| Category      | string   | Group |
| Metrics       | string   | Metric label |
| ResourceCount | long     | Resource count |
| RequestCount  | long     | Requests count |

- Column Explain:
  - Use replace_string on Metrics to normalize naming as in example.

Column usage quick reference (common across tables)
- Date/Week/Month: Always align to period boundaries using startofday/startofweek/startofmonth or endofmonth to avoid partial-period artifacts.
- SubscriptionId: Primary dimension for segmentation; join to SubscriptionMappings for CustomerType/BillingType/SegmentName; exclude internal IDs via SignalRTeamInternalSubscriptionIds().
- ResourceId: Use provider path to split SignalR vs Web PubSub; derive PrimaryResource by trimming '/replicas/' for replica-aware counts.
- SKU: Use for tier splits; map to revenue via <UnitPriceStandard>/<UnitPricePremium> placeholders; exclude message SKUs when counting subscriptions or consumption units.
- Region: Use to slice QoS and manage methods; watch for EU vs NonEU shards (FeatureTrackV2_EU_Daily).
- HasConnection/ActiveDays/LiveRatio: Derived via joins to ResourceMetrics; thresholds: ActiveDays < 3 => 'Swift'; <10 => 'Occasional'; else 'Dedicate'.

When to choose between similar tables
- Daily vs Weekly vs Monthly:
  - Use BillingUsage_Daily + joins for precise day-level metrics and custom aggregations.
  - Use Cached_*_Weekly/Monthly_Snapshot for pre-aggregated counts suitable for dashboards; faster and stable.
- Feature tracking:
  - FeatureTrackV2_* for richer categories and EU shards; FeatureTrack_Daily for legacy flags (ServerSticky, MultiEndpoints).
- QoS:
  - OperationQoS_Daily for operational uptime; ConnectivityQoS_Daily for connectivity; use rolling windows by joining with the latest env_time/date value.

Access limitations and workarounds
- CustomerModel: Access denied; if unavailable, enrich subscriptions via SubscriptionMappings and ResourceMetrics.
- BillingNormalizedRevenue: Not a persisted table; derive from BillingUsage_Daily using unit price placeholders.
- Unionizer/WebTools_Raw: Cross-cluster sources; reproduce outputs by following query patterns; do not assume schema unless your environment has access.
- DeleteSurvey/FeedbackSurvey (and Web PubSub variants): Not accessible in this environment; use projected fields from queries when building reports.

Conservative defaults to reuse
- Use 28-day rolling windows for subscription/AI cohorts to avoid partial month noise.
- For trend visuals, restrict to the last 8–12 weeks or 8–12 months and parameterize N to scale gradually.
- Always exclude SignalRTeamInternalSubscriptionIds() when counting external/billable signals.

Example reusable Kusto fragments
- Revenue derivation:
  ```kusto
  BillingUsage_Daily
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  | extend UnitPrice = case(SKU=='Free', 0.0, SKU=='Standard', <UnitPriceStandard>, SKU=='Premium', <UnitPricePremium>, 1.0)
  | extend Revenue = UnitPrice * Quantity
  ```

- HasConnection flag from ResourceMetrics:
  ```kusto
  BillingUsage_Daily
  | join kind=leftouter ResourceMetrics on ResourceId, Date
  | extend HasConnection = MaxConnectionCount > 0
  ```

- Subscription segmentation:
  ```kusto
  ... // fact table
  | join kind=leftouter SubscriptionMappings on SubscriptionId
  | extend UsageType = iif(CustomerType=='Internal', CustomerType, BillingType)
  ```

This playbook covers all used tables with schemas where accessible, common usage patterns, and selection guidance to compose correct Kusto queries for SignalR and Web PubSub analytics.