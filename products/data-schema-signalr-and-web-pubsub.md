# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

Azure SignalR Service (ASRS) and Azure Web PubSub (AWPS) real-time messaging services. This overview and schema enable PMAgent to interpret product-specific telemetry, billing, and operational metrics across SignalR and Web PubSub. The scope covers OKR reporting (ARR, consumption, subscriptions), revenue and usage (connections, messages), service-type growth (SignalR/WebPubSub/SocketIO), feature tracking (replicas, auto-scale, Aspire, etc.), external/billable and top customers, retention analytics, and totals across overview/resource/subscription/customer. It also includes additional Visual Studio integration telemetry, QoS, and runtime requests.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product: SignalR and Web PubSub
- Product Nick Names:
  - [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples might include: "SignalR", "ASRS", "Web PubSub", "AWPS", "SocketIO" (if applicable).
- Kusto Cluster: signalrinsights.eastus2
- Kusto Database: SignalRBI
- Access Control:
  - [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# SignalR and Web PubSub - Kusto Query Playbook

## Overview
- Product: SignalR and Web PubSub. Power BI report blocks containing Azure Data Explorer (Kusto) queries for SignalR and Web PubSub, covering OKR (ARR/consumption/subscriptions), revenue and usage metrics (connections, messages), service type growth (SignalR/WebPubSub/SocketIO), feature tracking (replicas, auto-scale, Aspire, etc.), external/billable and top customers, retention, and overview/resource/subscription/customer totals. Includes additional VS integration, QoS, and runtime requests blocks.
- Primary cluster: signalrinsights.eastus2
- Primary database: SignalRBI
- Alternate sources used in queries:
  - ddtelinsights cluster for WebTools_Raw (VS integration telemetry)
  - armprodgbl.eastus cluster for Unionizer (ARM requests log)

## Conventions & Assumptions

### Time semantics
- Canonical Time Columns observed:
  - Date: primary business metrics and facts (BillingUsage_Daily, ResourceMetrics, MaxConnectionCount_Daily, FeatureTrack*, ManageResourceTags)
  - env_time: QoS tables (OperationQoS_Daily, ConnectivityQoS_Daily)
  - AdvancedServerTimestampUtc: VS telemetry (WebTools_Raw)
  - TIMESTAMP: ARM request union (Unionizer)
- Canonical aliasing pattern:
  - env_time → Date via project Date = env_time
  - AdvancedServerTimestampUtc → Date via project Date = startofday(AdvancedServerTimestampUtc) or week/month bin
  - Start-of-period bins:
    - Day: startofday(Date)
    - Week: startofweek(Date)
    - Month: startofmonth(Date)
- Typical windows and bins:
  - Daily facts: last 60–61 days; EU/Non-EU completeness gate applied
  - Weekly: last 8–12 weeks
  - Monthly: last 12–16 months
  - Product milestones:
    - WebPubSub cohort filters start around datetime(20210426)
- Timezone: not stated; treat timestamps as UTC by default. Be cautious with “current day” data—prefer end-of-previous full day/week/month.

### Freshness & Completeness Gates
- Current-day incompleteness: multiple queries exclude the very latest day and/or use effective end dates.
- Sentinel multi-slice gate:
  - EndDate determined by the last day where both regions report (australiaeast and westeurope).
  - Pattern used to ensure cross-shard completeness before summarizing totals.
- Rolling windows:
  - Rolling7 and Rolling28 QoS use the latest env_time to anchor the window and summarize quality within the last 7/28 days.
- Recommendation when unknown: use previous complete week/month or gate to EndDate where sentinel slices are present; avoid using now() directly for KPIs.

### Joins & Alignment
- Frequent keys:
  - SubscriptionId
  - ResourceId (ARM path string for SignalR/WebPubSub resource)
  - Role (lowercased ResourceId alignment with MaxConnectionCount_Daily)
  - Region
- Typical join kinds:
  - inner: aligning facts across Date/ResourceId/SubscriptionId (e.g., with MaxConnectionCount_Daily, ResourceMetrics)
  - leftouter: enrichment (SubscriptionMappings), optional metrics presence
  - fullouter: merge with static goal tables (datatable) to overlay targets
- Post-join hygiene:
  - Resolve duplicate columns and normalize case:
    - project-away duplicate columns (e.g., TimeStamp1, SubscriptionId1/2/3)
    - tolower() normalization of ResourceId before joins
  - Align bins prior to join (set Week/Month consistently on both sides)

### Filters & Idioms
- Default exclusions:
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds) to drop internal/test subscriptions
  - SKU filters:
    - Exclude MessageCount/MessageCountPremium when computing consumption/revenue distinct from message SKUs
    - Billable filters typically SKU in ('Standard', 'Premium')
- Service type detection:
  - SignalR resources: ResourceId has 'microsoft.signalrservice/signalr'
  - WebPubSub resources: ResourceId has 'microsoft.signalrservice/webpubsub' or contains '/webpubsub/'
- AI cohort filter:
  - ResourceId matches any of: 'gpt', 'ai', 'ml', 'cognitive' or contains 'openai', 'chatgpt'
- Cohort composition:
  - Build allowlist via facts, then inner join; reuse consistent bins before summarization.

### Cross-cluster/DB & Sharding
- Qualify cross-cluster sources when needed:
  - cluster('armprodgbl.eastus').database('<DB>').Unionizer
  - cluster('ddtelinsights').database('<DB>').WebTools_Raw
- EU vs Non-EU sharding:
  - FeatureTrackV2_Daily and RuntimeRequests groups have EU counterparts (FeatureTrackV2_EU_Daily, RuntimeRequestsGroups_EU_Daily, RuntimeTransport_EU_Daily)
  - Use union to merge shards, then standardize metrics keys and time bins before summarize.

### Important conventions observed in queries
- ResourceId normalization and replica handling: lowercase ResourceId; for replicas, use substring(ResourceId, 0, indexof('/replicas/')) to reference the primary resource and avoid double counting.
- Exclude internal telemetry: SubscriptionId !in (SignalRTeamInternalSubscriptionIds or SignalRTeamInternalSubscriptionIds()) applied per query scope.
- Activity confirmation: join with MaxConnectionCount_Daily and/or ResourceMetrics to ensure active resources/subscriptions and to avoid counting idle entities.
- SKU normalization: SKU in ('Free','Standard','Premium'), exclude 'MessageCount' and 'MessageCountPremium' for revenue/consumption queries.
- Time windows: narrow windows (ago(30d), rolling 28d/7d, startofweek/month); use startofweek/month for weekly/monthly cohort math and retention.
- Revenue mapping: case(SKU == 'Free', 0.0, 'Standard', <UnitPriceStandard>, 'Premium', <UnitPricePremium>, 1.0)*Quantity; do not hardcode prices—use placeholders.
- Pack/mv-expand pattern: pack-array and mv-expand used for emitting multi-category series in a single stream.

### Freshness note
- “Daily/Weekly/Monthly” table names imply batch updates at those cadences; exact delay and timezone are unknown. Be cautious using current-day data—it may be incomplete.

### Notes on usage patterns and anti-patterns
- Freshness and timezone: Unknown. Current-day data can be incomplete. Prefer end-of-period markers (endofweek/endofmonth) and lagging windows.
- Activity gating: To avoid counting idle entities, inner-join MaxConnectionCount_Daily or ResourceMetrics and apply HasConnection flags.
- Replica handling: Deduplicate using PrimaryResource = substring(ResourceId, 0, indexof('/replicas/')) and count both ResourceId and PrimaryResource in replica aggregations.
- Revenue and consumption: Do not use MessageCount SKUs for revenue. Use <UnitPriceStandard>/<UnitPricePremium>/<DefaultUnitPrice> placeholders. Normalize consumption to daily by Quantity*24 where queries do so.
- Segment and internal filters: Always exclude internal team subscriptions; enrich with SubscriptionMappings to derive CustomerType, SegmentName, Offer*, BillingType.
- Goals overlay: For OKR plots, fullouter join snapshots with datatable goals on TimeStamp/Date to overlay target lines; backfill TimeStamp when empty.

## Entity & Counting Rules (Core Definitions)
- Entity tiers and keys:
  - Resource → Subscription → Customer
  - ResourceId: ARM path of resource; may include '/replicas/' suffix
  - SubscriptionId: extracted from ResourceId (split or parse)
  - Customer: CloudCustomerGuid, C360_ID, TPID (from CustomerModel/retention snapshots)
- Grouping levels:
  - Resource-level when analyzing feature usage, connection/message metrics
  - Subscription-level for billing units, revenue, and service mode (serverless/server)
  - Customer-level summarizes CloudCustomerGuid cohorts and segments
- Counting rules:
  - Distinct counts use dcount(..., sampling) with noise parameter 3 or 4 for stability
  - HasConnection: MaxConnectionCount > 0 (per ResourceMetrics), often used as active flag
  - LiveRatio classification:
    - Swift: ActiveDays < 3
    - Occasional: ActiveDays < 10
    - Dedicate: otherwise
- Business definitions (observed):
  - UsageType: if CustomerType == 'Internal' then 'Internal' else BillingType
  - Billable units: sumif(Quantity, SKU in ('Standard', 'Premium'))
  - Revenue: case(SKU == 'Free', 0, SKU == 'Standard', <StandardUnitPrice>, SKU == 'Premium', <PremiumUnitPrice>, <DefaultUnitPrice>)*Quantity
  - Serverless vs ServerMode: from ConnectionMode_Daily summarization over ServerlessConnection and ProxyConnection
  - Replica detection: ResourceId has '/replicas/' and PrimaryResource = substring(ResourceId, 0, indexof('/replicas/'))
  - SocketIO kind: RPSettingLatest.Kind == 'SocketIO'; ServiceMode from Extras JSON (e.g., $.socketIO.serviceMode)

## Views (Reusable Layers)
- Table classes
  - Fact tables (event/daily):
    - BillingUsage_Daily, ResourceMetrics, MaxConnectionCount_Daily, OperationQoS_Daily, ConnectivityQoS_Daily, ManageRPQosDaily, ManageResourceTags, FeatureTrackV2_Daily/EU, FeatureTrack_Daily, ConnectionMode_Daily, RuntimeRequestsGroups*/Transport*
  - Snapshot / Pre-aggregated:
    - Cached_* snapshots (ARR, EstRevenue, Subs totals, Customer/Resource flows, TopCustomers)
    - RetentionSnapshot tables (SubscriptionRetentionSnapshot, CustomerRetentionSnapshot, ResourceRetentionSnapshot; AWPS counterparts)
  - Usage guidance:
    - Prefer fact tables for flexible ad-hoc analysis and derived definitions.
    - Use Cached_* snapshots for standardized KPIs and historical cohort baselines (performance and consistency).
    - Snapshots often embed business logic (HasConnection, LiveRatio, Offer details); verify definitions before blending with new facts.
- WebPubSub-related tables (ResourceFlow/SubscriptionFlow/CustomerFlow functions)
  - What these represent: Functions producing weekly/monthly “New/Leaving” cohorts for resources/subscriptions/customers based on BillingUsage_Daily + MaxConnectionCount_Daily + CustomerModel.
  - Freshness expectations: Computed on demand; input tables are daily; use startofweek/month alignment.
  - When to use / When to avoid:
    - Use the functions when you need cohort breakdown; pass resourceType argument: 0-All, 1-SignalR, 2-WebPubSub.
    - Avoid recomputing flows manually unless custom logic needed.
  - Function outputs (from definitions):
    - ResourceFlow_Weekly/Monthly: summarize ResourceCnt by period, Category, Region, SKU, HasConnection, LiveRatio.
    - SubscriptionFlow_Weekly/Monthly: summarize SubscriptionCnt with Offer/Billing/CustomerType attributes.
    - CustomerFlow_Weekly/Monthly: summarize CustomerCnt with segment.

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Anchor windows to effective end time and use conservative bins to avoid partial current-day/week/month data. Apply EU/Non-EU completeness gate when merging shards.
  - Snippet:
    ```kusto
    // Effective end date using sentinel shards (EU + NonEU)
    let EndDate =
        toscalar(
            BillingUsage_Daily
            | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
            | summarize counter = dcount(Region) by Date
            | where counter >= 2
            | top 1 by Date desc
            | project Date
        );

    // Daily window gated to EndDate
    BillingUsage_Daily
    | where Date > ago(61d) and Date <= EndDate
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    ```

    ```kusto
    // Anchor rolling windows to latest QoS slice
    let anchor = toscalar(OperationQoS_Daily | top 1 by env_time desc | project env_time);
    OperationQoS_Daily
    | where env_time > anchor - 28d
    | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
    ```

    ```kusto
    // Monthly bin excluding current month
    let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
    BillingUsage_Daily
    | where Date < startofmonth(Current)
    | summarize Total = sum(Quantity) by Month = startofmonth(Date)
    ```

- Join template
  - Description: Align facts on Date and ResourceId/SubscriptionId; enrich with mappings; standardize case and bins before join; prefer inner join to enforce activity and leftouter for enrichment.
  - Snippet:
    ```kusto
    // Standard alignment then enrichment
    let usage =
        BillingUsage_Daily
        | where Date >= ago(60d)
        | extend ResourceId = tolower(ResourceId)
        | summarize Quantity = sum(Quantity) by Date, ResourceId, SubscriptionId;

    let activity =
        MaxConnectionCount_Daily
        | where Date >= ago(60d)
        | extend ResourceId = tolower(Role)  // Role in MaxConnectionCount_Daily aligns to ResourceId
        | summarize MaxConn = max(MaxConnectionCount) by Date, ResourceId;

    usage
    | join kind=inner activity on Date, ResourceId
    | join kind=leftouter SubscriptionMappings on SubscriptionId
    | project-away SubscriptionId1  // drop duplicate join columns if present
    ```

- De-dup pattern
  - Description: Use row_number with partition changes to select latest run per period; use distinct for snapshot cohorts; use dcount sampling (3/4) for stable distinct counts.
  - Snippet:
    ```kusto
    // Latest run per period from monthly churn snapshots
    ChurnCustomers_Monthly
    | where ServiceType == 'SignalR'
    | order by Month asc, RunDay desc
    | extend Rank = row_number(1, prev(Month) != Month)
    | where Rank == 1
    ```

    ```kusto
    // Stable distinct counts with sampling parameter
    summarize SubscriptionCnt = dcount(SubscriptionId, 4)
    ```

- Important filters
  - Description: Default exclusions and service type selectors; AI cohort; SKU filters for billable metrics.
  - Snippet:
    ```kusto
    // Internal/test exclusions and SKU gates
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | where SKU in ('Standard', 'Premium')  // billable units only

    // Service type cohorts
    | where ResourceId has 'microsoft.signalrservice/signalr'  // SignalR services
    | where ResourceId has 'microsoft.signalrservice/webpubsub'  // Web PubSub services

    // AI cohort
    | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml'
        or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
    ```

- Important Definitions
  - Description: Reusable projections for business semantics.
  - Snippet:
    ```kusto
    // Revenue with unit price placeholders
    let StandardUnitPrice = <StandardUnitPrice>;
    let PremiumUnitPrice = <PremiumUnitPrice>;
    let DefaultUnitPrice = <DefaultUnitPrice>;

    extend Revenue =
        case(
            SKU == 'Free', 0.0,
            SKU == 'Standard', StandardUnitPrice,
            SKU == 'Premium', PremiumUnitPrice,
            DefaultUnitPrice
        ) * Quantity
    ```

    ```kusto
    // UsageType derivation
    extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)

    // HasConnection and LiveRatio classification
    extend HasConnection = MaxConnectionCount > 0;
    extend LiveRatio =
        case(ActiveDays < 3, 'Swift', ActiveDays < 10, 'Occasional', 'Dedicate')
    ```

    ```kusto
    // Serverless vs ServerMode flags
    summarize
        IsServerless = sum(ServerlessConnection) > 0,
        IsServerMode = sum(ProxyConnection) > 0
        by SubscriptionId
    ```

- ID parsing/derivation
  - Description: Extract SubscriptionId, normalize ResourceId, strip replicas, parse from URLs.
  - Snippet:
    ```kusto
    // Parse SubscriptionId from ResourceId ARM path
    parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *

    // Normalize and strip replica suffix
    extend ResourceId = tolower(ResourceId)
    extend IsReplicas = ResourceId has '/replicas/'
    extend PrimaryResource = iif(IsReplicas, substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)

    // Extract from VS telemetry property
    extend SubscriptionId = tostring(split(Properties['vs.webtools.azuretools.common.httpclient.uri'], '/')[4])
    ```

- Sharded union
  - Description: Merge EU and Non-EU shards for FeatureTrack and Runtime requests; standardize Metrics before summarization.
  - Snippet:
    ```kusto
    FeatureTrackV2_Daily
    | union FeatureTrackV2_EU_Daily
    | where Date > startofweek(now()) - 56d
    | extend Date = startofday(Date)
    | extend ResourceId = tolower(ResourceId)
    | summarize RequestCount = sum(RequestCount) by Date, Feature, ResourceId, SubscriptionId
    ```

    ```kusto
    RuntimeRequestsGroups_Daily
    | where Date > ago(60d) and Category != 'Transport'
    | union (RuntimeRequestsGroups_EU_Daily | where Date > ago(60d) and Category != 'Transport')
    | extend Metrics = iif(Category == 'RestApiScenario' and Metrics startswith 'v1' and Metrics !contains 'HubProxy', replace_string(Metrics, 'v1', 'v1-HubProxy'), Metrics)
    ```

## Example Queries (with explanations)

```kusto
Cached_ZnOKRARR_Snapshot
| join kind = fullouter (datatable(TimeStamp: datetime, SignalRGoal: real, SignalRGrowthGoal: real)[
datetime(2023-9-30), 22939552, 0.03085,
datetime(2023-10-31), 23647313, 0.03085,
datetime(2023-11-30), 24376911, 0.03085,
datetime(2023-12-31), 25129020, 0.03085,
datetime(2024-01-31), 25904333, 0.03085,
datetime(2024-02-29), 26703568, 0.03085,
datetime(2024-03-31), 27527462, 0.03085]) on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
```
Description: OKR ARR goals overlay. Merges pre-aggregated ARR snapshot with a static goals datatable using fullouter join so both actuals and goals appear even if dates mismatch. Adapt by changing goal values or adding rows and adjusting the time filter.

```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium') and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) 
| project Date, Role = tolower(Role)) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr', isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
Income = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0)*Quantity
| summarize Income = sum(Income) by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind = leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU, CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1])
| union (raw
| summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU = ' JOIN(OR)', CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1]))
```
Description: Daily income by SKU and service type, excluding message SKUs and internal subscriptions, with activity gate via MaxConnectionCount_Daily. Enriches with SubscriptionMappings; packs totals for SignalR vs Web PubSub. Adapt by parameterizing prices and extending cohorts (e.g., AI filter).

```kusto
let NonEU = BillingUsage_Daily 
    | where Region == 'australiaeast' 
    | top 1 by Date desc 
    | project Date;
let EU = BillingUsage_Daily 
    | where Region == 'westeurope' 
    | top 1 by Date desc 
    | project Date;
let Current = toscalar(NonEU | union EU | top 1 by Date asc);
let DoM = 28d; // 28-day rolling window
let LatestPeriod = BillingUsage_Daily
| where Date > Current - DoM and Date <= Current
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or 
       ResourceId has 'ai' or 
       ResourceId has 'ml' or 
       ResourceId has 'cognitive' or 
       ResourceId contains 'openai' or 
       ResourceId contains 'chatgpt'
| extend 
    IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', 
    IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
    Month = startofday(Current)
| summarize 
    SubscriptionCnt = dcount(SubscriptionId), 
    SignalR = dcountif(SubscriptionId, IsSignalR, 4), 
    WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) 
    by Month;
let LatestPeriodBeforeLast = BillingUsage_Daily
| where Date > Current - 2*DoM and Date <= Current - DoM
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or 
       ResourceId has 'ai' or 
       ResourceId has 'ml' or 
       ResourceId has 'cognitive' or 
       ResourceId contains 'openai' or 
       ResourceId contains 'chatgpt'
| extend 
    IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', 
    IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
    Month = startofday(Current) - 1h
| summarize 
    SubscriptionCnt = dcount(SubscriptionId), 
    SignalR = dcountif(SubscriptionId, IsSignalR, 4), 
    WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) 
    by Month;
let Historical = BillingUsage_Daily
| where Date >= endofmonth(now(), -14) and Date < startofmonth(Current)
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or 
       ResourceId has 'ai' or 
       ResourceId has 'ml' or 
       ResourceId has 'cognitive' or 
       ResourceId contains 'openai' or 
       ResourceId contains 'chatgpt'
| extend 
    IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', 
    IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
    Month = startofday(endofmonth(Date))
| summarize 
    SubscriptionCnt = dcount(SubscriptionId), 
    SignalR = dcountif(SubscriptionId, IsSignalR, 4), 
    WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) 
    by Month;
LatestPeriod
| union LatestPeriodBeforeLast
| union Historical
| join kind = fullouter (
    datatable(Month: datetime, SubscriptionGoal: int, SubscriptionGrowthGoal: real)[
        datetime(2025-06-30), 395, 0.08,
        datetime(2025-07-31), 426, 0.08,
        datetime(2025-08-31), 460, 0.08,
        datetime(2025-09-30), 496, 0.08,
        datetime(2025-10-31), 535, 0.08,
        datetime(2025-11-30), 577, 0.08,
        datetime(2025-12-31), 623, 0.08
    ]
) on Month
| extend Month = iif(isempty(Month), Month1, Month)
| project-away Month1
```
Description: AI cohort subscriptions with rolling 28-day windows anchored to a cross-shard Current date. Builds latest, previous, and historical monthly points; unions; overlays goals via fullouter. Adapt by changing cohort keywords, window size, or goals datatable.

```kusto
BillingUsage_Daily 
| where Date >= startofmonth(now(), -12) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and ResourceId has 'microsoft.signalrservice/signalr' and SKU in ('Free', 'Standard', 'Premium')
| extend Month = startofmonth(Date)
| summarize SKU = max(SKU) by Month, ResourceId
| join kind = inner (ResourceMetrics
| where Date >= startofmonth(now(), -12) and ResourceId has 'microsoft.signalrservice/signalr'
| extend Month = startofmonth(Date)
| summarize HasConnection = max(MaxConnectionCount) > 0, Region = max(Region), ActiveDays = dcount(Date) by Month, ResourceId) on Month, ResourceId
| project Month, ResourceId, Category = 'Total', Region, SKU, HasConnection, LiveRatio = case(ActiveDays < 3, 'Swift', ActiveDays < 10, 'Occasional', 'Dedicate')
| summarize ResourceCnt = dcount(ResourceId, 3) by Month, Category, Region, SKU, HasConnection, LiveRatio
```
Description: Monthly SignalR resource totals by SKU with active/live classifications. Combines BillingUsage_Daily and ResourceMetrics on Month/ResourceId. Adapt by adjusting bins (Week), adding WebPubSub filter, or removing active filters.

```kusto
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| extend IsNew = StartDate > startofday(now(), -29), IsRetained = EndDate >= startofday(now(), -3)
| join kind = inner CustomerModel on SubscriptionId
| project SubscriptionId, Revenue, MaxConnection, Messages=MessageCount, Rate, CloudCustomerName, CustomerType, TPName, BillingType, OfferName, OfferType, P360_ID, IsRetained, IsNew,
C360Url = strcat('https://cxp.azure.com/cxobserve/customers/ch:customer::tpid:',TPID,'/summary')
| join kind = leftouter (RuntimeResourceTags_Daily | where Date > startofday(now(), -29) and ServiceType == 'SignalR'
| summarize IsAppService = max(IsAppService), UseProxy = max(IsProxy), IsStaticApps = max(IsStaticApps) by SubscriptionId) on SubscriptionId
| join kind = leftouter (FeatureTrack_Daily | where Date > startofday(now(), -29) and ResourceId has '/signalr/'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| summarize ServerSticky = sumif(RequestCount, Feature == 'ServerSticky'), NeededScale = sumif(RequestCount, Feature == 'ConnectionCountLimitReached'),
MultiEndpoints = sumif(RequestCount, Feature == 'MultiEndpoints') by SubscriptionId) on SubscriptionId
| extend ServerSticky = ServerSticky > 0, NeededScale = NeededScale > 0, MultiEndpoints = MultiEndpoints > 0
| join kind = leftouter (ConnectionMode_Daily | where Date > startofday(now(), -29) and ResourceId has '/signalr/'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| summarize IsServerless = sum(ServerlessConnection) > 0, IsServerMode = sum(ProxyConnection) > 0 by SubscriptionId) on SubscriptionId
| project-away SubscriptionId1, SubscriptionId2, SubscriptionId3
```
Description: Top subscriptions (SignalR) enriched with customer info, runtime tags, feature signals, and connection modes. Flags retention/new, serverless/server, and operational features. Adapt by switching Service to WebPubSub or altering the last-N-days window.

```kusto
let raw = OperationQoS_Daily
| where env_time > startofweek(now(), -8) and resourceId has 'microsoft.signalrservice/signalr'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)), UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec) by StartWeek = startofweek(env_time), Region = env_cloud_location, ResourceId = env_cloud_role;
raw
| summarize TotalOperation = sum(TotalTime), Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)), SlaAttainment = 1.0 * dcountif(ResourceId, Qos >=0.995, 4)/dcount(ResourceId, 4) by StartWeek, Region
| union ( raw
| summarize TotalOperation = sum(TotalTime), Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)), SlaAttainment = 1.0 * dcountif(ResourceId, Qos >=0.995, 4)/dcount(ResourceId, 4) by StartWeek, Region = 'Overall')
```
Description: Weekly QoS for SignalR computing uptime ratios and SLA attainment across regions, plus overall. Adapt by changing SLA threshold (0.995), extending weeks, or switching to WebPubSub resourceId contains filter.

```kusto
FeatureTrack_AutoScale_Daily
| where Date >= startofweek(now(), -12) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and ResourceId has '/signalr/'
| summarize ResourceCount = dcount(ResourceId) by Week = startofweek(Date)
| join kind = inner (BillingUsage_Daily 
| where Date >= startofweek(now(), -12) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and SKU == 'Premium' and ResourceId has '/signalr/'
| summarize TotalResource = dcount(ResourceId) by Week = startofweek(Date)) on Week
| extend PercentInPremium = 1.0*ResourceCount/TotalResource
| project-away Week1
```
Description: AutoScale feature adoption among Premium SignalR resources over the last 12 weeks. Counts feature-using resources and total Premium resources to compute percentage. Adapt by changing ResourceId cohort (WebPubSub), feature tables, or SKU.

```kusto
ConnectionMode_Daily 
| where Date > ago(60d) and ResourceId has 'microsoft.signalrservice/signalr'
| summarize ResourceCount = dcount(ResourceId), ConnectionCount = sum(ServerlessConnection) + sum(ProxyConnection) by Date, ServiceMode
```
Description: Daily connection mode summary (serverless vs proxy) for SignalR. Helps delineate service mode usage and counts. Adapt to WebPubSub by changing ResourceId filter; bin to Week/Month as needed.

```kusto
let initTime = datetime_add('year', -1, startofmonth(now()));
range x from 0 to 12 step 1
| extend RangeMonth = datetime_add('month', -1*x, startofmonth(now())), fakeKey = 1
| join kind = inner (SubscriptionRetentionSnapshot 
| where StartDate >= initTime
| extend StartMonth = startofmonth(StartDate), fakeKey = 1) on fakeKey
| extend Periods = datetime_diff('month', RangeMonth, StartMonth)
| where StartMonth <= RangeMonth and EndDate >= RangeMonth
| summarize Retain = dcount(SubscriptionId) by StartMonth, Periods
| join kind = inner (SubscriptionRetentionSnapshot 
| where StartDate >= initTime
| extend StartMonth = startofmonth(StartDate)
| distinct StartMonth, SubscriptionId, EndDate
| summarize Total = dcount(SubscriptionId) by StartMonth) on StartMonth
| extend Category = 'Subscription'
| project Month = StartMonth, Periods, Total, Retain, Ratio = 1.0*Retain/Total, Category
```
Description: Monthly subscription retention curve (SignalR) using retention snapshots. Computes retain and total per start cohort, then ratio by months since start. Adapt by using CustomerRetentionSnapshot or ResourceRetentionSnapshot, or AWPS retention tables.

## Reasoning Notes (only if uncertain)
- Timezone: Not explicitly stated; assumed UTC based on startofday/startofweek usage. If data stored with regional timezone, adjust bins accordingly.
- SignalRTeamInternalSubscriptionIds: Appears as a function or macro returning IDs; treated as an exclusion set everywhere. If unresolved in your environment, replace with a concrete list or function definition.
- Revenue unit prices: Queries use 1.61 (Standard) and 2.0 (Premium). In this playbook we recommend parameterizing as <StandardUnitPrice>/<PremiumUnitPrice>/<DefaultUnitPrice> to avoid hardcoding; ensure alignment with finance-approved rates.
- dcount sampling parameter (3 or 4): Used to stabilize cardinality estimates; if exact counts are required, consider count_distinct at performance cost.
- Completeness gate via EU/NonEU: Assumes these two regions are representative sentinel slices. If your sharding differs, update the region set to those that reliably indicate global completeness.
- Activity alignment: Many joins enforce presence in MaxConnectionCount_Daily to approximate “active” resources/subscriptions. If you need inclusive cohorts, use leftouter joins and avoid this gate.

- Acceptance Checklist
  - Identified timestamp columns (Date, env_time, AdvancedServerTimestampUtc, TIMESTAMP), windows and bins; timezone marked unknown (assumed UTC).
  - Documented freshness gating via sentinel regions and rolling anchors; advised effective end time strategy.
  - Produced entity model with keys and counting rules; snapshot vs. daily facts guidance.
  - Called out EU/Non-EU sharded tables and provided union pattern.
  - Included default exclusion patterns using placeholders for internal/test data and SKU gating.
  - Provided ID parsing/derivation snippets.
  - Example queries are copy-paste-ready with descriptions and adaptation guidance.
  - No fabricated fields; prices abstracted using placeholders where relevant.

## Canonical Tables

Below are the canonical tables used by SignalR and Web PubSub analytics in the main ADX cluster signalrinsights.eastus2, database SignalRBI, followed by cross-source tables. High-priority tables are listed first, then Normal, then Low. For each table: how it’s used, typical filters, and its exact schema. Where schema is not accessible cross-cluster, it is called out explicitly.

Important conventions observed in queries:
- ResourceId normalization and replica handling: lowercase ResourceId; for replicas, use substring(ResourceId, 0, indexof('/replicas/')) to reference the primary resource and avoid double counting.
- Exclude internal telemetry: SubscriptionId !in (SignalRTeamInternalSubscriptionIds or SignalRTeamInternalSubscriptionIds()) applied per query scope.
- Activity confirmation: join with MaxConnectionCount_Daily and/or ResourceMetrics to ensure active resources/subscriptions and to avoid counting idle entities.
- SKU normalization: SKU in ('Free','Standard','Premium'), exclude 'MessageCount' and 'MessageCountPremium' for revenue/consumption queries.
- Time windows: narrow windows (ago(30d), rolling 28d/7d, startofweek/month); use startofweek/month for weekly/monthly cohort math and retention.
- Revenue mapping: case(SKU == 'Free', 0.0, 'Standard', <UnitPriceStandard>, 'Premium', <UnitPricePremium>, 1.0)*Quantity; do not hardcode prices—use placeholders.
- Pack/mv-expand pattern: pack-array and mv-expand used for emitting multi-category series in a single stream.

Freshness note:
- “Daily/Weekly/Monthly” table names imply batch updates at those cadences; exact delay and timezone are unknown. Be cautious using current-day data—it may be incomplete.

---

### Table name: signalrinsights.eastus2/SignalRBI.BillingUsage_Daily
- Priority: High
- What this table represents: Daily billing usage facts per resource/subscription/region/SKU. Fact table; zero rows for a day imply no usage ingested for that scope.
- Freshness expectations: Daily batch. Queries commonly use ago(30–61d) and start of week/month windows.
- When to use / When to avoid:
  - Use to compute consumption (Quantity * 24 where appropriate) and revenue (Quantity * <UnitPrice>).
  - Use to count paid units by SKU and trend by Day/Week/Month.
  - Join to SubscriptionMappings for segmentation (CustomerType, SegmentName, Offer/Billing).
  - Avoid mixing ‘MessageCount’ SKUs in revenue; exclude internal subscriptions.
- Similar tables & how to choose:
  - ResourceMetrics contains operational usage (connections/messages); BillingUsage_Daily is billing facts. Use both together for “top subscriptions” and activity gating.
  - Cached_SubsTotalWeekly/Monthly_Snapshot are precomputed totals; choose those for reporting cohorts.
- Common Filters: Date >= ago(30–61d); ResourceId has '/signalr/' or '/webpubsub/'; SKU in ('Free','Standard','Premium'); SubscriptionId !in (SignalRTeamInternalSubscriptionIds).

Table columns:
| Column          | Type     | Description or meaning |
|-----------------|----------|------------------------|
| Date            | datetime | Usage/billing day (partition key) |
| Region          | string   | Azure region of the resource |
| SubscriptionId  | string   | Subscription GUID owning the resource |
| ResourceId      | string   | ARM resource ID (lowercased in queries) |
| SKU             | string   | Plan: Free, Standard, Premium, MessageCount, etc. |
| Quantity        | real     | Daily billed quantity (units depend on SKU) |

Column Explain:
- Date: Use for time slicing (Day/Week/Month via startofweek/startofmonth).
- SKU: Segment paid vs free. Exclude MessageCount for revenue.
- Quantity: Multiply by <UnitPrice> to estimate revenue; sometimes multiply by 24 to normalize consumption.
- ResourceId: Filter by service type ('/signalr/', '/webpubsub/'); handle replicas separately.
- SubscriptionId/Region: Join to segment and filter by region.

---

### Table name: signalrinsights.eastus2/SignalRBI.MaxConnectionCount_Daily
- Priority: High
- What this table represents: Daily max connection count per resource/subscription and region. Fact table; zero or missing implies no connections ingested.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use to confirm activity (HasConnection) before counting resources/subscriptions.
  - Use for connection trend lines by Date/Week/Month.
  - Avoid using standalone for customer segmentation—join to SubscriptionMappings.
- Similar tables & how to choose:
  - ResourceMetrics also contains MaxConnectionCount rolled from events; use ResourceMetrics for combined metrics (messages + connections), MaxConnectionCount_Daily for activity gating and simple maxima.
- Common Filters: Date >= ago(60d); matches $left.Role == $right.Role in some joins; SubscriptionId; Region.

Table columns:
| Column          | Type     | Description or meaning |
|-----------------|----------|------------------------|
| Date            | datetime | Day of max connection count |
| Role            | string   | Resource identifier (normalized resource id) |
| SubscriptionId  | string   | Subscription GUID |
| CustomerType    | string   | Customer classification if present in ingestion |
| Region          | string   | Azure region |
| MaxConnectionCount | long  | Max connections observed that day |

Column Explain:
- MaxConnectionCount: Use to set HasConnection = MaxConnectionCount > 0.
- Role: Often matches lowercased ResourceId; used in inner joins with BillingUsage_Daily.
- Date: Used to form Week/Month and rolling windows.

---

### Table name: signalrinsights.eastus2/SignalRBI.SubscriptionMappings
- Priority: High
- What this table represents: Subscription-to-customer mapping snapshot (segmentation and offers). Dimension table; missing rows imply unmapped subscription.
- Freshness expectations: Snapshot; update cadence unknown.
- When to use / When to avoid:
  - Use to enrich billing/usage with CustomerType, SegmentName, OfferName/Type, BillingType, and identities.
  - Avoid assuming stability for long windows; rejoin for every time slice.
- Similar tables & how to choose:
  - CustomerModel used in top-subscription lists; SubscriptionMappings is broader and used for most joins.
- Common Filters: Direct joins by SubscriptionId; distinct SegmentName for slicers.

Table columns:
| Column          | Type     | Description or meaning |
|-----------------|----------|------------------------|
| P360_ID         | string   | Partner/customer 360 ID |
| CloudCustomerGuid | string | Cloud customer GUID |
| SubscriptionId  | string   | Subscription GUID |
| CustomerType    | string   | ‘Internal’, ‘External’, etc. |
| CustomerName    | string   | Display name |
| SegmentName     | string   | Customer segment |
| OfferType       | string   | Offer category |
| OfferName       | string   | Offer name |
| BillingType     | string   | Billing classification (‘EA’, ‘PAYG’, etc.) |
| WorkloadType    | string   | Workload classification |
| S500            | string   | Additional classification tag |

Column Explain:
- CustomerType/BillingType: Use to derive UsageType = Internal vs external billing categories.
- SegmentName: Build slicers and segment reports.
- OfferType/Name: Breakdowns in cohort summaries.

---

### Table name: signalrinsights.eastus2/SignalRBI.ResourceMetrics
- Priority: High
- What this table represents: Daily operational usage per resource (messages, connections, errors). Fact table for operational metrics.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use to trend messages and connections alongside billing data.
  - Use to define activity thresholds (AvgConnectionCount/MaxConnectionCount).
  - Avoid direct revenue math; always combine with BillingUsage_Daily for paid units.
- Similar tables & how to choose:
  - MaxConnectionCount_Daily for simple max; ResourceMetrics gives combined views (MessageCount, AvgConn).
- Common Filters: Date windows; ResourceId has 'microsoft.signalrservice/signalr' or '.../webpubsub'.

Table columns:
| Column            | Type     | Description or meaning |
|-------------------|----------|------------------------|
| Date              | datetime | Metric day |
| Region            | string   | Azure region |
| ResourceId        | string   | ARM resource |
| SumMessageCount   | real     | Total messages |
| MaxConnectionCount| real     | Max connections (operational) |
| AvgConnectionCount| real     | Average connections |
| SumSystemErrors   | real     | System error count |
| SumTotalOperations| real     | Operation count (requests/events) |

Column Explain:
- SumMessageCount/Connections: Use for activity, top subscription trends.
- ResourceId/Date: Join with BillingUsage_Daily for composite views.

---

### Table name: signalrinsights.eastus2/SignalRBI.RPSettingLatest
- Priority: High
- What this table represents: Latest RP settings per resource (SKU, Kind, mode, security). Snapshot; one row per resource.
- Freshness expectations: Snapshot; updated when settings change.
- When to use / When to avoid:
  - Use to determine ServiceMode (Default/Serverless/etc.), Kind (SignalR/WebPubSub/SocketIO), TLS/logging flags.
  - Use Extras JSON for feature detection (e.g., Aspire, SocketIO serviceMode).
  - Avoid relying on it for time series; it’s latest-only.
- Similar tables & how to choose:
  - ConnectionMode_Daily shows connections by ServiceMode; combine to quantify adoption.
- Common Filters: ResourceId has '/Microsoft.SignalRService/SignalR/' or '/WebPubSub/'; Extras has 'isAspire'; Kind == 'SocketIO'.

Table columns:
| Column                 | Type     | Description or meaning |
|------------------------|----------|------------------------|
| ResourceId             | string   | ARM resource (lowercased) |
| Region                 | string   | Azure region |
| SKU                    | string   | Free/Standard/Premium |
| Kind                   | string   | Service kind: SignalR/WebPubSub/SocketIO |
| State                  | string   | Provisioning state |
| ServiceMode            | string   | Service mode (e.g., Serverless) |
| IsUpstreamSet          | bool     | Upstream configured |
| IsEventHandlerSet      | bool     | Event handler configured |
| EnableTlsClientCert    | bool     | TLS client cert enabled |
| IsPrivateEndpointSet   | bool     | Private endpoint configured |
| EnablePublicNetworkAccess | bool  | Public network enabled |
| DisableLocalAuth       | bool     | Local auth disabled |
| DisableAadAuth         | bool     | AAD auth disabled |
| IsServerlessTimeoutSet | bool     | Serverless timeout configured |
| AllowAnonymousConnect  | bool     | Anonymous connect enabled |
| EnableRegionEndpoint   | bool     | Region endpoint enabled |
| ResourceStopped        | bool     | Resource stopped |
| EnableLiveTrace        | bool     | Live trace enabled |
| EnableResourceLog      | bool     | Resource log enabled |
| LastUpdated            | datetime | Last update timestamp |
| Extras                 | string   | JSON with extra settings (e.g., socketIO.serviceMode) |

Column Explain:
- ServiceMode/Kind: Use to classify SocketIO serverless adoption; Aspire flags via Extras.
- Region/SKU: Join to BillingUsage_Daily for premium-specific features.

---

### Table name: signalrinsights.eastus2/SignalRBI.ConnectionMode_Daily
- Priority: High
- What this table represents: Daily serverless/proxy connection counts by resource and service mode.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use to infer serverless adoption for SignalR/WebPubSub via sum(ServerlessConnection) and sum(ProxyConnection).
  - Use in top-subscription features (IsServerless vs ServerMode).
  - Avoid using without ResourceId normalization for replicas.
- Similar tables & how to choose:
  - RPSettingLatest for declared ServiceMode; ConnectionMode_Daily for observed connections by mode.
- Common Filters: Date > ago(60d); ResourceId has '/signalr/'.

Table columns:
| Column              | Type     | Description or meaning |
|---------------------|----------|------------------------|
| Date                | datetime | Day |
| ResourceId          | string   | ARM resource |
| ServerlessConnection| long     | Serverless connections that day |
| ProxyConnection     | long     | Proxy/server connections that day |
| ServiceMode         | string   | Declared mode |

Column Explain:
- ServerlessConnection/ProxyConnection: Use to set flags in top subscription summaries (IsServerless/IsServerMode).

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_SubsTotalWeekly_Snapshot
- Priority: High
- What this table represents: Weekly precomputed subscription totals with attributes. Aggregate snapshot.
- Freshness expectations: Weekly batch; snapshot updated for latest week.
- When to use / When to avoid:
  - Use to quickly aggregate SubscriptionCnt by cohort dimensions.
  - Avoid recomputing raw counts from BillingUsage_Daily unless specialized logic is needed.
- Similar tables & how to choose:
  - Cached_SubsTotalMonthly_Snapshot for month; use weekly vs monthly based on reporting period.
- Common Filters: ServiceType == 'SignalR' or 'WebPubSub'; Week; join to SubscriptionMappings for CloudCustomerGuid.

Table columns:
| Column         | Type     | Description or meaning |
|----------------|----------|------------------------|
| Week           | datetime | Week start |
| ServiceType    | string   | SignalR/WebPubSub |
| SubscriptionId | string   | Subscription GUID |
| Region         | string   | Region |
| SKU            | string   | SKU |
| HasConnection  | bool     | Any connection activity |
| LiveRatio      | string   | Swift/Occasional/Dedicate classification |

Column Explain:
- HasConnection/LiveRatio: Cohort classification derived from activity days and MaxConn.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_SubsTotalMonthly_Snapshot
- Priority: High
- What this table represents: Monthly precomputed subscription totals. Aggregate snapshot.
- Freshness expectations: Monthly batch.
- When to use / When to avoid:
  - Use for monthly cohorts across Offer/BillingType/CustomerType.
  - Avoid mixing with current month incomplete data.
- Similar tables & how to choose:
  - Weekly snapshot when weekly granularity is required.
- Common Filters: ServiceType; Month; join to SubscriptionMappings.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Month         | datetime | Month start |
| ServiceType   | string   | SignalR/WebPubSub |
| SubscriptionId| string   | Subscription GUID |
| Region        | string   | Region |
| SKU           | string   | SKU |
| HasConnection | bool     | Any connection activity |
| LiveRatio     | string   | Swift/Occasional/Dedicate |

Column Explain:
- Month: Use startofmonth(Date) for alignment; use for growth calculation via prior-month join.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_Asrs_TopCustomersWoW_v2_Snapshot
- Priority: High
- What this table represents: Top external customers for SignalR with week-over-week deltas per category (Revenue, Connections, etc.). Snapshot of ranking metrics.
- Freshness expectations: Weekly batch.
- When to use / When to avoid:
  - Use to surface top movers and top absolute values for subscriptions/customers.
  - Avoid mixing categories without pivoting.
- Similar tables & how to choose:
  - Cached_Awps_TopCustomersWoW_v2_Snapshot for WebPubSub.
- Common Filters: Order by DeltaValue asc/desc; use Rank/W1Rank/W3Rank to select top N.

Table columns:
| Column                 | Type     | Description or meaning |
|------------------------|----------|------------------------|
| P360_ID                | string   | Customer 360 ID |
| P360_CustomerDisplayName | string | Display name |
| SKU                    | string   | SKU |
| CustomerType           | string   | Internal/External |
| BillingType            | string   | Billing classification |
| Category               | string   | Metric category (Revenue, Connections, etc.) |
| CurrentValue           | real     | Current metric value |
| P360Url                | string   | Deep link to CXP |
| LastDay                | datetime | Last day evaluated |
| UsageType              | string   | Derived usage type |
| CurrentValue1          | real     | Alternate current metric |
| PrevValue              | real     | Previous period value |
| W3Value                | real     | 3-week value |
| DeltaValue             | real     | Delta vs prior |
| Rank                   | long     | Current rank |
| W1Rank                 | long     | 1-week rank |
| W3Rank                 | long     | 3-week rank |

Column Explain:
- Category/CurrentValue/DeltaValue: Use for ranking and trend direction.
- BillingType/CustomerType: Segment top customers.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_Awps_TopCustomersWoW_v2_Snapshot
- Priority: High
- What this table represents: Same as above, for WebPubSub.
- Freshness expectations: Weekly batch.
- When to use / When to avoid: As above.
- Similar tables & how to choose: ASRS vs AWPS choose based on ServiceType.

Table columns: same structure as ASRS top customers.

Column Explain: same considerations.

---

### Table name: signalrinsights.eastus2/SignalRBI.FeatureTrackV2_Daily
- Priority: High
- What this table represents: Daily feature usage events per resource (Feature, Category). Fact events with counts.
- Freshness expectations: Daily batch; EU and Non-EU variants are unioned for completeness.
- When to use / When to avoid:
  - Use to quantify feature adoption (BlazorServerSide, Samples, throttles, pings).
  - Use for specific feature signals (NeededScale, MultiEndpoints, Upstream errors via FeatureTrack_Daily).
  - Avoid without gating by BillingUsage_Daily to exclude idle resources.
- Similar tables & how to choose:
  - FeatureTrack_Daily for core feature signals; FeatureTrackV2_EU_Daily for EU data; RuntimeResourceTags_Daily for environment tags.
- Common Filters: Date > startofweek(now()) - 56d; ResourceId has '/signalr/' or '/webpubsub/'; Feature in set; exclude internal subs.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Event day (start-of-day often applied) |
| Feature       | string   | Feature name |
| Category      | string   | Feature category |
| ResourceId    | string   | Resource emitting the feature |
| SubscriptionId| string   | Owner subscription |
| Properties    | string   | Additional properties JSON |
| RequestCount  | long     | Event/request count |

Column Explain:
- Feature/Category: Use to group metrics; normalize Category (e.g., ping groups).
- RequestCount: Aggregate per Week for adoption views.

---

### Table name: signalrinsights.eastus2/SignalRBI.FeatureTrackV2_EU_Daily
- Priority: High
- What this table represents: EU-localized feature tracking events. Same semantics as FeatureTrackV2_Daily.
- Freshness expectations: Daily batch.
- When to use / When to avoid: Union with Non-EU for global coverage.
- Common Filters: same.

Table columns: same as FeatureTrackV2_Daily.

Column Explain: same.

---

### Table name: signalrinsights.eastus2/SignalRBI.FeatureTrack_AutoScale_Daily
- Priority: High
- What this table represents: Auto-scale related events per resource/day. Used to compute percentage of premium resources with auto-scale usage.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use to count auto-scale resources per Week and compute PercentInPremium by joining premium resources from BillingUsage_Daily.
  - Avoid standalone percentage without premium filter alignment.
- Similar tables & how to choose:
  - BillingUsage_Daily (Premium subset) to create denominator; FeatureTrack_Daily for scale-limitation signals.
- Common Filters: Date >= startofweek(now(), -12); ResourceId has '/signalr/' or '/webpubsub/'; SubscriptionId !in internal list.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Event day |
| Region        | string   | Region |
| ResourceId    | string   | Resource |
| SubscriptionId| string   | Subscription |
| RequestCount  | long     | Auto-scale related event count |

Column Explain:
- RequestCount: Proxy for auto-scale activity; join to compute resource counts and ratios.

---

### Table name: signalrinsights.eastus2/SignalRBI.FeatureTrack_Daily
- Priority: High
- What this table represents: Core feature signals (e.g., ServerSticky, ConnectionCountLimitReached, MultiEndpoints, Upstream_Exceptions).
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use for “TopSubscriptions” derived feature flags (sticky, scale needed, multi endpoints).
  - Avoid using without proper Date window alignment (~29 days in queries).
- Similar tables & how to choose:
  - FeatureTrackV2_Daily used for broader feature coverage; FeatureTrack_Daily for canonical signals referenced by dashboards.
- Common Filters: ResourceId has '/signalr/' or '/webpubsub/'; Date > startofday(now()) - 29d; SKU != 'MessageCount' when joined with BillingUsage_Daily.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Event day |
| Feature       | string   | Signal name |
| ResourceId    | string   | Resource ID |
| SubscriptionId| string   | Subscription |
| RequestCount  | long     | Count of occurrences |

Column Explain:
- Feature: Use case-level definitions: e.g., ‘ConnectionCountLimitReached’ for scaling needs; ‘ServerSticky’ adoption.

---

### Table name: signalrinsights.eastus2/SignalRBI.RuntimeResourceTags_Daily
- Priority: High
- What this table represents: Daily classification tags for resources (AppService, StaticApps, Proxy, Sample flags, success/failure).
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use to tag top subscriptions with environment usage (AppService, StaticApps, Proxy).
  - Use for feature grouping of samples for WebPubSub dashboards.
  - Avoid assuming stability; aggregate per week for adoption rates.
- Similar tables & how to choose:
  - FeatureTrack tables for feature-level events; this table is environment characteristics.
- Common Filters: Date > startofday(now(), -29); ServiceType == 'SignalR' or 'WebPubSub'; group by SubscriptionId.

Table columns:
| Column          | Type     | Description or meaning |
|-----------------|----------|------------------------|
| Date            | datetime | Day |
| ResourceId      | string   | Resource |
| SubscriptionId  | string   | Subscription |
| ServiceType     | string   | SignalR/WebPubSub |
| IsAppService    | bool     | AppService usage flag |
| IsStaticApps    | bool     | Static Web Apps usage flag |
| IsSample        | bool     | Sample flag |
| IsProxy         | bool     | Using proxy |
| HasFailure      | bool     | Failure observed |
| HasSuccess      | bool     | Success observed |
| Extra           | string   | Additional info |

Column Explain:
- IsAppService/IsStaticApps/IsProxy: Derive environment adoption ratios; join with top subscriptions.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_TopSubscriptions_Snapshot
- Priority: High
- What this table represents: Snapshot summarizing top subscriptions (Revenue, Connections, Messages, etc.) with rate and active windows.
- Freshness expectations: Daily/weekly snapshot; used with 29-day filter in queries.
- When to use / When to avoid:
  - Use to present per-subscription metric categories via mv-expand (PaidUnits, Revenue, Messages, Connections, Resources).
  - Avoid mixing different Service types; filter Service == 'SignalR' or 'WebPubSub'.
- Similar tables & how to choose:
  - Combine with ResourceMetrics and BillingUsage_Daily for per-day trend series.
- Common Filters: Service == 'SignalR' or 'WebPubSub'; Date > startofday(now(), -29).

Table columns:
| Column         | Type     | Description or meaning |
|----------------|----------|------------------------|
| SubscriptionId | string   | Subscription |
| Revenue        | real     | Revenue snapshot value |
| MaxConnection  | long     | Max connections |
| MessageCount   | long     | Messages |
| StartDate      | datetime | Start of snapshot window |
| EndDate        | datetime | End of snapshot window |
| TopRevenue     | real     | Top revenue value used for ranks |
| TopConnection  | long     | Top connections used for ranks |
| TopMessageCount| long     | Top messages used for ranks |
| Rate           | real     | Composite rate |
| Service        | string   | SignalR/WebPubSub |

Column Explain:
- Revenue/PaidUnits are derived via joins with BillingUsage_Daily; use pack/mv-expand for multi-category trend streams.

---

### Table name: signalrinsights.eastus2/SignalRBI.CustomerModel
- Priority: High
- What this table represents: Customer enrichment model with subscription-level attributes used in top-subscription lists (names, TP info, rates).
- Freshness expectations: Snapshot; update cadence unknown.
- Accessibility: Not accessible via current product connection—get_table_schema returned cross-cluster access denied (customerdomrptwus3prod.westus3/customerdomdata). Column definitions are inferred from usage only.
- When to use / When to avoid:
  - Use to enrich top subscriptions with CloudCustomerName, TPName, Rate, Offer/Billing info, P360_ID/TPID.
  - Avoid relying on columns without verifying in your cluster; cross-cluster permissions required.
- Similar tables & how to choose:
  - SubscriptionMappings is accessible and provides customer/offer info; CustomerModel adds richer metrics used for top lists.
- Common Filters: Join on SubscriptionId.

Table columns (inferred from queries; schema fetch not accessible):
| Column              | Type     | Description or meaning |
|---------------------|----------|------------------------|
| SubscriptionId      | string   | Key for joins |
| CloudCustomerName   | string   | Customer display name |
| CustomerType        | string   | Internal/External |
| BillingType         | string   | Billing classification |
| OfferName           | string   | Offer name |
| OfferType           | string   | Offer type |
| P360_ID             | string   | Customer 360 ID |
| TPID                | string   | Tenant partner ID |
| TPName              | string   | Partner name |
| Rate                | real     | Composite rate used in ranking |
| Revenue             | real     | Revenue metric (seen in joins) |
| MaxConnection       | long     | Max connection metric |
| MessageCount        | long     | Message count metric |

Column Explain:
- P360_ID/TPID/TPName: Use for deep links and partner context.
- Rate/Revenue/MaxConnection/MessageCount: Used in top-subscription summaries.

---

### Table name: signalrinsights.eastus2/SignalRBI.OKRv2021
- Priority: High
- What this table represents: Time series for OKR metrics with Category and Value; pivoted for tiles.
- Freshness expectations: Historical dataset; update cadence unknown.
- When to use / When to avoid:
  - Use for OKR trend pivots via evaluate pivot(Category, sum(Value)).
  - Avoid mixing with current ad-hoc goals; goals are often injected via datatable and fullouter join.
- Similar tables & how to choose:
  - OKRv2021_AWPS and OKRv2021_SocketIO for AWPS and SocketIO slices.
- Common Filters: Date >= datetime(20200701); pivot by Category.

Table columns:
| Column   | Type     | Description or meaning |
|----------|----------|------------------------|
| Date     | datetime | Time series date |
| Category | string   | OKR category label |
| Value    | real     | Metric value |

Column Explain:
- Category: Choose the correct categories to pivot into columns.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_ZnOKRARR_Snapshot
- Priority: High
- What this table represents: Snapshot for ARR goals vs actual (often joined with a datatable of goals). Aggregate.
- Freshness expectations: Monthly snapshots; filtered to startofmonth ranges.
- When to use / When to avoid:
  - Use for OKR income view with added goal lines via fullouter join on TimeStamp.
  - Avoid relying on real revenue without joining BillingUsage_Daily-derived income.
- Common Filters: Project TimeStamp and goal columns; filter TimeStamp windows.

Table columns:
| Column     | Type     | Description or meaning |
|------------|----------|------------------------|
| TimeStamp  | datetime | Monthly timestamp |
| SignalR    | real     | SignalR income/ARR snapshot |
| WebPubSub  | real     | WebPubSub income/ARR snapshot |

Column Explain:
- TimeStamp: Align with monthly goals; ensure consistent startofmonth windows.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_ZnOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Weekly estimated revenue snapshot.
- Freshness expectations: Weekly snapshot.
- Common Filters: Use with OKR income weekly tiles.

Table columns:
| Column   | Type     | Description or meaning |
|----------|----------|------------------------|
| Date     | datetime | Week date |
| Category | string   | Revenue category |
| Value    | real     | Estimated revenue |

Column Explain:
- Category/Value: Plot weekly revenue trend.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_ZnOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Monthly estimated revenue snapshot.
- Freshness expectations: Monthly.
- Common Filters: Use startofmonth windows.

Table columns:
| Column   | Type     | Description or meaning |
|----------|----------|------------------------|
| Date     | datetime | Month date |
| Category | string   | Revenue category |
| Value    | real     | Estimated revenue |

Column Explain:
- Value: Use for monthly revenue trend in OKR.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_ZnOKRSubs_Snapshot
- Priority: High
- What this table represents: Snapshot for subscription OKRs (SignalR/WebPubSub), joined to goal datatable.
- Freshness expectations: Monthly.
- Common Filters: Fullouter join goals on TimeStamp.

Table columns:
| Column     | Type   | Description or meaning |
|------------|--------|------------------------|
| TimeStamp  | datetime | Month timestamp |
| SignalR    | long   | Subscription count snapshot (SignalR) |
| WebPubSub  | long   | Subscription count snapshot (WebPubSub) |

Column Explain:
- Use to compare against monthly subscription goals.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_CuOKRConsumption_Snapshot
- Priority: High
- What this table represents: Consumption OKR snapshot for SignalR/WebPubSub.
- Freshness expectations: Monthly.
- Common Filters: Joined to datatable of goals on TimeStamp.

Table columns:
| Column     | Type     | Description or meaning |
|------------|----------|------------------------|
| TimeStamp  | datetime | Month timestamp |
| Consumption| real     | Total consumption snapshot |
| SignalR    | real     | SignalR consumption |
| WebPubSub  | real     | WebPubSub consumption |

Column Explain:
- Use with consumption goals/growth target values.

---

### Table name: signalrinsights.eastus2/SignalRBI.OKRv2021_AWPS
- Priority: High
- What this table represents: OKR time series for AWPS; similar to OKRv2021 but filtered to AWPS.
- Freshness expectations: Historical; update cadence unknown.
- Common Filters: Union with OKRv2021_SocketIO in queries.

Table columns:
| Column   | Type     | Description or meaning |
|----------|----------|------------------------|
| Date     | datetime | Time series date |
| Category | string   | OKR category |
| Value    | real     | Value |

Column Explain:
- Combine with SocketIO variants for composite view.

---

### Table name: signalrinsights.eastus2/SignalRBI.OKRv2021_SocketIO
- Priority: High
- What this table represents: OKR series for SocketIO specifically.
- Freshness expectations: Historical; update cadence unknown.
- Common Filters: Union with OKRv2021_AWPS; join with goal datatables in OKR_AWPS_SocketIO.

Table columns:
| Column   | Type     | Description or meaning |
|----------|----------|------------------------|
| Date     | datetime | Time series date |
| Category | string   | Category |
| Value    | real     | Metric value |

Column Explain:
- SocketIO adoption metrics.

---

### Table name: signalrinsights.eastus2/SignalRBI.OKR_AWPS_SocketIO
- Priority: High
- What this table represents: Derived OKR stream for SocketIO used in OKR comparisons; often joined with a datatable of goals (SocketIOGoal/GrowthGoal).
- Freshness expectations: Historical/time series.
- Common Filters: where Date >= datetime(20230820); join on Date, CustomerType.

Table columns:
| Column       | Type   | Description or meaning |
|--------------|--------|------------------------|
| Date         | datetime | Time series date |
| CustomerType | string | Internal/External |
| Value        | int    | Metric value (derived series) |

Column Explain:
- Used for goal comparison; filter to External customer types.

---

### Table name: signalrinsights.eastus2/SignalRBI.KPIv2019
- Priority: Normal
- What this table represents: KPI counts (subscriptions/resources) over time for SignalR.
- Freshness expectations: Historical KPI; update cadence unknown.
- When to use / When to avoid:
  - Use for simple KPI charts; filter Date >= datetime(20190101).
  - Avoid mixing with AWPS KPIs unless pivoting separately.
- Similar tables & how to choose: KPI_AWPS, KPI_SocketIO.

Table columns:
| Column            | Type   | Description or meaning |
|-------------------|--------|------------------------|
| Date              | datetime | Date |
| SubscriptionCount | long   | Count of subscriptions |
| ResourceCount     | long   | Count of resources |

Column Explain:
- Use for long-range KPI baselines.

---

### Table name: signalrinsights.eastus2/SignalRBI.KPI_AWPS
- Priority: Normal
- What this table represents: AWPS KPIs (subscriptions/resources) similar to KPIv2019.
- Freshness expectations: Historical.
- Common Filters: Direct table selection.

Table columns: same as KPIv2019.

Column Explain: same.

---

### Table name: signalrinsights.eastus2/SignalRBI.KPI_SocketIO
- Priority: Normal
- What this table represents: SocketIO KPIs (subscriptions/resources).
- Freshness expectations: Historical.

Table columns: same as KPIv2019.

Column Explain: same.

---

### Table name: signalrinsights.eastus2/SignalRBI.ChurnCustomers_Monthly
- Priority: Normal
- What this table represents: Monthly churn metrics per service type.
- Freshness expectations: Monthly snapshots with RunDay (latest run per month).
- When to use / When to avoid:
  - Use to compute churn rates: StandardChurn/Standard, Churn/Total.
  - Avoid using non-latest RunDay; filter by row_number Rank == 1.
- Common Filters: ServiceType == 'SignalR' or 'WebPubSub'.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Month         | datetime | Month |
| ServiceType   | string   | SignalR/WebPubSub |
| Total         | long     | Total active |
| Churn         | long     | Total churned |
| Standard      | long     | Standard plan count |
| StandardChurn | long     | Standard churn count |
| RunDay        | datetime | Snapshot run timestamp |

Column Explain:
- Compute churn rates with division; select latest per month.

---

### Table name: signalrinsights.eastus2/SignalRBI.ConvertCustomer_Weekly
- Priority: Normal
- What this table represents: Weekly conversion transitions (Free→Standard/Paid/Premium; Standard→Premium).
- Freshness expectations: Weekly snapshots; latest per week by RunDay.
- When to use / When to avoid:
  - Use to show conversion counts; coalesce nulls to 0 in tiles.
- Common Filters: ServiceType; Week >= startofweek(now(), -12).

Table columns:
| Column             | Type     | Description or meaning |
|--------------------|----------|------------------------|
| Week               | datetime | Week |
| ServiceType        | string   | SignalR/WebPubSub |
| FreeToStandard     | long     | Conversions from Free to Standard |
| TotalCustomers     | long     | Total customers considered |
| StandardCustomers  | long     | Standard customers |
| RunDay             | datetime | Snapshot run timestamp |
| FreeToPaid         | long     | Free to any paid |
| StandardToPremium  | long     | Standard to Premium |
| FreeToPremium      | long     | Free to Premium |
| PremiumCustomers   | long     | Premium customers |

Column Explain:
- Use the corrected columns (coalesce where null) for badges.

---

### Table name: signalrinsights.eastus2/SignalRBI.SubscriptionRetentionSnapshot
- Priority: Normal
- What this table represents: Retention snapshot with StartDate/EndDate windows per subscription.
- Freshness expectations: Snapshot; used for retention cohort analysis.
- Common Filters: StartDate >= initTime; use join/group to compute Retain/Total.

Table columns:
| Column         | Type     | Description or meaning |
|----------------|----------|------------------------|
| SubscriptionId | string   | Subscription |
| StartDate      | datetime | Cohort start |
| EndDate        | datetime | Cohort end |

Column Explain:
- Used to produce retention curves by Month/Week.

---

### Table name: signalrinsights.eastus2/SignalRBI.CustomerRetentionSnapshot
- Priority: Normal
- What this table represents: Customer-level retention snapshot (C360_ID).
- Freshness expectations: Snapshot.

Table columns:
| Column   | Type     | Description or meaning |
|----------|----------|------------------------|
| C360_ID  | string   | Customer 360 ID |
| StartDate| datetime | Cohort start |
| EndDate  | datetime | Cohort end |

Column Explain:
- Use for customer-level retention curves.

---

### Table name: signalrinsights.eastus2/SignalRBI.ResourceRetentionSnapshot
- Priority: Normal
- What this table represents: Resource-level retention snapshot.
- Freshness expectations: Snapshot.

Table columns:
| Column    | Type     | Description or meaning |
|-----------|----------|------------------------|
| ResourceId| string   | Resource id |
| StartDate | datetime | Cohort start |
| EndDate   | datetime | Cohort end |

Column Explain:
- Use for resource-level retention curves.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_ResourceFlow_Snapshot
- Priority: Normal
- What this table represents: Precomputed resource flow cohorts (New/Leaving) by Date, ServiceType and partition (Week/Month).
- Freshness expectations: Weekly/Monthly snapshots.
- When to use / When to avoid:
  - Use for ResourceCategory_W/M tiles.
- Common Filters: ServiceType == 'SignalR'/'WebPubSub'; Partition == 'Week'/'Month'.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Category      | string   | New/Leaving cohort |
| Region        | string   | Region |
| SKU           | string   | SKU |
| HasConnection | bool     | Has activity |
| LiveRatio     | string   | Swift/Occasional/Dedicate |
| ResourceCnt   | long     | Count |
| Date          | datetime | Week/Month date |
| ServiceType   | string   | Service type |
| Partition     | string   | 'Week' or 'Month' |

Column Explain:
- Use Category/Partition to select cohort and period.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_CustomerFlow_Snapshot
- Priority: Normal
- What this table represents: Precomputed customer flow cohorts with segmentation.
- Freshness expectations: Weekly/Monthly snapshots.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Category      | string   | New/Leaving |
| Region        | string   | Region |
| SKU           | string   | SKU |
| HasConnection | bool     | Activity |
| LiveRatio     | string   | Activity ratio |
| CustomerType  | string   | Customer type |
| SegmentionType| string   | Segment name |
| CustomerCnt   | long     | Count |
| Date          | datetime | Date |
| ServiceType   | string   | Service type |
| Partition     | string   | Week/Month |

Column Explain:
- SegmentionType: Use for segment splits.

---

### Table name: signalrinsights.eastus2/SignalRBI.Cached_SubscriptionFlow_Snapshot
- Priority: Normal
- What this table represents: Precomputed subscription flow cohorts with offer/billing attributes.
- Freshness expectations: Weekly/Monthly snapshots.

Table columns:
| Column         | Type     | Description or meaning |
|----------------|----------|------------------------|
| Category       | string   | New/Leaving |
| Region         | string   | Region |
| SKU            | string   | SKU |
| HasConnection  | bool     | Activity |
| LiveRatio      | string   | Activity ratio |
| CustomerType   | string   | Customer type |
| OfferName      | string   | Offer name |
| OfferType      | string   | Offer type |
| BillingType    | string   | Billing type |
| SubscriptionCnt| long     | Count |
| Date           | datetime | Date |
| ServiceType    | string   | Service type |
| Partition      | string   | Week/Month |

Column Explain:
- Use Offer/Billing attributes for cohort breakdowns.

---

### Table name: signalrinsights.eastus2/SignalRBI.OperationQoS_Daily
- Priority: Low
- What this table represents: Daily operational QoS metrics per environment and region (totalUpTimeSec/totalTimeSec).
- Freshness expectations: Daily batch.
- Common Filters: env_time windows; resourceId has 'microsoft.signalrservice/signalr' or 'webpubsub'.

Table columns:
| Column                | Type     | Description or meaning |
|-----------------------|----------|------------------------|
| env_name              | string   | Environment name |
| env_time              | datetime | Metric day |
| resourceId            | string   | Resource id |
| env_cloud_role        | string   | Role |
| env_cloud_roleInstance| string   | Role instance |
| env_cloud_environment | string   | Cloud env |
| env_cloud_location    | string   | Region |
| env_cloud_deploymentUnit | string| Deployment unit |
| totalUpTimeSec        | long     | Up time seconds |
| totalTimeSec          | long     | Total time seconds |

Column Explain:
- Use sums to compute Qos = sum(UpTime)/sum(TotalTime).

---

### Table name: signalrinsights.eastus2/SignalRBI.ConnectivityQoS_Daily
- Priority: Low
- What this table represents: Daily connectivity QoS (similar schema to OperationQoS_Daily).
- Freshness expectations: Daily batch.
- Common Filters: Same.

Table columns: same as OperationQoS_Daily.

Column Explain: same.

---

### Table name: signalrinsights.eastus2/SignalRBI.ManageRPQosDaily
- Priority: Low
- What this table represents: Daily RP manage-plane API QoS per API/region/result.
- Freshness expectations: Daily batch.
- Common Filters: Date > ago(43–60d); ApiName filters; CustomerType filters.

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Day |
| ApiName       | string   | Manage API name |
| SubscriptionId| string   | Subscription |
| CustomerType  | string   | Customer type |
| Region        | string   | Region |
| Result        | string   | Outcome (Success/Timeout/CustomerError/…) |
| Count         | long     | Request count |

Column Explain:
- Compute QoS ratios with sumif by Result sets; total via sum(Count).

---

### Table name: signalrinsights.eastus2/SignalRBI.ManageResourceTags
- Priority: Normal
- What this table represents: Manage-plane operations tagged by RequestName/Tags; counts per resource/subscription/day.
- Freshness expectations: Daily batch.
- Common Filters: ResourceId !contains 'Microsoft.Authorization'; RequestName != 'Other'; Date > ago(30d).

Table columns:
| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Day |
| SubscriptionId| string   | Subscription |
| ResourceId    | string   | Resource id |
| RequestName   | string   | Operation name |
| Tags          | string   | Tag metadata |
| Count         | long     | Operation count |

Column Explain:
- Aggregate counts to summarize operation volumes.

---

### Table name: signalrinsights.eastus2/SignalRBI.KPI (WebPubSub and SocketIO variants also used)
- Priority: Normal
- What this table represents: KPI streams by service type; same schema as KPIv2019/AWPS/SocketIO.
- Freshness expectations: Historical.

Columns: same as KPIv2019.

---

### Table name: signalrinsights.eastus2/SignalRBI.AwpsRetention_SubscriptionSnapshot
- Priority: Normal
- What this table represents: AWPS subscription retention snapshots.
- Freshness expectations: Snapshot.

Table columns: same structure as SubscriptionRetentionSnapshot.

---

### Table name: signalrinsights.eastus2/SignalRBI.AwpsRetention_CustomerSnapshot
- Priority: Normal
- What this table represents: AWPS customer retention snapshots.
- Freshness expectations: Snapshot.

Table columns: same structure as CustomerRetentionSnapshot.

---

### Table name: signalrinsights.eastus2/SignalRBI.AwpsRetention_ResourceSnapshot
- Priority: Normal
- What this table represents: AWPS resource retention snapshots.
- Freshness expectations: Snapshot.

Table columns: same structure as ResourceRetentionSnapshot.

---

### Table name: signalrinsights.eastus2/SignalRBI.DeleteSurvey
- Priority: Normal
- What this table represents: Delete survey events (TIMESTAMP, reason, feedback).
- Accessibility: Not accessible via current product connection—cross-cluster access denied (azportalpartnerrow.westus/azureportal). Schema unknown.
- When to use / When to avoid:
  - Use for customer feedback tiles if permitted; otherwise omit.

---

### Table name: signalrinsights.eastus2/SignalRBI.DeleteSurveyWebPubSub
- Priority: Normal
- What this table represents: WebPubSub delete survey events.
- Accessibility: Likely same cross-cluster constraint; verify access. Schema unknown.

---

### Table name: signalrinsights.eastus2/SignalRBI.RuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: Grouped runtime request metrics (non-transport), used for daily requests analysis.
- Freshness expectations: Daily.
- Common Filters: Date > ago(60d); ResourceCount > 10; RequestCount > 200; Category != 'Transport'.

(Columns not fetched; infer usage: Date, ResourceId, Category, Metrics, ResourceCount, RequestCount.)

---

### Table name: signalrinsights.eastus2/SignalRBI.RuntimeRequestsGroups_EU_Daily
- Priority: Low
- What this table represents: EU variant of grouped runtime requests.

---

### Table name: signalrinsights.eastus2/SignalRBI.RuntimeTransport_Daily
- Priority: Low
- What this table represents: Runtime transport metrics (Framework-Transport), used in union for transport category.
- Freshness expectations: Daily.

---

### Table name: signalrinsights.eastus2/SignalRBI.RuntimeTransport_EU_Daily
- Priority: Low
- What this table represents: EU variant of runtime transport.

---

### Table name: signalrinsights.eastus2/SignalRBI.OKR_AWPS_SocketIO (duplicate entry consolidated above)
- Priority: High
- See OKR_AWPS_SocketIO section above.

---

### Table name: signalrinsights.eastus2/SignalRBI.WebPubSub-related tables (ResourceFlow/SubscriptionFlow/CustomerFlow functions)
- Priority: Normal
- What these represent: Functions producing weekly/monthly “New/Leaving” cohorts for resources/subscriptions/customers based on BillingUsage_Daily + MaxConnectionCount_Daily + CustomerModel.
- Freshness expectations: Computed on demand; input tables are daily; use startofweek/month alignment.
- When to use / When to avoid:
  - Use the functions when you need cohort breakdown; pass resourceType argument: 0-All, 1-SignalR, 2-WebPubSub.
  - Avoid recomputing flows manually unless custom logic needed.

Function outputs (from definitions):
- ResourceFlow_Weekly/Monthly: summarize ResourceCnt by period, Category, Region, SKU, HasConnection, LiveRatio.
- SubscriptionFlow_Weekly/Monthly: summarize SubscriptionCnt with Offer/Billing/CustomerType attributes.
- CustomerFlow_Weekly/Monthly: summarize CustomerCnt with segment.

---

### Table name: ddtelinsights.WebTools_Raw
- Priority: Low
- What this table represents: Visual Studio/WebTools telemetry events (publish, dependencies, provisioning). Used for VS integration tiles.
- Accessibility: Cross-cluster (ddtelinsights); schema not fetched via current product tool.
- When to use / When to avoid:
  - Use for VS integration dashboards; avoid for business OKR analysis (user marked low priority).
- Common Filters: AdvancedServerTimestampUtc; EventName; Properties/Measures; MacAddressHash.

---

### Table name: armprodgbl.eastus.Unionizer
- Priority: Low
- What this table represents: Cross-resource telemetry union function for ARM logs (Requests/HttpIncomingRequests).
- Accessibility: Cross-cluster; schema not fetched.
- When to use / When to avoid:
  - Use for ARM request tracking (e.g., EventGrid filters); avoid for business usage metrics.

---

## Notes on usage patterns and anti-patterns

- Freshness and timezone: Unknown. Current-day data can be incomplete. Prefer end-of-period markers (endofweek/endofmonth) and lagging windows.
- Activity gating: To avoid counting idle entities, inner-join MaxConnectionCount_Daily or ResourceMetrics and apply HasConnection flags.
- Replica handling: Deduplicate using PrimaryResource = substring(ResourceId, 0, indexof('/replicas/')) and count both ResourceId and PrimaryResource in replica aggregations.
- Revenue and consumption: Do not use MessageCount SKUs for revenue. Use <UnitPriceStandard>/<UnitPricePremium> placeholders. Normalize consumption to daily by Quantity*24 where queries do so.
- Segment and internal filters: Always exclude internal team subscriptions; enrich with SubscriptionMappings to derive CustomerType, SegmentName, Offer*, BillingType.
- Goals overlay: For OKR plots, fullouter join snapshots with datatable goals on TimeStamp/Date to overlay target lines; backfill TimeStamp when empty.